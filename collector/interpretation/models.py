"""Modelo interno de dados do IGNIS, desacoplado do formato da FIRMS."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class Confidence(str, Enum):
    LOW = "low"
    NOMINAL = "nominal"
    HIGH = "high"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class FireDetection:
    latitude: float
    longitude: float
    acquired_at: datetime
    sensor: str
    satellite: Optional[str]
    confidence: Confidence
    confidence_raw: str
    frp_mw: Optional[float]
    brightness_k: Optional[float]
    scan_km: Optional[float]
    track_km: Optional[float]
    daynight: Optional[str]

    @property
    def pixel_area_km2(self) -> Optional[float]:
        # scan/track são os eixos de uma elipse, não os lados de um retângulo —
        # aproximação de ordem de grandeza, não área geodésica exata.
        if self.scan_km is None or self.track_km is None:
            return None
        return round(self.scan_km * self.track_km, 4)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["acquired_at"] = self.acquired_at.isoformat()
        d["confidence"] = self.confidence.value
        d["pixel_area_km2"] = self.pixel_area_km2
        return d


@dataclass
class FireCluster:
    cluster_id: int
    detections: list[FireDetection] = field(default_factory=list)

    @property
    def detection_count(self) -> int:
        return len(self.detections)

    @property
    def centroid(self) -> tuple[float, float]:
        lat = sum(d.latitude for d in self.detections) / len(self.detections)
        lon = sum(d.longitude for d in self.detections) / len(self.detections)
        return round(lat, 5), round(lon, 5)

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        lats = [d.latitude for d in self.detections]
        lons = [d.longitude for d in self.detections]
        return min(lons), min(lats), max(lons), max(lats)

    @property
    def first_seen(self) -> datetime:
        return min(d.acquired_at for d in self.detections)

    @property
    def last_seen(self) -> datetime:
        return max(d.acquired_at for d in self.detections)

    @property
    def duration_hours(self) -> float:
        delta = self.last_seen - self.first_seen
        return round(delta.total_seconds() / 3600, 2)

    @property
    def total_frp_mw(self) -> float:
        return round(sum(d.frp_mw or 0.0 for d in self.detections), 2)

    @property
    def max_frp_mw(self) -> Optional[float]:
        values = [d.frp_mw for d in self.detections if d.frp_mw is not None]
        return round(max(values), 2) if values else None

    @property
    def high_confidence_ratio(self) -> float:
        if not self.detections:
            return 0.0
        high = sum(1 for d in self.detections if d.confidence == Confidence.HIGH)
        return round(high / len(self.detections), 3)

    def to_dict(self) -> dict:
        lat, lon = self.centroid
        west, south, east, north = self.bbox
        return {
            "cluster_id": self.cluster_id,
            "detection_count": self.detection_count,
            "centroid": {"latitude": lat, "longitude": lon},
            "bbox": {"west": west, "south": south, "east": east, "north": north},
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "duration_hours": self.duration_hours,
            "total_frp_mw": self.total_frp_mw,
            "max_frp_mw": self.max_frp_mw,
            "high_confidence_ratio": self.high_confidence_ratio,
        }


@dataclass
class InterpretationReport:
    generated_at: datetime
    region: str
    bbox: str
    sensor: str
    window_start: Optional[datetime]
    window_end: Optional[datetime]
    total_detections: int
    detections: list[FireDetection]
    clusters: list[FireCluster]
    density_grid: list[dict]
    daily_counts: dict[str, int]
    hourly_counts: dict[str, int]
    trend: dict
    severity_ranking: list[dict]
    caveats: list[str]

    def to_dict(self) -> dict:
        return {
            "generated_at": self.generated_at.isoformat(),
            "region": self.region,
            "bbox": self.bbox,
            "sensor": self.sensor,
            "window_start": self.window_start.isoformat() if self.window_start else None,
            "window_end": self.window_end.isoformat() if self.window_end else None,
            "total_detections": self.total_detections,
            "clusters": [c.to_dict() for c in self.clusters],
            "density_grid": self.density_grid,
            "temporal": {
                "daily_counts": self.daily_counts,
                "hourly_counts": self.hourly_counts,
                "trend": self.trend,
            },
            "severity_ranking": self.severity_ranking,
            "caveats": self.caveats,
        }


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
