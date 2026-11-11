"""Tokens de assinatura (RNF04).

- Confirmação (double opt-in): token aleatório; só o SHA-256 fica no banco (`confirm_token_hash`).
- Descadastro/exclusão: HMAC-SHA256 do id do assinante com um segredo do servidor. Não precisa de coluna
  extra, vale para sempre e não dá para forjar sem o segredo — requisito para o link em toda mensagem.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid

from ignis.config import Settings


class SubscriptionsDisabled(Exception):
    """Sem SUBSCRIPTION_SECRET/JWT_SECRET não dá para assinar links: as assinaturas ficam desligadas."""


def _key(settings: Settings) -> bytes:
    secret = settings.subscription_secret or settings.jwt_secret
    value = secret.get_secret_value() if secret else ""
    if len(value) < 32:
        raise SubscriptionsDisabled("defina SUBSCRIPTION_SECRET (ou JWT_SECRET) com 32+ caracteres")
    return value.encode()


def ensure_enabled(settings: Settings) -> None:
    """Levanta SubscriptionsDisabled se não há segredo para assinar os links."""
    _key(settings)


def manage_token(subscriber_id: uuid.UUID, settings: Settings) -> str:
    return hmac.new(_key(settings), f"manage:{subscriber_id}".encode(), hashlib.sha256).hexdigest()


def verify_manage_token(subscriber_id: uuid.UUID, token: str, settings: Settings) -> bool:
    return hmac.compare_digest(manage_token(subscriber_id, settings), token or "")


def new_confirm_token() -> tuple[str, str]:
    """(token para o e-mail, hash para o banco)."""
    token = secrets.token_urlsafe(32)
    return token, hash_token(token)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
