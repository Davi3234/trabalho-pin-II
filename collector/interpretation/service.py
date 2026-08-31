"""Orquestra mapper -> spatial -> temporal -> severity em um InterpretationReport."""

from __future__ import annotations

import pandas as pd

from .mapper import map_dataframe
from .models import Confidence, FireDetection, InterpretationReport, utcnow
from .severity import DEFAULT_WEIGHTS, rank_clusters_by_severity
from .spatial import (
    DEFAULT_DISTANCE_KM,
    DEFAULT_GRID_CELL_DEG,
    DEFAULT_TIME_WINDOW_HOURS,
    cluster_detections,
    grid_density,
)
from .temporal import compute_trend, daily_counts, hourly_counts

STRUCTURAL_CAVEATS = [
    "Um foco de calor detectado não é, por si só, prova de incêndio florestal: "
    "queimadas agrícolas controladas, fontes industriais e outras anomalias "
    "térmicas também acionam a detecção.",
    "O produto NRT usado aqui não inclui o campo 'type' que distingue foco "
    "vegetal de fonte estática/industrial em outros produtos da FIRMS — essa "
    "distinção não pode ser feita a partir destes dados.",
    "Cada linha é uma detecção pontual de UM sobrevoo do satélite, não uma "
    "medição contínua: o mesmo incêndio real gera novas linhas a cada "
    "passagem, e uma frente de fogo alongada pode aparecer como múltiplas "
    "detecções em linha (ver documentação FIRMS).",
    "Dados NRT têm defasagem de até ~3h entre a passagem do satélite e a "
    "disponibilização (fora da cobertura Ultra Real-Time, restrita a "
    "EUA/Canadá) — o horário reportado é o da aquisição pelo satélite, não "
    "o do início real do incêndio.",
    "Nuvens, fumaça densa ou dossel florestal fechado podem ocultar focos "
    "reais; incêndios que começam e terminam entre duas passagens do "
    "satélite não são detectados.",
]


def interpret(
    df: pd.DataFrame,
    region: str,
    bbox: str,
    sensor: str,
    distance_km: float = DEFAULT_DISTANCE_KM,
    time_window_hours: float = DEFAULT_TIME_WINDOW_HOURS,
    grid_cell_deg: float = DEFAULT_GRID_CELL_DEG,
    severity_weights: dict[str, float] | None = None,
) -> InterpretationReport:
    if df is None or df.empty:
        return InterpretationReport(
            generated_at=utcnow(), region=region, bbox=bbox, sensor=sensor,
            window_start=None, window_end=None, total_detections=0,
            detections=[], clusters=[], density_grid=[],
            daily_counts={}, hourly_counts={}, trend={"status": "indeterminado", "reason": "nenhuma detecção no período"},
            severity_ranking=[],
            caveats=["Nenhum foco de calor retornado pela FIRMS para esta região/período — "
                     "isso pode significar ausência real de fogo OU cobertura de nuvens "
                     "impedindo a detecção; a API não distingue os dois casos."] + STRUCTURAL_CAVEATS,
        )

    mapping = map_dataframe(df, sensor)
    detections = mapping.detections

    clusters = cluster_detections(detections, distance_km=distance_km, time_window_hours=time_window_hours)
    density = grid_density(detections, cell_size_deg=grid_cell_deg)
    day_counts = daily_counts(detections)
    hour_counts = hourly_counts(detections)
    trend = compute_trend(day_counts)
    severity = rank_clusters_by_severity(clusters, weights=severity_weights or DEFAULT_WEIGHTS)

    caveats = list(STRUCTURAL_CAVEATS)
    if mapping.rows_rejected:
        caveats.append(
            f"{mapping.rows_rejected} de {mapping.rows_received} linha(s) recebida(s) da FIRMS "
            f"foram descartadas por dados inválidos (coordenadas ou data/hora não parseáveis)."
        )
    if mapping.rows_duplicated:
        caveats.append(
            f"{mapping.rows_duplicated} linha(s) duplicada(s) (mesma coordenada, horário e "
            f"sensor) foram descartadas dentro desta coleta."
        )
    low_conf = sum(1 for d in detections if d.confidence in (Confidence.LOW, Confidence.UNKNOWN))
    if low_conf:
        pct = round(100 * low_conf / len(detections), 1) if detections else 0
        caveats.append(
            f"{low_conf} de {len(detections)} detecção(ões) ({pct}%) têm confiança baixa ou "
            f"não reconhecida — maior probabilidade de falso positivo (sun glint, ruído)."
        )

    acquired_times = [d.acquired_at for d in detections]

    return InterpretationReport(
        generated_at=utcnow(),
        region=region,
        bbox=bbox,
        sensor=sensor,
        window_start=min(acquired_times) if acquired_times else None,
        window_end=max(acquired_times) if acquired_times else None,
        total_detections=len(detections),
        detections=detections,
        clusters=clusters,
        density_grid=density,
        daily_counts=day_counts,
        hourly_counts=hour_counts,
        trend=trend,
        severity_ranking=severity,
        caveats=caveats,
    )


class FireInterpretationService:
    def __init__(
        self,
        distance_km: float = DEFAULT_DISTANCE_KM,
        time_window_hours: float = DEFAULT_TIME_WINDOW_HOURS,
        grid_cell_deg: float = DEFAULT_GRID_CELL_DEG,
        severity_weights: dict[str, float] | None = None,
    ):
        self.distance_km = distance_km
        self.time_window_hours = time_window_hours
        self.grid_cell_deg = grid_cell_deg
        self.severity_weights = severity_weights

    def interpret(self, df: pd.DataFrame, region: str, bbox: str, sensor: str) -> InterpretationReport:
        return interpret(
            df, region=region, bbox=bbox, sensor=sensor,
            distance_km=self.distance_km,
            time_window_hours=self.time_window_hours,
            grid_cell_deg=self.grid_cell_deg,
            severity_weights=self.severity_weights,
        )
