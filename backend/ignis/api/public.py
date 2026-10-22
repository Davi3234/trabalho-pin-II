"""Endpoints públicos de leitura do portal (RF03, RF04, RF05, RF08)."""

from __future__ import annotations

import csv
import io
import math
from collections.abc import Iterator
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from ignis.api.schemas import BBox
from ignis.db.models import CollectionRun, FireDetection, FwiReading, Region, RunStatus
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

DEFAULT_GEOJSON_LIMIT = 5000
MAX_GEOJSON_LIMIT = 50000
MAX_HISTORY_DAYS = 366

# área queimada estimada (ver docs/area_queimada.md): grade de células do tamanho do pixel VIIRS
VIIRS_PIXEL_KM = 0.375
KM_PER_DEGREE_LAT = 111.32
CELL_DEG = VIIRS_PIXEL_KM / KM_PER_DEGREE_LAT

FWI_ATTRIBUTION = "EFFIS/GWIS, Copernicus Emergency Management Service (CC BY 4.0)"

CSV_COLUMNS = [
    "acquired_at_utc",
    "latitude",
    "longitude",
    "sensor",
    "satellite",
    "confidence",
    "confidence_raw",
    "frp_mw",
    "brightness_k",
    "scan_km",
    "track_km",
    "daynight",
]


def _region_or_404(session: Session, slug: str) -> Region:
    region = session.scalar(select(Region).where(Region.slug == slug))
    if region is None:
        raise HTTPException(status_code=404, detail=f"região '{slug}' não encontrada")
    return region


def _in_region(stmt: Select, region: Region) -> Select:
    # pertença espacial: o foco não guarda região (ver ignis/db/models.py)
    region_geom = select(Region.geom).where(Region.id == region.id).scalar_subquery()
    return stmt.where(func.ST_Intersects(FireDetection.geom, region_geom))


def _attribute_filters(
    stmt: Select, sensor: str | None, min_confidence: str | None, min_frp: float | None
) -> Select:
    """Filtros de sensor, confiança mínima e FRP mínimo, comuns ao mapa e ao histórico (RF04, RF08)."""
    if sensor:
        stmt = stmt.where(FireDetection.source == sensor)
    if min_confidence:
        allowed = CONFIDENCE_ORDER[CONFIDENCE_ORDER.index(Confidence(min_confidence)) :]
        stmt = stmt.where(FireDetection.confidence.in_(allowed))
    if min_frp is not None:
        stmt = stmt.where(FireDetection.frp >= min_frp)
    return stmt


def _window_end(until: date | None) -> datetime:
    """Fim exclusivo da janela: meia-noite UTC depois de `until`, ou agora."""
    if until:
        return datetime.combine(until + timedelta(days=1), time.min, tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


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
    end = _window_end(until)
    since = end - timedelta(hours=hours)

    stmt = _in_region(
        select(FireDetection).where(FireDetection.acquired_at >= since, FireDetection.acquired_at < end), reg
    )
    stmt = _attribute_filters(stmt, sensor, min_confidence, min_frp)

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


def _bbox_or_422(text: str) -> BBox:
    try:
        return BBox.parse(text)
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail=f"bbox inválido: {exc}") from None


@router.get("/detections")
def detections_geojson(
    response: Response,
    region: str | None = Query(None, description="slug da região; vazio = sem recorte por região"),
    bbox: str | None = Query(None, description="oeste,sul,leste,norte em graus (recorte da tela do mapa)"),
    hours: int = Query(24, ge=1, le=MAX_HOURS, description="tamanho da janela, em horas"),
    until: date | None = Query(None, description="último dia (UTC) da janela; vazio = até agora"),
    sensor: str | None = Query(None, description="ex.: VIIRS_NOAA20_NRT; vazio = todos"),
    min_confidence: Literal["low", "nominal", "high"] | None = Query(None),
    min_frp: float | None = Query(None, ge=0, description="FRP mínimo em MW"),
    limit: int = Query(DEFAULT_GEOJSON_LIMIT, ge=1, le=MAX_GEOJSON_LIMIT),
    session: Session = Depends(get_session),
) -> dict:
    """Focos em GeoJSON (RF04), do mais recente para o mais antigo. Acima de `limit`, a resposta
    traz só os mais recentes e marca `truncated = true` (o mapa deve pedir um recorte menor)."""
    end = _window_end(until)
    since = end - timedelta(hours=hours)
    stmt = select(FireDetection).where(FireDetection.acquired_at >= since, FireDetection.acquired_at < end)
    if region:
        stmt = _in_region(stmt, _region_or_404(session, region))
    if bbox:
        box = _bbox_or_422(bbox)
        envelope = func.ST_MakeEnvelope(box.west, box.south, box.east, box.north, 4326)
        stmt = stmt.where(func.ST_Intersects(FireDetection.geom, envelope))
    stmt = _attribute_filters(stmt, sensor, min_confidence, min_frp)

    # pede um a mais só para saber se cortou
    rows = session.scalars(
        stmt.order_by(FireDetection.acquired_at.desc(), FireDetection.id.desc()).limit(limit + 1)
    ).all()
    truncated = len(rows) > limit
    rows = rows[:limit]
    response.headers["Cache-Control"] = PUBLIC_CACHE
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": r.id,
                "geometry": {"type": "Point", "coordinates": [float(r.longitude), float(r.latitude)]},
                "properties": {
                    "acquired_at": r.acquired_at.isoformat(),
                    "sensor": r.source,
                    "satellite": r.satellite,
                    "confidence": r.confidence.value,
                    "frp_mw": r.frp,
                    "brightness_k": r.brightness,
                    "daynight": r.daynight,
                },
            }
            for r in rows
        ],
        "metadata": {
            "count": len(rows),
            "limit": limit,
            "truncated": truncated,
            "window_start": since.isoformat(),
            "window_end": end.isoformat(),
            "source": "NASA FIRMS (NRT)",
        },
    }


