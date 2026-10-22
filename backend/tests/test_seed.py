from ignis.db.models import RegionKind
from ignis.db.seed import bbox_to_multipolygon, multipolygon_bbox, seed_rows


def test_seed_has_monitoring_areas_and_country_subregions():
    rows = {r["slug"]: r for r in seed_rows()}

    assert {"mediterraneo", "grecia", "california"} <= rows.keys()
    assert {"portugal", "espanha", "franca", "italia", "grecia-pais", "california-estado"} <= rows.keys()
    assert rows["mediterraneo"]["bbox"] == (-10.0, 35.0, 28.0, 45.0)
    # só as áreas de coleta geram chamadas à FIRMS; países servem para ranking/alertas
    assert all(r["collect"] == (r["kind"] == RegionKind.MONITORING) for r in rows.values())


def test_seed_slugs_are_unique():
    slugs = [r["slug"] for r in seed_rows()]
    assert len(slugs) == len(set(slugs))


def test_country_polygons_exclude_atlantic_islands():
    rows = {r["slug"]: r for r in seed_rows()}
    # Açores/Madeira (Portugal) e Canárias (Espanha) ficam fora do recorte mediterrâneo
    assert rows["portugal"]["bbox"][0] > -10.0
    assert rows["espanha"]["bbox"][1] > 35.0


def test_bbox_roundtrip():
    geometry = bbox_to_multipolygon(-125, 32, -114, 42)
    assert multipolygon_bbox(geometry) == (-125, 32, -114, 42)
