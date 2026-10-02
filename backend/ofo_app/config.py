# Copied/adapted from abhayla/algochanakya@bf9faf7:backend/app/config.py (ADR-047)
# Pattern only: pydantic-settings BaseSettings with a required database URL. Broker, TOTP, JWT and AI fields dropped.
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from the environment (or a local, never-committed .env)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str
    APP_ENV: str = "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # DATABASE_URL comes from the environment
