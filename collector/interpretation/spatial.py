"""Análise espacial: densidade por célula e clustering de focos.

Clustering = componentes conexos por distância haversine + janela temporal
(union-find), equivalente a single-linkage / DBSCAN com min_samples=1.
Metodologia e justificativa completas em docs/interpretacao_focos.md.
"""

from __future__ import annotations

import math
from collections import defaultdict

from .models import FireCluster, FireDetection

EARTH_RADIUS_KM = 6371.0

DEFAULT_DISTANCE_KM = 3.0
DEFAULT_TIME_WINDOW_HOURS = 12.0
DEFAULT_GRID_CELL_DEG = 0.1  # ~11 km no equador


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


class _UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def cluster_detections(
    detections: list[FireDetection],
    distance_km: float = DEFAULT_DISTANCE_KM,
    time_window_hours: float = DEFAULT_TIME_WINDOW_HOURS,
) -> list[FireCluster]:
    n = len(detections)
    if n == 0:
        return []

    uf = _UnionFind(n)
    time_window_seconds = time_window_hours * 3600

    for i in range(n):
        for j in range(i + 1, n):
            dt = abs((detections[i].acquired_at - detections[j].acquired_at).total_seconds())
            if dt > time_window_seconds:
                continue
            if haversine_km(
                detections[i].latitude, detections[i].longitude,
                detections[j].latitude, detections[j].longitude,
            ) <= distance_km:
                uf.union(i, j)

    groups: dict[int, list[FireDetection]] = defaultdict(list)
    for i in range(n):
        groups[uf.find(i)].append(detections[i])

    clusters = [
        FireCluster(cluster_id=cluster_id, detections=members)
        for cluster_id, members in enumerate(groups.values())
    ]
    clusters.sort(key=lambda c: c.detection_count, reverse=True)
    for new_id, cluster in enumerate(clusters):
        cluster.cluster_id = new_id
    return clusters


def grid_density(
    detections: list[FireDetection],
    cell_size_deg: float = DEFAULT_GRID_CELL_DEG,
) -> list[dict]:
    cells: dict[tuple[float, float], list[FireDetection]] = defaultdict(list)
    for d in detections:
        cell_lat = math.floor(d.latitude / cell_size_deg) * cell_size_deg
        cell_lon = math.floor(d.longitude / cell_size_deg) * cell_size_deg
        cells[(round(cell_lat, 4), round(cell_lon, 4))].append(d)

    result = [
        {
            "cell_south": lat,
            "cell_west": lon,
            "cell_size_deg": cell_size_deg,
            "detection_count": len(members),
            "total_frp_mw": round(sum(d.frp_mw or 0.0 for d in members), 2),
        }
        for (lat, lon), members in cells.items()
    ]
    result.sort(key=lambda c: c["detection_count"], reverse=True)
    return result