def _history_query(
    session: Session,
    region: str,
    start: date | None,
    end: date | None,
    sensor: str | None,
    min_confidence: str | None,
    min_frp: float | None,
) -> tuple[Select, date, date]:
    end = end or datetime.now(timezone.utc).date()
    start = start or end - timedelta(days=6)
    if start > end:
        raise HTTPException(status_code=422, detail="o início do período deve ser anterior ao fim")
    if (end - start).days + 1 > MAX_HISTORY_DAYS:
        raise HTTPException(status_code=422, detail=f"período máximo de {MAX_HISTORY_DAYS} dias")
    reg = _region_or_404(session, region)
    stmt = select(FireDetection).where(
        FireDetection.acquired_at >= datetime.combine(start, time.min, tzinfo=timezone.utc),
        FireDetection.acquired_at < _window_end(end),
    )
    stmt = _attribute_filters(_in_region(stmt, reg), sensor, min_confidence, min_frp)
    return stmt, start, end


def _history_row(r: FireDetection) -> dict:
    return {
        "acquired_at_utc": r.acquired_at.isoformat(),
        "latitude": float(r.latitude),
        "longitude": float(r.longitude),
        "sensor": r.source,
        "satellite": r.satellite,
        "confidence": r.confidence.value,
        "confidence_raw": r.confidence_raw,
        "frp_mw": r.frp,
        "brightness_k": r.brightness,
        "scan_km": r.scan,
        "track_km": r.track,
        "daynight": r.daynight,
    }


