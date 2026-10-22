"""Seed idempotente das regiões iniciais (upsert por slug).

Uso: python -m ignis.db.seed
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ignis.db.models import Region, RegionKind
from ignis.db.session import session_scope

logger = logging.getLogger("ignis.seed")

SEED_FILE = Path(__file__).resolve().parents[2] / "seeds" / "regions.geojson"

# áreas de coleta (oeste, sul, leste, norte) — enviadas à FIRMS a cada ciclo
MONITORING_REGIONS = [
    ("mediterraneo", "Mediterrâneo europeu", (-10.0, 35.0, 28.0, 45.0)),
    ("grecia", "Grécia (recorte fino)", (19.0, 34.0, 29.0, 42.0)),
    ("california", "Califórnia (EUA)", (-125.0, 32.0, -114.0, 42.0)),
]


def bbox_to_multipolygon(west: float, south: float, east: float, north: float) -> dict:
    ring = [[west, south], [east, south], [east, north], [west, north], [west, south]]
    return {"type": "MultiPolygon", "coordinates": [[ring]]}


def multipolygon_bbox(geometry: dict) -> tuple[float, float, float, float]:
    xs, ys = [], []
    for polygon in geometry["coordinates"]:
        for x, y in polygon[0]:
            xs.append(x)
            ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)


def seed_rows() -> list[dict]:
    rows = [
        {
            "slug": slug,
            "name": name,
            "kind": RegionKind.MONITORING,
            "bbox": bbox,
            "collect": True,
            "geometry": bbox_to_multipolygon(*bbox),
        }
        for slug, name, bbox in MONITORING_REGIONS
    ]
    collection = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    for feature in collection["features"]:
        props = feature["properties"]
        rows.append(
            {
                "slug": props["slug"],
                "name": props["name"],
                "kind": RegionKind(props["kind"]),
                "bbox": multipolygon_bbox(feature["geometry"]),
                "collect": False,
                "geometry": feature["geometry"],
            }
        )
    return rows


def upsert_regions(session: Session) -> tuple[int, int]:
    created = updated = 0
    for row in seed_rows():
        west, south, east, north = row["bbox"]
        geom = func.ST_SetSRID(func.ST_GeomFromGeoJSON(json.dumps(row["geometry"])), 4326)
        region = session.scalar(select(Region).where(Region.slug == row["slug"]))
        if region is None:
            region = Region(slug=row["slug"])
            session.add(region)
            created += 1
        else:
            updated += 1
        region.name = row["name"]
        region.kind = row["kind"]
        region.west, region.south, region.east, region.north = west, south, east, north
        region.collect = row["collect"]
        region.geom = geom
    return created, updated


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    with session_scope() as session:
        created, updated = upsert_regions(session)
    logger.info("Regiões: %d criada(s), %d atualizada(s).", created, updated)


if __name__ == "__main__":
    main()
