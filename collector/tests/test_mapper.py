from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from interpretation.mapper import map_dataframe
from interpretation.models import Confidence

FIXTURE = Path(__file__).parent / "fixtures" / "firms_sample.csv"


def load_sample() -> pd.DataFrame:
    return pd.read_csv(FIXTURE)


def test_valid_rows_are_mapped_with_correct_types():
    result = map_dataframe(load_sample(), sensor="VIIRS_NOAA20_NRT")
    assert result.rows_received == 10
    # 1 linha com coordenadas inválidas + 1 duplicata exata da 1ª linha
    assert result.rows_rejected == 1
    assert result.rows_duplicated == 1
    assert len(result.detections) == 10 - 1 - 1

    first = result.detections[0]
    assert first.latitude == 38.5
    assert first.longitude == 23.0
    assert first.acquired_at == datetime(2026, 8, 18, 1, 30, tzinfo=timezone.utc)
    assert first.confidence == Confidence.NOMINAL
    assert first.frp_mw == 1.2
    assert first.sensor == "VIIRS_NOAA20_NRT"


def test_viirs_confidence_codes_map_correctly():
    result = map_dataframe(load_sample(), sensor="VIIRS_NOAA20_NRT")
    by_coord = {(d.latitude, d.longitude): d for d in result.detections}
    assert by_coord[(38.5, 23.0)].confidence == Confidence.NOMINAL
    assert by_coord[(38.51, 23.01)].confidence == Confidence.HIGH
    assert by_coord[(38.9, 23.5)].confidence == Confidence.LOW


def test_invalid_coordinates_are_rejected_not_silently_dropped():
    result = map_dataframe(load_sample(), sensor="VIIRS_NOAA20_NRT")
    assert any("coordenadas inválidas" in w for w in result.warnings)
    assert not any(d.latitude == 99.9 for d in result.detections)


def test_exact_duplicate_within_same_fetch_is_deduplicated():
    result = map_dataframe(load_sample(), sensor="VIIRS_NOAA20_NRT")
    coords = [(d.latitude, d.longitude, d.acquired_at) for d in result.detections]
    assert len(coords) == len(set(coords))


def test_modis_numeric_confidence_thresholds():
    df = pd.DataFrame([
        {"latitude": 10.0, "longitude": 10.0, "acq_date": "2026-08-18", "acq_time": 100, "confidence": 10, "frp": 1.0},
        {"latitude": 10.1, "longitude": 10.1, "acq_date": "2026-08-18", "acq_time": 100, "confidence": 50, "frp": 1.0},
        {"latitude": 10.2, "longitude": 10.2, "acq_date": "2026-08-18", "acq_time": 100, "confidence": 90, "frp": 1.0},
    ])
    result = map_dataframe(df, sensor="MODIS_NRT")
    levels = [d.confidence for d in result.detections]
    assert levels == [Confidence.LOW, Confidence.NOMINAL, Confidence.HIGH]


def test_negative_frp_is_discarded_as_none_with_warning():
    df = pd.DataFrame([
        {"latitude": 10.0, "longitude": 10.0, "acq_date": "2026-08-18", "acq_time": 100, "confidence": "n", "frp": -5.0},
    ])
    result = map_dataframe(df, sensor="VIIRS_NOAA20_NRT")
    assert result.detections[0].frp_mw is None
    assert any("frp negativo" in w for w in result.warnings)


def test_missing_required_columns_raises_clear_error():
    df = pd.DataFrame([{"latitude": 10.0, "longitude": 10.0}])
    with pytest.raises(ValueError, match="colunas obrigatórias"):
        map_dataframe(df, sensor="VIIRS_NOAA20_NRT")


def test_empty_dataframe_maps_to_no_detections():
    df = pd.DataFrame(columns=["latitude", "longitude", "acq_date", "acq_time", "confidence", "frp"])
    result = map_dataframe(df, sensor="VIIRS_NOAA20_NRT")
    assert result.detections == []
    assert result.rows_received == 0
