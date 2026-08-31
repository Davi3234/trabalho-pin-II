from datetime import datetime, timezone

import pytest

from interpretation.models import Confidence, FireDetection
from interpretation.temporal import compute_trend, daily_counts, hourly_counts


def make_detection(day, hour) -> FireDetection:
    return FireDetection(
        latitude=38.5, longitude=23.0,
        acquired_at=datetime(2026, 8, day, hour, 0, tzinfo=timezone.utc),
        sensor="VIIRS_NOAA20_NRT", satellite="NOAA-20",
        confidence=Confidence.NOMINAL, confidence_raw="n",
        frp_mw=1.0, brightness_k=300.0, scan_km=0.4, track_km=0.4, daynight="D",
    )


def test_daily_counts_groups_by_date():
    detections = [make_detection(18, 1), make_detection(18, 5), make_detection(19, 10)]
    counts = daily_counts(detections)
    assert counts == {"2026-08-18": 2, "2026-08-19": 1}


def test_hourly_counts_groups_by_hour_across_days():
    detections = [make_detection(18, 1), make_detection(19, 1), make_detection(18, 5)]
    counts = hourly_counts(detections)
    assert counts["01h"] == 2
    assert counts["05h"] == 1


def test_trend_indeterminate_with_single_day():
    counts = {"2026-08-18": 5}
    trend = compute_trend(counts)
    assert trend["status"] == "indeterminado"


def test_trend_increasing():
    counts = {"2026-08-18": 3, "2026-08-19": 5}
    trend = compute_trend(counts)
    assert trend["status"] == "crescente"
    assert trend["variacao_percentual"] == pytest.approx(66.7, abs=0.1)


def test_trend_decreasing():
    counts = {"2026-08-18": 10, "2026-08-19": 4}
    trend = compute_trend(counts)
    assert trend["status"] == "decrescente"


def test_trend_stable():
    counts = {"2026-08-18": 10, "2026-08-19": 11}
    trend = compute_trend(counts)
    assert trend["status"] == "estável"
