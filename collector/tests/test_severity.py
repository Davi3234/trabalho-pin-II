from datetime import datetime, timezone

from interpretation.models import Confidence, FireCluster, FireDetection
from interpretation.severity import rank_clusters_by_severity


def make_detection(lat, lon, hour, frp, confidence=Confidence.HIGH) -> FireDetection:
    return FireDetection(
        latitude=lat, longitude=lon,
        acquired_at=datetime(2026, 8, 18, hour, 0, tzinfo=timezone.utc),
        sensor="VIIRS_NOAA20_NRT", satellite="NOAA-20",
        confidence=confidence, confidence_raw=confidence.value,
        frp_mw=frp, brightness_k=300.0, scan_km=0.4, track_km=0.4, daynight="D",
    )


def test_empty_clusters_returns_empty_ranking():
    assert rank_clusters_by_severity([]) == []


def test_more_intense_persistent_extensive_cluster_ranks_first():
    small_weak = FireCluster(cluster_id=0, detections=[
        make_detection(10.0, 10.0, 10, frp=0.5),
    ])
    big_intense = FireCluster(cluster_id=1, detections=[
        make_detection(20.0, 20.0, 1, frp=50.0),
        make_detection(20.01, 20.01, 5, frp=60.0),
        make_detection(20.02, 20.02, 10, frp=70.0),
    ])
    ranking = rank_clusters_by_severity([small_weak, big_intense])
    assert ranking[0]["cluster_id"] == 1
    assert ranking[0]["rank"] == 1
    assert ranking[0]["score"] > ranking[1]["score"]


def test_low_confidence_cluster_is_discounted_not_zeroed():
    high_conf = FireCluster(cluster_id=0, detections=[
        make_detection(10.0, 10.0, 1, frp=10.0, confidence=Confidence.HIGH),
    ])
    low_conf = FireCluster(cluster_id=1, detections=[
        make_detection(20.0, 20.0, 1, frp=10.0, confidence=Confidence.LOW),
    ])
    ranking = rank_clusters_by_severity([high_conf, low_conf])
    by_id = {r["cluster_id"]: r for r in ranking}
    assert by_id[0]["score"] > by_id[1]["score"]
    assert by_id[1]["score"] > 0  # descontado, não zerado


def test_score_is_bounded_between_zero_and_one():
    cluster = FireCluster(cluster_id=0, detections=[make_detection(10.0, 10.0, 1, frp=100.0)])
    ranking = rank_clusters_by_severity([cluster])
    assert 0.0 <= ranking[0]["score"] <= 1.0
