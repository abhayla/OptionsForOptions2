"""FastAPI application builder. No module-level app, no create_all: the schema comes only from Alembic.

Lifespan pattern referenced from abhayla/algochanakya@bf9faf7:backend/app/main.py (ADR-047, REFERENCE only). Unlike
its global handler (main.py:293-307), no handler here returns str(exc): every error body comes from
`ofo_app.errors` (W-024 round 9 part 6), only from a render() catalogue message.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ofo_app import errors, live_market, replay_mode
from ofo_app.broker_config import BrokerConfig, load_broker_config
from ofo_app.db import close_db
from ofo_app.routes import broker, health, outcome, strategies

log = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    market = None
    if live_market.live_requested():  # W-065: off unless LIVE_MARKET is set
        market = live_market.LiveMarket()
        live_market.set_current(market)
        try:
            await market.start(app.state.broker.config)
        except Exception as exc:  # the app still serves; live data stays "not connected". Never the message.
            market.state = live_market.NOT_CONNECTED
            log.error("live market data did not start: %s", type(exc).__name__)
    yield
    if market is not None:
        await market.stop()
        live_market.set_current(None)
    await close_db()


def create_app(broker_config: BrokerConfig | None = None) -> FastAPI:
    """Builds the app. The broker routes refuse to start without a valid broker configuration (W-058):
    ``load_broker_config`` raises BrokerConfigError, so the app is never built without its token key."""
    config = broker_config if broker_config is not None else load_broker_config()
    app = FastAPI(title="OptionsForOptions2 API", version="0.1.0", lifespan=_lifespan)
    errors.install(app)
    if live_market.live_requested():  # refused before anything is served when a test would reach the real Kite
        live_market.require_safe(os.environ.get("APP_ENV", "development"),
                                 os.environ.get("KITE_WS_URL", live_market.REAL_KITE_WS))
    if replay_mode.replay_requested():  # W-064 test-only; refused outside APP_ENV=test, before anything is served
        replay_mode.require_test_env(os.environ.get("APP_ENV", "development"))
        ctx = replay_mode.build_replay_context()
        app.dependency_overrides[outcome.get_market_context] = lambda: ctx
    app.include_router(health.router)
    app.include_router(outcome.router)
    broker.mount(app, config)
    app.include_router(strategies.router)  # W-061: Save Draft and activity history
    return app
