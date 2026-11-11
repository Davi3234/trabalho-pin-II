"""Teste manual do SMTP configurado no .env (o "smoke test" do e-mail).

python -m ignis.notifications --to voce@exemplo.com

Envia uma mensagem de teste usando SMTP_HOST/SMTP_PORT/... do ambiente. Sai com código 0 se o
servidor aceitou a mensagem e 1 se falhou (sem imprimir senha nem o endereço de destino).
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone

from ignis.config import get_settings
from ignis.notifications.mailer import EmailMessageData, EmailSendError, SmtpEmailSender


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Envia um e-mail de teste pelo SMTP do IGNIS")
    parser.add_argument("--to", required=True, help="destinatário do teste")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    settings = get_settings()
    try:
        sender = SmtpEmailSender.from_settings(settings)
        sender.send(
            EmailMessageData(
                to=args.to,
                subject="IGNIS — teste de envio de e-mail",
                text=(
                    "Se você recebeu esta mensagem, o SMTP do IGNIS está configurado corretamente.\n"
                    f"Enviada em {datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC.\n"
                ),
            )
        )
    except EmailSendError as exc:
        print(f"FALHOU: {exc}", file=sys.stderr)
        return 1
    print(f"OK: o servidor {settings.smtp_host}:{settings.smtp_port} aceitou a mensagem.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
