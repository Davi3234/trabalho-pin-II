"""Alertas disparados, em leitura pública (RF10): o portal mostra o aviso sem expor destinatários."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ignis.db.models import AlertEvent, Region
from ignis.db.session import get_session

router = APIRouter(tags=["público"])


@router.get("/alerts/recent")
def recent_alerts(
    response: Response,
    region: str | None = Query(None, description="slug da região; vazio = todas"),
    hours: int = Query(48, ge=1, le=24 * 30),
    limit: int = Query(20, ge=1, le=100),
    session: Session = Depends(get_session),
) -> list[dict]:
    """Alertas dos últimos `hours` horas, do mais recente ao mais antigo. Sem lista de destinatários."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    stmt = select(AlertEvent).where(AlertEvent.triggered_at >= since)
    if region:
        region_id = session.scalar(select(Region.id).where(Region.slug == region))
        stmt = stmt.where(AlertEvent.region_id == region_id) if region_id else stmt.where(False)
    events = session.scalars(stmt.order_by(AlertEvent.triggered_at.desc(), AlertEvent.id.desc()).limit(limit))
    response.headers["Cache-Control"] = "public, max-age=60"
    return [
        {
            "id": e.id,
            "region": e.rule_snapshot.get("region_slug"),
            "region_name": e.rule_snapshot.get("region_name"),
            "rule": e.rule_snapshot.get("name"),
            "metric": e.rule_snapshot.get("metric"),
            "measured_value": e.measured_value,
            "threshold": e.threshold,
            "window_hours": e.rule_snapshot.get("window_hours"),
            "triggered_at": e.triggered_at.isoformat(),
        }
        for e in events
    ]
