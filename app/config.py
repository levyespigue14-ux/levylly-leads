"""Configurações lidas do ambiente (ou do arquivo .env)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./levylly_leads.db"
    dias_primeiro_followup: int = 3
    dias_segundo_followup: int = 2
    dias_socio: int = 2
    limite_diario: int = 25


@lru_cache
def get_settings() -> Settings:
    return Settings()
