"""Interface das fontes de FWI (RF03) e classes de perigo oficiais do EFFIS.

A fonte fica atrás de `FwiProvider` para poder trocar o WMS do GWIS pelo CDS/EWDS (ou outra)
sem mexer no ciclo de coleta. Investigação e escolha da fonte: docs/fonte-fwi.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

import numpy as np

from ignis.db.models import DangerClass

# Limite inferior de cada classe, fechado à esquerda (11,2 já é moderado). Fonte: página técnica
# do EFFIS e legenda da camada ecmwf.fwi, conferidas em 2026-10-21.
DANGER_THRESHOLDS: tuple[tuple[float, DangerClass], ...] = (
    (70.0, DangerClass.VERY_EXTREME),
    (50.0, DangerClass.EXTREME),
    (38.0, DangerClass.VERY_HIGH),
    (21.3, DangerClass.HIGH),
    (11.2, DangerClass.MODERATE),
)


def classify(fwi: float) -> DangerClass:
    for lower, danger in DANGER_THRESHOLDS:
        if fwi >= lower:
            return danger
    return DangerClass.LOW


@dataclass(frozen=True)
class FwiGrid:
    """Raster de FWI em WGS84 cobrindo exatamente o bbox pedido; linha 0 = borda norte."""

    values: np.ndarray
    west: float
    south: float
    east: float
    north: float
    nodata: float = 0.0  # o GWIS devolve 0,0 no mar (ver docs/fonte-fwi.md)

    def valid_cells(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(longitudes, latitudes, valores) dos centros dos pixels com dado."""
        rows, cols = self.values.shape
        pixel_w = (self.east - self.west) / cols
        pixel_h = (self.north - self.south) / rows
        lons = self.west + (np.arange(cols) + 0.5) * pixel_w
        lats = self.north - (np.arange(rows) + 0.5) * pixel_h
        lon_grid, lat_grid = np.meshgrid(lons, lats)
        valid = np.isfinite(self.values) & (self.values != self.nodata) & (self.values >= 0)
        return lon_grid[valid], lat_grid[valid], self.values[valid].astype(float)


class FwiProvider(Protocol):
    name: str  # gravado em fwi_readings.provider

    def fetch(self, west: float, south: float, east: float, north: float, day: date) -> FwiGrid: ...
