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
from ofo.broker import rate_limit as _rate_limit

from ofo_app import (
    catalogue_refresh,
    errors,
    event_loop,
    execute_replay_switch,
    feed_mode,
    held_switches,
    live_market,
    paper_monitor,
    paper_settlement,
    pinned_clock,
    replay_mode,
    scenario_mode,
)
from ofo_app.broker_config import BrokerConfig, load_broker_config
from ofo_app.config import Settings, app_env
from ofo_app.db import close_db, verify_pool_budget
from ofo_app.routes import (
    adjustment,
    adjustment_check,
    broker,
    broker_capabilities,
    broker_status,
    catalogue,
    chain,
    execute,
    execution_return,
    features,
    health,
    indices,
    leg_edit,
    leg_picker,
    live,
    outcome,
    paper,
    planned_entry,
    positions,
    ready_made,
    strategies,
    strategy_templates,
    tracking,
    zerodha_account,
)

log = logging.getLogger(__name__)

#: The only APP_ENV values that serve /docs, /redoc and /openapi.json (ADR-073).
DOCS_ENVS = frozenset({"development", "test"})


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    event_loop.require_selector_loop()  # W-080 r7: refuses to start on a loop whose connects the egress gate can't see
    if not _egress.installed():  # W-080: create_app installs it; an app built any other way does not start
        raise _egress.EgressRefused("the egress gate is not installed; the API starts only through create_app")
    await verify_pool_budget()  # GC-6: a pool above the role's connection limit refuses to start
    market = None
    if live_market.live_requested():  # W-065: off unless LIVE_MARKET is set
        market = live_market.LiveMarket()
        live_market.set_current(market)
        try:
            await market.start(app.state.broker.config)
        except Exception as exc:  # the app still serves; live data stays "not connected". Never the message.  # noqa: BLE001
            market.state = live_market.NOT_CONNECTED
            log.error("live market data did not start: %s", type(exc).__name__)
    refresh = catalogue_refresh.start() if catalogue_refresh.refresh_requested() else None  # W-133: off unless asked
    monitor = paper_monitor.start() if market is not None else None  # GC-TP 7a: paper stops, live only
    settlement = paper_settlement.start() if market is not None else None  # GC-TP 5b: expiry settlement, live only
    yield
    await paper_settlement.stop(settlement)  # a strategy's settle in flight is cancelled and rolls back
    await paper_monitor.stop(monitor)  # a fire in flight is cancelled and rolls back
    await catalogue_refresh.stop(refresh)  # a run in flight is cancelled and rolls back
    if market is not None:
        live_market.set_current(None)  # a login arriving now finds no market (#296)
        await market.close()
    await close_db()


def _mount_routes(app: FastAPI, config: BrokerConfig) -> None:
    """Every router and door socket, in the one order the app has always mounted them (one include per route)."""
    app.include_router(health.router)
    app.include_router(outcome.router)
    errors.add_socket_route(app, live.socket_route())  # W-065: the strategy live push, a door socket
    errors.add_socket_route(app, chain.socket_route())  # W-116: the read-only Option Chain push, a door socket
    app.include_router(chain.router)  # W-116: the chain's first paint and socket-down fallback
    app.include_router(adjustment.router)  # W-196: adjustment approaches (REQ-155)
    app.include_router(adjustment_check.router)  # GC-ADJ2 1C: the playbook check (REQ-158 AC-5)
    app.include_router(leg_edit.router)  # W-148: one leg edit, answered by the engine
    app.include_router(leg_picker.router)  # W-147: the leg picker's strikes, futures and depth reads (REQ-080)
    errors.add_socket_route(app, indices.socket_route())  # W-114: the read-only index push, a door socket
    app.include_router(strategy_templates.router)  # W-117: the Learn page's reviewed templates (read-only, no DB)
    app.include_router(indices.router)  # W-114: the index view's first paint and socket-down fallback
    broker.mount(app, config)
    app.include_router(broker_capabilities.router)  # W-132: the seven named broker flags (read-only, no DB)
    app.include_router(broker_status.router)  # W-089: Settings -> Broker & Market Data
    app.include_router(zerodha_account.router)  # RD-013: masked Zerodha id + Zerodha's own margin (read only)
    app.include_router(strategies.router)  # W-061: Save Draft and activity history
    app.include_router(execute.router)  # W-095: Execute -> gate -> read-only Kite basket, plan stored first
    app.include_router(execution_return.router)  # W-096: return from Kite - read back by tag, close, reconcile
    app.include_router(features.router)  # W-121: which switchable features are on (the order path)
    app.include_router(ready_made.router)  # W-125: ready-made shapes, held (Q211)
    app.include_router(catalogue.router)  # W-068: the leg picker's expiries and contracts (read-only)
    app.include_router(planned_entry.router)  # W-068: planned entry captured only from a live price
    app.include_router(positions.router)  # W-111: Positions read - own lots per strategy, outside lots apart, no money
    app.include_router(tracking.router)  # W-122: paper tracking of a saved strategy + Q253 condition 1
    app.include_router(paper.router)  # GC-TP 1b: the paper order book (net positions, orderbook, typed orders)


