from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from ignis.api.main import app
from ignis.db.session import get_session


class _FakeSession:
    def __init__(self, last_run=None, db_down=False):
        self._last_run = last_run
        self._db_down = db_down

    def execute(self, *_):
        if self._db_down:
            raise OperationalError("SELECT 1", {}, Exception("conexão recusada"))

    def scalar(self, *_):
        return self._last_run


def _client(session) -> TestClient:
    app.dependency_overrides[get_session] = lambda: session
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def test_health_ok_with_recent_collection():
    resp = _client(_FakeSession(datetime.now(timezone.utc) - timedelta(minutes=30))).get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_health_degraded_when_collection_is_stale_but_portal_stays_up():
    resp = _client(_FakeSession(datetime.now(timezone.utc) - timedelta(hours=5))).get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "degraded"


def test_health_degraded_when_never_collected():
    body = _client(_FakeSession(None)).get("/health").json()
    assert body["status"] == "degraded"
    assert body["last_collection_at"] is None


def test_health_503_when_database_is_down():
    resp = _client(_FakeSession(db_down=True)).get("/health")
    assert resp.status_code == 503
    assert resp.json()["database"] == "unreachable"
