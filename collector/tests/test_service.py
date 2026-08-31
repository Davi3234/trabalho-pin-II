import json
from pathlib import Path

import pandas as pd

from interpretation.service import FireInterpretationService, interpret

FIXTURE = Path(__file__).parent / "fixtures" / "firms_sample.csv"


def test_end_to_end_report_on_sample_csv():
    df = pd.read_csv(FIXTURE)
    report = interpret(df, region="mediterraneo", bbox="-10,35,28,45", sensor="VIIRS_NOAA20_NRT")

    assert report.total_detections == 8  # 10 linhas - 1 inválida - 1 duplicata
    # 3 clusters: par em 38.50/23.00 (2 focos), grupo em 41.0x (5 focos) e o
    # ponto isolado em 38.90/23.50 (~47km do par acima, longe do limiar de 3km)
    assert len(report.clusters) == 3
    assert sorted(c.detection_count for c in report.clusters) == [1, 2, 5]
    assert report.daily_counts == {"2026-08-18": 3, "2026-08-19": 5}
    assert report.trend["status"] == "crescente"
    assert len(report.severity_ranking) == len(report.clusters)
    assert len(report.caveats) >= 5  # caveats estruturais sempre presentes


def test_report_is_json_serializable():
    df = pd.read_csv(FIXTURE)
    report = interpret(df, region="mediterraneo", bbox="-10,35,28,45", sensor="VIIRS_NOAA20_NRT")
    payload = json.dumps(report.to_dict(), ensure_ascii=False)
    assert '"total_detections": 8' in payload


def test_empty_dataframe_produces_empty_report_with_caveat():
    df = pd.DataFrame(columns=["latitude", "longitude", "acq_date", "acq_time", "confidence", "frp"])
    report = interpret(df, region="mediterraneo", bbox="-10,35,28,45", sensor="VIIRS_NOAA20_NRT")
    assert report.total_detections == 0
    assert report.clusters == []
    assert any("Nenhum foco" in c for c in report.caveats)


def test_none_dataframe_is_treated_as_empty():
    report = interpret(None, region="mediterraneo", bbox="-10,35,28,45", sensor="VIIRS_NOAA20_NRT")
    assert report.total_detections == 0


def test_service_wrapper_delegates_to_interpret():
    df = pd.read_csv(FIXTURE)
    service = FireInterpretationService(distance_km=3.0, time_window_hours=12.0)
    report = service.interpret(df, region="mediterraneo", bbox="-10,35,28,45", sensor="VIIRS_NOAA20_NRT")
    assert report.total_detections == 8
