"""Relatórios por IA e boletins (RF11, RF07) contra PostGIS real; o LLM é sempre um falso."""

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import sessionmaker

from ignis.api.main import app
from ignis.api.reports import get_llm_provider
from ignis.collectors.firms.service import persist_detections
from ignis.config import Settings
from ignis.db.models import Region
from ignis.db.session import get_session
from ignis.interpretation.models import Confidence, FireDetection
from ignis.reports.llm import LlmError, LlmResult
from ignis.reports.payload import build_report_input
from ignis.reports.service import publish_daily_bulletin

pytestmark = pytest.mark.db

NOW = datetime.now(timezone.utc).replace(second=0, microsecond=0)


def _det(lat, lon, when, frp=10.0, confidence=Confidence.HIGH):
    return FireDetection(
        latitude=lat,
        longitude=lon,
        acquired_at=when,
        sensor="VIIRS_NOAA20_NRT",
        satellite="N20",
        confidence=confidence,
        confidence_raw="h",
        frp_mw=frp,
        brightness_k=330.0,
        scan_km=0.4,
        track_km=0.4,
        daynight="D",
    )


class EchoLlm:
    """Escreve um texto só com números do JSON recebido, como um LLM bem-comportado."""

    name, model = "fake", "fake-1"

    def __init__(self):
        self.calls = 0

    def generate(self, system, user):
        self.calls += 1
        data = json.loads(user.split("\n", 1)[1])
        return LlmResult(
            text=f"Foram {data['focos']['total']} focos em {data['periodo']['dias']} dias.",
            model=self.model,
            usage={"total_tokens": 5},
        )


class DownLlm:
    name, model = "fake", "fake-1"

    def generate(self, system, user):
        raise LlmError("fora do ar")


@pytest.fixture
def env(clean_detections, db_session_scope):
    with clean_detections.begin() as conn:
        conn.execute(text("TRUNCATE ai_reports, bulletins, fwi_readings RESTART IDENTITY CASCADE"))
    with db_session_scope() as session:
        persist_detections(
            session,
            [
                _det(37.98, 23.72, NOW - timedelta(hours=2)),  # Grécia
                _det(37.981, 23.721, NOW - timedelta(hours=3), frp=30.0),  # Grécia, mesmo agrupamento
                _det(38.57, -7.91, NOW - timedelta(hours=5), confidence=Confidence.LOW),  # Portugal
            ],
            run_id=None,
        )
    factory = sessionmaker(bind=clean_detections, expire_on_commit=False)

    def override():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_session] = override
    llm = EchoLlm()
    app.dependency_overrides[get_llm_provider] = lambda: llm
    yield TestClient(app), llm, factory
    app.dependency_overrides.clear()


def test_payload_has_real_numbers_from_the_database(env):
    _, _, factory = env
    with factory() as session:
        region = session.scalar(select(Region).where(Region.slug == "grecia-pais"))
        payload = build_report_input(session, region, NOW.date() - timedelta(days=6), NOW.date())
    assert payload["focos"]["total"] == 2
    assert payload["focos"]["alta_confianca"] == 2
    assert payload["focos"]["frp_total_mw"] == 40.0
    assert payload["focos"]["frp_max_mw"] == 30.0
    assert len(payload["focos"]["serie_diaria"]) == 7
    assert payload["comparacao_periodo_anterior"] == {"total_anterior": 0, "variacao_pct": None}
    assert payload["agrupamentos_mais_criticos"][0]["focos"] == 2
    assert payload["ranking_paises"] == []  # região de país não tem ranking de países
    assert payload["fwi"] is None  # a fixture zera fwi_readings
    assert isinstance(payload["alertas_disparados"], list)  # alert_events é append-only: não dá para zerar


def test_post_generates_with_llm_and_second_call_is_served_from_cache(env):
    client, llm, _ = env
    body = {"region": "grecia-pais", "days": 7}
    first = client.post("/api/reports/ai", json=body).json()
    assert first["ai_generated"] is True and first["cached"] is False
    assert first["text"].startswith("Foram 2 focos em 7 dias.")
    assert "gerado por IA" in first["text"]
    assert first["validation"]["numbers_ok"] is True

    second = client.post("/api/reports/ai", json=body).json()
    assert second["cached"] is True and second["id"] == first["id"]
    assert llm.calls == 1  # o cache por input_hash não gasta cota


def test_post_without_llm_falls_back_to_template(env):
    client, _, _ = env
    app.dependency_overrides[get_llm_provider] = lambda: None
    body = client.post("/api/reports/ai", json={"region": "grecia-pais"}).json()
    assert body["generated_by"] == "template" and body["ai_generated"] is False
    assert body["validation"]["fallback_reason"] == "llm_not_configured"
    assert "2 focos de calor" in body["text"]  # o template traz o número real do banco
    assert "sem uso de inteligência artificial" in body["notice"]


def test_llm_outage_still_returns_a_report(env):
    client, _, _ = env
    app.dependency_overrides[get_llm_provider] = lambda: DownLlm()
    body = client.post("/api/reports/ai", json={"region": "grecia-pais"})
    assert body.status_code == 200
    assert body.json()["validation"]["fallback_reason"] == "llm_error"


def test_daily_quota_switches_to_template(env, monkeypatch):
    client, llm, _ = env
    monkeypatch.setattr(
        "ignis.api.reports.get_settings", lambda: Settings(_env_file=None, llm_max_on_demand_per_day=1)
    )
    first = client.post("/api/reports/ai", json={"region": "grecia-pais", "days": 7}).json()
    assert first["ai_generated"] is True and first["llm_quota_exhausted"] is False

    other = client.post("/api/reports/ai", json={"region": "grecia-pais", "days": 5}).json()
    assert other["generated_by"] == "template" and other["llm_quota_exhausted"] is True
    assert llm.calls == 1


def test_validation_of_request(env):
    client, _, _ = env
    assert client.post("/api/reports/ai", json={"region": "nao-existe"}).status_code == 404
    assert client.post("/api/reports/ai", json={"region": "grecia-pais", "days": 99}).status_code == 422


def test_get_report_by_id(env):
    client, _, _ = env
    created = client.post("/api/reports/ai", json={"region": "grecia-pais"}).json()
    got = client.get(f"/api/reports/{created['id']}").json()
    assert got["text"] == created["text"] and got["data"]["regiao_slug"] == "grecia-pais"
    assert client.get("/api/reports/99999").status_code == 404


def test_daily_bulletin_is_published_once_and_readable(env):
    client, llm, factory = env
    today = NOW.date()
    with factory() as session:
        region = session.scalar(select(Region).where(Region.slug == "grecia-pais"))
        assert publish_daily_bulletin(session, region, llm, today=today) is not None
        session.commit()
    with factory() as session:
        region = session.scalar(select(Region).where(Region.slug == "grecia-pais"))
        assert publish_daily_bulletin(session, region, llm, today=today) is None  # idempotente
    assert llm.calls == 1

    listing = client.get("/api/bulletins", params={"region": "grecia-pais"}).json()
    assert [b["date"] for b in listing] == [today.isoformat()]

    page = client.get(f"/api/bulletins/{today.isoformat()}/grecia-pais").json()
    assert page["kind"] == "daily_bulletin" and page["date"] == today.isoformat()
    # os 7 dias completos até ontem
    assert page["data"]["periodo"]["fim"] == (today - timedelta(days=1)).isoformat()
    assert client.get(f"/api/bulletins/{today.isoformat()}/portugal").status_code == 404