def create_app(broker_config: BrokerConfig | None = None) -> FastAPI:
    """Builds the app. The broker routes refuse to start without a valid broker configuration (W-058):
    ``load_broker_config`` raises BrokerConfigError, so the app is never built without its token key.

    The FIRST thing it does is install the runtime egress gate (REQ-073 AC-4, ``ofo.broker.egress``): from here on
    this process connects only to loopback, the database and the Kite doors, and starts no process. Unconditional:
    no environment value or flag skips it, and an audit hook cannot be removed."""
    _egress.install()
    config = broker_config if broker_config is not None else load_broker_config()
    _rate_limit.install_app_key(config.api_key)  # REQ-118 AC-1: a keyless call (instrument file) uses the app's bucket
    # ADR-073: the framework docs page and API description exist only in development and test; in production
    # (and any other APP_ENV) they are not mounted, so they answer 404.
    docs: dict[str, None] = {} if app_env() in DOCS_ENVS else {
        "docs_url": None, "redoc_url": None, "openapi_url": None}
    app = FastAPI(title="OptionsForOptions2 API", version="0.1.0", lifespan=_lifespan, redirect_slashes=False, **docs)
    app.router.route_class = errors.ClosedRoute  # every route added on the app itself goes through the response door
    errors.install(app)
    errors.set_frontend_origin(config.frontend_origin)  # write-once (#159)
    feed_mode.require_valid(app_env() or "", live_market.live_requested())  # REQ-113: an allow-list, before serving
    if live_market.live_requested():  # refused before anything is served when a test would reach the real Kite
        live_market.require_safe(app_env() or "",
                                 os.environ.get("KITE_WS_URL", live_market.REAL_KITE_WS))
        Settings()  # type: ignore[call-arg]  # ADR-078: raises (the factory fails) on a test/unnamed database; the lifespan catch never sees it
    held_switches.require_valid_configuration()  # W-125: a held feature on without a reference refuses to start
    live.set_replay_feed(None)
    scenario = None
    if scenario_mode.scenario_requested():  # GC-ADJ1 1b dev/test only; refused elsewhere, before anything is served
        scenario_mode.require_dev_or_test(app_env())
        scenario = scenario_mode.current()  # also refuses a malformed or unknown scenario id
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
    if execute_replay_switch.replay_requested():  # W-101 test-only; refused outside APP_ENV=test, first
        execute_replay_switch.require_test_env(app_env() or "")
        from ofo_app import execute_replay  # noqa: PLC0415 - only here: production never reads test fixtures
        # Execute + return answer from the recorded 2026-10-16 replies, no live session
        app.dependency_overrides.update(execute_replay.overrides())
    _mount_routes(app, config)
    if scenario is not None:
        unclassified = scenario_mode.unclassified_mutating_routes(app.routes)
        if unclassified:  # fail closed: a new mutating route must be classified before scenario mode serves it
            raise scenario_mode.ScenarioRefused(f"unclassified mutating routes in scenario mode: {unclassified}")
        app.dependency_overrides.update(scenario_mode.overrides(scenario))  # every seam a scenario serves
    return app
