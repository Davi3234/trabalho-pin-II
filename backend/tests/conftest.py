"""Fixtures compartilhadas.

Testes marcados com `db` usam PostgreSQL+PostGIS real e são pulados sem TEST_DATABASE_URL, ex.:
    TEST_DATABASE_URL=postgresql+psycopg://ignis:senha@127.0.0.1:5432/ignis_test pytest
O schema é recriado via Alembic (downgrade base + upgrade head) — use um banco descartável.
"""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

BACKEND_DIR = Path(__file__).resolve().parent.parent
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


@pytest.fixture(scope="session")
def db_engine():
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL não definida")

    from alembic import command
    from alembic.config import Config

    from ignis.config import get_settings
    from ignis.db.seed import upsert_regions

    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    get_settings.cache_clear()
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")

    engine = create_engine(TEST_DATABASE_URL)
    with Session(engine) as session:
        upsert_regions(session)
        session.commit()
    yield engine
    engine.dispose()


@pytest.fixture
def clean_detections(db_engine):
    """Zera focos e execuções antes do teste (alert_events é append-only e não é tocada)."""
    with db_engine.begin() as conn:
        conn.execute(text("TRUNCATE fire_detections, collection_runs RESTART IDENTITY CASCADE"))
    return db_engine


@pytest.fixture
def db_session_scope(db_engine):
    factory = sessionmaker(bind=db_engine, expire_on_commit=False)

    @contextmanager
    def scope() -> Iterator[Session]:
        session = factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    return scope
