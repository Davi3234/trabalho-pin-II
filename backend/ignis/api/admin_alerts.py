"""Área administrativa de alertas: CRUD de regras e consulta ao histórico (RF06, RF10). Exige JWT."""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ignis.api.auth import require_admin
from ignis.db.models import (
    AlertEvent,
    AlertMetric,
    AlertRule,
    Region,
    Subscriber,
    SubscriberStatus,
)
from ignis.db.session import get_session
from ignis.interpretation.models import Confidence

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


def _check_webhook(value: str | None) -> str | None:
    if value in (None, ""):
        return None
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("webhook_url deve ser http(s)://...")
    return value


class RuleCreate(BaseModel):
    region: str = Field(description="slug da região")
    name: str = Field(min_length=2, max_length=120)
    metric: AlertMetric
    threshold: float = Field(gt=0)
    window_hours: int = Field(24, ge=1, le=168)
    min_confidence: Literal["low", "nominal", "high"] | None = None
    cooldown_hours: int = Field(12, ge=0, le=168)
    notify_subscribers: bool = True
    webhook_url: str | None = Field(None, max_length=500)

    _webhook = field_validator("webhook_url")(_check_webhook)


class RuleUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=120)
    metric: AlertMetric | None = None
    threshold: float | None = Field(None, gt=0)
    window_hours: int | None = Field(None, ge=1, le=168)
    min_confidence: Literal["low", "nominal", "high"] | None = None
    cooldown_hours: int | None = Field(None, ge=0, le=168)
    notify_subscribers: bool | None = None
    webhook_url: str | None = Field(None, max_length=500)
    active: bool | None = None

    _webhook = field_validator("webhook_url")(_check_webhook)


def _rule_dict(rule: AlertRule, region: Region) -> dict:
    return {
        "id": rule.id,
        "region": region.slug,
        "region_name": region.name,
        "name": rule.name,
        "metric": rule.metric.value,
        "threshold": rule.threshold,
        "window_hours": rule.window_hours,
        "min_confidence": rule.min_confidence.value if rule.min_confidence else None,
        "cooldown_hours": rule.cooldown_hours,
        "notify_subscribers": rule.notify_subscribers,
        "webhook_url": rule.webhook_url,
        "active": rule.active,
        "created_at": rule.created_at.isoformat() if rule.created_at else None,
    }


def _get_rule(session: Session, rule_id: int) -> tuple[AlertRule, Region]:
    rule = session.get(AlertRule, rule_id)
    if rule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "regra não encontrada")
    return rule, session.get(Region, rule.region_id)


@router.get("/alert-rules")
def list_rules(session: Session = Depends(get_session)) -> list[dict]:
    rows = session.execute(
        select(AlertRule, Region).join(Region, Region.id == AlertRule.region_id).order_by(AlertRule.id)
    ).all()
    return [_rule_dict(r, reg) for r, reg in rows]


@router.post("/alert-rules", status_code=status.HTTP_201_CREATED)
def create_rule(body: RuleCreate, session: Session = Depends(get_session)) -> dict:
    region = session.scalar(select(Region).where(Region.slug == body.region, Region.active))
    if region is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"região '{body.region}' não encontrada")
    rule = AlertRule(
        region_id=region.id,
        name=body.name,
        metric=body.metric,
        threshold=body.threshold,
        window_hours=body.window_hours,
        min_confidence=Confidence(body.min_confidence) if body.min_confidence else None,
        cooldown_hours=body.cooldown_hours,
        notify_subscribers=body.notify_subscribers,
        webhook_url=body.webhook_url,
    )
    session.add(rule)
    session.commit()
    return _rule_dict(rule, region)


@router.patch("/alert-rules/{rule_id}")
def update_rule(rule_id: int, body: RuleUpdate, session: Session = Depends(get_session)) -> dict:
    rule, region = _get_rule(session, rule_id)
    changes = body.model_dump(exclude_unset=True)
    if "min_confidence" in changes:
        changes["min_confidence"] = (
            Confidence(changes["min_confidence"]) if changes["min_confidence"] else None
        )
    for field, value in changes.items():
        setattr(rule, field, value)
    session.commit()
    return _rule_dict(rule, region)


@router.delete("/alert-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(rule_id: int, session: Session = Depends(get_session)) -> Response:
    """Apaga a regra; os eventos já gravados ficam (têm cópia da regra, sem FK)."""
    rule, _ = _get_rule(session, rule_id)
    session.delete(rule)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/alert-events")
def list_events(
    rule_id: int | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    session: Session = Depends(get_session),
) -> list[dict]:
    """Histórico de alertas disparados (RF10), do mais recente ao mais antigo."""
    stmt = select(AlertEvent).order_by(AlertEvent.triggered_at.desc(), AlertEvent.id.desc()).limit(limit)
    if rule_id is not None:
        stmt = stmt.where(AlertEvent.rule_id == rule_id)
    return [
        {
            "id": e.id,
            "rule_id": e.rule_id,
            "region_id": e.region_id,
            "rule": e.rule_snapshot,
            "measured_value": e.measured_value,
            "threshold": e.threshold,
            "window_start": e.window_start.isoformat(),
            "window_end": e.window_end.isoformat(),
            "triggered_at": e.triggered_at.isoformat(),
            "recipients": e.recipients,
        }
        for e in session.scalars(stmt)
    ]


@router.get("/subscribers/summary")
def subscribers_summary(session: Session = Depends(get_session)) -> dict:
    """Só contagens: o painel não mostra e-mails (minimização, RNF04)."""
    counts = dict(session.execute(select(Subscriber.status, func.count()).group_by(Subscriber.status)).all())
    return {s.value: counts.get(s, 0) for s in SubscriberStatus}
