"""Gera backend/seeds/regions.geojson a partir do Natural Earth 1:50m v5.1.2.

Uso (arquivos baixados de github.com/nvkelso/natural-earth-vector/tree/v5.1.2/geojson):
    python scripts/build_regions_seed.py <dir com admin0.geojson e admin1.geojson> seeds/regions.geojson
"""

import json
import sys

ne, out = sys.argv[1], sys.argv[2]


def parts(geom):
    return geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]


def bbox_of(poly):
    xs = [p[0] for p in poly[0]]
    ys = [p[1] for p in poly[0]]
    return min(xs), min(ys), max(xs), max(ys)


def keep(poly, box):
    w, s, e, n = bbox_of(poly)
    return not (e < box[0] or w > box[2] or n < box[1] or s > box[3])


def rnd(poly):
    return [[[round(x, 4), round(y, 4)] for x, y in ring] for ring in poly]


MED = (-10, 35, 28, 45)
COUNTRIES = {
    "PRT": ("portugal", "Portugal"),
    "ESP": ("espanha", "Espanha"),
    "FRA": ("franca", "França"),
    "ITA": ("italia", "Itália"),
    "GRC": ("grecia-pais", "Grécia"),
}
feats = []
for f in json.load(open(f"{ne}/admin0.geojson", encoding="utf-8"))["features"]:
    iso = f["properties"]["ADM0_A3"]
    if iso in COUNTRIES:
        polys = [rnd(p) for p in parts(f["geometry"]) if keep(p, MED)]
        slug, name = COUNTRIES[iso]
        feats.append(
            {
                "type": "Feature",
                "properties": {"slug": slug, "name": name, "kind": "country", "iso_a3": iso},
                "geometry": {"type": "MultiPolygon", "coordinates": polys},
            }
        )
for f in json.load(open(f"{ne}/admin1.geojson", encoding="utf-8"))["features"]:
    p = f["properties"]
    if p.get("adm0_a3") == "USA" and p.get("name") == "California":
        feats.append(
            {
                "type": "Feature",
                "properties": {
                    "slug": "california-estado",
                    "name": "Califórnia (estado)",
                    "kind": "country",
                    "iso_a3": "USA-CA",
                },
                "geometry": {"type": "MultiPolygon", "coordinates": [rnd(x) for x in parts(f["geometry"])]},
            }
        )
assert len(feats) == 6, [x["properties"]["slug"] for x in feats]
json.dump(
    {
        "type": "FeatureCollection",
        "source": "Natural Earth 1:50m v5.1.2 (domínio público) — "
        "partes fora do Mediterrâneo (Açores, Madeira, Canárias, ultramar francês) removidas",
        "features": feats,
    },
    open(out, "w", encoding="utf-8"),
    ensure_ascii=False,
    separators=(",", ":"),
)
print({x["properties"]["slug"]: len(x["geometry"]["coordinates"]) for x in feats})
