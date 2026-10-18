"""AC-4 (REQ-015): the Settings status route reports the four Zerodha statuses from real stored state.

Part 1 (no database): ``build_status`` for every state - connected, partial (each named fix), disconnected, and the
stale session. Part 2 (real PostgreSQL, skips locally without TEST_DATABASE_URL, runs in CI): the core proof through
the real route - a stored session reads Connected, a disconnected or expired one reads Disconnected with the guide -
and the reply never holds a token, key or secret (allow-list of reply keys, generated).
"""
from __future__ import annotations

import asyncio
import base64
import datetime
import os
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from ofo_app import broker_sync, live_market
from ofo_app import broker_token_store as store
from ofo_app.broker_config import BrokerSettings, load_broker_config
from ofo_app.broker_crypto import TokenCipher
from ofo_app.db import get_db
from ofo_app.main import create_app
from ofo_app.routes import broker as broker_routes
from ofo_app.routes.broker_status import BrokerStatusOut, StatusOut, build_status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

FRONTEND = os.environ["FRONTEND_ORIGIN"]
ACCESS_TOKEN = "ACtok_fake_status_5d2f4a6c7e"  # noqa: S105
API_KEY = "kite_fake_status_key"
API_SECRET = "kite_fake_status_secret_value"  # noqa: S105
T0 = datetime.datetime(2026, 10, 17, 9, 0, tzinfo=datetime.UTC)
LATER = T0 + datetime.timedelta(minutes=5)
EARLIER = T0 - datetime.timedelta(hours=2)
#: The only keys a status reply may carry (an allow-list, never a list of banned names).
REPLY_KEYS = frozenset({"account_connection", "live_market_data", "position_sync", "order_execution",
                        "last_successful_sync", "historical_data", "state", "fix"})
FOUR = ("account_connection", "live_market_data", "position_sync", "order_execution")


def _states(out: BrokerStatusOut) -> dict[str, tuple[str, str | None]]:
    return {n: (getattr(out, n).state, getattr(out, n).fix) for n in FOUR}


@pytest.fixture(autouse=True)
def _clean_sync():
    broker_sync.forget()
    yield
    broker_sync.forget()


def test_everything_connected_only_with_a_session_a_running_feed_and_a_read_after_login():
    """AC-4: all four Connected, with the last successful sync time."""
    out = build_status((T0, False), LATER, live_market.LIVE, True)
    assert _states(out) == dict.fromkeys(FOUR, ("connected", None))
    assert out.last_successful_sync == LATER and out.historical_data == "not_available"


@pytest.mark.parametrize(("live_state", "fix"), [
    (live_market.NOT_STARTED, "live_feed_off"),
    (live_market.SESSION_ENDED, "live_feed_session_ended"),
    (live_market.NOT_CONNECTED, "live_feed_not_running"),
])
def test_a_session_without_a_running_feed_is_partial_and_names_the_fix(live_state, fix):
    """AC-4: never Connected by default - a stored session alone does not make live data Connected."""
    out = build_status((T0, False), LATER, live_state, False)
    assert _states(out) == {"account_connection": ("connected", None), "live_market_data": ("partial", fix),
                            "position_sync": ("connected", None),
                            "order_execution": ("partial", "live_data_not_connected")}


def test_no_read_since_login_is_partial_and_a_read_before_login_does_not_count():
    """AC-4: a read older than this session (the previous login's) is not this session's sync."""
    for last in (None, EARLIER):
        out = build_status((T0, False), last, live_market.LIVE, True)
        assert _states(out)["position_sync"] == ("partial", "no_read_yet")
        assert _states(out)["order_execution"] == ("partial", "positions_not_synced")
        assert out.last_successful_sync is None


def test_no_session_is_disconnected_with_the_guide_everywhere():
    """AC-4: Disconnected (with the guide) for all four, even if the feed word says live."""
    out = build_status(None, LATER, live_market.LIVE, True)
    assert _states(out) == dict.fromkeys(FOUR, ("disconnected", "connect_zerodha"))
    assert out.last_successful_sync is None


def test_a_stale_session_past_todays_expiry_is_not_connected():
    """AC-4 attack 3: a session older than Kite's expiry reads Disconnected, whatever else is running."""
    out = build_status((T0, True), LATER, live_market.LIVE, True)
    assert _states(out) == dict.fromkeys(FOUR, ("disconnected", "session_expired"))


def test_the_reply_model_is_closed_to_unknown_states():
    """AC-4: a state outside the three words cannot be built (fail closed)."""
    with pytest.raises(ValueError, match="state"):
        StatusOut(state="unknown", fix=None)  # type: ignore[arg-type]


# ----------------------------------------------------------------------------------------------------------------
# Real PostgreSQL (CI)
# ----------------------------------------------------------------------------------------------------------------


def _user() -> str:
    return "test-" + uuid.uuid4().hex


def _app(maker, user_ref: str):
    config = load_broker_config(BrokerSettings(
        KITE_API_KEY=API_KEY, KITE_API_SECRET=API_SECRET, KITE_REDIRECT_URL="http://127.0.0.1:8000/kite/callback",
        FRONTEND_ORIGIN=FRONTEND, KITE_EXPECTED_USER_ID="AB1234",
        BROKER_TOKEN_KEY=base64.urlsafe_b64encode(os.urandom(32)).decode()))
    app = create_app(config)

    async def _db():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[broker_routes.current_user_ref] = lambda: user_ref
    return app


def _client(app) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


def _keys(value, found: set[str]) -> set[str]:
    if isinstance(value, dict):
        for k, v in value.items():
            found.add(k)
            _keys(v, found)
    return found


