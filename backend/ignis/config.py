"""Configuração central lida do ambiente / .env (segredos nunca no código)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://ignis:ignis@127.0.0.1:5432/ignis"

    firms_map_key: str | None = None
    firms_sources: str = "VIIRS_NOAA20_NRT,VIIRS_SNPP_NRT,MODIS_NRT"
    collect_interval_minutes: int = 60
    collect_day_range: int = 2

    # FWI (GWIS/EFFIS): sem chave; recoleta ontem + hoje + previsão de N dias (máx. 9 no GWIS)
    fwi_interval_hours: int = 12
    fwi_days_ahead: int = 3

    # /health considera a coleta atrasada acima deste limite (RNF01: ciclo <= 3h)
    max_collection_age_minutes: int = 180

    # área administrativa (RF09): um único usuário vindo do .env; sem senha ou segredo, fica desligada
    admin_username: str = "admin"
    admin_password: SecretStr | None = None
    jwt_secret: SecretStr | None = None
    jwt_expire_minutes: int = 480

    # e-mail de alertas (RF06): relay SMTP externo (ex.: Amazon SES, porta 587) ou Mailpit em dev.
    # Sem SMTP_HOST/SMTP_FROM o envio fica desligado (os alertas continuam sendo gravados).
    # chave geral: com EMAIL_ENABLED=false (padrão) nada é enviado e as assinaturas ficam desligadas, mesmo
    # com SMTP_* preenchido. Ligue depois de testar com `python -m ignis.notifications --to ...`
    email_enabled: bool = False
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_security: Literal["starttls", "ssl", "none"] = "starttls"
    smtp_from: str | None = None
    smtp_from_name: str = "IGNIS"
    smtp_timeout_seconds: int = 15

    # alertas e assinaturas (RF06, RNF04): links nos e-mails apontam para PUBLIC_BASE_URL (origem pública,
    # ex.: https://ignis.exemplo.org). Os tokens de descadastro são HMAC deste segredo (ou do JWT_SECRET).
    public_base_url: str = "http://127.0.0.1:8000"
    subscription_secret: SecretStr | None = None
    terms_version: str = "2026-11"
    confirm_token_hours: int = 48

    # relatórios por IA (RF11) e boletim diário (RF07). Sem LLM_API_KEY, tudo sai pelo template.
    llm_provider: Literal["gemini", "none"] = "gemini"
    llm_api_key: SecretStr | None = None
    # confira no Google AI Studio qual modelo está na camada gratuita: os nomes e limites mudam
    llm_model: str = "gemini-3.5-flash-lite"
    llm_timeout_seconds: int = 40
    # boletim diário: hora UTC do disparo e regiões (slugs separados por vírgula). 1 região = 1 chamada/dia
    bulletin_hour_utc: int = 7
    bulletin_regions: str = "mediterraneo"

    @property
    def bulletin_region_list(self) -> list[str]:
        return [s.strip() for s in self.bulletin_regions.split(",") if s.strip()]

    @property
    def firms_source_list(self) -> list[str]:
        return [s.strip() for s in self.firms_sources.split(",") if s.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
