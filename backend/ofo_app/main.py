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
from ofo.broker import egress as _egress

from ofo_app import errors, event_loop, execute_replay, live_market, pinned_clock, replay_mode
from ofo_app.broker_config import BrokerConfig, load_broker_config
from ofo_app.config import Settings, app_env
from ofo_app.db import close_db
from ofo_app.routes import (
    broker,
    catalogue,
    execute,
    execution_return,
    health,
    live,
    outcome,
    planned_entry,
    strategies,
)

log = logging.getLogger(__name__)

#: The only APP_ENV values that serve /docs, /redoc and /openapi.json (ADR-073).
DOCS_ENVS = frozenset({"development", "test"})


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    event_loop.require_selector_loop()  # W-080 r7: refuses to start on a loop whose connects the egress gate can't see
    if not _egress.installed():  # W-080: create_app installs it; an app built any other way does not start
        raise _egress.EgressRefused("the egress gate is not installed; the API starts only through create_app")
    market = None
    if live_market.live_requested():  # W-065: off unless LIVE_MARKET is set
        market = live_market.LiveMarket()
        live_market.set_current(market)
        try:
            await market.start(app.state.broker.config)
        except Exception as exc:  # the app still serves; live data stays "not connected". Never the message.  # noqa: BLE001
            market.state = live_market.NOT_CONNECTED
            log.error("live market data did not start: %s", type(exc).__name__)
    yield
    if market is not None:
        live_market.set_current(None)  # a login arriving now finds no market (#296)
        await market.close()
    await close_db()


def create_app(broker_config: BrokerConfig | None = None) -> FastAPI:
    """Builds the app. The broker routes refuse to start without a valid broker configuration (W-058):
    ``load_broker_config`` raises BrokerConfigError, so the app is never built without its token key.

    The FIRST thing it does is install the runtime egress gate (REQ-073 AC-4, ``ofo.broker.egress``): from here on
    this process connects only to loopback, the database and the Kite doors, and starts no process. Unconditional:
    no environment value or flag skips it, and an audit hook cannot be removed."""
    _egress.install()
    config = broker_config if broker_config is not None else load_broker_config()
    # ADR-073: the framework docs page and API description exist only in development and test; in production
    # (and any other APP_ENV) they are not mounted, so they answer 404.
    docs: dict[str, None] = {} if app_env() in DOCS_ENVS else {
        "docs_url": None, "redoc_url": None, "openapi_url": None}
    app = FastAPI(title="OptionsForOptions2 API", version="0.1.0", lifespan=_lifespan, redirect_slashes=False, **docs)
    app.router.route_class = errors.ClosedRoute  # every route added on the app itself goes through the response door
    errors.install(app)
    errors.set_frontend_origin(config.frontend_origin)  # write-once (#159)
    if live_market.live_requested():  # refused before anything is served when a test would reach the real Kite
        live_market.require_safe(app_env() or "",
                                 os.environ.get("KITE_WS_URL", live_market.REAL_KITE_WS))
        Settings()  # type: ignore[call-arg]  # ADR-078: raises (the factory fails) on a test/unnamed database; the lifespan catch never sees it
    live.set_replay_feed(None)
    if pinned_clock.pin_requested():  # #237 test-only; refused outside APP_ENV=test, before anything is served
        pinned_clock.require_test_env(app_env() or "")
        pinned_clock.pinned_today()  # also refuses a value that is not a plain date
    if replay_mode.replay_requested():  # W-064 test-only; refused outside APP_ENV=test, before anything is served
        replay_mode.require_test_env(app_env() or "")
        ctx = replay_mode.build_replay_context()
        app.dependency_overrides[outcome.get_market_context] = lambda: ctx
        feeds = replay_mode.ReplayFeeds(ctx)  # W-065: one replay feed per socket connection (reconnects get prices)
        live.set_replay_feed(feeds)
        app.dependency_overrides[outcome.get_streaming] = lambda: feeds.streaming  # REST not live after a socket drop
    if execute_replay.replay_requested():  # W-101 test-only; refused outside APP_ENV=test, before anything is served
        execute_replay.require_test_env(app_env() or "")
        execute_replay.install(app)  # Execute + return answer from the recorded 2026-10-16 Kite replies, no live session
    app.include_router(health.router)
    app.include_router(outcome.router)
    errors.add_socket_route(app, live.socket_route())  # W-065: the strategy live push, a door socket
    broker.mount(app, config)
    app.include_router(strategies.router)  # W-061: Save Draft and activity history
    app.include_router(execute.router)  # W-095: Execute -> gate -> read-only Kite basket, plan stored first
    app.include_router(execution_return.router)  # W-096: return from Kite - read back by tag, close, reconcile
    app.include_router(catalogue.router)  # W-068: the leg picker's expiries and contracts (read-only)
    app.include_router(planned_entry.router)  # W-068: planned entry captured only from a live price
    return app
