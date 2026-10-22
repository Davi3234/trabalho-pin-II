"""Ciclo de coleta da FIRMS: regiões do banco -> requisições -> normalização -> persistência.

RF01: itera `regions WHERE collect AND active` x FIRMS_SOURCES (regiões são dados, RNF05).
RF02: INSERT ... ON CONFLICT DO NOTHING na chave natural; histórico nunca é apagado.
RNF01: cada execução fica registrada em collection_runs.
RNF02: limitador em janela deslizante + status oficial da MAP_KEY + cache de respostas.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ignis.collectors.firms import client as firms_client
from ignis.collectors.firms.rate_limiter import RateLimitExceeded, SlidingWindowRateLimiter
from ignis.db.models import CollectionRun, FireDetection, Region, RunStatus
from ignis.interpretation.mapper import map_dataframe
from ignis.interpretation.models import FireDetection as Detection

logger = logging.getLogger("ignis.collector")

INSERT_BATCH_SIZE = 1000
CACHE_TTL_SECONDS = 15 * 60

# Medido em 2026-10-21 com o endpoint de status: 2 dias de VIIRS no Mediterrâneo = 4 transações.
# Estimativa conservadora usada só pelo limitador local; o valor real vem do status da MAP_KEY.
TRANSACTIONS_PER_DAY = 2


def estimate_cost(days: int) -> int:
    return TRANSACTIONS_PER_DAY * days


@dataclass(frozen=True)
class CollectionTarget:
    region_slug: str
    bbox: str


def _contains(outer: Region, inner: Region) -> bool:
    return (
        outer.west <= inner.west
        and outer.south <= inner.south
        and outer.east >= inner.east
        and outer.north >= inner.north
    )


def plan_targets(regions: list[Region]) -> list[CollectionTarget]:
    """Pula áreas cujo bbox está inteiro dentro de outra área coletada.

    Os focos delas já chegam pela área maior e a pertença a região é espacial (ST_Intersects),
    então a chamada extra só gastaria transações (ex.: uma região "Sicília" cadastrada pelo admin).
    """
    ordered = sorted(regions, key=lambda r: r.id or 0)
    targets = []
    for region in ordered:
        covered = any(
            other is not region
            and _contains(other, region)
            and (not _contains(region, other) or other.id < region.id)
            for other in ordered
        )
        if covered:
            logger.info("Região %s contida em outra área coletada — sem requisição própria.", region.slug)
            continue
        targets.append(CollectionTarget(region.slug, region.bbox_str))
    return targets


class ResponseCache:
    """Cache em memória das respostas da FIRMS (evita repetir a mesma consulta dentro do TTL)."""

    def __init__(self, ttl_seconds: float = CACHE_TTL_SECONDS, clock: Callable[[], float] = time.monotonic):
        self.ttl = ttl_seconds
        self._clock = clock
        self._items: dict[tuple, tuple[float, pd.DataFrame]] = {}

    def get(self, key: tuple) -> pd.DataFrame | None:
        item = self._items.get(key)
        if item is None or self._clock() - item[0] > self.ttl:
            self._items.pop(key, None)
            return None
        return item[1]

    def put(self, key: tuple, df: pd.DataFrame) -> None:
        self._items[key] = (self._clock(), df)


def detection_to_row(d: Detection, run_id: int | None) -> dict:
    acquired = d.acquired_at.astimezone(timezone.utc)
    lat = Decimal(str(round(d.latitude, 5)))
    lon = Decimal(str(round(d.longitude, 5)))
    return {
        "source": d.sensor,
        "latitude": lat,
        "longitude": lon,
        "acq_date": acquired.date(),
        "acq_time": acquired.hour * 100 + acquired.minute,
        "acquired_at": acquired,
        "satellite": d.satellite,
        "confidence": d.confidence,
        "confidence_raw": d.confidence_raw[:8],
        "frp": d.frp_mw,
        "brightness": d.brightness_k,
        "scan": d.scan_km,
        "track": d.track_km,
        "daynight": d.daynight,
        "geom": f"SRID=4326;POINT({lon} {lat})",
        "first_run_id": run_id,
    }


def persist_detections(session: Session, detections: list[Detection], run_id: int | None) -> int:
    """Insere com dedup pela chave natural; retorna quantos focos eram realmente novos."""
    new = 0
    rows = [detection_to_row(d, run_id) for d in detections]
    for start in range(0, len(rows), INSERT_BATCH_SIZE):
        stmt = (
            insert(FireDetection)
            .values(rows[start : start + INSERT_BATCH_SIZE])
            .on_conflict_do_nothing(constraint="uq_fire_detections_natural")
            .returning(FireDetection.id)
        )
        new += len(session.execute(stmt).all())
    return new


@dataclass
class CycleResult:
    run_id: int
    status: RunStatus
    fetched_rows: int = 0
    new_detections: int = 0
    transactions_used: int = 0
    details: list[dict] = field(default_factory=list)


def _windows(day_range: int, days_back: int | None) -> Iterator[tuple[int, date | None]]:
    """Janelas (dias, data inicial) a pedir. Backfill quebra em blocos de até 5 dias (limite da API)."""
    if days_back is None:
        yield day_range, None
        return
    today = datetime.now(timezone.utc).date()
    first = today - timedelta(days=days_back - 1)
    cursor = first
    while cursor <= today:
        span = min(firms_client.DAY_RANGE_MAX, (today - cursor).days + 1)
        yield span, cursor
        cursor += timedelta(days=span)


class FirmsCollector:
    def __init__(
        self,
        session_scope: Callable[[], AbstractContextManager[Session]],
        map_key: str,
        sources: list[str],
        limiter: SlidingWindowRateLimiter | None = None,
        cache: ResponseCache | None = None,
        fetch: Callable[..., pd.DataFrame] = firms_client.coletar,
        key_status: Callable[[str], dict | None] = firms_client.consultar_status,
    ):
        self.session_scope = session_scope
        self.map_key = map_key
        self.sources = sources
        self.limiter = limiter or SlidingWindowRateLimiter()
        self.cache = cache or ResponseCache()
        self.fetch = fetch
        self.key_status = key_status

    def _start_run(self) -> int:
        with self.session_scope() as session:
            run = CollectionRun(job="firms", status=RunStatus.RUNNING, details={})
            session.add(run)
            session.flush()
            return run.id

    def _targets(self) -> list[CollectionTarget]:
        with self.session_scope() as session:
            regions = list(session.scalars(select(Region).where(Region.collect, Region.active)))
            return plan_targets(regions)

    def run_cycle(self, day_range: int = 2, days_back: int | None = None) -> CycleResult:
        """Um ciclo completo. `days_back` ativa o modo backfill (histórico de N dias)."""
        run_id = self._start_run()
        result = CycleResult(run_id=run_id, status=RunStatus.RUNNING)
        estimated = 0

        status_before = self.key_status(self.map_key)
        if status_before:
            self.limiter.sync(status_before["current_transactions"])

        try:
            targets = self._targets()
        except Exception as exc:  # banco fora: registra e encerra
            logger.exception("Falha ao carregar regiões")
            return self._finish(result, RunStatus.FAILED, estimated, status_before, error=str(exc))

        errors = 0
        for target in targets:
            for source in self.sources:
                for days, start in _windows(day_range, days_back):
                    item = {"region": target.region_slug, "source": source, "days": days}
                    if start:
                        item["date"] = start.isoformat()
                    try:
                        cache_key = (source, target.bbox, days, start)
                        df = self.cache.get(cache_key)
                        item["cached"] = df is not None
                        if df is None:
                            cost = estimate_cost(days)
                            self.limiter.acquire(cost)
                            estimated += cost
                            df = self.fetch(self.map_key, source, target.bbox, days, start)
                            self.cache.put(cache_key, df)
                        item.update(self._store(df, source, run_id))
                        result.fetched_rows += item["rows"]
                        result.new_detections += item["new"]
                    except RateLimitExceeded as exc:
                        errors += 1
                        item["error"] = str(exc)
                        logger.warning("Limite da FIRMS: %s — encerrando o ciclo.", exc)
                        result.details.append(item)
                        return self._finish(result, RunStatus.PARTIAL, estimated, status_before)
                    except Exception as exc:  # uma região/sensor com erro não derruba as demais
                        errors += 1
                        item["error"] = f"{type(exc).__name__}: {exc}"[:500]
                        logger.warning("Falha em %s/%s: %s", target.region_slug, source, item["error"])
                    result.details.append(item)

        total = len(result.details)
        if total and errors == total:
            status = RunStatus.FAILED
        elif errors:
            status = RunStatus.PARTIAL
        else:
            status = RunStatus.SUCCESS
        return self._finish(result, status, estimated, status_before)

    def _store(self, df: pd.DataFrame, source: str, run_id: int) -> dict:
        if df is None or df.empty:
            return {"rows": 0, "new": 0, "rejected": 0}
        mapping = map_dataframe(df, source)
        with self.session_scope() as session:
            new = persist_detections(session, mapping.detections, run_id)
        return {"rows": mapping.rows_received, "new": new, "rejected": mapping.rows_rejected}

    def _finish(
        self,
        result: CycleResult,
        status: RunStatus,
        estimated: int,
        status_before: dict | None,
        error: str | None = None,
    ) -> CycleResult:
        status_after = self.key_status(self.map_key) if status_before else None
        if status_before and status_after:
            # o contador oficial é da janela de 10 min; delta negativo = janela "rolou" no meio do ciclo
            delta = status_after["current_transactions"] - status_before["current_transactions"]
            result.transactions_used = delta if delta >= 0 else estimated
        else:
            result.transactions_used = estimated
        result.status = status

        with self.session_scope() as session:
            run = session.get(CollectionRun, result.run_id)
            run.finished_at = datetime.now(timezone.utc)
            run.status = status
            run.fetched_rows = result.fetched_rows
            run.new_detections = result.new_detections
            run.transactions_used = result.transactions_used
            run.details = {"items": result.details, "estimated_transactions": estimated}
            run.error = error
        logger.info(
            "Ciclo FIRMS #%d: %s | %d linhas | %d focos novos | %d transações (estimadas: %d)",
            result.run_id,
            status.value,
            result.fetched_rows,
            result.new_detections,
            result.transactions_used,
            estimated,
        )
        return result
