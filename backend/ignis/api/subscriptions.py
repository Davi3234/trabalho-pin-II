"""Assinatura de alertas por e-mail (RNF04, LGPD/GDPR).

- Só o mínimo: e-mail + regiões de interesse; consentimento explícito com data e versão do termo.
- Double opt-in: nada é enviado antes de o link de confirmação ser aberto (vale CONFIRM_TOKEN_HOURS).
- Descadastro em toda mensagem (link assinado por HMAC) e exclusão definitiva dos dados.
- Respostas não revelam se um e-mail já estava cadastrado; e-mails nunca vão para log.
"""

from __future__ import annotations

import html
import re
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ignis.alerts.messages import confirmation_email
from ignis.alerts.tokens import (
    SubscriptionsDisabled,
    ensure_enabled,
    hash_token,
    new_confirm_token,
    verify_manage_token,
)
from ignis.config import Settings, get_settings
from ignis.db.models import Region, Subscriber, SubscriberStatus
from ignis.db.session import get_session
from ignis.notifications.mailer import EmailSendError, SmtpEmailSender, build_sender

router = APIRouter(tags=["assinaturas"])

_EMAIL = re.compile(r"^[^\s@<>,;\"]+@[^\s@<>,;\"]+\.[^\s@<>,;\"]+$")

PRIVACY_TEXT = (
    "O IGNIS guarda apenas o seu e-mail e as regiões que você escolheu, para enviar alertas de incêndios "
    "florestais. Registramos a data do seu consentimento e a versão deste termo. Só enviamos e-mails depois "
    "que você confirma a inscrição. Todo e-mail traz um link para cancelar e para apagar definitivamente os "
    "seus dados. Não compartilhamos seu e-mail e não o escrevemos em registros (logs) do sistema."
)


class SubscribeRequest(BaseModel):
    email: str = Field(max_length=254)
    regions: list[str] = Field(min_length=1, max_length=20)
    consent: bool = Field(description="o usuário aceitou o termo de privacidade")

    @field_validator("email")
    @classmethod
    def _valid_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not _EMAIL.match(value):
            raise ValueError("e-mail inválido")
        return value

    @field_validator("consent")
    @classmethod
    def _consent_required(cls, value: bool) -> bool:
        if not value:
            raise ValueError("é preciso aceitar o termo de privacidade")
        return value


class ManageRequest(BaseModel):
    id: uuid.UUID
    token: str


def get_email_sender() -> SmtpEmailSender | None:
    """Dependência separada para os testes trocarem o remetente."""
    return build_sender(get_settings())


def _page(title: str, body: str, code: int = 200, script: str = "") -> HTMLResponse:
    doc = (
        '<!doctype html><html lang="pt-BR"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{html.escape(title)}</title>"
        '<body style="font-family:system-ui,sans-serif;max-width:34rem;margin:3rem auto;padding:0 1rem;line-height:1.5">'  # noqa: E501
        f"<h1>{html.escape(title)}</h1>{body}{script}</body></html>"
    )
    return HTMLResponse(doc, status_code=code, headers={"Cache-Control": "no-store"})


@router.get("/privacy")
def privacy(response: Response, settings: Settings = Depends(get_settings)) -> dict:
    """Política de privacidade da assinatura e se a inscrição está disponível (o portal lê daqui)."""
    try:
        ensure_enabled(settings)
        has_secret = True
    except SubscriptionsDisabled:
        has_secret = False
    response.headers["Cache-Control"] = "public, max-age=300"
    return {
        "terms_version": settings.terms_version,
        "text": PRIVACY_TEXT,
        "subscriptions_enabled": has_secret and build_sender(settings) is not None,
    }


