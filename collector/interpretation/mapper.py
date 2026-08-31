"""Mapper: DataFrame cru da FIRMS -> list[FireDetection] (modelo interno)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd

from .models import Confidence, FireDetection

REQUIRED_COLUMNS = {"latitude", "longitude", "acq_date", "acq_time"}

# Limiares não-oficiais: a FIRMS não documenta corte fixo para o % contínuo
# do MODIS (orienta "abordagem empírica"). Calibrável.
MODIS_LOW_MAX = 30
MODIS_NOMINAL_MAX = 80

VIIRS_CONFIDENCE_MAP = {
    "l": Confidence.LOW,
    "n": Confidence.NOMINAL,
    "h": Confidence.HIGH,
}


@dataclass
class MappingResult:
    detections: list[FireDetection]
    warnings: list[str]
    rows_received: int
    rows_rejected: int
    rows_duplicated: int


def _parse_confidence(raw: object, sensor: str) -> tuple[Confidence, str]:
    raw_str = str(raw).strip()
    if sensor.upper().startswith("VIIRS"):
        level = VIIRS_CONFIDENCE_MAP.get(raw_str.lower())
        if level is not None:
            return level, raw_str
        return Confidence.UNKNOWN, raw_str

    try:
        pct = float(raw_str)
    except ValueError:
        return Confidence.UNKNOWN, raw_str
    if pct < MODIS_LOW_MAX:
        return Confidence.LOW, raw_str
    if pct < MODIS_NOMINAL_MAX:
        return Confidence.NOMINAL, raw_str
    return Confidence.HIGH, raw_str


def _parse_acquired_at(acq_date: object, acq_time: object) -> datetime | None:
    # acq_time vem como HHMM sem separador e sempre em UTC (ex.: 120 = 01:20 UTC).
    try:
        time_str = str(int(acq_time)).zfill(4)
        hour, minute = int(time_str[:2]), int(time_str[2:])
        date_part = pd.to_datetime(str(acq_date)).date()
        return datetime(
            date_part.year, date_part.month, date_part.day, hour, minute,
            tzinfo=timezone.utc,
        )
    except (ValueError, TypeError):
        return None


def _to_optional_float(value: object) -> float | None:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        return float(value)
    except (ValueError, TypeError):
        return None


def map_dataframe(df: pd.DataFrame, sensor: str) -> MappingResult:
    warnings: list[str] = []
    rows_received = len(df)

    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(
            f"CSV da FIRMS sem colunas obrigatórias: {sorted(missing)}. "
            f"Colunas recebidas: {list(df.columns)}"
        )

    detections: list[FireDetection] = []
    seen_keys: set[tuple] = set()
    rows_rejected = 0
    rows_duplicated = 0

    for idx, row in df.iterrows():
        lat = _to_optional_float(row.get("latitude"))
        lon = _to_optional_float(row.get("longitude"))
        if lat is None or lon is None or not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            warnings.append(f"linha {idx}: coordenadas inválidas (lat={row.get('latitude')}, lon={row.get('longitude')})")
            rows_rejected += 1
            continue

        acquired_at = _parse_acquired_at(row.get("acq_date"), row.get("acq_time"))
        if acquired_at is None:
            warnings.append(f"linha {idx}: acq_date/acq_time não parseável (date={row.get('acq_date')}, time={row.get('acq_time')})")
            rows_rejected += 1
            continue

        confidence, confidence_raw = _parse_confidence(row.get("confidence"), sensor)

        frp = _to_optional_float(row.get("frp"))
        if frp is not None and frp < 0:
            warnings.append(f"linha {idx}: frp negativo ({frp}) descartado, tratado como ausente")
            frp = None

        dedup_key = (lat, lon, acquired_at, sensor)
        if dedup_key in seen_keys:
            rows_duplicated += 1
            continue
        seen_keys.add(dedup_key)

        detections.append(FireDetection(
            latitude=lat,
            longitude=lon,
            acquired_at=acquired_at,
            sensor=sensor,
            satellite=(str(row["satellite"]) if "satellite" in df.columns and pd.notna(row.get("satellite")) else None),
            confidence=confidence,
            confidence_raw=confidence_raw,
            frp_mw=frp,
            brightness_k=_to_optional_float(row.get("bright_ti4", row.get("brightness"))),
            scan_km=_to_optional_float(row.get("scan")),
            track_km=_to_optional_float(row.get("track")),
            daynight=(str(row["daynight"]) if "daynight" in df.columns and pd.notna(row.get("daynight")) else None),
        ))

    return MappingResult(
        detections=detections,
        warnings=warnings,
        rows_received=rows_received,
        rows_rejected=rows_rejected,
        rows_duplicated=rows_duplicated,
    )
