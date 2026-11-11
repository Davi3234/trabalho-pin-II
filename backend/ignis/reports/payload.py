"""Monta o JSON estruturado que alimenta o LLM e o template (RF11).

Tudo que o texto pode citar nasce aqui, com as mesmas consultas dos gráficos. O período é
[inicio, fim] em dias UTC (inclusive); a comparação usa o período imediatamente anterior, do mesmo tamanho.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ignis.db.models import (
    AlertEvent,
    CollectionRun,
    FireDetection,
    FwiReading,
    Region,
    RunStatus,
)
from ignis.interpretation.models import Confidence
from ignis.interpretation.models import FireDetection as Detection
from ignis.interpretation.service import interpret_detections
from ignis.reports.template import DANGER_PT

SOURCES = ["NASA FIRMS (VIIRS/MODIS, quase tempo real)", "EFFIS/GWIS (índice FWI)"]
TOP_CLUSTERS = 3


def input_hash(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _in_region(stmt, region: Region):
    region_geom = select(Region.geom).where(Region.id == region.id).scalar_subquery()
    return stmt.where(func.ST_Intersects(FireDetection.geom, region_geom))


def _totals(session: Session, region: Region, start: date, end: date) -> dict:
    row = session.execute(
        _in_region(
            select(
                func.count().label("total"),
                func.count().filter(FireDetection.confidence == Confidence.HIGH).label("high"),
                func.coalesce(func.sum(FireDetection.frp), 0).label("frp_sum"),
                func.max(FireDetection.frp).label("frp_max"),
            ).where(FireDetection.acq_date.between(start, end)),
            region,
        )
    ).one()
    return {
        "total": row.total,
        "alta_confianca": row.high,
        "frp_total_mw": round(float(row.frp_sum), 1),
        "frp_max_mw": round(float(row.frp_max), 1) if row.frp_max is not None else None,
    }


def _daily(session: Session, region: Region, start: date, end: date) -> list[dict]:
    rows = session.execute(
        _in_region(
            select(FireDetection.acq_date, func.count()).where(FireDetection.acq_date.between(start, end)),
            region,
        ).group_by(FireDetection.acq_date)
    ).all()
    by_day = {d: n for d, n in rows}
    days = (end - start).days + 1
    return [
        {"data": (start + timedelta(days=i)).isoformat(), "focos": by_day.get(start + timedelta(days=i), 0)}
        for i in range(days)
    ]


def _top_clusters(session: Session, region: Region, start: date, end: date) -> list[dict]:
    rows = session.scalars(
        _in_region(select(FireDetection).where(FireDetection.acq_date.between(start, end)), region).order_by(
            FireDetection.acquired_at
        )
    ).all()
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
    if not detections:
        return []
    report = interpret_detections(detections, region=region.name, bbox=region.bbox_str, sensor="todos")
    return [
        {
            "posicao": entry["rank"],
            "focos": entry["detection_count"],
            "frp_total_mw": round(entry["total_frp_mw"], 1),
            "duracao_horas": round(entry["duration_hours"], 1),
            "latitude": round(entry["centroid"]["latitude"], 2),
            "longitude": round(entry["centroid"]["longitude"], 2),
        }
        for entry in report.severity_ranking[:TOP_CLUSTERS]
    ]


def _ranking(session: Session, start: date, end: date) -> list[dict]:
    stmt = (
        select(Region.name, func.count(FireDetection.id).label("n"))
        .select_from(Region)
        .join(
            FireDetection,
            func.ST_Intersects(FireDetection.geom, Region.geom) & FireDetection.acq_date.between(start, end),
            isouter=True,
        )
        .where(Region.kind == "country", Region.active)
        .group_by(Region.id)
        .order_by(func.count(FireDetection.id).desc())
    )
    return [{"pais": name, "focos": n} for name, n in session.execute(stmt) if n]


def _fwi(session: Session, region: Region, start: date, end: date) -> dict | None:
    readings = session.scalars(
        select(FwiReading)
        .where(FwiReading.region_id == region.id, FwiReading.date >= start)
        .order_by(FwiReading.date)
    ).all()
    if not readings:
        return None
    in_period = [r.fwi_value for r in readings if start <= r.date <= end]
    today = datetime.now(timezone.utc).date()
    at_ref = next((r for r in readings if r.date == min(end, today)), None)
    # classes já em português: o LLM e o template citam o texto como está
    return {
        "media_periodo": round(sum(in_period) / len(in_period), 1) if in_period else None,
        "classe_hoje": DANGER_PT[at_ref.danger_class.value] if at_ref else None,
        "previsao": [
            {
                "data": r.date.isoformat(),
                "classe": DANGER_PT[r.danger_class.value],
                "indice_medio": round(r.fwi_value, 1),
            }
            for r in readings
            if r.date > end
        ],
    }


def _alerts(session: Session, region: Region, start: date, end: date) -> list[dict]:
    lo = datetime.combine(start, time.min, tzinfo=timezone.utc)
    hi = datetime.combine(end + timedelta(days=1), time.min, tzinfo=timezone.utc)
    events = session.scalars(
        select(AlertEvent)
        .where(AlertEvent.region_id == region.id, AlertEvent.triggered_at >= lo, AlertEvent.triggered_at < hi)
        .order_by(AlertEvent.triggered_at)
    ).all()
    return [
        {
            "regra": (e.rule_snapshot or {}).get("name", "regra de alerta"),
            "valor": round(e.measured_value, 1),
            "limiar": round(e.threshold, 1),
            "em": e.triggered_at.isoformat(),
        }
        for e in events
    ]


def _last_collection(session: Session) -> str | None:
    last = session.scalar(
        select(CollectionRun.finished_at)
        .where(CollectionRun.job == "firms", CollectionRun.status.in_([RunStatus.SUCCESS, RunStatus.PARTIAL]))
        .order_by(CollectionRun.finished_at.desc())
        .limit(1)
    )
    return last.isoformat() if last else None


def build_report_input(session: Session, region: Region, start: date, end: date) -> dict:
    days = (end - start).days + 1
    current = _totals(session, region, start, end)
    prev_start, prev_end = start - timedelta(days=days), start - timedelta(days=1)
    previous = _totals(session, region, prev_start, prev_end)["total"]

    variacao = round(100 * (current["total"] - previous) / previous, 1) if previous else None
    return {
        "regiao": region.name,
        "regiao_slug": region.slug,
        "periodo": {"inicio": start.isoformat(), "fim": end.isoformat(), "dias": days},
        "fontes": SOURCES,
        "focos": {**current, "serie_diaria": _daily(session, region, start, end)},
        "comparacao_periodo_anterior": {"total_anterior": previous, "variacao_pct": variacao},
        "agrupamentos_mais_criticos": _top_clusters(session, region, start, end),
        "ranking_paises": _ranking(session, start, end) if region.kind.value != "country" else [],
        "fwi": _fwi(session, region, start, end),
        "alertas_disparados": _alerts(session, region, start, end),
        "dados_atualizados_em": _last_collection(session),
    }
