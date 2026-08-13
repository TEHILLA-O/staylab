"""API settings, sourced from the environment."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from analytics.config import PROJECT_ROOT, database_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", extra="ignore", case_sensitive=False
    )

    database_url: str = database_url()
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000"
    default_experiment_key: str = "EXP-024"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
