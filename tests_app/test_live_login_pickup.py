"""#296: with LIVE_MARKET on, a Kite login stored by the callback after the API started brings the live market from
not_connected (or session_ended) to live, with no process restart; never a second socket, never the token in a log.

Class: every login completed while the app runs with LIVE_MARKET on and the market state not_connected/session_ended
(incl. the daily login after the token stops, F-37). Before the fix 100% needed a restart. No Kite, no database: the
token store, catalogue and KiteSocket are fakes (the recorded 2026-10-08 catalogue), the callback is the real route.
"""
from __future__ import annotations

import asyncio
import logging

import pytest
from httpx import ASGITransport, AsyncClient

from test_kite_login import ACCESS_TOKEN, CALLBACK, REQUEST_TOKEN, FakeKite, _app, _state, _TxDB
from test_strategy_live_push import DB, FakeSocket, held_replay, settle
from marketdata._kite_fixture import new_provider  # tests/ is on sys.path via test_strategy_live_push
from ofo.instruments.catalogue import Catalogue as RealCatalogue
from ofo_app import broker_token_store, catalogue_store, db, kite_ws, live_market, main
from ofo_app.config import get_settings
from ofo_app.routes import broker as broker_routes

CONNECTED = broker_routes.CONNECTED_FRONTEND_PATH


class _Conn:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *a):
        return False


class _Engine:
    def connect(self):
        return _Conn()


def socket_tasks() -> list[asyncio.Task]:
    return [t for t in asyncio.all_tasks() if t.get_name() == "kite-socket" and not t.done()]


@pytest.fixture
async def kite_world(monkeypatch):
    """The stored-session world: ``world["token"]`` is what the token store answers (None = no session); every
    lookup is counted; the socket the market builds is a fake that runs until stopped."""
    provider, clock, items = new_provider()
    world: dict = {"token": None, "lookups": 0, "sockets": [], "raise": None}

    async def token(*a, **k):
        world["lookups"] += 1
        await asyncio.sleep(0.01)  # a real lookup yields to the loop: lets two logins interleave
        if world["raise"] is not None:
            raise world["raise"]
        return world["token"]

    class Catalogue:
        def all_entries(self):
            c = RealCatalogue()
            c.load(items)
            return c.all_entries()

    async def load(conn):
        return Catalogue()

    class Sock(FakeSocket):
        def __init__(self, prov, *, api_key, access_token, clock, base_url):
            super().__init__(prov, result="stopped")
            world["sockets"].append(self)

    async def stored(*a, **k):
        world["stored"] = True

    monkeypatch.setattr(db, "get_engine", _Engine)
    monkeypatch.setattr(broker_token_store, "access_token_for", token)
    monkeypatch.setattr(catalogue_store, "load_catalogue", load)
    monkeypatch.setattr(kite_ws, "KiteSocket", Sock)
    monkeypatch.setattr(broker_routes, "store_session", stored)
    monkeypatch.setenv("DATABASE_URL", DB)
    monkeypatch.setenv("KITE_WS_URL", "ws://127.0.0.1:1/fake-kite")
    monkeypatch.delenv("APP_ENV", raising=False)
    get_settings.cache_clear()
    yield world
    for sock in world["sockets"]:  # a failed test must not leave a socket task for the next one to count
        sock.stopped = True
    for task in socket_tasks():
        task.cancel()
    await settle()
    live_market.set_current(None)
    get_settings.cache_clear()


async def login(app) -> object:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        state = await _state(ac)
        return await ac.get(CALLBACK, params={"status": "success", "request_token": REQUEST_TOKEN, "state": state})


def connected(response) -> None:
    assert response.status_code == 302 and response.headers["location"] == CONNECTED


async def test_a_login_after_start_brings_not_connected_to_live_and_shutdown_stops_it(kite_world, monkeypatch,
                                                                                      caplog):
    """Core + checklist 6: the real lifespan starts with no session; the real callback stores one; the market goes
    live with one socket task; leaving the lifespan stops that task."""
    async def no_db() -> None:  # the engine is a fake here; nothing to dispose
        return None

    monkeypatch.setattr(main, "close_db", no_db)
    app = _app(FakeKite(), _TxDB())
    monkeypatch.setenv("LIVE_MARKET", "1")  # after create_app: the factory's own guards are tested elsewhere
    caplog.set_level(logging.DEBUG)
    kite_world["token"] = None
    async with app.router.lifespan_context(app):
        market = live_market._current
        assert market is not None and market.state == live_market.NOT_CONNECTED and market.context() is None
        kite_world["token"] = ACCESS_TOKEN
        connected(await login(app))
        assert kite_world.get("stored") is True
        assert market.state == live_market.LIVE and live_market.current_context() is market.feed.ctx
        assert len(socket_tasks()) == 1 and len(kite_world["sockets"]) == 1
    assert socket_tasks() == [] and kite_world["sockets"][0].stopped is True
    assert live_market._current is None
    assert all(ACCESS_TOKEN not in (r.getMessage() + (r.exc_text or "")) for r in caplog.records)


