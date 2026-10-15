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

from ofo.marketdata.fanout import FanOut
from ofo_app import errors, live_market, live_push, replay_mode
from ofo_app.config import app_env
from ofo_app.broker_config import BrokerConfig, load_broker_config
from ofo_app.db import close_db
from ofo_app.routes import broker, catalogue, health, live, outcome, planned_entry, strategies

log = logging.getLogger(__name__)

#: The only APP_ENV values that serve /docs, /redoc and /openapi.json (ADR-073).
DOCS_ENVS = frozenset({"development", "test"})


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
    # ADR-073: the framework docs page and API description exist only in development and test; in production
    # (and any other APP_ENV) they are not mounted, so they answer 404.
    docs: dict[str, None] = {} if app_env() in DOCS_ENVS else {
        "docs_url": None, "redoc_url": None, "openapi_url": None}
    app = FastAPI(title="OptionsForOptions2 API", version="0.1.0", lifespan=_lifespan, redirect_slashes=False, **docs)
    app.router.route_class = errors.ClosedRoute  # every route added on the app itself goes through the response door
    errors.install(app)
    if live_market.live_requested():  # refused before anything is served when a test would reach the real Kite
        live_market.require_safe(app_env() or "",
                                 os.environ.get("KITE_WS_URL", live_market.REAL_KITE_WS))
    live.set_replay_feed(None)
    if replay_mode.replay_requested():  # W-064 test-only; refused outside APP_ENV=test, before anything is served
        replay_mode.require_test_env(app_env() or "")
        ctx = replay_mode.build_replay_context()
        app.dependency_overrides[outcome.get_market_context] = lambda: ctx
        live.set_replay_feed(live_push.LiveFeed(ctx, FanOut(ctx.provider)))  # the socket replays the same frames
    app.include_router(health.router)
    app.include_router(outcome.router)
    live.mount(app)  # W-065: the strategy live push, a door socket
    broker.mount(app, config)
    app.include_router(strategies.router)  # W-061: Save Draft and activity history
    app.include_router(catalogue.router)  # W-068: the leg picker's expiries and contracts (read-only)
    app.include_router(planned_entry.router)  # W-068: planned entry captured only from a live price
    return app
