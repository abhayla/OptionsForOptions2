"""AC-8 (REQ-015): Disconnect ends the session and keeps strategies, history, entitlements and the account.

Real PostgreSQL (skips locally without TEST_DATABASE_URL, runs in CI). The anonymous case swaps the single sign-in seam
(``current_user_ref``, the dependency every route uses) for one that refuses.
"""
from __future__ import annotations

import asyncio
import base64
import os
import uuid

from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from ofo_app import broker_token_store as store
from ofo_app import live_market
from ofo_app.broker_config import BrokerSettings, load_broker_config
from ofo_app.broker_crypto import TokenCipher
from ofo_app.db import get_db
from ofo_app.main import create_app
from ofo_app.routes import broker as broker_routes
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

FRONTEND = os.environ["FRONTEND_ORIGIN"]
ACCESS_TOKEN = "ACtok_fake_disconnect_8c1e3a5b"  # noqa: S105
API_SECRET = "kite_fake_secret_value"  # noqa: S105
STATUS = "/api/broker/status"
DISCONNECT = "/api/broker/disconnect"


def _user() -> str:
    return "test-" + uuid.uuid4().hex


def _app(maker, user_ref: str | None):
    config = load_broker_config(BrokerSettings(
        KITE_API_KEY="kite_fake_key", KITE_API_SECRET=API_SECRET,
        KITE_REDIRECT_URL="http://127.0.0.1:8000/kite/callback", FRONTEND_ORIGIN=FRONTEND,
        KITE_EXPECTED_USER_ID="AB1234", BROKER_TOKEN_KEY=base64.urlsafe_b64encode(os.urandom(32)).decode()))
    app = create_app(config)

    async def _db():
        async with maker() as session:
            yield session

    def _anonymous() -> str:
        raise HTTPException(status_code=401)

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[broker_routes.current_user_ref] = (_anonymous if user_ref is None else (lambda: user_ref))
    return app


async def _digest(admin_engine) -> dict[str, str]:
    """A digest of every public table except broker_sessions: strategies, history, entitlements, accounts..."""
    async with admin_engine.connect() as conn:
        names = [r[0] for r in await conn.execute(text(
            "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relname <> 'broker_sessions' ORDER BY 1"))]
        return {name: (await conn.execute(text(
            f'SELECT md5(coalesce(string_agg(x::text, \'|\' ORDER BY x::text), \'\')) FROM public."{name}" x'  # noqa: S608
        ))).scalar_one() for name in names}


async def _row(admin_engine, user: str) -> dict:
    async with admin_engine.connect() as conn:
        return dict((await conn.execute(text(
            "SELECT ended_at, end_reason, token_ciphertext FROM public.broker_sessions WHERE user_ref = :u "
            "ORDER BY id DESC LIMIT 1"), {"u": user})).one()._mapping)


async def test_disconnect_ends_the_session_and_leaves_every_other_table_unchanged(app_engine, admin_engine):
    """AC-8: Disconnect then status -> Disconnected; strategies, history, entitlements and the account unchanged."""
    user, cipher = _user(), TokenCipher(os.urandom(32))
    maker = async_sessionmaker(app_engine, class_=AsyncSession, expire_on_commit=False)
    async with app_engine.begin() as conn:
        await store.store_session(conn, user, ACCESS_TOKEN, cipher)
    before = await _digest(admin_engine)
    async with AsyncClient(transport=ASGITransport(app=_app(maker, user)), base_url="http://t") as ac:
        assert (await ac.get(STATUS)).json()["account_connection"]["state"] == "connected"
        response = await ac.post(DISCONNECT)
        assert (response.status_code, response.json()) == (200, {"disconnected": True})
        assert ACCESS_TOKEN.encode() not in response.content
        status = (await ac.get(STATUS)).json()
        assert status["account_connection"] == {"state": "disconnected", "fix": "connect_zerodha"}
        assert status["last_successful_sync"] is None
        again = await ac.post(DISCONNECT)  # nothing active: says so, changes nothing
        assert again.json() == {"disconnected": False}
    row = await _row(admin_engine, user)
    assert row["end_reason"] == "disconnected" and row["ended_at"] is not None and row["token_ciphertext"] is None
    assert await _digest(admin_engine) == before


async def test_disconnect_by_an_anonymous_caller_is_refused_and_ends_nothing(app_engine, admin_engine):
    """AC-8 attack 2: with no signed-in owner the call is refused and the session stays active."""
    user, cipher = _user(), TokenCipher(os.urandom(32))
    maker = async_sessionmaker(app_engine, class_=AsyncSession, expire_on_commit=False)
    async with app_engine.begin() as conn:
        await store.store_session(conn, user, ACCESS_TOKEN, cipher)
    async with AsyncClient(transport=ASGITransport(app=_app(maker, None)), base_url="http://t") as ac:
        assert (await ac.post(DISCONNECT)).status_code == 401  # noqa: PLR2004
    assert (await _row(admin_engine, user))["ended_at"] is None


