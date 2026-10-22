"""Worker do IGNIS: agenda a coleta da FIRMS e do FWI (RNF01).

python -m ignis.worker                     # agendado (FIRMS a cada COLLECT_INTERVAL_MINUTES, FWI a cada
                                           # FWI_INTERVAL_HOURS; os dois rodam já ao iniciar)
python -m ignis.worker --once              # um ciclo de cada e sai
python -m ignis.worker --backfill 30       # histórico de focos dos últimos 30 dias (blocos de 5 dias)
python -m ignis.worker --backfill-fwi 30   # histórico do FWI dos últimos 30 dias
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone

from apscheduler.schedulers.blocking import BlockingScheduler

from ignis.collectors.firms.service import FirmsCollector
from ignis.collectors.fwi.gwis import GwisWmsProvider
from ignis.collectors.fwi.service import FwiCollector
from ignis.config import get_settings
from ignis.db.session import session_scope

logger = logging.getLogger("ignis.worker")


def build_collector() -> FirmsCollector:
    settings = get_settings()
    if not settings.firms_map_key or settings.firms_map_key == "coloque_sua_chave_aqui":
        logger.error("FIRMS_MAP_KEY não definida no .env — veja docs/guia_map_key_firms.md")
        sys.exit(1)
    return FirmsCollector(session_scope, settings.firms_map_key, settings.firms_source_list)


def build_fwi_collector() -> FwiCollector:
    return FwiCollector(session_scope, GwisWmsProvider(), days_ahead=get_settings().fwi_days_ahead)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(description="Worker de coleta do IGNIS.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--once", action="store_true", help="Executa um ciclo de cada coleta e sai.")
    group.add_argument(
        "--backfill", type=int, metavar="DIAS", help="Carrega o histórico de focos dos últimos N dias e sai."
    )
    group.add_argument(
        "--backfill-fwi",
        type=int,
        metavar="DIAS",
        help="Carrega o histórico do FWI dos últimos N dias e sai.",
    )
    args = parser.parse_args()

    settings = get_settings()

    # o FWI não depende da MAP_KEY da FIRMS
    if args.backfill_fwi:
        build_fwi_collector().run_cycle(backfill_days=args.backfill_fwi)
        return

    collector = build_collector()
    fwi_collector = build_fwi_collector()

    if args.backfill:
        collector.run_cycle(days_back=args.backfill)
        return
    if args.once:
        collector.run_cycle(day_range=settings.collect_day_range)
        fwi_collector.run_cycle()
        return

    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(
        collector.run_cycle,
        "interval",
        minutes=settings.collect_interval_minutes,
        kwargs={"day_range": settings.collect_day_range},
        next_run_time=datetime.now(timezone.utc),
        max_instances=1,
        coalesce=True,
        misfire_grace_time=settings.collect_interval_minutes * 60,
        id="firms_collection",
    )
    scheduler.add_job(
        fwi_collector.run_cycle,
        "interval",
        hours=settings.fwi_interval_hours,
        next_run_time=datetime.now(timezone.utc),
        max_instances=1,
        coalesce=True,
        misfire_grace_time=settings.fwi_interval_hours * 3600,
        id="fwi_collection",
    )
    logger.info(
        "Coleta agendada a cada %d min (janela de %d dia(s), sensores: %s); FWI a cada %d h (previsão D+%d).",
        settings.collect_interval_minutes,
        settings.collect_day_range,
        ", ".join(settings.firms_source_list),
        settings.fwi_interval_hours,
        settings.fwi_days_ahead,
    )
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Worker encerrado.")


if __name__ == "__main__":
    main()
