from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
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
