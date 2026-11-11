"""Envio de e-mail por SMTP (RF06), só com a biblioteca padrão.

Regras de projeto:
- RNF04: o endereço do destinatário nunca vai para log nem para mensagens de erro (só mascarado).
- Sem injeção de cabeçalho: quebras de linha em destinatário, assunto ou cabeçalhos são rejeitadas.
- Credenciais só trafegam com TLS (STARTTLS ou SSL); `none` é para relay local sem login (Mailpit).
- `EmailSendError.permanent` separa falha definitiva (endereço recusado) de transitória (rede, 4xx),
  para o motor de alertas decidir se tenta de novo.
"""

from __future__ import annotations

import logging
import re
import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

from ignis.config import Settings

logger = logging.getLogger("ignis.notifications")

_ADDRESS = re.compile(r"^[^\s@<>,;\"]+@[^\s@<>,;\"]+\.[^\s@<>,;\"]+$|^[^\s@<>,;\"]+@localhost$")


class EmailSendError(Exception):
    """Falha ao enviar. Nunca carrega o endereço do destinatário nem credenciais."""

    def __init__(self, message: str, *, permanent: bool = False):
        super().__init__(message)
        self.permanent = permanent


class EmailNotConfigured(EmailSendError):
    """SMTP desligado ou configuração inválida."""


@dataclass(frozen=True)
class EmailMessageData:
    to: str
    subject: str
    text: str
    html: str | None = None
    headers: dict[str, str] = field(default_factory=dict)  # ex.: List-Unsubscribe


def mask_email(address: str) -> str:
    """`pessoa@dominio.com` → `p***@dominio.com` (para logs); entradas inválidas viram `***`."""
    local, sep, domain = address.partition("@")
    if not sep or not local or not domain:
        return "***"
    return f"{local[0]}***@{domain}"


def _has_newline(value: str) -> bool:
    return "\r" in value or "\n" in value


class SmtpEmailSender:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        security: str,
        from_address: str,
        from_name: str,
        timeout: int,
    ):
        if security not in ("starttls", "ssl", "none"):
            raise EmailNotConfigured("SMTP_SECURITY deve ser starttls, ssl ou none")
        if security == "none" and (username or password):
            raise EmailNotConfigured("não envie usuário/senha sem TLS: use SMTP_SECURITY=starttls ou ssl")
        if not _ADDRESS.match(from_address) or _has_newline(from_name):
            raise EmailNotConfigured("SMTP_FROM inválido")
        self._host, self._port = host, port
        self._username, self._password = username, password
        self._security = security
        self._from_address, self._from_name = from_address, from_name
        self._timeout = timeout

    def __repr__(self) -> str:  # sem a senha
        return f"SmtpEmailSender(host={self._host!r}, port={self._port}, security={self._security!r})"

    @classmethod
    def from_settings(cls, settings: Settings) -> SmtpEmailSender:
        if not settings.smtp_host or not settings.smtp_from:
            raise EmailNotConfigured("defina SMTP_HOST e SMTP_FROM para enviar e-mails")
        return cls(
            host=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username,
            password=settings.smtp_password.get_secret_value() if settings.smtp_password else None,
            security=settings.smtp_security,
            from_address=settings.smtp_from,
            from_name=settings.smtp_from_name,
            timeout=settings.smtp_timeout_seconds,
        )

    def _build(self, data: EmailMessageData) -> EmailMessage:
        if not _ADDRESS.match(data.to) or _has_newline(data.to):
            raise EmailSendError("destinatário inválido", permanent=True)
        if _has_newline(data.subject):
            raise EmailSendError("assunto com quebra de linha")
        for name, value in data.headers.items():
            if _has_newline(name) or _has_newline(value):
                raise EmailSendError("cabeçalho com quebra de linha")

        msg = EmailMessage()
        msg["From"] = formataddr((self._from_name, self._from_address))
        msg["To"] = data.to
        msg["Subject"] = data.subject
        msg["Date"] = formatdate(localtime=False)
        msg["Message-ID"] = make_msgid(domain=self._from_address.rpartition("@")[2])
        for name, value in data.headers.items():
            msg[name] = value
        msg.set_content(data.text)
        if data.html:
            msg.add_alternative(data.html, subtype="html")
        return msg

    def send(self, data: EmailMessageData) -> None:
        msg = self._build(data)
        masked = mask_email(data.to)
        try:
            if self._security == "ssl":
                conn = smtplib.SMTP_SSL(
                    self._host, self._port, timeout=self._timeout, context=ssl.create_default_context()
                )
            else:
                conn = smtplib.SMTP(self._host, self._port, timeout=self._timeout)
            with conn:
                conn.ehlo()
                if self._security == "starttls":
                    conn.starttls(context=ssl.create_default_context())
                    conn.ehlo()
                if self._username:
                    conn.login(self._username, self._password or "")
                conn.send_message(msg)
        except smtplib.SMTPAuthenticationError as exc:
            # problema nosso (credenciais), não do destinatário: não marcar como definitivo
            raise EmailSendError(f"autenticação SMTP recusada (código {exc.smtp_code})") from None
        except smtplib.SMTPRecipientsRefused:
            logger.warning("SMTP recusou o destinatário %s", masked)
            raise EmailSendError("destinatário recusado pelo servidor SMTP", permanent=True) from None
        except smtplib.SMTPResponseException as exc:
            logger.warning("SMTP respondeu %s ao enviar para %s", exc.smtp_code, masked)
            raise EmailSendError(
                f"servidor SMTP respondeu {exc.smtp_code}", permanent=500 <= exc.smtp_code < 600
            ) from None
        except (smtplib.SMTPException, OSError) as exc:
            logger.warning("falha de rede/SMTP ao enviar para %s: %s", masked, type(exc).__name__)
            raise EmailSendError(f"falha de conexão SMTP ({type(exc).__name__})") from None
        logger.info("e-mail enviado para %s", masked)


def build_sender(settings: Settings) -> SmtpEmailSender | None:
    """Remetente do sistema, ou None se o e-mail está desligado (EMAIL_ENABLED=false) ou sem SMTP_*."""
    if not settings.email_enabled:
        return None
    try:
        return SmtpEmailSender.from_settings(settings)
    except EmailNotConfigured as exc:
        logger.warning("EMAIL_ENABLED=true, mas o SMTP não está utilizável: %s", exc)
        return None
