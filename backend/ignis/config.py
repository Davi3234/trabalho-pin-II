"""Configuração central lida do ambiente / .env (segredos nunca no código)."""

from __future__ import annotations

from functools import lru_cache

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

    @property
    def firms_source_list(self) -> list[str]:
        return [s.strip() for s in self.firms_sources.split(",") if s.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
