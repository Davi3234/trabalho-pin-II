"""FWI diário pelo WMS do GWIS/EFFIS (Copernicus EMS), camada `ecmwf.fwi`.

`GetMap` com `format=image/tiff` devolve um GeoTIFF float32 com o FWI bruto por pixel: uma
requisição por região e data, sem chave. Dados sob CC BY 4.0 (atribuição obrigatória).
Detalhes e testes feitos contra o serviço real: docs/fonte-fwi.md.
"""

from __future__ import annotations

import math
from datetime import date
from io import BytesIO

import numpy as np
import requests
from PIL import Image

from ignis.collectors.firms.client import _sessao_resiliente
from ignis.collectors.fwi.provider import FwiGrid

GWIS_WMS_URL = "https://maps.effis.emergency.copernicus.eu/gwis"
LAYER = "ecmwf.fwi"
# grade pedida ao WMS; o modelo da ECMWF tem cerca de 8 km
RESOLUTION_DEG = 0.1
MAX_PIXELS_PER_SIDE = 2048
USER_AGENT = "IGNIS/0.2 (UDESC - Projeto Integrador II; monitoramento de incendios)"


class GwisWmsProvider:
    name = "gwis_ecmwf"

    def __init__(
        self,
        session: requests.Session | None = None,
        resolution: float = RESOLUTION_DEG,
        url: str = GWIS_WMS_URL,
    ):
        self.session = session or _sessao_resiliente()
        self.session.headers.setdefault("User-Agent", USER_AGENT)
        self.resolution = resolution
        self.url = url

    def params(self, west: float, south: float, east: float, north: float, day: date) -> dict:
        width = min(MAX_PIXELS_PER_SIDE, max(1, math.ceil((east - west) / self.resolution)))
        height = min(MAX_PIXELS_PER_SIDE, max(1, math.ceil((north - south) / self.resolution)))
        return {
            "service": "WMS",
            "version": "1.1.1",  # na 1.1.1 o bbox é lon,lat (na 1.3.0 com EPSG:4326 seria lat,lon)
            "request": "GetMap",
            "layers": LAYER,
            "styles": "",  # obrigatório no MapServer >= 8
            "srs": "EPSG:4326",
            # precisão total: a georreferência da grade vem deste bbox, não das tags do TIFF
            "bbox": ",".join(f"{v:.10g}" for v in (west, south, east, north)),
            "width": width,
            "height": height,
            "format": "image/tiff",
            "time": day.isoformat(),
        }

    def fetch(self, west: float, south: float, east: float, north: float, day: date) -> FwiGrid:
        try:
            resp = self.session.get(self.url, params=self.params(west, south, east, north, day), timeout=60)
        except requests.exceptions.RequestException as exc:
            raise RuntimeError(f"Falha de rede ao consultar o GWIS: {exc}") from exc
        resp.raise_for_status()

        # exceções do MapServer chegam com HTTP 200 e corpo XML
        if not resp.headers.get("Content-Type", "").startswith("image/tiff"):
            raise RuntimeError(f"Resposta inesperada do GWIS (não é GeoTIFF): {resp.text[:200]!r}")

        with Image.open(BytesIO(resp.content)) as image:
            if image.mode != "F":
                raise RuntimeError(f"GeoTIFF do GWIS em modo {image.mode!r}; esperado float32 ('F')")
            values = np.asarray(image, dtype=np.float32)
        return FwiGrid(values, west, south, east, north)