@router.get("/history")
def history(
    response: Response,
    region: str = Query("mediterraneo", description="slug da região"),
    start: date | None = Query(None, description="primeiro dia (UTC); vazio = 6 dias antes do fim"),
    end: date | None = Query(None, description="último dia (UTC), inclusive; vazio = hoje"),
    sensor: str | None = Query(None),
    min_confidence: Literal["low", "nominal", "high"] | None = Query(None),
    min_frp: float | None = Query(None, ge=0),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    session: Session = Depends(get_session),
) -> dict:
    """Histórico de focos por período e região, paginado, do mais recente ao mais antigo (RF08)."""
    stmt, start, end = _history_query(session, region, start, end, sensor, min_confidence, min_frp)
    total = session.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = session.scalars(
        stmt.order_by(FireDetection.acquired_at.desc(), FireDetection.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    response.headers["Cache-Control"] = PUBLIC_CACHE
    return {
        "region": region,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": math.ceil(total / page_size),
        "items": [_history_row(r) for r in rows],
    }


def _csv_chunks(bind, stmt: Select) -> Iterator[str]:
    # sessão própria: a da dependência pode ser fechada antes de o corpo terminar de ser enviado
    with Session(bind) as session:
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for row in session.scalars(stmt, execution_options={"yield_per": 2000}):
            writer.writerow(_history_row(row))
            if buffer.tell() > 64 * 1024:
                yield buffer.getvalue()
                buffer.seek(0)
                buffer.truncate()
        yield buffer.getvalue()


@router.get("/history.csv", response_class=StreamingResponse)
def history_csv(
    region: str = Query("mediterraneo"),
    start: date | None = Query(None),
    end: date | None = Query(None),
    sensor: str | None = Query(None),
    min_confidence: Literal["low", "nominal", "high"] | None = Query(None),
    min_frp: float | None = Query(None, ge=0),
    session: Session = Depends(get_session),
) -> StreamingResponse:
    """Exportação CSV do histórico com os mesmos filtros de /history, em ordem cronológica (RF08)."""
    stmt, start, end = _history_query(session, region, start, end, sensor, min_confidence, min_frp)
    stmt = stmt.order_by(FireDetection.acquired_at, FireDetection.id)
    filename = f"ignis_focos_{region}_{start.isoformat()}_{end.isoformat()}.csv"
    return StreamingResponse(
        _csv_chunks(session.get_bind(), stmt),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": PUBLIC_CACHE},
    )


@router.get("/stats/burned-area")
def burned_area(
    response: Response,
    region: str = Query("mediterraneo"),
    days: int = Query(60, ge=1, le=366),
    session: Session = Depends(get_session),
) -> dict:
    """Área queimada acumulada ESTIMADA a partir dos focos VIIRS (RF05).

    Cada foco cai numa célula de ~375 m × 375 m; a célula conta uma vez, no dia da primeira
    detecção no período. Área = células × 0,140625 km². Método e limitações em docs/area_queimada.md.
    """
    reg = _region_or_404(session, region)
    today = datetime.now(timezone.utc).date()
    first = today - timedelta(days=days - 1)

    row = func.floor(FireDetection.latitude / CELL_DEG)
    # largura em longitude corrigida pela latitude, para a célula ter ~375 m também no sentido leste-oeste
    col = func.floor(FireDetection.longitude * func.cos(func.radians((row + 0.5) * CELL_DEG)) / CELL_DEG)
    cells = (
        _in_region(
            select(row.label("r"), col.label("c"), func.min(FireDetection.acq_date).label("first_day")).where(
                FireDetection.source.like("VIIRS%"), FireDetection.acq_date >= first
            ),
            reg,
        )
        .group_by(row, col)
        .subquery()
    )
    new_cells = dict(
        session.execute(select(cells.c.first_day, func.count()).group_by(cells.c.first_day)).tuples().all()
    )

    cell_km2 = VIIRS_PIXEL_KM**2
    series, cumulative = [], 0
    for offset in range(days):
        day = first + timedelta(days=offset)
        count = new_cells.get(day, 0)
        cumulative += count
        series.append(
            {
                "date": day.isoformat(),
                "new_km2": round(count * cell_km2, 2),
                "cumulative_km2": round(cumulative * cell_km2, 2),
            }
        )
    response.headers["Cache-Control"] = PUBLIC_CACHE
    return {
        "region": region,
        "estimated": True,
        "method": "células VIIRS de 375 m com foco no período (cada célula conta uma vez)",
        "cell_km2": cell_km2,
        "total_km2": round(cumulative * cell_km2, 2),
        "series": series,
        "caveats": [
            "Estimativa a partir de focos de calor, não é área queimada oficial (EFFIS/MODIS burned area).",
            "Nuvens e fumaça escondem focos (subestima); pixels fora do nadir são maiores que 375 m e "
            "fontes de calor industriais também contam (superestima).",
            "Só VIIRS: os pixels de 1 km do MODIS inflariam a área e duplicariam as mesmas frentes.",
        ],
    }


@router.get("/fwi")
def fwi(
    response: Response,
    region: str = Query("mediterraneo"),
    days_back: int = Query(7, ge=0, le=366, description="dias anteriores a hoje; a previsão vem sempre"),
    session: Session = Depends(get_session),
) -> dict:
    """Índice meteorológico de perigo de incêndio (FWI) por dia na região, com a previsão (RF03)."""
    reg = _region_or_404(session, region)
    today = datetime.now(timezone.utc).date()
    readings = session.scalars(
        select(FwiReading)
        .where(FwiReading.region_id == reg.id, FwiReading.date >= today - timedelta(days=days_back))
        .order_by(FwiReading.date, FwiReading.provider)
    ).all()
    response.headers["Cache-Control"] = PUBLIC_CACHE
    return {
        "region": region,
        "today": today.isoformat(),
        "attribution": FWI_ATTRIBUTION,
        "readings": [
            {
                "date": r.date.isoformat(),
                "forecast": r.date > today,
                "fwi_mean": round(r.fwi_value, 1),
                "fwi_max": round(r.fwi_max, 1),
                "danger_class": r.danger_class.value,
                "pixel_count": r.pixel_count,
                "provider": r.provider,
                "fetched_at": r.fetched_at.isoformat(),
            }
            for r in readings
        ],
    }
