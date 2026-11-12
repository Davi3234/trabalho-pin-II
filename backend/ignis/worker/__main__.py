"""Worker do IGNIS: agenda a coleta da FIRMS e do FWI (RNF01).

python -m ignis.worker                     # agendado (FIRMS a cada COLLECT_INTERVAL_MINUTES, FWI a cada
                                           # FWI_INTERVAL_HOURS; os dois rodam já ao iniciar)
python -m ignis.worker --once              # um ciclo de cada e sai
python -m ignis.worker --backfill 30       # histórico de focos dos últimos 30 dias (blocos de 5 dias)
python -m ignis.worker --backfill-fwi 30   # histórico do FWI dos últimos 30 dias
python -m ignis.worker --bulletin          # gera já o boletim de hoje (se ainda não existir) e sai
python -m ignis.worker --bulletin-backfill 7  # gera pelo Gemini os boletins dos últimos 7 dias e sai
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.blocking import BlockingScheduler
from sqlalchemy import select

from ignis.alerts.engine import evaluate_rules
from ignis.collectors.firms.service import FirmsCollector
from ignis.collectors.fwi.gwis import GwisWmsProvider
from ignis.collectors.fwi.service import FwiCollector
from ignis.config import get_settings
from ignis.db.models import Region, ReportGenerator
from ignis.db.session import session_scope
from ignis.notifications.mailer import build_sender
from ignis.reports.llm import build_provider
from ignis.reports.service import publish_daily_bulletin

logger = logging.getLogger("ignis.worker")


def build_collector() -> FirmsCollector:
    settings = get_settings()
    if not settings.firms_map_key or settings.firms_map_key == "coloque_sua_chave_aqui":
        logger.error("FIRMS_MAP_KEY não definida no .env — veja docs/guia_map_key_firms.md")
        sys.exit(1)
    return FirmsCollector(session_scope, settings.firms_map_key, settings.firms_source_list)


def build_fwi_collector() -> FwiCollector:
    return FwiCollector(session_scope, GwisWmsProvider(), days_ahead=get_settings().fwi_days_ahead)


def collect_and_alert(collector: FirmsCollector, **kwargs) -> None:
    """Um ciclo de coleta seguido da avaliação das regras de alerta (RF06). Um erro nos alertas
    não derruba o worker nem desfaz a coleta."""
    collector.run_cycle(**kwargs)
    try:
        settings = get_settings()
        sender = build_sender(settings)
        if sender is None:
            logger.info("E-mail desligado (EMAIL_ENABLED): alertas serão gravados, sem e-mail.")
        with session_scope() as session:
            evaluate_rules(session, sender=sender, settings=settings)
    except Exception:
        logger.exception("Falha ao avaliar as regras de alerta.")


def run_daily_bulletins() -> None:
    """Boletim diário (RF07): um por região de BULLETIN_REGIONS. Idempotente e tolerante a falhas:
    um erro numa região não impede as outras, e sem LLM o boletim sai pelo template."""
    settings = get_settings()
    provider = build_provider(settings)
    if provider is None:
        logger.warning("LLM não configurado (LLM_API_KEY): boletins sairão pelo template.")
    for slug in settings.bulletin_region_list:
        try:
            with session_scope() as session:
                region = session.scalar(select(Region).where(Region.slug == slug, Region.active))
                if region is None:
                    logger.error("Boletim: região '%s' não existe ou está inativa.", slug)
                    continue
                bulletin = publish_daily_bulletin(session, region, provider)
                logger.info("Boletim de %s: %s.", slug, "publicado" if bulletin else "já existia para hoje")
        except Exception:
            logger.exception("Falha ao gerar o boletim de '%s'.", slug)


def run_bulletin_backfill(days: int, pause_seconds: float = 15.0) -> None:
    """Gera os boletins dos `days` dias anteriores a hoje (o de hoje é do agendamento normal).

    Exige o LLM configurado e só grava boletim feito pelo Gemini: um boletim por template não é
    gravado, porque a geração é idempotente e ele impediria uma nova tentativa. Se a chamada ao LLM
    falhar (cota, rede), para na hora para não gastar o resto da cota. Pausa entre as chamadas para
    respeitar o limite por minuto da camada gratuita. Rode `--backfill` e `--backfill-fwi` antes."""
    settings = get_settings()
    provider = build_provider(settings)
    if provider is None:
        logger.error("Backfill de boletins exige LLM_API_KEY configurada; nada foi gerado.")
        return
    today = datetime.now(timezone.utc).date()
    made = skipped = 0
    for slug in settings.bulletin_region_list:
        for offset in range(1, days + 1):
            day = today - timedelta(days=offset)
            if offset > 1:
                time.sleep(pause_seconds)
            try:
                with session_scope() as session:
                    region = session.scalar(select(Region).where(Region.slug == slug, Region.active))
                    if region is None:
                        logger.error("Boletim: região '%s' não existe ou está inativa.", slug)
                        return
                    bulletin = publish_daily_bulletin(session, region, provider, today=day)
                    if bulletin is None:
                        logger.info("Boletim de %s em %s: já existia.", slug, day)
                        continue
                    report = bulletin.report
                    if report.generator != ReportGenerator.LLM:
                        reason = (report.validation or {}).get("fallback_reason")
                        session.delete(bulletin)  # sem boletim por template: permite repetir depois
                        skipped += 1
                        logger.warning("Boletim de %s em %s NÃO gravado (template: %s).", slug, day, reason)
                        if reason == "llm_error":
                            logger.error("Chamada ao Gemini falhou (cota/rede?); interrompendo.")
                            session.commit()
                            logger.info("Backfill: %d pelo Gemini, %d descartado(s).", made, skipped)
                            return
                        continue
                    made += 1
                    logger.info("Boletim de %s em %s gerado pelo Gemini.", slug, day)
            except Exception:
                logger.exception("Falha ao gerar o boletim de '%s' em %s.", slug, day)
    logger.info("Backfill: %d gerado(s) pelo Gemini, %d descartado(s).", made, skipped)


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
    group.add_argument(
        "--bulletin", action="store_true", help="Gera o boletim diário de hoje (se não existir) e sai."
    )
    group.add_argument(
        "--bulletin-backfill",
        type=int,
        metavar="DIAS",
        help="Gera pelo Gemini os boletins dos últimos N dias (antes de hoje) e sai.",
    )
    args = parser.parse_args()

    settings = get_settings()

    if args.bulletin:
        run_daily_bulletins()
        return
    if args.bulletin_backfill:
        run_bulletin_backfill(args.bulletin_backfill)
        return

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
        collect_and_alert(collector, day_range=settings.collect_day_range)
        fwi_collector.run_cycle()
        return

    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(
        collect_and_alert,
        "interval",
        args=[collector],
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
    scheduler.add_job(
        run_daily_bulletins,
        "cron",
        hour=settings.bulletin_hour_utc,
        minute=0,
        misfire_grace_time=6 * 3600,
        coalesce=True,
        id="daily_bulletin",
    )
    # se o worker subiu depois da hora do boletim, recupera o de hoje (a função é idempotente)
    scheduler.add_job(run_daily_bulletins, "date", run_date=datetime.now(timezone.utc) + timedelta(minutes=2))
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
