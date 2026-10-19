# Copied/adapted from abhayla/algochanakya@bf9faf7:backend/app/config.py (ADR-047)
# Pattern only: pydantic-settings BaseSettings with a required database URL. Broker, TOTP, JWT and AI fields dropped.
from __future__ import annotations

import os
from decimal import Decimal
from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

#: ADR-078: the database only the test suites write to. A live run (LIVE_MARKET) must never use it.
TEST_DATABASE_NAME = "ofo_test"


def database_name(url: str) -> str | None:
    """The database name in a connection URL (path without its slash, query dropped), or None when there is none."""
    name = urlsplit(url).path.lstrip("/").split("/")[0]
    return name or None


class Settings(BaseSettings):
    """Application settings loaded from the environment (or a local, never-committed .env)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str
    APP_ENV: str = "development"
    #: ADR-058 admin setting: refuse a catalogue update that would drop MORE than this percentage of an index's live
    #: contracts at once (catalogue_store.DEFAULT_MAX_DELIST_PERCENT; a test asserts both are 10).
    CATALOGUE_MAX_DELIST_PERCENT: Decimal = Decimal("10")
    #: W-064: TEST-ONLY. Serves the outcome route from the recorded 2026-10-08 frames (ofo_app.replay_mode). Refused at
    #: start-up unless APP_ENV is exactly "test", so production settings cannot enable it.
    OUTCOME_REPLAY: bool = False
    #: W-065: live market data. Off by default. When on, the app holds a KiteProvider fed by the Kite WebSocket with the
    #: owner's stored session. Refused under APP_ENV=test unless KITE_WS_URL is a local fake (tests never reach Kite).
    LIVE_MARKET: bool = False
    KITE_WS_URL: str = "wss://ws.kite.trade"
    #: #237: TEST-ONLY. Pins the catalogue routes' "today" (ofo_app.pinned_clock) so a recorded fixture stays live in CI.
    #: Refused unless APP_ENV is exactly "test".
    TEST_CATALOGUE_DATE: str | None = None
    #: #370: the API's database pool. The defaults are SQLAlchemy's own (5 kept + 10 extra: no change for a normal
    #: run). The throwaway CI role has CONNECTION LIMIT 5 (ADR-048) shared by three API processes, so the e2e job
    #: starts each with 1 + 0: three connections in all, the rest of the limit left for seeding and tests.
    DB_POOL_SIZE: int = Field(default=5, ge=1)
    DB_MAX_OVERFLOW: int = Field(default=10, ge=0)

    @model_validator(mode="after")
    def _replay_is_test_only(self) -> "Settings":
        if self.TEST_CATALOGUE_DATE and self.APP_ENV != "test":
            raise ValueError("TEST_CATALOGUE_DATE is a test-only setting: it needs APP_ENV=test")
        if self.OUTCOME_REPLAY and self.APP_ENV != "test":
            raise ValueError("OUTCOME_REPLAY is a test-only setting: it needs APP_ENV=test")
        if self.LIVE_MARKET and self.APP_ENV == "test" and self.KITE_WS_URL.startswith("wss://ws.kite.trade"):
            raise ValueError("LIVE_MARKET under APP_ENV=test needs a KITE_WS_URL that is not the real Kite")
        if self.LIVE_MARKET:
            db = database_name(self.DATABASE_URL)
            test_db = database_name(os.environ.get("TEST_DATABASE_URL", ""))
            if db is None or db == TEST_DATABASE_NAME or (test_db is not None and db == test_db):
                raise ValueError(
                    f"LIVE_MARKET must not use the test database or an unnamed one ('{db or ''}') (ADR-078): "
                    "live runs use ofo_dev; point "
                    "DATABASE_URL at DEV_DATABASE_URL, because the test suites use only the test database"
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # DATABASE_URL comes from the environment


class _AppEnv(BaseSettings):
    """Only APP_ENV, with no default: whether it was set at all is part of the answer (ADR-073)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_ENV: str | None = None


def app_env() -> str | None:
    """The one source of APP_ENV (process environment first, then the .env file), or None when it is set nowhere.
    Not cached: read at app build time. Docs and replay mode both decide from this value."""
    return _AppEnv().APP_ENV
