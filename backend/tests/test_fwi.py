from datetime import date
from io import BytesIO

import numpy as np
import pytest
import responses
from PIL import Image
from sqlalchemy import func, select, text

from ignis.collectors.fwi.gwis import GWIS_WMS_URL, GwisWmsProvider
from ignis.collectors.fwi.provider import FwiGrid, classify
from ignis.collectors.fwi.service import FwiCollector, dates_to_collect
from ignis.db.models import CollectionRun, DangerClass, FwiReading, Region, RunStatus


def _tiff(values: np.ndarray) -> bytes:
    buffer = BytesIO()
    Image.fromarray(values.astype(np.float32)).save(buffer, format="TIFF")
    return buffer.getvalue()


# --- unidade -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("fwi", "expected"),
    [
        (0.0, DangerClass.LOW),
        (11.19, DangerClass.LOW),
        (11.2, DangerClass.MODERATE),  # limites fechados à esquerda
        (21.3, DangerClass.HIGH),
        (37.99, DangerClass.HIGH),
        (38.0, DangerClass.VERY_HIGH),
        (50.0, DangerClass.EXTREME),
        (70.0, DangerClass.VERY_EXTREME),
        (115.0, DangerClass.VERY_EXTREME),
    ],
)
def test_classify_follows_official_effis_scale(fwi, expected):
    assert classify(fwi) == expected


def test_grid_cells_are_pixel_centers_and_skip_nodata():
    values = np.array([[1.0, 0.0, 3.0], [4.0, 5.0, np.nan]])  # linha 0 = norte
    grid = FwiGrid(values, west=0, south=0, east=3, north=2)

    lons, lats, vals = grid.valid_cells()

    assert vals.tolist() == [1.0, 3.0, 4.0, 5.0]
    assert lons.tolist() == [0.5, 2.5, 0.5, 1.5]
    assert lats.tolist() == [1.5, 1.5, 0.5, 0.5]


def test_dates_cover_yesterday_through_forecast_horizon():
    assert dates_to_collect(date(2026, 10, 21), days_back=1, days_ahead=3) == [
        date(2026, 10, 20),
        date(2026, 10, 21),
        date(2026, 10, 22),
        date(2026, 10, 23),
        date(2026, 10, 24),
    ]


def test_without_forecast_dates_end_today():
    assert dates_to_collect(date(2026, 10, 21), days_back=2, days_ahead=0) == [
        date(2026, 10, 19),
        date(2026, 10, 20),
        date(2026, 10, 21),
    ]


@responses.activate
def test_gwis_requests_float_geotiff_and_reads_values():
    values = np.array([[0.0, 12.5], [30.25, 71.0]])
    responses.get(GWIS_WMS_URL, body=_tiff(values), content_type="image/tiff")

    grid = GwisWmsProvider(resolution=0.5).fetch(-9.5, 38.0, -8.5, 39.0, date(2026, 10, 20))

    params = responses.calls[0].request.params
    assert params["request"] == "GetMap"
    assert params["layers"] == "ecmwf.fwi"
    assert params["format"] == "image/tiff"
    assert params["styles"] == ""  # obrigatório no MapServer >= 8
    assert params["time"] == "2026-10-20"
    assert params["bbox"] == "-9.5,38,-8.5,39"
    assert (params["width"], params["height"]) == ("2", "2")
    np.testing.assert_allclose(grid.values, values)
    assert (grid.west, grid.south, grid.east, grid.north) == (-9.5, 38.0, -8.5, 39.0)


@responses.activate
def test_gwis_service_exception_is_an_error():
    # o MapServer responde exceções com HTTP 200 e XML
    responses.get(
        GWIS_WMS_URL,
        body="<ServiceExceptionReport><ServiceException>Time value invalid</ServiceException>",
        content_type="application/vnd.ogc.se_xml",
    )
    with pytest.raises(RuntimeError, match="GWIS"):
        GwisWmsProvider().fetch(-9.5, 38.0, -8.5, 39.0, date(2026, 10, 20))


# --- integração com PostGIS ---------------------------------------------------


class FakeProvider:
    """Grade de 0,1° com valor constante por data; regiões em `fail` levantam erro."""

    name = "fake"

    def __init__(self, value_by_date: dict | None = None, default: float = 25.0, fail: set = frozenset()):
        self.value_by_date = value_by_date or {}
        self.default = default
        self.fail = fail
        self.calls: list[tuple] = []

    def fetch(self, west, south, east, north, day):
        self.calls.append(((west, south, east, north), day))
        if (west, south, east, north) in self.fail:
            raise RuntimeError("GWIS fora do ar")
        width, height = round((east - west) / 0.1), round((north - south) / 0.1)
        value = self.value_by_date.get(day, self.default)
        return FwiGrid(np.full((height, width), value), west, south, east, north)