@router.post("/subscriptions", status_code=status.HTTP_202_ACCEPTED)
def subscribe(
    body: SubscribeRequest,
    session: Session = Depends(get_session),
    sender: SmtpEmailSender | None = Depends(get_email_sender),
    settings: Settings = Depends(get_settings),
) -> dict:
    if sender is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "o envio de e-mails está desativado")
    try:
        ensure_enabled(settings)
    except SubscriptionsDisabled:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "assinaturas indisponíveis") from None

    regions = session.scalars(select(Region).where(Region.slug.in_(body.regions), Region.active)).all()
    if len(regions) != len(set(body.regions)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "região desconhecida")

    now = datetime.now(timezone.utc)
    sub = session.scalar(select(Subscriber).where(Subscriber.email == body.email))
    needs_confirmation = True
    token, token_hash = new_confirm_token()
    if sub is None:
        sub = Subscriber(email=body.email, status=SubscriberStatus.PENDING)
        session.add(sub)
    elif sub.status == SubscriberStatus.CONFIRMED:
        needs_confirmation = False  # já inscrito: não revelamos isso na resposta
    sub.regions = list(regions) if needs_confirmation else sub.regions
    if needs_confirmation:
        sub.status = SubscriberStatus.PENDING
        sub.consent_at = now
        sub.consent_terms_version = settings.terms_version
        sub.confirm_token_hash = token_hash
        sub.confirmed_at = None
    session.flush()

    if needs_confirmation:
        try:
            sender.send(
                confirmation_email(
                    settings, to=sub.email, token=token, region_names=[r.name for r in regions]
                )
            )
        except EmailSendError:
            session.rollback()
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, "não foi possível enviar o e-mail de confirmação agora"
            ) from None
    session.commit()
    return {"message": "Se o endereço for válido, você receberá um e-mail para confirmar a inscrição."}


@router.get("/subscriptions/confirm", response_class=HTMLResponse)
def confirm(
    token: str = Query(min_length=10),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    sub = session.scalar(
        select(Subscriber).where(
            Subscriber.confirm_token_hash == hash_token(token), Subscriber.status == SubscriberStatus.PENDING
        )
    )
    expired = sub is not None and sub.consent_at < datetime.now(timezone.utc) - timedelta(
        hours=settings.confirm_token_hours
    )
    if sub is None or expired:
        return _page(
            "Link inválido ou expirado",
            "<p>Este link de confirmação não vale mais. Faça a inscrição de novo no portal do IGNIS.</p>",
            code=400,
        )
    sub.status = SubscriberStatus.CONFIRMED
    sub.confirmed_at = datetime.now(timezone.utc)
    sub.confirm_token_hash = None
    session.commit()
    return _page(
        "Inscrição confirmada", "<p>Pronto! Você passará a receber os alertas das regiões escolhidas.</p>"
    )


def _subscriber_or_404(session: Session, sub_id: uuid.UUID, token: str, settings: Settings) -> Subscriber:
    try:
        valid = verify_manage_token(sub_id, token, settings)
    except SubscriptionsDisabled:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "assinaturas indisponíveis") from None
    sub = session.get(Subscriber, sub_id) if valid else None
    if sub is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "link inválido")
    return sub


@router.get("/subscriptions/unsubscribe", response_class=HTMLResponse)
def unsubscribe_page(
    id: uuid.UUID,
    token: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    """Link do e-mail: descadastra na hora e oferece apagar os dados de vez."""
    try:
        sub = _subscriber_or_404(session, id, token, settings)
    except HTTPException as exc:
        return _page("Link inválido", "<p>Não foi possível usar este link.</p>", code=exc.status_code)
    sub.status = SubscriberStatus.UNSUBSCRIBED
    sub.confirm_token_hash = None
    session.commit()
    script = (
        "<script>async function apagar(){const r=await fetch('/api/subscriptions/delete',{method:'POST',"
        "headers:{'Content-Type':'application/json'},body:JSON.stringify({id:%s,token:%s})});"
        "document.getElementById('msg').textContent=r.ok?'Seus dados foram apagados.':'Não foi possível apagar agora.';}"  # noqa: E501
        "</script>"
    ) % (repr(str(id)).replace("'", '"'), repr(token).replace("'", '"'))
    return _page(
        "Inscrição cancelada",
        "<p>Você não receberá mais alertas do IGNIS.</p>"
        "<p>Se preferir, apague também seus dados (e-mail e regiões) de forma definitiva:</p>"
        '<button onclick="apagar()">Apagar meus dados</button><p id="msg"></p>',
        script=script,
    )


@router.post("/subscriptions/unsubscribe")
def unsubscribe_one_click(
    id: uuid.UUID,
    token: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Descadastro em um clique (List-Unsubscribe-Post, usado por Gmail e similares)."""
    sub = _subscriber_or_404(session, id, token, settings)
    sub.status = SubscriberStatus.UNSUBSCRIBED
    sub.confirm_token_hash = None
    session.commit()
    return {"status": "unsubscribed"}


@router.post("/subscriptions/delete")
def delete_subscription(
    body: ManageRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Exclusão definitiva dos dados do assinante (direito ao apagamento)."""
    sub = _subscriber_or_404(session, body.id, body.token, settings)
    session.delete(sub)  # as linhas de subscriber_regions saem em cascata
    session.commit()
    return {"status": "deleted"}
