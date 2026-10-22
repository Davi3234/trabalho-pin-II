from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from ignis.api.main import app
from ignis.collectors.firms.service import persist_detections
from ignis.db.session import get_session
from ignis.interpretation.models import Confidence, FireDetection

pytestmark = pytest.mark.db

NOW = datetime.now(timezone.utc).replace(second=0, microsecond=0)


def _det(lat, lon, when, frp=10.0, confidence=Confidence.HIGH, sensor="VIIRS_NOAA20_NRT"):
    return FireDetection(
        latitude=lat,
        longitude=lon,
        acquired_at=when,
        sensor=sensor,
        satellite="N20",
        confidence=confidence,
        confidence_raw="h",
        frp_mw=frp,
        brightness_k=330.0,
        scan_km=0.4,
        track_km=0.4,
        daynight="D",
    )


@pytest.fixture
def client(clean_detections, db_session_scope):
    with db_session_scope() as session:
        persist_detections(
            session,
            [
                _det(37.98, 23.72, NOW - timedelta(hours=2)),  # Atenas
                _det(37.981, 23.721, NOW - timedelta(hours=3), frp=30.0),  # vizinho -> mesmo cluster
                _det(38.57, -7.91, NOW - timedelta(hours=5), confidence=Confidence.LOW),  # Évora
                _det(38.57, -7.91, datetime(2026, 8, 27, 13, 0, tzinfo=timezone.utc)),  # histórico
            ],
            run_id=None,
        )
    factory = sessionmaker(bind=clean_detections)

    def override():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_session] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_regions_are_listed(client):
    slugs = [r["slug"] for r in client.get("/api/regions").json()]
    assert {"mediterraneo", "california", "portugal", "grecia-pais"} <= set(slugs)


def test_interpretation_filters_by_region_geometry_and_window(client):
    body = client.get("/api/interpretation", params={"region": "grecia-pais", "hours": 24}).json()
    assert body["total_detections"] == 2
    assert len(body["clusters"]) == 1
    assert body["detections"][0]["conf"] == "h"
    assert body["filters"]["region"] == "grecia-pais"


def test_interpretation_min_confidence_excludes_low(client):
    params = {"region": "portugal", "hours": 24}
    assert client.get("/api/interpretation", params=params).json()["total_detections"] == 1
    params["min_confidence"] = "nominal"
    assert client.get("/api/interpretation", params=params).json()["total_detections"] == 0


def test_interpretation_until_shows_a_past_day(client):
    body = client.get(
        "/api/interpretation", params={"region": "portugal", "hours": 24, "until": "2026-08-27"}
    ).json()
    assert body["total_detections"] == 1
    assert body["window_start"].startswith("2026-08-27T13:00")


def test_unknown_region_is_404(client):
    assert client.get("/api/interpretation", params={"region": "atlantida"}).status_code == 404


def test_daily_series_fills_empty_days_with_zero(client):
    series = client.get("/api/stats/daily", params={"region": "grecia-pais", "days": 7}).json()
    assert len(series) == 7
    assert series[-1]["date"] == datetime.now(timezone.utc).date().isoformat()
    assert sum(d["count"] for d in series) == 2


def test_ranking_counts_per_country(client):
    ranking = {r["slug"]: r["count"] for r in client.get("/api/stats/ranking", params={"hours": 24}).json()}
    assert ranking["grecia-pais"] == 2
    assert ranking["portugal"] == 1
    assert ranking["california-estado"] == 0


def test_public_responses_are_cacheable(client):
    resp = client.get("/api/stats/ranking")
    assert "max-age" in resp.headers["cache-control"]


def test_detections_geojson_by_region(client):
    body = client.get("/api/detections", params={"region": "grecia-pais"}).json()
    assert body["type"] == "FeatureCollection"
    assert body["metadata"] == body["metadata"] | {"count": 2, "truncated": False}
    feature = body["features"][0]
    assert feature["geometry"] == {"type": "Point", "coordinates": [23.72, 37.98]}  # lon, lat; mais recente
    assert feature["properties"]["confidence"] == "high"


def test_detections_limit_keeps_newest_and_flags_truncation(client):
    body = client.get("/api/detections", params={"limit": 1}).json()
    assert body["metadata"]["truncated"] is True
    assert body["features"][0]["geometry"]["coordinates"] == [23.72, 37.98]


def test_detections_bbox_crops_the_map(client):
    body = client.get("/api/detections", params={"bbox": "-10,36,-6,40"}).json()
    assert [f["geometry"]["coordinates"] for f in body["features"]] == [[-7.91, 38.57]]


@pytest.mark.parametrize("bbox", ["1,2,3", "10,36,-6,40", "x,y,z,w"])
def test_detections_invalid_bbox_is_422(client, bbox):
    assert client.get("/api/detections", params={"bbox": bbox}).status_code == 422


def test_history_is_paginated_newest_first(client):
    params = {"region": "portugal", "start": "2026-08-01", "page_size": 1}
    page1 = client.get("/api/history", params=params).json()
    assert (page1["total"], page1["pages"]) == (2, 2)
    page2 = client.get("/api/history", params={**params, "page": 2}).json()
    assert page1["items"][0]["acquired_at_utc"] > page2["items"][0]["acquired_at_utc"]
    assert page2["items"][0]["acquired_at_utc"].startswith("2026-08-27T13:00")


def test_history_rejects_inverted_period(client):
    params = {"region": "portugal", "start": "2026-09-10", "end": "2026-09-01"}
    assert client.get("/api/history", params=params).status_code == 422


def test_history_csv_export(client):
    resp = client.get(
        "/api/history.csv", params={"region": "portugal", "start": "2026-08-27", "end": "2026-08-27"}
    )
    assert resp.status_code == 200
    assert "ignis_focos_portugal_2026-08-27_2026-08-27.csv" in resp.headers["content-disposition"]
    lines = resp.text.strip().split("\n")
    assert lines[0].startswith("acquired_at_utc,latitude,longitude,sensor")
    assert len(lines) == 2
    assert lines[1].startswith("2026-08-27T13:00:00+00:00,38.57,-7.91,VIIRS_NOAA20_NRT")


def test_burned_area_counts_each_viirs_cell_once(client):
    # os dois focos de Atenas estão a ~110 m: mesma célula de 375 m
    body = client.get("/api/stats/burned-area", params={"region": "grecia-pais", "days": 7}).json()
    assert body["estimated"] is True
    assert body["total_km2"] == round(0.375**2, 2)
    assert body["series"][-1]["cumulative_km2"] == body["total_km2"]
    assert len(body["series"]) == 7


def test_fwi_series_marks_forecast_and_attribution(client, db_engine):
    today = datetime.now(timezone.utc).date()
    with db_engine.begin() as conn:
        conn.execute(text("TRUNCATE fwi_readings"))
        region_id = conn.scalar(text("SELECT id FROM regions WHERE slug = 'grecia-pais'"))
        for offset, value in [(-1, 30.0), (0, 40.0), (2, 55.0)]:
            conn.execute(
                text(
                    "INSERT INTO fwi_readings (region_id, date, fwi_value, fwi_max, pixel_count, "
                    "danger_class, provider) VALUES (:r, :d, :v, :v + 10, 100, 'high', 'gwis_ecmwf')"
                ),
                {"r": region_id, "d": today + timedelta(days=offset), "v": value},
            )
    body = client.get("/api/fwi", params={"region": "grecia-pais", "days_back": 0}).json()
    assert "Copernicus" in body["attribution"]
    assert [(r["fwi_mean"], r["forecast"]) for r in body["readings"]] == [(40.0, False), (55.0, True)]
