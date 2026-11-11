"""Remetente SMTP (etapa 5, RF06/RNF04). Nenhum teste abre conexão real: smtplib é substituído."""

import logging
import smtplib

import pytest

from ignis.config import Settings
from ignis.notifications import mailer as email_mod
from ignis.notifications.mailer import (
    EmailMessageData,
    EmailNotConfigured,
    EmailSendError,
    SmtpEmailSender,
    build_sender,
    mask_email,
)


class FakeSMTP:
    """Registra o que o remetente faz; `instances` guarda cada conexão aberta."""

    instances: list["FakeSMTP"] = []
    fail_with: Exception | None = None

    def __init__(self, host, port, timeout=None, context=None):
        self.host, self.port, self.timeout, self.context = host, port, timeout, context
        self.calls: list[str] = []
        self.sent = []
        FakeSMTP.instances.append(self)
        if FakeSMTP.fail_with and isinstance(FakeSMTP.fail_with, OSError):
            raise FakeSMTP.fail_with

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def ehlo(self):
        self.calls.append("ehlo")

    def starttls(self, context=None):
        self.calls.append("starttls")
        self.context = context

    def login(self, user, password):
        self.calls.append(f"login:{user}")

    def send_message(self, msg):
        if FakeSMTP.fail_with:
            raise FakeSMTP.fail_with
        self.calls.append("send")
        self.sent.append(msg)


