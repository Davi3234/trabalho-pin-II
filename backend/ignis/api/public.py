"""Endpoints públicos de leitura (portal). Fatia mínima da etapa 4 (RF04, RF05)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from ignis.db.models import CollectionRun, FireDetection, Region, RunStatus
from ignis.db.session import get_session
from ignis.interpretation.models import Confidence
from ignis.interpretation.models import FireDetection as Detection
from ignis.interpretation.service import interpret_detections

router = APIRouter(tags=["público"])

# dados mudam no máximo a cada ciclo de coleta (1h): 5 min de cache aliviam picos (RNF06)
PUBLIC_CACHE = "public, max-age=300"
MAX_HOURS = 24 * 7

CONFIDENCE_ORDER = [Confidence.LOW, Confidence.NOMINAL, Confidence.HIGH]
CONF_SHORT = {Confidence.LOW: "l", Confidence.NOMINAL: "n", Confidence.HIGH: "h", Confidence.UNKNOWN: "?"}


def _region_or_404(session: Session, slug: str) -> Region:
    region = session.scalar(select(Region).where(Region.slug == slug))
    if region is None:
        raise HTTPException(status_code=404, detail=f"região '{slug}' não encontrada")
    return region


def _in_region(stmt: Select, region: Region) -> Select:
    # pertença espacial: o foco não guarda região (ver ignis/db/models.py)
    region_geom = select(Region.geom).where(Region.id == region.id).scalar_subquery()
    return stmt.where(func.ST_Intersects(FireDetection.geom, region_geom))


def _last_collection(session: Session) -> datetime | None:
    return session.scalar(
        select(CollectionRun.finished_at)
        .where(CollectionRun.job == "firms", CollectionRun.status.in_([RunStatus.SUCCESS, RunStatus.PARTIAL]))
        .order_by(CollectionRun.finished_at.desc())
        .limit(1)
    )


@router.get("/regions")
def list_regions(response: Response, session: Session = Depends(get_session)) -> list[dict]:
    response.headers["Cache-Control"] = PUBLIC_CACHE
    regions = session.scalars(select(Region).where(Region.active).order_by(Region.kind.desc(), Region.id))
    return [
        {
            "slug": r.slug,
            "name": r.name,
            "kind": r.kind.value,
            "collect": r.collect,
            "bbox": {"west": r.west, "south": r.south, "east": r.east, "north": r.north},
        }
        for r in regions
    ]


@router.get("/interpretation")
def interpretation(
    response: Response,
    region: str = Query("mediterraneo", description="slug da região"),
    hours: int = Query(48, ge=1, le=MAX_HOURS, description="tamanho da janela, em horas"),
    until: date | None = Query(None, description="último dia (UTC) da janela; vazio = até agora (RF08)"),
    sensor: str | None = Query(None, description="ex.: VIIRS_NOAA20_NRT; vazio = todos"),
    min_confidence: Literal["low", "nominal", "high"] | None = Query(None),
    min_frp: float | None = Query(None, ge=0, description="FRP mínimo em MW"),
    session: Session = Depends(get_session),
) -> dict:
    """Relatório de interpretação (clusters, densidade, tendência, criticidade) sobre os focos
    do banco, no mesmo formato do JSON gerado pelo coletor — mais os focos individuais."""
    reg = _region_or_404(session, region)
    end = (
        datetime.combine(until + timedelta(days=1), time.min, tzinfo=timezone.utc)
        if until
        else datetime.now(timezone.utc)
    )
    since = end - timedelta(hours=hours)

    stmt = _in_region(
        select(FireDetection).where(FireDetection.acquired_at >= since, FireDetection.acquired_at < end), reg
    )
    if sensor:
        stmt = stmt.where(FireDetection.source == sensor)
    if min_confidence:
        allowed = CONFIDENCE_ORDER[CONFIDENCE_ORDER.index(Confidence(min_confidence)) :]
        stmt = stmt.where(FireDetection.confidence.in_(allowed))
    if min_frp is not None:
        stmt = stmt.where(FireDetection.frp >= min_frp)

    rows = session.scalars(stmt.order_by(FireDetection.acquired_at)).all()
    detections = [
        Detection(
            latitude=float(r.latitude),
            longitude=float(r.longitude),
            acquired_at=r.acquired_at,
            sensor=r.source,
            satellite=r.satellite,
            confidence=r.confidence,
            confidence_raw=r.confidence_raw,
            frp_mw=r.frp,
            brightness_k=r.brightness,
            scan_km=r.scan,
            track_km=r.track,
            daynight=r.daynight,
        )
        for r in rows
    ]
    report = interpret_detections(detections, region=reg.name, bbox=reg.bbox_str, sensor=sensor or "todos")
    body = report.to_dict()
    body["detections"] = [
        {
            "lat": d.latitude,
            "lon": d.longitude,
            "frp": d.frp_mw,
            "conf": CONF_SHORT[d.confidence],
            "t": d.acquired_at.strftime("%d/%m %H:%M"),
            "sensor": d.sensor,
        }
        for d in detections
    ]
    last = _last_collection(session)
    body["filters"] = {
        "region": region,
        "hours": hours,
        "until": until.isoformat() if until else None,
        "sensor": sensor,
        "min_confidence": min_confidence,
        "min_frp": min_frp,
    }
    body["last_collection_at"] = last.isoformat() if last else None
    response.headers["Cache-Control"] = PUBLIC_CACHE
    return body


@router.get("/stats/daily")
def daily_series(
    response: Response,
    region: str = Query("mediterraneo"),
    days: int = Query(60, ge=1, le=366),
    session: Session = Depends(get_session),
) -> list[dict]:
    """Série diária de focos e FRP somado (RF05) — dias sem foco aparecem com zero."""
    reg = _region_or_404(session, region)
    today = datetime.now(timezone.utc).date()
    first = today - timedelta(days=days - 1)
    stmt = _in_region(
        select(
            FireDetection.acq_date,
            func.count().label("count"),
            func.coalesce(func.sum(FireDetection.frp), 0).label("frp_sum"),
        ).where(FireDetection.acq_date >= first),
        reg,
    ).group_by(FireDetection.acq_date)
    by_day = {row.acq_date: row for row in session.execute(stmt)}
    response.headers["Cache-Control"] = PUBLIC_CACHE
    series = []
    for offset in range(days):
        day = first + timedelta(days=offset)
        row = by_day.get(day)
        series.append(
            {
                "date": day.isoformat(),
                "count": row.count if row else 0,
                "frp_sum": round(row.frp_sum, 1) if row else 0,
            }
        )
    return series


@router.get("/stats/ranking")
def country_ranking(
    response: Response,
    hours: int = Query(24 * 7, ge=1, le=24 * 366),
    session: Session = Depends(get_session),
) -> list[dict]:
    """Focos por sub-região (país) no período (RF05)."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    stmt = (
        select(
            Region.slug,
            Region.name,
            func.count(FireDetection.id).label("count"),
            func.coalesce(func.sum(FireDetection.frp), 0).label("frp_sum"),
        )
        .select_from(Region)
        .join(
            FireDetection,
            func.ST_Intersects(FireDetection.geom, Region.geom) & (FireDetection.acquired_at >= since),
            isouter=True,
        )
        .where(Region.kind == "country", Region.active)
        .group_by(Region.id)
        .order_by(func.count(FireDetection.id).desc())
    )
    response.headers["Cache-Control"] = PUBLIC_CACHE
    return [
        {"slug": r.slug, "name": r.name, "count": r.count, "frp_sum": round(r.frp_sum, 1)}
        for r in session.execute(stmt)
    ]


@router.get("/collection/status")
def collection_status(session: Session = Depends(get_session)) -> dict:
    """Última execução da coleta — base do indicador "dados atualizados em …" (RNF06)."""
    run = session.scalar(
        select(CollectionRun)
        .where(CollectionRun.job == "firms")
        .order_by(CollectionRun.started_at.desc())
        .limit(1)
    )
    total = session.scalar(select(func.count()).select_from(FireDetection))
    last_ok = _last_collection(session)
    return {
        "last_success_at": last_ok.isoformat() if last_ok else None,
        "total_detections": total,
        "last_run": (
            None
            if run is None
            else {
                "id": run.id,
                "status": run.status.value,
                "started_at": run.started_at.isoformat(),
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                "fetched_rows": run.fetched_rows,
                "new_detections": run.new_detections,
                "transactions_used": run.transactions_used,
            }
        ),
    }
