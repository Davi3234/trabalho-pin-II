"""Integração com PostgreSQL+PostGIS real. Pulados sem TEST_DATABASE_URL.

Ex.: TEST_DATABASE_URL=postgresql+psycopg://ignis:senha@127.0.0.1:5432/ignis_test pytest -m db
O banco é recriado via Alembic (downgrade base + upgrade head) — use um banco descartável.
"""

import os
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from ignis.db.models import AlertEvent, FireDetection, Region
from ignis.interpretation.models import Confidence

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL não definida"),
]


@pytest.fixture(scope="module")
def engine():
    from alembic import command
    from alembic.config import Config

    from ignis.config import get_settings

    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    get_settings.cache_clear()
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "migrations"))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")

    eng = create_engine(TEST_DATABASE_URL)
    with Session(eng) as session:
        from ignis.db.seed import upsert_regions

        upsert_regions(session)
        session.commit()
    yield eng
    eng.dispose()


def _detection(lat: float, lon: float, frp: float = 5.0) -> dict:
    return {
        "source": "VIIRS_NOAA20_NRT",
        "latitude": lat,
        "longitude": lon,
        "acq_date": date(2026, 8, 20),
        "acq_time": 41,
        "acquired_at": datetime(2026, 8, 20, 0, 41, tzinfo=timezone.utc),
        "confidence": Confidence.NOMINAL,
        "confidence_raw": "n",
        "frp": frp,
        "geom": func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326),
    }


def test_duplicate_detection_is_ignored_on_conflict(engine):
    # RETURNING conta só as linhas realmente inseridas (rowcount não é confiável aqui com psycopg 3)
    stmt = (
        insert(FireDetection)
        .on_conflict_do_nothing(constraint="uq_fire_detections_natural")
        .returning(FireDetection.id)
    )
    with Session(engine) as session:
        first = session.execute(stmt.values(**_detection(38.71234, -9.13456))).all()
        again = session.execute(stmt.values(**_detection(38.71234, -9.13456, frp=99.0))).all()
        session.commit()
        stored_frp = session.scalar(select(FireDetection.frp).where(FireDetection.latitude == 38.71234))
    assert len(first) == 1
    assert again == []
    assert stored_frp == 5.0  # a primeira gravação é preservada


def test_detection_belongs_to_overlapping_regions_without_duplication(engine):
    # ponto em Atenas: dentro do Mediterrâneo, da Grécia (bbox) e do polígono do país
    stmt = insert(FireDetection).on_conflict_do_nothing(constraint="uq_fire_detections_natural")
    with Session(engine) as session:
        session.execute(stmt.values(**_detection(37.98, 23.72)))
        session.commit()
        slugs = set(
            session.scalars(
                select(Region.slug)
                .join(FireDetection, func.ST_Intersects(Region.geom, FireDetection.geom))
                .where(FireDetection.latitude == 37.98, FireDetection.longitude == 23.72)
            )
        )
    assert {"mediterraneo", "grecia", "grecia-pais"} <= slugs
    assert "italia" not in slugs


def test_alert_events_are_append_only(engine):
    with Session(engine) as session:
        session.add(
            AlertEvent(
                rule_id=1,
                region_id=1,
                rule_snapshot={"metric": "count"},
                measured_value=12,
                threshold=10,
                window_start=datetime(2026, 8, 19, tzinfo=timezone.utc),
                window_end=datetime(2026, 8, 20, tzinfo=timezone.utc),
                recipients={},
            )
        )
        session.commit()
        with pytest.raises(DBAPIError, match="append-only"):
            session.execute(text("UPDATE alert_events SET measured_value = 0"))
        session.rollback()
        with pytest.raises(DBAPIError, match="append-only"):
            session.execute(text("DELETE FROM alert_events"))
        session.rollback()


def test_seed_is_idempotent(engine):
    from ignis.db.seed import upsert_regions

    with Session(engine) as session:
        before = session.scalar(select(func.count()).select_from(Region))
        created, _ = upsert_regions(session)
        session.commit()
        after = session.scalar(select(func.count()).select_from(Region))
    assert created == 0
    assert before == after == 9
