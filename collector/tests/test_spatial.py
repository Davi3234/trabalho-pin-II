from datetime import datetime, timezone

from interpretation.models import Confidence, FireDetection
from interpretation.spatial import cluster_detections, grid_density, haversine_km


def make_detection(lat, lon, hour=12, minute=0, day=18, frp=1.0, confidence=Confidence.NOMINAL) -> FireDetection:
    return FireDetection(
        latitude=lat, longitude=lon,
        acquired_at=datetime(2026, 8, day, hour, minute, tzinfo=timezone.utc),
        sensor="VIIRS_NOAA20_NRT", satellite="NOAA-20",
        confidence=confidence, confidence_raw=confidence.value,
        frp_mw=frp, brightness_k=300.0, scan_km=0.4, track_km=0.4, daynight="D",
    )


def test_haversine_known_distance():
    # ~ Atenas a Tessalônica, aprox. 400 km (tolerância ampla, só sanity check de ordem de grandeza)
    d = haversine_km(37.9838, 23.7275, 40.6401, 22.9444)
    assert 300 < d < 500


def test_close_points_form_one_cluster_far_points_do_not():
    detections = [
        make_detection(38.50, 23.00),
        make_detection(38.501, 23.001),  # ~120m de distância
        make_detection(40.00, 20.00),    # bem distante
    ]
    clusters = cluster_detections(detections, distance_km=3.0, time_window_hours=12.0)
    sizes = sorted(c.detection_count for c in clusters)
    assert sizes == [1, 2]


def test_transitive_chain_forms_single_cluster():
    # A-B perto, B-C perto, A-C distante -> ainda deve virar 1 cluster (single-linkage)
    detections = [
        make_detection(38.500, 23.000),
        make_detection(38.520, 23.000),  # ~2.2km de A
        make_detection(38.540, 23.000),  # ~2.2km de B, ~4.4km de A
    ]
    clusters = cluster_detections(detections, distance_km=3.0, time_window_hours=12.0)
    assert len(clusters) == 1
    assert clusters[0].detection_count == 3


def test_time_window_prevents_clustering_of_spatially_close_but_old_detections():
    detections = [
        make_detection(38.50, 23.00, hour=0),
        make_detection(38.501, 23.001, hour=23),  # mesmo local, 23h depois
    ]
    clusters = cluster_detections(detections, distance_km=3.0, time_window_hours=12.0)
    assert len(clusters) == 2


def test_empty_input_returns_empty_list():
    assert cluster_detections([]) == []


def test_cluster_derived_properties():
    detections = [
        make_detection(38.50, 23.00, frp=1.0, confidence=Confidence.HIGH),
        make_detection(38.501, 23.001, frp=2.0, confidence=Confidence.LOW),
    ]
    clusters = cluster_detections(detections, distance_km=3.0, time_window_hours=12.0)
    cluster = clusters[0]
    assert cluster.detection_count == 2
    assert cluster.total_frp_mw == 3.0
    assert cluster.max_frp_mw == 2.0
    assert cluster.high_confidence_ratio == 0.5


def test_grid_density_groups_by_cell_and_sorts_desc():
    detections = [
        make_detection(38.51, 23.01),
        make_detection(38.52, 23.02),
        make_detection(40.00, 20.00),
    ]
    density = grid_density(detections, cell_size_deg=0.1)
    assert density[0]["detection_count"] == 2
    assert density[1]["detection_count"] == 1
    assert sum(c["detection_count"] for c in density) == 3
