# Copied/adapted from abhayla/algochanakya@bf9faf7:backend/app/config.py (ADR-047)
# Pattern only: pydantic-settings BaseSettings with a required database URL. Broker, TOTP, JWT and AI fields dropped.
from __future__ import annotations

from decimal import Decimal
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    @model_validator(mode="after")
    def _replay_is_test_only(self) -> "Settings":
        if self.OUTCOME_REPLAY and self.APP_ENV != "test":
            raise ValueError("OUTCOME_REPLAY is a test-only setting: it needs APP_ENV=test")
        if self.LIVE_MARKET and self.APP_ENV == "test" and self.KITE_WS_URL.startswith("wss://ws.kite.trade"):
            raise ValueError("LIVE_MARKET under APP_ENV=test needs a KITE_WS_URL that is not the real Kite")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # DATABASE_URL comes from the environment
