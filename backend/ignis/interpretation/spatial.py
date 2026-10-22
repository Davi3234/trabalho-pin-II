"""Densidade por célula e clustering de focos.

Clustering: componentes conexos por distância haversine + janela temporal
(union-find), equivalente a single-linkage / DBSCAN com min_samples=1.
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


KM_PER_DEG_LAT = math.pi * EARTH_RADIUS_KM / 180  # ~111,2 km


def _bucket_index(detections: list[FireDetection], cell_deg: float) -> dict[tuple[int, int], list[int]]:
    buckets: dict[tuple[int, int], list[int]] = defaultdict(list)
    for i, d in enumerate(detections):
        buckets[(math.floor(d.latitude / cell_deg), math.floor(d.longitude / cell_deg))].append(i)
    return buckets


def _neighbour_candidates(
    detections: list[FireDetection], buckets: dict[tuple[int, int], list[int]], cell_deg: float, i: int
):
    """Índices j > i que PODEM estar a <= distance_km de i (filtro grosso por grade).

    Evita comparar todos os pares (O(n²)): a célula tem o lado da distância-limite em
    latitude, e em longitude olhamos k células para cada lado, com k crescendo com a
    latitude (1° de longitude encolhe por cos(lat)). A decisão final continua sendo a
    haversine, então o resultado é idêntico ao da comparação exaustiva.
    """
    d = detections[i]
    ci, cj = math.floor(d.latitude / cell_deg), math.floor(d.longitude / cell_deg)
    lat_extent = min(89.0, abs(d.latitude) + 2 * cell_deg)
    k = math.ceil(1 / math.cos(math.radians(lat_extent))) + 1
    for di in (-1, 0, 1):
        for dj in range(-k, k + 1):
            for j in buckets.get((ci + di, cj + dj), ()):
                if j > i:
                    yield j


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
    cell_deg = distance_km / KM_PER_DEG_LAT
    buckets = _bucket_index(detections, cell_deg)

    for i in range(n):
        for j in _neighbour_candidates(detections, buckets, cell_deg, i):
            dt = abs((detections[i].acquired_at - detections[j].acquired_at).total_seconds())
            if dt > time_window_seconds:
                continue
            if (
                haversine_km(
                    detections[i].latitude,
                    detections[i].longitude,
                    detections[j].latitude,
                    detections[j].longitude,
                )
                <= distance_km
            ):
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
