"""Relatórios por IA (RF11) e boletins diários (RF07).

Públicos e sem login, então o uso do LLM é limitado por dia (`LLM_MAX_ON_DEMAND_PER_DAY`): acima do
limite, ou sem LLM configurado, a resposta vem do template (e do cache, quando já existe). A chave do
LLM fica só no servidor; o frontend chama esta API, nunca o fornecedor.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ignis.config import get_settings
from ignis.db.models import AiReport, Bulletin, Region, ReportGenerator, ReportKind
from ignis.db.session import get_session
from ignis.reports.llm import LlmProvider, build_provider
from ignis.reports.service import generate_report, llm_calls_today
from ignis.reports.template import notice

router = APIRouter(tags=["relatórios"])

PUBLIC_CACHE = "public, max-age=300"
MAX_DAYS = 31


class ReportRequest(BaseModel):
    region: str = Field("mediterraneo", description="slug da região")
    days: int = Field(7, ge=1, le=MAX_DAYS, description="tamanho do período, em dias")
    until: date | None = Field(None, description="último dia (UTC) do período; vazio = hoje")


def get_llm_provider() -> LlmProvider | None:
    """Dependência separada para os testes trocarem o LLM por um falso."""
    return build_provider(get_settings())


def _region_or_404(session: Session, slug: str) -> Region:
    region = session.scalar(select(Region).where(Region.slug == slug, Region.active))
    if region is None:
        raise HTTPException(status_code=404, detail=f"região '{slug}' não encontrada")
    return region


def report_to_dict(report: AiReport, region: Region | None, *, cached: bool | None = None) -> dict:
    generator = report.generator.value
    body = {
        "id": report.id,
        "kind": report.kind.value,
        "region": region.slug if region else None,
        "region_name": region.name if region else None,
        "period_start": report.period_start.isoformat(),
        "period_end": report.period_end.isoformat(),
        "generated_by": generator,
        "ai_generated": report.generator == ReportGenerator.LLM,
        "model": report.model,
        "text": report.output_text,
        "notice": notice(generator, report.input_json),
        "validation": {
            "numbers_ok": (report.validation.get("numbers") or {}).get("ok"),
            "numbers_checked": (report.validation.get("numbers") or {}).get("checked"),
            "fallback_reason": report.validation.get("fallback_reason"),
        },
        "data": report.input_json,
        "created_at": report.created_at.isoformat(),
    }
    if cached is not None:
        body["cached"] = cached
    return body


@router.post("/reports/ai")
def create_ai_report(
    request: ReportRequest,
    response: Response,
    session: Session = Depends(get_session),
    provider: LlmProvider | None = Depends(get_llm_provider),
) -> dict:
    """Gera (ou reaproveita, por hash dos dados) o relatório da região e do período."""
    region = _region_or_404(session, request.region)
    end = request.until or datetime.now(timezone.utc).date()
    start = end - timedelta(days=request.days - 1)

    quota_exhausted = False
    if provider is not None and llm_calls_today(session) >= get_settings().llm_max_on_demand_per_day:
        provider, quota_exhausted = None, True

    result = generate_report(session, region, start, end, kind=ReportKind.ON_DEMAND, provider=provider)
    session.commit()
    response.headers["Cache-Control"] = "no-store"
    body = report_to_dict(result.report, region, cached=result.cached)
    body["llm_quota_exhausted"] = quota_exhausted
    return body


@router.get("/reports/{report_id}")
def get_report(report_id: int, response: Response, session: Session = Depends(get_session)) -> dict:
    report = session.get(AiReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="relatório não encontrado")
    response.headers["Cache-Control"] = PUBLIC_CACHE
    return report_to_dict(report, session.get(Region, report.region_id) if report.region_id else None)


@router.get("/bulletins")
def list_bulletins(
    response: Response,
    region: str | None = Query(None, description="slug da região; vazio = todas"),
    limit: int = Query(30, ge=1, le=100),
    session: Session = Depends(get_session),
) -> list[dict]:
    stmt = select(Bulletin, Region).join(Region, Region.id == Bulletin.region_id)
    if region:
        stmt = stmt.where(Region.slug == region)
    rows = session.execute(stmt.order_by(Bulletin.date.desc(), Region.id).limit(limit)).all()
    response.headers["Cache-Control"] = PUBLIC_CACHE
    return [
        {
            "date": b.date.isoformat(),
            "region": r.slug,
            "region_name": r.name,
            "report_id": b.report_id,
            "generated_by": b.report.generator.value,
            "published_at": b.published_at.isoformat(),
        }
        for b, r in rows
    ]


@router.get("/bulletins/{day}/{region}")
def get_bulletin(day: date, region: str, response: Response, session: Session = Depends(get_session)) -> dict:
    """Página permanente do boletim de uma data e região."""
    reg = session.scalar(select(Region).where(Region.slug == region))
    bulletin = (
        session.scalar(select(Bulletin).where(Bulletin.date == day, Bulletin.region_id == reg.id))
        if reg
        else None
    )
    if bulletin is None:
        raise HTTPException(status_code=404, detail="boletim não encontrado")
    response.headers["Cache-Control"] = PUBLIC_CACHE
    body = report_to_dict(bulletin.report, reg)
    body["date"] = day.isoformat()
    return body