async def test_core_proof_a_stored_session_reads_connected_and_ending_it_reads_disconnected(app_engine, monkeypatch):
    """AC-4: real stored state through the real route, no token in the reply."""
    user = _user()
    maker = async_sessionmaker(app_engine, class_=AsyncSession, expire_on_commit=False)
    app = _app(maker, user)
    monkeypatch.setattr(live_market, "_current", None)
    async with _client(app) as ac:
        before = (await ac.get("/api/broker/status")).json()
        assert {n: before[n]["state"] for n in FOUR} == dict.fromkeys(FOUR, "disconnected")
        assert before["account_connection"]["fix"] == "connect_zerodha"
        async with app_engine.begin() as conn:
            await store.store_session(conn, user, ACCESS_TOKEN, TokenCipher(os.urandom(32)))
        response = await ac.get("/api/broker/status")
        body = response.json()
        assert response.status_code == 200  # noqa: PLR2004
        assert body["account_connection"] == {"state": "connected", "fix": None}
        assert body["live_market_data"] == {"state": "partial", "fix": "live_feed_off"}  # no feed: never by default
        assert body["position_sync"] == {"state": "partial", "fix": "no_read_yet"}
        assert body["last_successful_sync"] is None and body["historical_data"] == "not_available"
        # allow-list of reply keys, and no secret anywhere in the bytes
        assert _keys(body, set()) <= REPLY_KEYS
        for secret in (ACCESS_TOKEN, API_KEY, API_SECRET):
            assert secret.encode() not in response.content
        broker_sync.note_read(datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=1))
        synced = (await ac.get("/api/broker/status")).json()
        assert synced["position_sync"]["state"] == "connected" and synced["last_successful_sync"] is not None
        async with app_engine.begin() as conn:
            await store.end_session(conn, user, store.EndReason.DISCONNECTED)
        after = (await ac.get("/api/broker/status")).json()
        assert {n: after[n]["state"] for n in FOUR} == dict.fromkeys(FOUR, "disconnected")


async def test_a_session_past_its_expiry_reads_disconnected_through_the_route(app_engine, admin_engine, monkeypatch):
    """AC-4 attack 3: the database clock decides; the guard column is moved by the owner role as in the store tests."""
    user = _user()
    maker = async_sessionmaker(app_engine, class_=AsyncSession, expire_on_commit=False)
    app = _app(maker, user)
    monkeypatch.setattr(live_market, "_current", None)
    async with app_engine.begin() as conn:
        session_id = await store.store_session(conn, user, ACCESS_TOKEN, TokenCipher(os.urandom(32)))
    async with admin_engine.begin() as conn:
        await conn.execute(text("ALTER TABLE public.broker_sessions DISABLE TRIGGER broker_sessions_guard"))
        await conn.execute(text("UPDATE public.broker_sessions SET expected_expiry = clock_timestamp() "
                                "- interval '1 hour' WHERE id = :i"), {"i": session_id})
        await conn.execute(text("ALTER TABLE public.broker_sessions ENABLE TRIGGER broker_sessions_guard"))
    async with _client(app) as ac:
        body = (await ac.get("/api/broker/status")).json()
    got = {n: (body[n]["state"], body[n]["fix"]) for n in FOUR}
    assert got == dict.fromkeys(FOUR, ("disconnected", "session_expired"))


async def test_a_database_failure_is_a_typed_error_not_a_connected_page(app_engine, monkeypatch):
    """AC-4 (unknown/error state): a failed read never answers Connected; the page shows its error text."""
    user = _user()
    maker = async_sessionmaker(app_engine, class_=AsyncSession, expire_on_commit=False)
    app = _app(maker, user)

    async def _broken():
        raise RuntimeError("db down")
        yield  # pragma: no cover

    app.dependency_overrides[get_db] = _broken
    async with AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://t") as ac:
        response = await ac.get("/api/broker/status")
    assert response.status_code >= 500  # noqa: PLR2004
    assert "connected" not in response.text.lower().replace("not connected", "")


async def _market(state: str, finished: bool):
    """A real LiveMarket whose state word is ``state`` and whose socket task is finished or still running."""
    market = live_market.LiveMarket()
    market.state = state
    market._task = asyncio.get_running_loop().create_task(asyncio.sleep(0 if finished else 30))
    if finished:
        await market._task
    return market


async def test_a_live_state_with_a_finished_socket_task_is_not_connected(app_engine, monkeypatch):
    """AC-4: the route's feed-running input is `running()`, not the state word: LIVE with a done task is not Connected;
    LIVE with a running task is."""
    user = _user()
    maker = async_sessionmaker(app_engine, class_=AsyncSession, expire_on_commit=False)
    app = _app(maker, user)
    async with app_engine.begin() as conn:
        await store.store_session(conn, user, ACCESS_TOKEN, TokenCipher(os.urandom(32)))
    market = await _market(live_market.LIVE, finished=True)
    monkeypatch.setattr(live_market, "_current", market)
    async with _client(app) as ac:
        dead = (await ac.get("/api/broker/status")).json()
        assert dead["live_market_data"]["state"] == "partial" and dead["order_execution"]["state"] == "partial"
        live = await _market(live_market.LIVE, finished=False)
        monkeypatch.setattr(live_market, "_current", live)
        monkeypatch.setattr(live, "_fingerprint", b"x")
        alive = (await ac.get("/api/broker/status")).json()
        assert alive["live_market_data"] == {"state": "connected", "fix": None}
        live._task.cancel()