async def test_session_ended_goes_live_after_a_login(kite_world, monkeypatch):
    provider, clock, items = new_provider()
    held_replay(provider, clock, items)
    market = live_market.LiveMarket()
    market.attach(provider, FakeSocket(provider), clock)  # the token stopped: the socket ends with "session ended"
    await settle()
    assert market.state == live_market.SESSION_ENDED
    old_feed = market.feed
    live_market.set_current(market)
    monkeypatch.setenv("LIVE_MARKET", "1")
    kite_world["token"] = ACCESS_TOKEN
    connected(await login(_app(FakeKite(), _TxDB())))
    assert market.state == live_market.LIVE and market.feed is not old_feed
    assert market.context().provider.status().session_ended is False
    assert len(socket_tasks()) == 1
    await market.close()
    assert socket_tasks() == []


async def test_a_login_while_live_leaves_the_running_socket_alone(kite_world, monkeypatch):
    provider, clock, _ = new_provider()
    market = live_market.LiveMarket()
    sock = FakeSocket(provider, result="stopped")
    market.attach(provider, sock, clock)
    task, feed = market._task, market.feed
    live_market.set_current(market)
    monkeypatch.setenv("LIVE_MARKET", "1")
    kite_world["token"] = ACCESS_TOKEN
    connected(await login(_app(FakeKite(), _TxDB())))
    assert market._task is task and market.feed is feed and sock.stopped is False
    assert kite_world["lookups"] == 0 and kite_world["sockets"] == []
    assert socket_tasks() == [task]
    await market.close()


async def test_two_logins_at_once_start_one_socket(kite_world, monkeypatch):
    market = live_market.LiveMarket()
    market.state = live_market.NOT_CONNECTED
    live_market.set_current(market)
    monkeypatch.setenv("LIVE_MARKET", "1")
    kite_world["token"] = ACCESS_TOKEN
    cfg = _app(FakeKite(), _TxDB()).state.broker.config
    await asyncio.gather(live_market.pick_up_login(cfg), live_market.pick_up_login(cfg))
    assert market.state == live_market.LIVE
    assert kite_world["lookups"] == 1 and len(kite_world["sockets"]) == 1 and len(socket_tasks()) == 1
    await market.close()


async def test_a_failing_restart_keeps_the_login_and_logs_the_class_name_only(kite_world, monkeypatch, caplog):
    market = live_market.LiveMarket()
    market.state = live_market.NOT_CONNECTED
    live_market.set_current(market)
    monkeypatch.setenv("LIVE_MARKET", "1")
    kite_world["raise"] = RuntimeError(f"decrypt failed for {ACCESS_TOKEN}")
    caplog.set_level(logging.DEBUG)
    connected(await login(_app(FakeKite(), _TxDB())))
    assert kite_world.get("stored") is True
    assert market.state == live_market.NOT_CONNECTED and market.context() is None and socket_tasks() == []
    mine = [r.getMessage() for r in caplog.records if r.name == live_market.log.name]
    assert any("RuntimeError" in m for m in mine), mine
    assert all(ACCESS_TOKEN not in (r.getMessage() + (r.exc_text or "")) for r in caplog.records)


async def test_live_market_off_never_starts_a_market_on_login(kite_world, monkeypatch):
    market = live_market.LiveMarket()
    market.state = live_market.NOT_CONNECTED
    live_market.set_current(market)  # even a market left registered is not started while LIVE_MARKET is off
    monkeypatch.delenv("LIVE_MARKET", raising=False)
    kite_world["token"] = ACCESS_TOKEN
    connected(await login(_app(FakeKite(), _TxDB())))
    assert kite_world["lookups"] == 0 and socket_tasks() == [] and market.state == live_market.NOT_CONNECTED


async def test_no_market_registered_means_the_login_only_stores(kite_world, monkeypatch):
    live_market.set_current(None)
    monkeypatch.setenv("LIVE_MARKET", "1")
    kite_world["token"] = ACCESS_TOKEN
    connected(await login(_app(FakeKite(), _TxDB())))
    assert kite_world.get("stored") is True and kite_world["lookups"] == 0 and socket_tasks() == []


async def test_a_pick_up_under_app_env_test_with_the_real_kite_is_refused(kite_world, monkeypatch):
    market = live_market.LiveMarket()
    market.state = live_market.NOT_CONNECTED
    live_market.set_current(market)
    monkeypatch.setenv("LIVE_MARKET", "1")
    kite_world["token"] = ACCESS_TOKEN
    cfg = _app(FakeKite(), _TxDB()).state.broker.config
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("KITE_WS_URL", live_market.REAL_KITE_WS)
    get_settings.cache_clear()
    await live_market.pick_up_login(cfg)
    assert kite_world["lookups"] == 0 and socket_tasks() == [] and market.state == live_market.NOT_CONNECTED


async def test_a_login_after_shutdown_starts_nothing(kite_world, monkeypatch):
    market = live_market.LiveMarket()
    market.state = live_market.NOT_CONNECTED
    await market.close()
    kite_world["token"] = ACCESS_TOKEN
    monkeypatch.setenv("LIVE_MARKET", "1")
    await market.pick_up_login(_app(FakeKite(), _TxDB()).state.broker.config)
    assert kite_world["lookups"] == 0 and socket_tasks() == []
