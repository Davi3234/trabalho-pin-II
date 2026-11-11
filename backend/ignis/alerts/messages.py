"""Textos dos e-mails de alerta e de confirmação (português, para leigos)."""

from __future__ import annotations

import html
import uuid

from ignis.alerts.tokens import manage_token
from ignis.config import Settings
from ignis.db.models import AlertMetric
from ignis.notifications.mailer import EmailMessageData

METRIC_LABEL = {
    AlertMetric.COUNT: "focos de calor",
    AlertMetric.FRP_SUM: "intensidade somada do fogo (FRP, em MW)",
    AlertMetric.FRP_MAX: "maior intensidade de fogo num único foco (FRP, em MW)",
}

DISCLAIMER = (
    "Os focos são detectados por satélite (NASA FIRMS) e não confirmam, por si só, um incêndio: pode haver "
    "queimadas agrícolas e fontes industriais. Em caso de emergência, siga as orientações da defesa civil local."  # noqa: E501
)


def manage_url(settings: Settings, subscriber_id: uuid.UUID, action: str) -> str:
    base = settings.public_base_url.rstrip("/")
    return (
        f"{base}/api/subscriptions/{action}?id={subscriber_id}&token={manage_token(subscriber_id, settings)}"
    )


def _fmt(value: float) -> str:
    return f"{value:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".").removesuffix(",0")


def alert_email(
    settings: Settings,
    *,
    to: str,
    subscriber_id: uuid.UUID,
    rule_name: str,
    region_name: str,
    metric: AlertMetric,
    value: float,
    threshold: float,
    window_hours: int,
) -> EmailMessageData:
    unsubscribe = manage_url(settings, subscriber_id, "unsubscribe")
    portal = settings.public_base_url.rstrip("/")
    what = METRIC_LABEL[metric]
    summary = (
        f"Nas últimas {window_hours} horas foram medidos {_fmt(value)} ({what}) em {region_name}, "
        f"acima do limite de {_fmt(threshold)} definido para este alerta."
    )
    text = (
        f"IGNIS — Alerta: {rule_name}\n\n{summary}\n\nVeja o mapa e o boletim: {portal}\n\n{DISCLAIMER}\n\n"
        f"Você recebe este e-mail porque se inscreveu nos alertas do IGNIS.\n"
        f"Para deixar de receber (e, se quiser, apagar seus dados): {unsubscribe}\n"
    )
    body_html = (
        f"<h2>IGNIS — Alerta: {html.escape(rule_name)}</h2><p>{html.escape(summary)}</p>"
        f'<p><a href="{html.escape(portal)}">Ver o mapa e o boletim</a></p>'
        f"<p><small>{html.escape(DISCLAIMER)}</small></p><hr>"
        f"<p><small>Você recebe este e-mail porque se inscreveu nos alertas do IGNIS. "
        f'<a href="{html.escape(unsubscribe)}">Cancelar inscrição e apagar meus dados</a></small></p>'
    )
    return EmailMessageData(
        to=to,
        subject=f"[IGNIS] Alerta: {rule_name} — {region_name}",
        text=text,
        html=body_html,
        headers={
            "List-Unsubscribe": f"<{unsubscribe}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        },
    )


def confirmation_email(
    settings: Settings, *, to: str, token: str, region_names: list[str]
) -> EmailMessageData:
    base = settings.public_base_url.rstrip("/")
    link = f"{base}/api/subscriptions/confirm?token={token}"
    regions = ", ".join(region_names)
    text = (
        "Olá! Alguém (esperamos que você) pediu para receber alertas de incêndios florestais do IGNIS "
        f"para: {regions}.\n\nPara confirmar, abra o link (vale {settings.confirm_token_hours} horas):\n{link}\n\n"  # noqa: E501
        "Se não foi você, ignore este e-mail: nada será enviado sem a confirmação."
    )
    body_html = (
        f"<p>Olá! Alguém (esperamos que você) pediu para receber alertas de incêndios florestais do IGNIS para: "  # noqa: E501
        f"<b>{html.escape(regions)}</b>.</p>"
        f'<p><a href="{html.escape(link)}">Confirmar minha inscrição</a> (vale {settings.confirm_token_hours} horas)</p>'  # noqa: E501
        "<p><small>Se não foi você, ignore este e-mail: nada será enviado sem a confirmação.</small></p>"
    )
    return EmailMessageData(
        to=to, subject="[IGNIS] Confirme sua inscrição nos alertas", text=text, html=body_html
    )
