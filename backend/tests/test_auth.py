from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from ignis.api.auth import create_token
from ignis.api.main import app
from ignis.api.schemas import BBox
from ignis.config import Settings, get_settings

SECRET = "x" * 40


def _settings(**overrides) -> Settings:
    values = {"admin_username": "admin", "admin_password": "senha-forte", "jwt_secret": SECRET}
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.fixture
def client():
    settings = _settings()
    app.dependency_overrides[get_settings] = lambda: settings
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_login_returns_bearer_token(client):
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "senha-forte"})
    assert resp.status_code == 200
    assert resp.json()["token_type"] == "bearer"


def test_wrong_password_is_401(client):
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "errada"})
    assert resp.status_code == 401


def test_admin_route_without_token_is_401(client):
    assert client.get("/api/admin/regions").status_code == 401


def test_tampered_token_is_401(client):
    token, _ = create_token(_settings(jwt_secret="y" * 40))  # assinado com outro segredo
    resp = client.get("/api/admin/regions", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_expired_token_is_401(client):
    token, _ = create_token(_settings(), now=datetime.now(timezone.utc) - timedelta(days=2))
    resp = client.get("/api/admin/regions", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "token expirado"


@pytest.mark.parametrize("overrides", [{"admin_password": None}, {"jwt_secret": "curto"}])
def test_admin_is_disabled_without_credentials_in_env(overrides):
    settings = _settings(**overrides)
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        client = TestClient(app)
        assert client.post("/api/auth/login", json={"username": "admin", "password": "x"}).status_code == 503
        assert client.get("/api/admin/regions").status_code == 503
    finally:
        app.dependency_overrides.clear()


def test_bbox_parse_accepts_firms_format():
    assert BBox.parse("-10,35,28,45") == BBox(west=-10, south=35, east=28, north=45)


@pytest.mark.parametrize("text", ["1,2,3", "10,35,-10,45", "-10,45,28,35", "-200,35,28,45", "a,b,c,d"])
def test_bbox_parse_rejects_invalid(text):
    with pytest.raises(ValueError):
        BBox.parse(text)