@pytest.fixture
def clean_fwi(db_engine):
    with db_engine.begin() as conn:
        conn.execute(text("TRUNCATE fwi_readings, collection_runs RESTART IDENTITY CASCADE"))
    return db_engine


def _readings(scope, slug):
    with scope() as session:
        return list(
            session.scalars(
                select(FwiReading).join(Region).where(Region.slug == slug).order_by(FwiReading.date)
            )
        )


@pytest.mark.db
def test_cycle_stores_mean_max_and_class_per_region_and_date(clean_fwi, db_session_scope):
    today = date(2026, 10, 21)
    provider = FakeProvider({date(2026, 10, 22): 72.0})
    collector = FwiCollector(db_session_scope, provider, days_back=1, days_ahead=1, today=lambda: today)

    result = collector.run_cycle()

    assert result.status == RunStatus.SUCCESS
    portugal = _readings(db_session_scope, "portugal")
    assert [r.date for r in portugal] == [date(2026, 10, 20), today, date(2026, 10, 22)]
    assert portugal[0].fwi_value == pytest.approx(25.0)
    assert portugal[0].fwi_max == pytest.approx(25.0)
    assert portugal[0].danger_class == DangerClass.HIGH
    assert portugal[2].danger_class == DangerClass.VERY_EXTREME
    assert portugal[0].provider == "fake"
    with db_session_scope() as session:
        regions = session.scalar(select(func.count()).select_from(Region).where(Region.active))
        run = session.get(CollectionRun, result.run_id)
    assert result.readings == regions * 3
    assert run.job == "fwi" and run.status == RunStatus.SUCCESS and run.fetched_rows == result.readings


@pytest.mark.db
def test_only_pixels_inside_the_region_polygon_are_aggregated(clean_fwi, db_session_scope):
    today = date(2026, 10, 21)
    FwiCollector(db_session_scope, FakeProvider(), days_back=0, days_ahead=0, today=lambda: today).run_cycle()

    with db_session_scope() as session:
        portugal = session.scalar(select(Region).where(Region.slug == "portugal"))
        bbox_pixels = round((portugal.east - portugal.west) / 0.1) * round(
            (portugal.north - portugal.south) / 0.1
        )
    reading = _readings(db_session_scope, "portugal")[0]
    # o polígono de Portugal ocupa cerca de metade do próprio bbox (mar e Espanha ficam de fora)
    assert 0.3 * bbox_pixels < reading.pixel_count < 0.7 * bbox_pixels


@pytest.mark.db
def test_forecast_is_overwritten_by_the_next_cycle(clean_fwi, db_session_scope):
    today = date(2026, 10, 21)
    for value in (30.0, 55.0):
        provider = FakeProvider(default=value)
        FwiCollector(db_session_scope, provider, days_back=0, days_ahead=0, today=lambda: today).run_cycle()

    readings = _readings(db_session_scope, "portugal")
    assert len(readings) == 1
    assert readings[0].fwi_value == pytest.approx(55.0)
    assert readings[0].danger_class == DangerClass.EXTREME


@pytest.mark.db
def test_region_without_valid_pixels_is_skipped_without_error(clean_fwi, db_session_scope):
    today = date(2026, 10, 21)
    collector = FwiCollector(
        db_session_scope, FakeProvider(default=0.0), days_back=0, days_ahead=0, today=lambda: today
    )

    result = collector.run_cycle()

    assert result.status == RunStatus.SUCCESS
    assert result.readings == 0
    assert all(item.get("skipped") for item in result.details)


@pytest.mark.db
def test_failure_in_one_region_marks_run_partial(clean_fwi, db_session_scope):
    today = date(2026, 10, 21)
    provider = FakeProvider(fail={(-125.0, 32.0, -114.0, 42.0)})  # área de coleta da Califórnia
    result = FwiCollector(
        db_session_scope, provider, days_back=0, days_ahead=0, today=lambda: today
    ).run_cycle()

    assert result.status == RunStatus.PARTIAL
    errors = [item for item in result.details if "error" in item]
    assert [item["region"] for item in errors] == ["california"]
    assert _readings(db_session_scope, "portugal")


@pytest.mark.db
def test_backfill_collects_only_past_days(clean_fwi, db_session_scope):
    today = date(2026, 10, 21)
    provider = FakeProvider()
    FwiCollector(db_session_scope, provider, days_back=1, days_ahead=3, today=lambda: today).run_cycle(
        backfill_days=2
    )

    assert {day for _, day in provider.calls} == {date(2026, 10, 20), today}
