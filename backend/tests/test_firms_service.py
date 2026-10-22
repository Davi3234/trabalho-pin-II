from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import func, select

from ignis.collectors.firms.rate_limiter import SlidingWindowRateLimiter
from ignis.collectors.firms.service import (
    FirmsCollector,
    ResponseCache,
    _windows,
    detection_to_row,
    estimate_cost,
    plan_targets,
)
from ignis.db.models import CollectionRun, FireDetection, Region, RunStatus
from ignis.interpretation.mapper import map_dataframe

FIXTURE = Path(__file__).parent / "fixtures" / "firms_sample.csv"


def _region(id_, slug, west, south, east, north):
    return Region(id=id_, slug=slug, west=west, south=south, east=east, north=north)


# --- unidade -----------------------------------------------------------------


def test_region_contained_in_another_collected_area_is_skipped():
    regions = [
        _region(1, "mediterraneo", -10, 35, 28, 45),
        _region(2, "grecia", 19, 34, 29, 42),  # sai pelo sul/leste: NÃO está contida
        _region(3, "sicilia", 12, 36.5, 15.7, 38.3),  # contida no Mediterrâneo
        _region(4, "california", -125, 32, -114, 42),
    ]
    slugs = [t.region_slug for t in plan_targets(regions)]
    assert slugs == ["mediterraneo", "grecia", "california"]


def test_identical_bboxes_are_requested_once():
    regions = [_region(1, "a", 0, 0, 10, 10), _region(2, "b", 0, 0, 10, 10)]
    assert [t.region_slug for t in plan_targets(regions)] == ["a"]


def test_backfill_windows_cover_period_in_blocks_of_at_most_five_days():
    windows = list(_windows(2, days_back=12))
    assert [days for days, _ in windows] == [5, 5, 2]
    today = datetime.now(timezone.utc).date()
    assert windows[0][1] == today - timedelta(days=11)
    assert windows[-1][1] + timedelta(days=windows[-1][0] - 1) == today


def test_regular_cycle_uses_a_single_window_without_date():
    assert list(_windows(2, days_back=None)) == [(2, None)]


def test_cost_estimate_grows_with_days():
    assert estimate_cost(2) == 4  # valor medido com o status da MAP_KEY em 2026-10-21


def test_cache_expires_after_ttl():
    now = [0.0]
    cache = ResponseCache(ttl_seconds=60, clock=lambda: now[0])
    df = pd.DataFrame({"a": [1]})
    cache.put(("k",), df)
    assert cache.get(("k",)) is df
    now[0] = 61
    assert cache.get(("k",)) is None


def test_detection_row_rebuilds_natural_key_from_acquisition_time():
    detection = map_dataframe(pd.read_csv(FIXTURE), "VIIRS_NOAA20_NRT").detections[0]
    row = detection_to_row(detection, run_id=7)
    assert row["acq_date"].isoformat() == "2026-08-18"
    assert row["acq_time"] == 130
    assert row["latitude"] == Decimal("38.5")
    assert row["geom"] == "SRID=4326;POINT(23.0 38.5)"
    assert row["first_run_id"] == 7


# --- integração com PostGIS ---------------------------------------------------


class FakeFirms:
    def __init__(self, df: pd.DataFrame, fail_sources: set[str] = frozenset()):
        self.df = df
        self.fail_sources = fail_sources
        self.calls: list[tuple] = []
        self.transactions = 100

    def fetch(self, map_key, source, bbox, days, start=None):
        self.calls.append((source, bbox, days, start))
        self.transactions += 2 * days
        if source in self.fail_sources:
            raise RuntimeError("Resposta inesperada da FIRMS")
        return self.df

    def status(self, map_key):
        return {"transaction_limit": 5000, "current_transactions": self.transactions}


def _collector(scope, fake: FakeFirms, sources=("VIIRS_NOAA20_NRT",)) -> FirmsCollector:
    return FirmsCollector(
        scope,
        "chave",
        list(sources),
        limiter=SlidingWindowRateLimiter(),
        cache=ResponseCache(ttl_seconds=0),
        fetch=fake.fetch,
        key_status=fake.status,
    )


@pytest.mark.db
def test_cycle_persists_detections_and_records_run(clean_detections, db_session_scope):
    fake = FakeFirms(pd.read_csv(FIXTURE))

    result = _collector(db_session_scope, fake).run_cycle(day_range=2)

    assert result.status == RunStatus.SUCCESS
    # Grécia não está contida no bbox do Mediterrâneo (vai a 34°S/29°E) -> 3 áreas, 3 chamadas
    assert {bbox for _, bbox, _, _ in fake.calls} == {"-10,35,28,45", "19,34,29,42", "-125,32,-114,42"}
    assert result.transactions_used == 12  # medido pelo status: 3 chamadas x 2 dias x 2
    with db_session_scope() as session:
        stored = session.scalar(select(func.count()).select_from(FireDetection))
        run = session.get(CollectionRun, result.run_id)
    assert stored == result.new_detections > 0
    assert run.status == RunStatus.SUCCESS
    assert run.finished_at is not None
    assert len(run.details["items"]) == 3


@pytest.mark.db
def test_second_cycle_with_same_data_inserts_nothing(clean_detections, db_session_scope):
    fake = FakeFirms(pd.read_csv(FIXTURE))
    first = _collector(db_session_scope, fake).run_cycle()
    second = _collector(db_session_scope, fake).run_cycle()

    assert first.new_detections > 0
    assert second.new_detections == 0
    assert second.fetched_rows == first.fetched_rows
    with db_session_scope() as session:
        assert session.scalar(select(func.count()).select_from(FireDetection)) == first.new_detections


@pytest.mark.db
def test_failure_in_one_source_marks_run_partial_and_keeps_the_rest(clean_detections, db_session_scope):
    fake = FakeFirms(pd.read_csv(FIXTURE), fail_sources={"MODIS_NRT"})
    result = _collector(db_session_scope, fake, sources=("VIIRS_NOAA20_NRT", "MODIS_NRT")).run_cycle()

    assert result.status == RunStatus.PARTIAL
    assert result.new_detections > 0
    errors = [i for i in result.details if "error" in i]
    assert errors and all(i["source"] == "MODIS_NRT" for i in errors)


@pytest.mark.db
def test_inactive_region_is_not_collected(clean_detections, db_session_scope):
    with db_session_scope() as session:
        session.execute(Region.__table__.update().where(Region.slug == "california").values(active=False))
    try:
        fake = FakeFirms(pd.read_csv(FIXTURE))
        _collector(db_session_scope, fake).run_cycle()
        assert "-125,32,-114,42" not in {bbox for _, bbox, _, _ in fake.calls}
    finally:
        with db_session_scope() as session:
            session.execute(Region.__table__.update().where(Region.slug == "california").values(active=True))
