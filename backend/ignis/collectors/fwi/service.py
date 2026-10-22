"""Ciclo de coleta do FWI: regiões ativas x datas -> grade do provedor -> média/máx. no polígono.

RF03: um valor por região e data em fwi_readings (média = fwi_value, que define a classe; máximo
= "pior ponto"). Datas futuras são previsão: o upsert as sobrescreve até a data passar, e o
dia anterior é recoletado para fechar o valor com a última rodada.
RNF01: cada execução fica registrada em collection_runs com job = "fwi".
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ignis.collectors.fwi.provider import FwiGrid, FwiProvider, classify
from ignis.db.models import CollectionRun, FwiReading, Region, RunStatus

logger = logging.getLogger("ignis.collector.fwi")

# Pertença espacial com o mesmo critério dos focos (ST_Intersects no polígono da região).
AGGREGATE_SQL = text("""
    SELECT count(*), avg(p.v), max(p.v)
    FROM regions r,
         unnest(CAST(:lons AS float8[]), CAST(:lats AS float8[]), CAST(:vals AS float8[])) AS p(lon, lat, v)
    WHERE r.id = :region_id
      AND ST_Intersects(r.geom, ST_SetSRID(ST_MakePoint(p.lon, p.lat), 4326))
    """)


def dates_to_collect(today: date, days_back: int, days_ahead: int) -> list[date]:
    """De `today - days_back` a `today + days_ahead`, inclusive."""
    return [today + timedelta(days=offset) for offset in range(-days_back, days_ahead + 1)]


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


@dataclass
class FwiCycleResult:
    run_id: int
    status: RunStatus
    readings: int = 0
    details: list[dict] = field(default_factory=list)


class FwiCollector:
    def __init__(
        self,
        session_scope: Callable[[], AbstractContextManager[Session]],
        provider: FwiProvider,
        days_back: int = 1,
        days_ahead: int = 3,
        today: Callable[[], date] = _utc_today,
    ):
        self.session_scope = session_scope
        self.provider = provider
        self.days_back = days_back
        self.days_ahead = days_ahead
        self.today = today

    def run_cycle(self, backfill_days: int | None = None) -> FwiCycleResult:
        """Um ciclo completo. `backfill_days` coleta só os últimos N dias (sem previsão)."""
        if backfill_days:
            dates = dates_to_collect(self.today(), backfill_days - 1, 0)
        else:
            dates = dates_to_collect(self.today(), self.days_back, self.days_ahead)

        with self.session_scope() as session:
            run = CollectionRun(job="fwi", status=RunStatus.RUNNING, details={})
            session.add(run)
            session.flush()
            result = FwiCycleResult(run_id=run.id, status=RunStatus.RUNNING)

        try:
            with self.session_scope() as session:
                regions = list(session.scalars(select(Region).where(Region.active).order_by(Region.id)))
        except Exception as exc:  # banco fora: registra e encerra
            logger.exception("Falha ao carregar regiões")
            return self._finish(result, RunStatus.FAILED, error=str(exc))

        errors = 0
        for region in regions:
            for day in dates:
                item = {"region": region.slug, "date": day.isoformat()}
                try:
                    grid = self.provider.fetch(region.west, region.south, region.east, region.north, day)
                    item.update(self._store(region, day, grid))
                    if not item.get("skipped"):
                        result.readings += 1
                except Exception as exc:  # uma região/data com erro não derruba as demais
                    errors += 1
                    item["error"] = f"{type(exc).__name__}: {exc}"[:500]
                    logger.warning("Falha no FWI de %s em %s: %s", region.slug, day, item["error"])
                result.details.append(item)

        total = len(result.details)
        if total and errors == total:
            status = RunStatus.FAILED
        elif errors:
            status = RunStatus.PARTIAL
        else:
            status = RunStatus.SUCCESS
        return self._finish(result, status)

    def _store(self, region: Region, day: date, grid: FwiGrid) -> dict:
        lons, lats, vals = grid.valid_cells()
        if not len(vals):
            return {"skipped": "sem pixels com dado (fora do horizonte de previsão ou só mar)"}

        with self.session_scope() as session:
            count, mean, peak = session.execute(
                AGGREGATE_SQL,
                {"region_id": region.id, "lons": lons.tolist(), "lats": lats.tolist(), "vals": vals.tolist()},
            ).one()
            if not count:
                return {"skipped": "nenhum pixel com dado dentro do polígono da região"}

            row = {
                "region_id": region.id,
                "date": day,
                "fwi_value": mean,
                "fwi_max": peak,
                "pixel_count": count,
                "danger_class": classify(mean),
                "provider": self.provider.name,
            }
            stmt = insert(FwiReading).values(row)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_fwi_region_date_provider",
                set_={
                    "fwi_value": stmt.excluded.fwi_value,
                    "fwi_max": stmt.excluded.fwi_max,
                    "pixel_count": stmt.excluded.pixel_count,
                    "danger_class": stmt.excluded.danger_class,
                    "fetched_at": func.now(),
                },
            )
            session.execute(stmt)
        return {"pixels": count, "fwi": round(mean, 2), "fwi_max": round(peak, 2)}

    def _finish(self, result: FwiCycleResult, status: RunStatus, error: str | None = None) -> FwiCycleResult:
        result.status = status
        with self.session_scope() as session:
            run = session.get(CollectionRun, result.run_id)
            run.finished_at = datetime.now(timezone.utc)
            run.status = status
            run.fetched_rows = result.readings
            run.details = {"items": result.details, "provider": self.provider.name}
            run.error = error
        logger.info(
            "Ciclo FWI #%d: %s | %d leituras | %d itens",
            result.run_id,
            status.value,
            result.readings,
            len(result.details),
        )
        return result
