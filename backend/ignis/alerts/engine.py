"""Motor de regras de alerta (RF06, RF10).

Após cada coleta, cada regra ativa (de região ativa) mede a métrica na janela; se passar do limiar e a
regra não estiver em cooldown, grava um `alert_event` (append-only) e notifica assinantes e webhook.

Ordem deliberada: notifica, depois grava o evento com o resultado das entregas, porque a tabela não
aceita UPDATE. Se o processo cair entre os dois passos, o próximo ciclo pode repetir o aviso: preferimos
isso a perder um alerta. Falha de entrega nunca impede o registro (senão o cooldown não valeria).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable
from urllib.parse import urlparse

import requests
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ignis.alerts.messages import alert_email
from ignis.alerts.tokens import SubscriptionsDisabled
from ignis.config import Settings, get_settings
from ignis.db.models import (
    AlertEvent,
    AlertMetric,
    AlertRule,
    FireDetection,
    Region,
    Subscriber,
    SubscriberRegion,
    SubscriberStatus,
)
from ignis.interpretation.models import Confidence
from ignis.notifications.mailer import EmailSendError, SmtpEmailSender

logger = logging.getLogger("ignis.alerts")

CONFIDENCE_ORDER = [Confidence.LOW, Confidence.NOMINAL, Confidence.HIGH]
WEBHOOK_TIMEOUT = 10

HttpPost = Callable[..., requests.Response]


@dataclass
class Triggered:
    rule: AlertRule
    region: Region
    value: float
    event: AlertEvent


def measure(session: Session, rule: AlertRule, region: Region, now: datetime) -> float:
    """Valor da métrica da regra na janela [now - window_hours, now], só com focos dentro da região."""
    start = now - timedelta(hours=rule.window_hours)
    region_geom = select(Region.geom).where(Region.id == region.id).scalar_subquery()
    stmt = select(
        func.count(),
        func.coalesce(func.sum(FireDetection.frp), 0),
        func.coalesce(func.max(FireDetection.frp), 0),
    ).where(
        FireDetection.acquired_at >= start,
        FireDetection.acquired_at <= now,
        func.ST_Intersects(FireDetection.geom, region_geom),
    )
    if rule.min_confidence is not None:
        allowed = CONFIDENCE_ORDER[CONFIDENCE_ORDER.index(Confidence(rule.min_confidence)) :]
        stmt = stmt.where(FireDetection.confidence.in_(allowed))
    count, frp_sum, frp_max = session.execute(stmt).one()
    return float(
        {AlertMetric.COUNT: count, AlertMetric.FRP_SUM: frp_sum, AlertMetric.FRP_MAX: frp_max}[rule.metric]
    )


def in_cooldown(session: Session, rule: AlertRule, now: datetime) -> bool:
    if rule.cooldown_hours <= 0:
        return False
    last = session.scalar(select(func.max(AlertEvent.triggered_at)).where(AlertEvent.rule_id == rule.id))
    return last is not None and last > now - timedelta(hours=rule.cooldown_hours)


def _snapshot(rule: AlertRule, region: Region) -> dict:
    return {
        "name": rule.name,
        "metric": rule.metric.value,
        "threshold": rule.threshold,
        "window_hours": rule.window_hours,
        "min_confidence": rule.min_confidence.value if rule.min_confidence else None,
        "cooldown_hours": rule.cooldown_hours,
        "region_slug": region.slug,
        "region_name": region.name,
    }


def _send_emails(
    session: Session,
    rule: AlertRule,
    region: Region,
    value: float,
    sender: SmtpEmailSender,
    settings: Settings,
) -> dict:
    subscribers = session.scalars(
        select(Subscriber)
        .join(SubscriberRegion, SubscriberRegion.subscriber_id == Subscriber.id)
        .where(SubscriberRegion.region_id == region.id, Subscriber.status == SubscriberStatus.CONFIRMED)
    ).all()
    sent, failed = [], []
    for sub in subscribers:
        try:
            sender.send(
                alert_email(
                    settings,
                    to=sub.email,
                    subscriber_id=sub.id,
                    rule_name=rule.name,
                    region_name=region.name,
                    metric=rule.metric,
                    value=value,
                    threshold=rule.threshold,
                    window_hours=rule.window_hours,
                )
            )
            sent.append(str(sub.id))
        except EmailSendError:
            failed.append(str(sub.id))  # o motivo já foi logado (sem o endereço) pelo remetente
    # só IDs: nunca e-mails em claro no registro de auditoria (RNF04)
    return {
        "attempted": len(subscribers),
        "sent": len(sent),
        "failed": len(failed),
        "sent_ids": sent,
        "failed_ids": failed,
    }


def _call_webhook(rule: AlertRule, region: Region, value: float, now: datetime, post: HttpPost) -> dict:
    url = rule.webhook_url or ""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return {"status": "invalid_url"}
    body = {
        "event": "alert",
        "rule": rule.name,
        "metric": rule.metric.value,
        "region": {"slug": region.slug, "name": region.name},
        "measured_value": value,
        "threshold": rule.threshold,
        "window_hours": rule.window_hours,
        "triggered_at": now.isoformat(),
    }
    try:
        resp = post(url, json=body, timeout=WEBHOOK_TIMEOUT)
    except requests.RequestException as exc:
        logger.warning("webhook da regra %s falhou (%s)", rule.id, type(exc).__name__)
        return {"host": parsed.hostname, "status": "failed"}
    ok = 200 <= resp.status_code < 300
    return {"host": parsed.hostname, "status": "ok" if ok else "failed", "http_status": resp.status_code}


def evaluate_rules(
    session: Session,
    *,
    now: datetime | None = None,
    sender: SmtpEmailSender | None = None,
    settings: Settings | None = None,
    http_post: HttpPost = requests.post,
) -> list[Triggered]:
    now = now or datetime.now(timezone.utc)
    settings = settings or get_settings()
    rules = session.execute(
        select(AlertRule, Region)
        .join(Region, Region.id == AlertRule.region_id)
        .where(AlertRule.active, Region.active)
        .order_by(AlertRule.id)
    ).all()

    triggered: list[Triggered] = []
    for rule, region in rules:
        value = measure(session, rule, region, now)
        if value <= rule.threshold or in_cooldown(session, rule, now):
            continue

        recipients: dict = {}
        if rule.notify_subscribers:
            if sender is None:
                recipients["email"] = {"status": "email_disabled"}
            else:
                try:
                    recipients["email"] = _send_emails(session, rule, region, value, sender, settings)
                except SubscriptionsDisabled:
                    recipients["email"] = {"status": "subscriptions_disabled"}
        if rule.webhook_url:
            recipients["webhook"] = _call_webhook(rule, region, value, now, http_post)

        event = AlertEvent(
            rule_id=rule.id,
            region_id=region.id,
            rule_snapshot=_snapshot(rule, region),
            measured_value=value,
            threshold=rule.threshold,
            window_start=now - timedelta(hours=rule.window_hours),
            window_end=now,
            triggered_at=now,
            recipients=recipients,
        )
        session.add(event)
        session.flush()
        triggered.append(Triggered(rule, region, value, event))
        logger.info(
            "Alerta disparado: regra %s (%s) valor=%s limiar=%s", rule.id, region.slug, value, rule.threshold
        )
    return triggered
