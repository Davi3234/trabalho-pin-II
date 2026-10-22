"""Autenticação da área administrativa: usuário único do .env + JWT HS256 (RF09).

O portal público é aberto; só as rotas sob /api/admin exigem `Authorization: Bearer <token>`.
Sem ADMIN_PASSWORD ou JWT_SECRET no ambiente, o login responde 503 e a área admin fica desligada.
"""

from __future__ import annotations

import hmac
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from ignis.config import Settings, get_settings

ALGORITHM = "HS256"
# PyJWT avisa com chaves HMAC menores que o tamanho do hash (32 bytes para SHA-256)
MIN_SECRET_LENGTH = 32

router = APIRouter(tags=["admin"])
bearer = HTTPBearer(auto_error=False)


class LoginRequest(BaseModel):
    username: str
    password: str


def _secret(settings: Settings) -> str:
    secret = settings.jwt_secret.get_secret_value() if settings.jwt_secret else ""
    if not settings.admin_password or len(secret) < MIN_SECRET_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="área administrativa desligada: defina ADMIN_PASSWORD e JWT_SECRET "
            f"(>= {MIN_SECRET_LENGTH} caracteres)",
        )
    return secret


def create_token(settings: Settings, now: datetime | None = None) -> tuple[str, datetime]:
    now = now or datetime.now(timezone.utc)
    expires = now + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": settings.admin_username, "iat": now, "exp": expires}
    return jwt.encode(payload, _secret(settings), algorithm=ALGORITHM), expires


@router.post("/auth/login")
def login(body: LoginRequest, settings: Settings = Depends(get_settings)) -> dict:
    """Troca usuário e senha do admin por um token JWT."""
    _secret(settings)
    # compare_digest nos dois campos: o tempo de resposta não revela qual deles errou
    user_ok = hmac.compare_digest(body.username.encode(), settings.admin_username.encode())
    expected_password = settings.admin_password.get_secret_value().encode()
    password_ok = hmac.compare_digest(body.password.encode(), expected_password)
    if not (user_ok and password_ok):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="usuário ou senha inválidos")
    token, expires = create_token(settings)
    return {"access_token": token, "token_type": "bearer", "expires_at": expires.isoformat()}


def require_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    settings: Settings = Depends(get_settings),
) -> str:
    """Dependência das rotas admin: devolve o usuário do token ou responde 401."""
    secret = _secret(settings)
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="token ausente",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = jwt.decode(credentials.credentials, secret, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=401, detail="token expirado", headers={"WWW-Authenticate": "Bearer"}
        ) from None
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=401, detail="token inválido", headers={"WWW-Authenticate": "Bearer"}
        ) from None
    if payload.get("sub") != settings.admin_username:
        raise HTTPException(status_code=401, detail="token inválido", headers={"WWW-Authenticate": "Bearer"})
    return payload["sub"]
