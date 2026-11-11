"""Motor de alertas, assinaturas (double opt-in, descadastro, exclusão) e admin de regras (RF06, RF10, RNF04).

Contra PostGIS real; SMTP e webhook são falsos.
"""

import re
from datetime import datetime, timedelta, timezone

import pytest
import requests
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from ignis.alerts.engine import evaluate_rules
from ignis.api.main import app
from ignis.api.subscriptions import get_email_sender
from ignis.collectors.firms.service import persist_detections
from ignis.config import Settings, get_settings
from ignis.db.models import (
    AlertEvent,
    AlertMetric,
    AlertRule,
    Region,
    Subscriber,
    SubscriberRegion,
    SubscriberStatus,
)
from ignis.db.session import get_session
from ignis.interpretation.models import Confidence, FireDetection
from ignis.notifications.mailer import EmailSendError

pytestmark = pytest.mark.db

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
SETTINGS = Settings(
    _env_file=None,
    admin_password="senha-forte",
    jwt_secret="x" * 40,
    public_base_url="https://ignis.exemplo.org",
)


class FakeSender:
    def __init__(self, fail_for: set[str] | None = None):
        self.sent = []
        self.fail_for = fail_for or set()

    def send(self, data):
        if data.to in self.fail_for:
            raise EmailSendError("falhou", permanent=False)
        self.sent.append(data)


class FakePost:
    def __init__(self, status=200, error: Exception | None = None):
        self.calls, self.status, self.error = [], status, error

    def __call__(self, url, json=None, timeout=None):
        self.calls.append((url, json))
        if self.error:
            raise self.error
        resp = requests.Response()
        resp.status_code = self.status
        return resp


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


