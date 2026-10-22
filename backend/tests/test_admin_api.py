import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from ignis.api.main import app
from ignis.collectors.firms.service import plan_targets
from ignis.config import Settings, get_settings
from ignis.db.models import Region
from ignis.db.session import get_session

pytestmark = pytest.mark.db

NEW_REGION = {
    "slug": "teste-sicilia",
    "name": "Sicília",
    "west": 12.3,
    "south": 36.6,
    "east": 15.7,
    "north": 38.3,
}


@pytest.fixture
def admin(db_engine):
    settings = Settings(_env_file=None, admin_password="senha-forte", jwt_secret="x" * 40)
    factory = sessionmaker(bind=db_engine)

    def override():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_session] = override
    client = TestClient(app)
    token = client.post("/api/auth/login", json={"username": "admin", "password": "senha-forte"}).json()
    client.headers["Authorization"] = f"Bearer {token['access_token']}"
    yield client
    app.dependency_overrides.clear()
    # desfaz o que os testes mudaram: regiões com collect = true entrariam nos testes da coleta
    with db_engine.begin() as conn:
        conn.execute(text("DELETE FROM regions WHERE slug LIKE 'teste-%'"))
        conn.execute(text("UPDATE regions SET active = true, collect = false WHERE slug = 'portugal'"))
        conn.execute(text("UPDATE regions SET collect = true WHERE slug = 'grecia'"))


def test_created_region_is_public_and_enters_next_collection(admin, db_engine):
    resp = admin.post("/api/admin/regions", json=NEW_REGION)
    assert resp.status_code == 201
    assert resp.json()["kind"] == "monitoring"

    public = {r["slug"]: r for r in admin.get("/api/regions").json()}
    assert public["teste-sicilia"]["bbox"]["west"] == 12.3

    with Session(db_engine) as session:
        geom_type = session.scalar(
            text("SELECT GeometryType(geom) FROM regions WHERE slug = 'teste-sicilia'")
        )
        collected = session.scalars(select(Region).where(Region.collect, Region.active)).all()
    assert geom_type == "MULTIPOLYGON"
    # a Sicília fica dentro do bbox do Mediterrâneo: entra na lista, mas sem requisição própria (RNF05)
    assert "teste-sicilia" in {r.slug for r in collected}
    assert "teste-sicilia" not in {t.region_slug for t in plan_targets(list(collected))}


def test_duplicate_slug_is_409(admin):
    admin.post("/api/admin/regions", json=NEW_REGION)
    assert admin.post("/api/admin/regions", json=NEW_REGION).status_code == 409


@pytest.mark.parametrize(
    "change",
    [{"west": 20, "east": 10}, {"south": 50, "north": 40}, {"north": 95}, {"slug": "Com Espaço"}],
)
def test_invalid_region_is_422(admin, change):
    assert admin.post("/api/admin/regions", json={**NEW_REGION, **change}).status_code == 422


def test_patch_updates_bbox_and_geometry(admin, db_engine):
    admin.post("/api/admin/regions", json=NEW_REGION)
    bbox = {"west": 13.0, "south": 37.0, "east": 15.0, "north": 38.0}
    resp = admin.patch("/api/admin/regions/teste-sicilia", json={"bbox": bbox, "name": "Sicília (centro)"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Sicília (centro)"
    with db_engine.connect() as conn:
        xmin = conn.scalar(text("SELECT ST_XMin(geom) FROM regions WHERE slug = 'teste-sicilia'"))
    assert xmin == 13.0


def test_country_bbox_is_not_editable(admin):
    bbox = {"west": -10, "south": 36, "east": -6, "north": 42}
    assert admin.patch("/api/admin/regions/portugal", json={"bbox": bbox}).status_code == 422


def test_delete_deactivates_and_hides_from_portal(admin):
    assert admin.delete("/api/admin/regions/portugal").status_code == 204
    assert "portugal" not in {r["slug"] for r in admin.get("/api/regions").json()}
    listed = {r["slug"]: r for r in admin.get("/api/admin/regions").json()}
    assert listed["portugal"]["active"] is False


def test_seed_on_boot_does_not_undo_admin_changes(admin, db_engine):
    from ignis.db.seed import upsert_regions

    admin.patch("/api/admin/regions/grecia", json={"collect": False})
    with Session(db_engine) as session:
        upsert_regions(session)
        session.commit()
        assert session.scalar(select(Region.collect).where(Region.slug == "grecia")) is False


def test_unknown_region_is_404(admin):
    assert admin.patch("/api/admin/regions/atlantida", json={"name": "Atlântida"}).status_code == 404
