"""Geração de relatórios (RF11) e do boletim diário (RF07).

Fluxo: JSON de entrada → cache por `input_hash` → LLM (com 1 regeneração se a validação reprovar)
→ fallback por template. O sistema nunca fica sem texto; o motivo do fallback vai em `validation`.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ignis.db.models import AiReport, Bulletin, Region, ReportGenerator, ReportKind
from ignis.reports.llm import LlmError, LlmProvider
from ignis.reports.payload import build_report_input, input_hash
from ignis.reports.template import notice, render_template
from ignis.reports.validation import validate_numbers

logger = logging.getLogger("ignis.reports")

MAX_ATTEMPTS = 2
# relatório por template de um hash recente é reaproveitado por este tempo (não martela uma API fora do ar)
TEMPLATE_RETRY_AFTER = timedelta(minutes=15)

SYSTEM_PROMPT = """\
Você é redator de boletins de situação sobre incêndios florestais para o público leigo.

Regras obrigatórias:
1. Use SOMENTE os números que estão no JSON fornecido. Não estime, não calcule valores novos, não
   arredonde de forma diferente e não acrescente dados externos.
2. Cite o período analisado e as fontes (NASA FIRMS e EFFIS).
3. Escreva em português do Brasil, com frases curtas e sem jargão. Explique FRP como "intensidade do
   fogo" e FWI como "risco de incêndio pelas condições do tempo".
4. Estrutura: Resumo (2 frases), Onde está o fogo, Evolução, Risco nos próximos dias, Alertas.
   Se uma seção não tiver dados no JSON, escreva que não há dados em vez de inventar.
5. Focos de calor detectados por satélite não são, necessariamente, incêndios confirmados: pode haver
   queimadas agrícolas e fontes industriais.
6. Não dê ordens de evacuação; oriente a seguir as orientações da defesa civil local.
7. Escreva só o boletim, sem comentários sobre estas instruções. Use texto simples (sem tabelas).
8. Formato: datas por extenso ("16 de outubro"), nunca no formato 2026-10-16; números decimais com
   vírgula ("14,7%") e milhar com ponto ("1.284"); níveis de risco em português.
9. Nunca cite nomes de campos, chaves ou a palavra "JSON". Se faltar um dado, diga "não há dados
   sobre isso neste período". Para coordenadas, diga "perto da latitude X e longitude Y".
"""


@dataclass
class Composed:
    text: str
    generator: ReportGenerator
    model: str | None
    validation: dict
    usage: dict


def _user_message(payload: dict) -> str:
    return "Dados do período (JSON):\n" + json.dumps(payload, ensure_ascii=False, indent=2)


def compose_report(payload: dict, provider: LlmProvider | None) -> Composed:
    """Sem acesso a banco: tenta o LLM e valida; senão, template. Fácil de testar."""
    validation: dict = {"attempts": 0}
    if provider is None:
        validation["fallback_reason"] = "llm_not_configured"
    else:
        user = _user_message(payload)
        for attempt in range(1, MAX_ATTEMPTS + 1):
            validation["attempts"] = attempt
            try:
                result = provider.generate(SYSTEM_PROMPT, user)
            except LlmError as exc:
                logger.warning("LLM indisponível: %s", exc)
                validation["fallback_reason"] = "llm_error"
                validation["error"] = str(exc)
                break  # falha de rede/cota: repetir não ajuda agora
            check = validate_numbers(result.text, payload)
            validation["numbers"] = check.to_dict()
            if check.ok:
                text = result.text
                if "gerado por ia" not in text.lower():
                    text = f"{text}\n\n{notice('llm', payload)}"
                validation.pop("fallback_reason", None)
                return Composed(text, ReportGenerator.LLM, result.model, validation, result.usage)
            logger.warning("números não conferem (tentativa %d): %s", attempt, check.unmatched)
            validation["fallback_reason"] = "validation_failed"

    return Composed(render_template(payload), ReportGenerator.TEMPLATE, None, validation, {})


@dataclass
class ReportResult:
    report: AiReport
    cached: bool


def _find_cached(session: Session, digest: str, now: datetime) -> AiReport | None:
    llm = session.scalar(
        select(AiReport)
        .where(AiReport.input_hash == digest, AiReport.generator == ReportGenerator.LLM)
        .order_by(AiReport.id.desc())
        .limit(1)
    )
    if llm:
        return llm
    return session.scalar(
        select(AiReport)
        .where(
            AiReport.input_hash == digest,
            AiReport.generator == ReportGenerator.TEMPLATE,
            AiReport.created_at >= now - TEMPLATE_RETRY_AFTER,
        )
        .order_by(AiReport.id.desc())
        .limit(1)
    )


def _utc(day: date, end_of_day: bool = False) -> datetime:
    return datetime.combine(day + timedelta(days=1) if end_of_day else day, time.min, tzinfo=timezone.utc)


def generate_report(
    session: Session,
    region: Region,
    start: date,
    end: date,
    *,
    kind: ReportKind,
    provider: LlmProvider | None,
    now: datetime | None = None,
) -> ReportResult:
    now = now or datetime.now(timezone.utc)
    payload = build_report_input(session, region, start, end)
    digest = input_hash(payload)

    cached = _find_cached(session, digest, now)
    if cached:
        return ReportResult(cached, True)

    composed = compose_report(payload, provider)
    report = AiReport(
        kind=kind,
        region_id=region.id,
        period_start=_utc(start),
        period_end=_utc(end, end_of_day=True),
        input_json=payload,
        input_hash=digest,
        output_text=composed.text,
        generator=composed.generator,
        model=composed.model,
        validation=composed.validation,
        usage=composed.usage,
    )
    session.add(report)
    session.flush()
    return ReportResult(report, False)


def publish_daily_bulletin(
    session: Session, region: Region, provider: LlmProvider | None, today: date | None = None
) -> Bulletin | None:
    """Um boletim por região por dia (RF07): os 7 dias completos até ontem. Idempotente:
    se já existe o boletim de hoje, não gera de novo (não gasta a cota da IA)."""
    today = today or datetime.now(timezone.utc).date()
    existing = session.scalar(select(Bulletin).where(Bulletin.date == today, Bulletin.region_id == region.id))
    if existing:
        return None
    end = today - timedelta(days=1)
    result = generate_report(
        session, region, end - timedelta(days=6), end, kind=ReportKind.DAILY_BULLETIN, provider=provider
    )
    stmt = (
        pg_insert(Bulletin)
        .values(date=today, region_id=region.id, report_id=result.report.id)
        .on_conflict_do_nothing(constraint="uq_bulletins_date_region")
        .returning(Bulletin.id)
    )
    session.execute(stmt)
    return session.scalar(select(Bulletin).where(Bulletin.date == today, Bulletin.region_id == region.id))