async def test_disconnect_ends_only_the_callers_session_and_is_post_only(app_engine, admin_engine):
    """AC-8: another user's active session is untouched; a GET cannot disconnect."""
    mine, other, cipher = _user(), _user(), TokenCipher(os.urandom(32))
    maker = async_sessionmaker(app_engine, class_=AsyncSession, expire_on_commit=False)
    async with app_engine.begin() as conn:
        await store.store_session(conn, mine, ACCESS_TOKEN, cipher)
        await store.store_session(conn, other, ACCESS_TOKEN, cipher)
    async with AsyncClient(transport=ASGITransport(app=_app(maker, mine)), base_url="http://t") as ac:
        assert (await ac.get(DISCONNECT)).status_code == 405  # noqa: PLR2004
        assert (await _row(admin_engine, mine))["ended_at"] is None
        assert (await ac.post(DISCONNECT)).json() == {"disconnected": True}
    assert (await _row(admin_engine, mine))["end_reason"] == "disconnected"
    assert (await _row(admin_engine, other))["ended_at"] is None


class _Socket:
    def __init__(self) -> None:
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


async def test_disconnect_stops_a_running_live_feed(app_engine, monkeypatch):
    """AC-8 (ADR-020 Q94): after Disconnect the live socket is stopped, not left streaming on the old token; status
    never says the feed is live."""
    user, cipher = _user(), TokenCipher(os.urandom(32))
    maker = async_sessionmaker(app_engine, class_=AsyncSession, expire_on_commit=False)
    async with app_engine.begin() as conn:
        await store.store_session(conn, user, ACCESS_TOKEN, cipher)
    market = live_market.LiveMarket()
    socket = _Socket()
    market.state, market._socket, market._fingerprint = live_market.LIVE, socket, b"fp"
    market._task = asyncio.get_running_loop().create_task(asyncio.sleep(30))
    monkeypatch.setattr(live_market, "_current", market)
    assert market.running()
    async with AsyncClient(transport=ASGITransport(app=_app(maker, user)), base_url="http://t") as ac:
        assert (await ac.post(DISCONNECT)).json() == {"disconnected": True}
        status = (await ac.get(STATUS)).json()
    assert socket.stopped and not market.running() and live_market.current_session() is None
    assert market.context() is None and market.state == live_market.NOT_CONNECTED
    assert status["live_market_data"]["state"] == "disconnected"


async def test_disconnect_succeeds_when_no_feed_exists(app_engine, monkeypatch):
    """AC-8: no registered market (LIVE_MARKET off) is not an error."""
    user = _user()
    maker = async_sessionmaker(app_engine, class_=AsyncSession, expire_on_commit=False)
    async with app_engine.begin() as conn:
        await store.store_session(conn, user, ACCESS_TOKEN, TokenCipher(os.urandom(32)))
    monkeypatch.setattr(live_market, "_current", None)
    async with AsyncClient(transport=ASGITransport(app=_app(maker, user)), base_url="http://t") as ac:
        assert (await ac.post(DISCONNECT)).json() == {"disconnected": True}


async def test_disconnect_wakes_the_market_data_process_in_bus_mode(app_engine, redis_url, monkeypatch):
    """REQ-113 A1: in ``bus`` mode the Disconnect route also publishes its one ``disconnect`` control message (the
    stored session is already ended - the feed process reads that, the message is only a wake-up)."""
    from ofo_app import feed_bus  # noqa: PLC0415

    user, cipher = _user(), TokenCipher(os.urandom(32))
    maker = async_sessionmaker(app_engine, class_=AsyncSession, expire_on_commit=False)
    async with app_engine.begin() as conn:
        await store.store_session(conn, user, ACCESS_TOKEN, cipher)
    market = live_market.LiveMarket()
    market.state = live_market.LIVE
    monkeypatch.setattr(live_market, "_current", market)
    monkeypatch.setenv("FEED_MODE", "bus")
    monkeypatch.setenv("REDIS_URL", redis_url)
    bus = feed_bus.new_client(redis_url)
    try:
        await bus.delete(feed_bus.control_key(live_market.OWNER_REF))
        async with AsyncClient(transport=ASGITransport(app=_app(maker, user)), base_url="http://t") as ac:
            assert (await ac.post(DISCONNECT)).json() == {"disconnected": True}
        sent = await bus.xrange(feed_bus.control_key(live_market.OWNER_REF))
        assert [fields[b"k"] for _id, fields in sent] == [b"disconnect"]
        assert all(set(fields) == {b"u", b"k", b"t"} for _id, fields in sent)
    finally:
        await bus.delete(feed_bus.control_key(live_market.OWNER_REF))
        await bus.aclose()