@pytest.fixture
def env(clean_detections, db_session_scope):
    with clean_detections.begin() as conn:
        conn.execute(text("TRUNCATE subscribers CASCADE"))
        conn.execute(text("DELETE FROM alert_rules"))  # sem RESTART: o id da regra nunca se repete
    with db_session_scope() as session:
        persist_detections(
            session,
            # 4 focos na Grécia (FRP 10, 10, 30, 50), 1 em Portugal
            [
                _det(37.98, 23.72, NOW - timedelta(hours=2)),
                _det(37.99, 23.73, NOW - timedelta(hours=3)),
                _det(38.00, 23.74, NOW - timedelta(hours=4), frp=30.0),
                _det(38.01, 23.75, NOW - timedelta(hours=5), frp=50.0, confidence=Confidence.LOW),
                _det(38.57, -7.91, NOW - timedelta(hours=2)),
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

    sender = FakeSender()
    app.dependency_overrides[get_session] = override
    app.dependency_overrides[get_settings] = lambda: SETTINGS
    app.dependency_overrides[get_email_sender] = lambda: sender
    yield factory, sender
    app.dependency_overrides.clear()


def _region(session: Session, slug: str) -> Region:
    return session.scalar(select(Region).where(Region.slug == slug))


def _rule(session: Session, slug="grecia-pais", **over) -> AlertRule:
    values = dict(
        name="Mais de 3 focos em 24h",
        metric=AlertMetric.COUNT,
        threshold=3,
        window_hours=24,
        cooldown_hours=12,
    )
    rule = AlertRule(region_id=_region(session, slug).id, **{**values, **over})
    session.add(rule)
    session.flush()
    return rule


def _subscriber(
    session: Session, email: str, slug="grecia-pais", status=SubscriberStatus.CONFIRMED
) -> Subscriber:
    sub = Subscriber(
        email=email,
        status=status,
        consent_at=NOW,
        consent_terms_version="2026-11",
    )
    sub.regions = [_region(session, slug)]
    session.add(sub)
    session.flush()
    return sub


# ---------- motor de regras ----------


def test_rule_below_threshold_does_not_fire(env):
    factory, sender = env
    with factory() as session:
        _rule(session, threshold=4)  # há exatamente 4 focos: não "supera"
        assert evaluate_rules(session, now=NOW, sender=sender, settings=SETTINGS) == []
    assert sender.sent == []


def test_rule_fires_and_notifies_only_confirmed_subscribers_of_the_region(env):
    factory, sender = env
    with factory() as session:
        _rule(session)
        _subscriber(session, "ok@exemplo.com")
        _subscriber(session, "pendente@exemplo.com", status=SubscriberStatus.PENDING)
        _subscriber(session, "saiu@exemplo.com", status=SubscriberStatus.UNSUBSCRIBED)
        _subscriber(session, "outra@exemplo.com", slug="portugal")
        fired = evaluate_rules(session, now=NOW, sender=sender, settings=SETTINGS)
        session.commit()

    assert len(fired) == 1 and fired[0].value == 4
    assert [m.to for m in sender.sent] == ["ok@exemplo.com"]
    msg = sender.sent[0]
    assert "Grécia" in msg.subject and "Mais de 3 focos" in msg.subject
    assert msg.headers["List-Unsubscribe"].startswith(
        "<https://ignis.exemplo.org/api/subscriptions/unsubscribe?id="
    )
    assert msg.headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert "unsubscribe?id=" in msg.text and "defesa civil" in msg.text


def test_event_is_audited_without_any_email_address(env):
    factory, sender = env
    with factory() as session:
        rule = _rule(session)
        _subscriber(session, "ok@exemplo.com")
        evaluate_rules(session, now=NOW, sender=sender, settings=SETTINGS)
        session.commit()
        event = session.scalar(select(AlertEvent).where(AlertEvent.rule_id == rule.id))

    assert event.measured_value == 4 and event.threshold == 3
    assert (
        event.rule_snapshot["name"] == "Mais de 3 focos em 24h" and event.rule_snapshot["metric"] == "count"
    )
    assert event.window_end == NOW and event.window_start == NOW - timedelta(hours=24)
    assert event.recipients["email"]["sent"] == 1 and len(event.recipients["email"]["sent_ids"]) == 1
    assert "@" not in str(event.recipients)


def test_cooldown_blocks_repeats_until_it_expires(env):
    factory, sender = env
    with factory() as session:
        _rule(session)
        _subscriber(session, "ok@exemplo.com")
        assert len(evaluate_rules(session, now=NOW, sender=sender, settings=SETTINGS)) == 1
        session.commit()
        assert evaluate_rules(session, now=NOW + timedelta(hours=1), sender=sender, settings=SETTINGS) == []
        # passado o cooldown de 12h, os focos (de 2 a 5h antes) ainda estão na janela de 24h: dispara de novo
        assert (
            len(evaluate_rules(session, now=NOW + timedelta(hours=13), sender=sender, settings=SETTINGS)) == 1
        )
    assert len(sender.sent) == 2


def test_metrics_and_confidence_filter(env):
    factory, sender = env
    with factory() as session:
        frp_sum = _rule(session, threshold=99)  # 10 + 10 + 30 + 50 = 100 > 99
        frp_sum.metric = AlertMetric.FRP_SUM
        frp_max = _rule(session, threshold=50)  # máximo é 50: não supera
        frp_max.metric = AlertMetric.FRP_MAX
        high_only = _rule(session, threshold=2, min_confidence=Confidence.HIGH)  # 3 focos de alta confiança
        fired = {
            t.rule.id: t.value for t in evaluate_rules(session, now=NOW, sender=sender, settings=SETTINGS)
        }
    assert fired == {frp_sum.id: 100.0, high_only.id: 3.0}


def test_inactive_rule_is_skipped(env):
    factory, sender = env
    with factory() as session:
        _rule(session, active=False)
        assert evaluate_rules(session, now=NOW, sender=sender, settings=SETTINGS) == []


def test_with_email_disabled_the_event_is_still_recorded(env):
    factory, _ = env
    with factory() as session:
        _rule(session)
        fired = evaluate_rules(session, now=NOW, sender=None, settings=SETTINGS)
    assert fired[0].event.recipients["email"] == {"status": "email_disabled"}


def test_one_failed_email_does_not_block_the_others(env):
    factory, _ = env
    sender = FakeSender(fail_for={"quebrado@exemplo.com"})
    with factory() as session:
        _rule(session)
        _subscriber(session, "quebrado@exemplo.com")
        _subscriber(session, "bom@exemplo.com")
        fired = evaluate_rules(session, now=NOW, sender=sender, settings=SETTINGS)
    email = fired[0].event.recipients["email"]
    assert (email["attempted"], email["sent"], email["failed"]) == (2, 1, 1)
    assert [m.to for m in sender.sent] == ["bom@exemplo.com"]


def test_webhook_is_called_with_the_event_and_host_only_is_recorded(env):
    factory, sender = env
    post = FakePost()
    with factory() as session:
        _rule(session, webhook_url="https://hooks.exemplo.org/segredo-no-caminho")
        fired = evaluate_rules(session, now=NOW, sender=sender, settings=SETTINGS, http_post=post)
    url, body = post.calls[0]
    assert url == "https://hooks.exemplo.org/segredo-no-caminho"
    assert (
        body["event"] == "alert" and body["measured_value"] == 4 and body["region"]["slug"] == "grecia-pais"
    )
    recorded = fired[0].event.recipients["webhook"]
    assert recorded == {"host": "hooks.exemplo.org", "status": "ok", "http_status": 200}
    assert "segredo" not in str(fired[0].event.recipients)


@pytest.mark.parametrize("post", [FakePost(status=500), FakePost(error=requests.ConnectionError("x"))])
def test_failing_webhook_still_records_the_event(env, post):
    factory, sender = env
    with factory() as session:
        _rule(session, webhook_url="https://hooks.exemplo.org/x")
        fired = evaluate_rules(session, now=NOW, sender=sender, settings=SETTINGS, http_post=post)
    assert fired[0].event.recipients["webhook"]["status"] == "failed"


# ---------- assinaturas ----------


def _subscribe(client, email="pessoa@exemplo.com", **over):
    body = {"email": email, "regions": ["grecia-pais"], "consent": True, **over}
    return client.post("/api/subscriptions", json=body)


def _token_from(msg) -> str:
    return re.search(r"confirm\?token=(\S+)", msg.text).group(1)


def test_subscribe_requires_consent_valid_email_and_known_region(env):
    client = TestClient(app)
    assert _subscribe(client, consent=False).status_code == 422
    assert _subscribe(client, email="sem-arroba").status_code == 422
    assert _subscribe(client, regions=["nao-existe"]).status_code == 422
    assert _subscribe(client, regions=[]).status_code == 422


def test_double_opt_in_flow(env):
    factory, sender = env
    client = TestClient(app)
    assert _subscribe(client).status_code == 202

    with factory() as session:
        sub = session.scalar(select(Subscriber).where(Subscriber.email == "pessoa@exemplo.com"))
        assert sub.status == SubscriberStatus.PENDING
        assert sub.consent_terms_version == SETTINGS.terms_version and sub.consent_at
        assert sub.confirm_token_hash and len(sub.confirm_token_hash) == 64

    (msg,) = sender.sent
    assert "Confirme" in msg.subject
    token = _token_from(msg)
    assert token not in sub.confirm_token_hash  # no banco só o hash

    ok = client.get("/api/subscriptions/confirm", params={"token": token})
    assert ok.status_code == 200 and "Inscrição confirmada" in ok.text
    with factory() as session:
        sub = session.scalar(select(Subscriber).where(Subscriber.email == "pessoa@exemplo.com"))
        assert (
            sub.status == SubscriberStatus.CONFIRMED and sub.confirmed_at and sub.confirm_token_hash is None
        )

    assert (
        client.get("/api/subscriptions/confirm", params={"token": token}).status_code == 400
    )  # link de uso único


def test_pending_subscriber_receives_no_alerts(env):
    factory, sender = env
    _subscribe(TestClient(app))
    sender.sent.clear()
    with factory() as session:
        _rule(session)
        evaluate_rules(session, now=NOW, sender=sender, settings=SETTINGS)
    assert sender.sent == []


def test_expired_confirmation_link_is_rejected(env):
    factory, sender = env
    client = TestClient(app)
    _subscribe(client)
    with factory() as session:
        session.execute(text("UPDATE subscribers SET consent_at = now() - interval '3 days'"))
        session.commit()
    resp = client.get("/api/subscriptions/confirm", params={"token": _token_from(sender.sent[0])})
    assert resp.status_code == 400


def test_resubscribing_a_confirmed_address_does_not_reveal_it_or_resend(env):
    factory, sender = env
    client = TestClient(app)
    _subscribe(client)
    client.get("/api/subscriptions/confirm", params={"token": _token_from(sender.sent[0])})
    first = _subscribe(client)
    assert first.status_code == 202 and len(sender.sent) == 1  # nenhum e-mail novo
    assert first.json() == _subscribe(client, email="outra@exemplo.com").json()  # mesma resposta
    with factory() as session:
        sub = session.scalar(select(Subscriber).where(Subscriber.email == "pessoa@exemplo.com"))
        assert sub.status == SubscriberStatus.CONFIRMED


def test_confirmation_email_failure_returns_502_and_stores_nothing(env):
    factory, _ = env
    app.dependency_overrides[get_email_sender] = lambda: FakeSender(fail_for={"pessoa@exemplo.com"})
    assert _subscribe(TestClient(app)).status_code == 502
    with factory() as session:
        assert session.scalar(select(Subscriber).where(Subscriber.email == "pessoa@exemplo.com")) is None


def test_subscribe_without_smtp_is_503(env):
    app.dependency_overrides[get_email_sender] = lambda: None
    assert _subscribe(TestClient(app)).status_code == 503


def test_unsubscribe_link_from_an_alert_stops_future_alerts_and_offers_deletion(env):
    factory, sender = env
    client = TestClient(app)
    with factory() as session:
        _rule(session)
        _subscriber(session, "ok@exemplo.com")
        evaluate_rules(session, now=NOW, sender=sender, settings=SETTINGS)
        session.commit()
    link = re.search(
        r"https://ignis\.exemplo\.org(/api/subscriptions/unsubscribe\?\S+)", sender.sent[0].text
    ).group(1)

    page = client.get(link)
    assert page.status_code == 200 and "Inscrição cancelada" in page.text and "Apagar meus dados" in page.text
    with factory() as session:
        assert session.scalar(select(Subscriber.status).where(Subscriber.email == "ok@exemplo.com")) == (
            SubscriberStatus.UNSUBSCRIBED
        )
        evaluate_rules(session, now=NOW + timedelta(hours=13), sender=sender, settings=SETTINGS)
    assert len(sender.sent) == 1  # nada novo depois do descadastro


def test_one_click_unsubscribe_and_bad_token(env):
    factory, sender = env
    client = TestClient(app)
    with factory() as session:
        _rule(session)
        sub = _subscriber(session, "ok@exemplo.com")
        evaluate_rules(session, now=NOW, sender=sender, settings=SETTINGS)
        session.commit()
        sub_id = str(sub.id)
    token = re.search(r"token=([0-9a-f]{64})", sender.sent[0].headers["List-Unsubscribe"]).group(1)

    assert (
        client.post("/api/subscriptions/unsubscribe", params={"id": sub_id, "token": "0" * 64}).status_code
        == 404
    )
    assert (
        client.get("/api/subscriptions/unsubscribe", params={"id": sub_id, "token": "0" * 64}).status_code
        == 404
    )
    assert client.post("/api/subscriptions/unsubscribe", params={"id": sub_id, "token": token}).json() == {
        "status": "unsubscribed"
    }


def test_definitive_deletion_erases_the_subscriber_and_regions(env):
    factory, sender = env
    client = TestClient(app)
    with factory() as session:
        _rule(session)
        sub = _subscriber(session, "ok@exemplo.com")
        evaluate_rules(session, now=NOW, sender=sender, settings=SETTINGS)
        session.commit()
        sub_id = str(sub.id)
    token = re.search(r"token=([0-9a-f]{64})", sender.sent[0].headers["List-Unsubscribe"]).group(1)

    assert client.post("/api/subscriptions/delete", json={"id": sub_id, "token": "f" * 64}).status_code == 404
    assert client.post("/api/subscriptions/delete", json={"id": sub_id, "token": token}).json() == {
        "status": "deleted"
    }
    with factory() as session:
        assert session.scalar(select(Subscriber).where(Subscriber.email == "ok@exemplo.com")) is None
        assert session.scalars(select(SubscriberRegion)).all() == []


def test_subscriptions_are_disabled_without_a_signing_secret(env):
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, public_base_url="https://x.org")
    assert _subscribe(TestClient(app)).status_code == 503


def test_privacy_endpoint_reports_whether_subscriptions_are_available(env):
    client = TestClient(app)
    body = client.get("/api/privacy").json()
    assert body["terms_version"] == SETTINGS.terms_version and "e-mail" in body["text"]
    assert body["subscriptions_enabled"] is False  # EMAIL_ENABLED desligado por padrão

    smtp = dict(smtp_host="smtp.exemplo.org", smtp_from="alertas@ignis.exemplo.org")
    on = Settings(_env_file=None, email_enabled=True, jwt_secret="x" * 40, **smtp)
    app.dependency_overrides[get_settings] = lambda: on
    assert client.get("/api/privacy").json()["subscriptions_enabled"] is True
    no_secret = Settings(_env_file=None, email_enabled=True, **smtp)
    app.dependency_overrides[get_settings] = lambda: no_secret
    assert client.get("/api/privacy").json()["subscriptions_enabled"] is False


# ---------- admin ----------


@pytest.fixture
def admin(env):
    client = TestClient(app)
    token = client.post("/api/auth/login", json={"username": "admin", "password": "senha-forte"}).json()
    client.headers["Authorization"] = f"Bearer {token['access_token']}"
    return client


def test_alert_admin_requires_login(env):
    client = TestClient(app)
    assert client.get("/api/admin/alert-rules").status_code in (401, 403)
    assert client.get("/api/admin/alert-events").status_code in (401, 403)


def test_rule_crud_and_validation(admin):
    created = admin.post(
        "/api/admin/alert-rules",
        json={"region": "grecia-pais", "name": "Regra A", "metric": "frp_sum", "threshold": 500},
    )
    assert created.status_code == 201
    rule = created.json()
    assert rule["window_hours"] == 24 and rule["cooldown_hours"] == 12 and rule["active"] is True

    bad = [
        {"region": "grecia-pais", "name": "x", "metric": "count", "threshold": 0},  # nome curto e limiar 0
        {"region": "grecia-pais", "name": "Regra B", "metric": "nada", "threshold": 1},
        {
            "region": "grecia-pais",
            "name": "Regra B",
            "metric": "count",
            "threshold": 1,
            "webhook_url": "ftp://x",
        },
        {"region": "grecia-pais", "name": "Regra B", "metric": "count", "threshold": 1, "window_hours": 0},
    ]
    assert [admin.post("/api/admin/alert-rules", json=b).status_code for b in bad] == [422] * 4
    assert (
        admin.post(
            "/api/admin/alert-rules",
            json={"region": "nao-existe", "name": "Regra B", "metric": "count", "threshold": 1},
        ).status_code
        == 404
    )

    patched = admin.patch(
        f"/api/admin/alert-rules/{rule['id']}",
        json={
            "threshold": 800,
            "min_confidence": "high",
            "webhook_url": "https://hooks.exemplo.org/a",
            "active": False,
        },
    ).json()
    assert patched["threshold"] == 800 and patched["min_confidence"] == "high" and patched["active"] is False

    assert [r["id"] for r in admin.get("/api/admin/alert-rules").json()] == [rule["id"]]
    assert admin.delete(f"/api/admin/alert-rules/{rule['id']}").status_code == 204
    assert admin.delete(f"/api/admin/alert-rules/{rule['id']}").status_code == 404


def test_events_listing_and_subscriber_summary_without_emails(admin, env):
    factory, sender = env
    with factory() as session:
        rule = _rule(session)
        _subscriber(session, "ok@exemplo.com")
        _subscriber(session, "pendente@exemplo.com", status=SubscriberStatus.PENDING)
        evaluate_rules(session, now=NOW, sender=sender, settings=SETTINGS)
        session.commit()
        rule_id = rule.id

    events = admin.get("/api/admin/alert-events", params={"rule_id": rule_id}).json()
    assert (
        len(events) == 1
        and events[0]["measured_value"] == 4
        and events[0]["rule"]["region_slug"] == "grecia-pais"
    )
    assert "@" not in str(events)

    summary = admin.get("/api/admin/subscribers/summary")
    assert summary.json() == {"pending": 1, "confirmed": 1, "unsubscribed": 0}
    assert "@" not in summary.text


def test_public_recent_alerts_hide_recipients_and_filter_by_region(env):
    factory, sender = env
    client = TestClient(app)
    # alert_events é append-only e acumula eventos de outros testes: olhamos só o que este teste criou
    before = {e["id"] for e in client.get("/api/alerts/recent", params={"limit": 100}).json()}
    now = datetime.now(timezone.utc)
    with factory() as session:
        _rule(session)
        _subscriber(session, "ok@exemplo.com")
        persist_detections(
            session,
            [_det(37.98 + i / 100, 23.72, now - timedelta(minutes=10 * i)) for i in range(1, 6)],
            run_id=None,
        )
        evaluate_rules(session, now=now, sender=sender, settings=SETTINGS)
        session.commit()

    def new_events(region):
        events = client.get("/api/alerts/recent", params={"region": region, "limit": 100}).json()
        return [e for e in events if e["id"] not in before]

    (ev,) = new_events("grecia-pais")
    assert (
        ev["region"] == "grecia-pais" and ev["rule"] == "Mais de 3 focos em 24h" and ev["measured_value"] >= 4
    )
    assert "recipients" not in ev and "@" not in str(ev)
    assert new_events("portugal") == []
    assert client.get("/api/alerts/recent", params={"region": "nao-existe"}).json() == []