@pytest.fixture(autouse=True)
def fake_smtp(monkeypatch):
    FakeSMTP.instances = []
    FakeSMTP.fail_with = None
    monkeypatch.setattr(email_mod.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(email_mod.smtplib, "SMTP_SSL", FakeSMTP)
    return FakeSMTP


def make_sender(**over) -> SmtpEmailSender:
    base = dict(
        host="smtp.exemplo.org",
        port=587,
        username="usuario",
        password="segredo",
        security="starttls",
        from_address="alertas@ignis.exemplo.org",
        from_name="IGNIS",
        timeout=5,
    )
    base.update(over)
    return SmtpEmailSender(**base)


def message(**over) -> EmailMessageData:
    base = dict(to="pessoa@exemplo.com", subject="Alerta IGNIS", text="Corpo em texto.")
    base.update(over)
    return EmailMessageData(**base)


def test_starttls_flow_authenticates_and_sends():
    make_sender().send(message())
    conn = FakeSMTP.instances[0]
    assert (conn.host, conn.port, conn.timeout) == ("smtp.exemplo.org", 587, 5)
    assert conn.calls == ["ehlo", "starttls", "ehlo", "login:usuario", "send"]
    assert conn.context is not None  # contexto TLS com verificação de certificado


def test_message_headers_and_bodies():
    html = "<p>Corpo <b>HTML</b></p>"
    make_sender().send(message(html=html, headers={"List-Unsubscribe": "<https://ignis.exemplo.org/u/abc>"}))
    msg = FakeSMTP.instances[0].sent[0]
    assert msg["To"] == "pessoa@exemplo.com"
    assert msg["From"] == "IGNIS <alertas@ignis.exemplo.org>"
    assert msg["Subject"] == "Alerta IGNIS"
    assert msg["List-Unsubscribe"] == "<https://ignis.exemplo.org/u/abc>"
    assert msg["Message-ID"] and msg["Date"]
    assert msg.get_body(("plain",)).get_content().strip() == "Corpo em texto."
    assert "HTML" in msg.get_body(("html",)).get_content()


def test_accented_subject_and_name_survive():
    make_sender(from_name="Alertas IGNIS — incêndios").send(message(subject="Alerta: Grécia — nível crítico"))
    msg = FakeSMTP.instances[0].sent[0]
    assert msg["Subject"] == "Alerta: Grécia — nível crítico"


def test_implicit_ssl_does_not_call_starttls():
    make_sender(port=465, security="ssl").send(message())
    assert FakeSMTP.instances[0].calls == ["ehlo", "login:usuario", "send"]


def test_no_auth_for_local_relay_like_mailpit():
    make_sender(host="mailpit", port=1025, security="none", username=None, password=None).send(message())
    assert FakeSMTP.instances[0].calls == ["ehlo", "send"]


def test_credentials_over_plaintext_are_refused():
    with pytest.raises(EmailNotConfigured):
        make_sender(security="none")  # usuário/senha sem TLS


@pytest.mark.parametrize("field", ["to", "subject"])
def test_header_injection_is_rejected(field):
    with pytest.raises(EmailSendError):
        make_sender().send(message(**{field: "x@exemplo.com\nBcc: outro@exemplo.com"}))
    assert FakeSMTP.instances == []  # nem chegou a conectar


def test_custom_header_injection_is_rejected():
    with pytest.raises(EmailSendError):
        make_sender().send(message(headers={"X-Teste": "a\r\nBcc: outro@exemplo.com"}))


@pytest.mark.parametrize("bad", ["", "sem-arroba", "a@", "@b.com", "a b@c.com"])
def test_invalid_recipient_is_rejected(bad):
    with pytest.raises(EmailSendError):
        make_sender().send(message(to=bad))


def test_connection_failure_is_transient():
    FakeSMTP.fail_with = ConnectionRefusedError("recusada")
    with pytest.raises(EmailSendError) as exc:
        make_sender().send(message())
    assert exc.value.permanent is False


def test_recipient_refused_is_permanent():
    FakeSMTP.fail_with = smtplib.SMTPRecipientsRefused({"pessoa@exemplo.com": (550, b"no such user")})
    with pytest.raises(EmailSendError) as exc:
        make_sender().send(message())
    assert exc.value.permanent is True


def test_auth_failure_is_reported_without_credentials():
    FakeSMTP.fail_with = smtplib.SMTPAuthenticationError(535, b"bad credentials")
    with pytest.raises(EmailSendError) as exc:
        make_sender().send(message())
    assert "segredo" not in str(exc.value)


def test_greylist_4xx_is_transient():
    FakeSMTP.fail_with = smtplib.SMTPResponseException(451, b"try later")
    with pytest.raises(EmailSendError) as exc:
        make_sender().send(message())
    assert exc.value.permanent is False


def test_errors_and_logs_never_contain_the_address(caplog):
    FakeSMTP.fail_with = smtplib.SMTPRecipientsRefused({"pessoa@exemplo.com": (550, b"no such user")})
    with caplog.at_level(logging.DEBUG, logger="ignis.notifications"):
        with pytest.raises(EmailSendError) as exc:
            make_sender().send(message())
    assert "pessoa@exemplo.com" not in str(exc.value)
    assert "pessoa@exemplo.com" not in caplog.text


def test_successful_send_logs_only_masked_address(caplog):
    with caplog.at_level(logging.INFO, logger="ignis.notifications"):
        make_sender().send(message())
    assert "pessoa@exemplo.com" not in caplog.text
    assert "p***@exemplo.com" in caplog.text


def test_mask_email():
    assert mask_email("pessoa@exemplo.com") == "p***@exemplo.com"
    assert mask_email("a@b.com") == "a***@b.com"
    assert mask_email("lixo") == "***"


def test_from_settings_requires_host_and_from():
    with pytest.raises(EmailNotConfigured):
        SmtpEmailSender.from_settings(Settings(_env_file=None))
    with pytest.raises(EmailNotConfigured):
        SmtpEmailSender.from_settings(Settings(_env_file=None, smtp_host="smtp.exemplo.org"))


def test_from_settings_builds_sender():
    s = Settings(
        _env_file=None,
        smtp_host="smtp.exemplo.org",
        smtp_username="u",
        smtp_password="p",
        smtp_from="alertas@ignis.exemplo.org",
    )
    sender = SmtpEmailSender.from_settings(s)
    sender.send(message())
    assert FakeSMTP.instances[0].port == 587


def test_password_is_not_in_repr():
    assert "segredo" not in repr(make_sender())


SMTP_OK = dict(
    smtp_host="smtp.exemplo.org", smtp_from="alertas@ignis.exemplo.org", smtp_username="u", smtp_password="p"
)


def test_build_sender_is_off_by_default_even_with_smtp_filled():
    assert build_sender(Settings(_env_file=None, **SMTP_OK)) is None


def test_build_sender_needs_the_switch_and_a_usable_smtp():
    assert build_sender(Settings(_env_file=None, email_enabled=True)) is None  # ligado, mas sem SMTP_*
    assert isinstance(build_sender(Settings(_env_file=None, email_enabled=True, **SMTP_OK)), SmtpEmailSender)
