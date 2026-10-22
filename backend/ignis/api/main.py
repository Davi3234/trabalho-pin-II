"""API do IGNIS: healthcheck (RNF06) + endpoints públicos de leitura em /api."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Response, status
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ignis.api.public import router as public_router
from ignis.config import get_settings
from ignis.db.models import CollectionRun, RunStatus
from ignis.db.session import get_session

app = FastAPI(title="IGNIS API", version="0.3.0", description="DSS de monitoramento de incêndios florestais.")
app.include_router(public_router, prefix="/api")


@app.get("/health", tags=["infra"])
def health(response: Response, session: Session = Depends(get_session)) -> dict:
    """`ok` com banco acessível e coleta recente; `degraded` se a coleta está atrasada
    (o portal continua servindo dados antigos); 503 só se o banco estiver fora."""
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "down", "database": "unreachable"}

    last_success = session.scalar(
        select(CollectionRun.finished_at)
        .where(CollectionRun.job == "firms", CollectionRun.status.in_([RunStatus.SUCCESS, RunStatus.PARTIAL]))
        .order_by(CollectionRun.finished_at.desc())
        .limit(1)
    )
    max_age = get_settings().max_collection_age_minutes
    age_minutes = None
    if last_success is not None:
        age_minutes = round((datetime.now(timezone.utc) - last_success).total_seconds() / 60, 1)

    collection_ok = age_minutes is not None and age_minutes <= max_age
    return {
        "status": "ok" if collection_ok else "degraded",
        "database": "ok",
        "last_collection_at": last_success.isoformat() if last_success else None,
        "last_collection_age_minutes": age_minutes,
        "max_collection_age_minutes": max_age,
    }
