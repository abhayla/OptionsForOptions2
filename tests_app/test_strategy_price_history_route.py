"""GC-UI step 5 server (D-B40 / D-B41; REQ-091 AC-1..AC-6 as rewritten by ADR-203; F-64): the Strategy Chart's route.

``GET /strategies/{id}/price-history?invert=&days=``. Kite is never called: ``KiteHistory`` runs with an injected
transport that answers the REAL recorded F-64 bodies (2026-10-14, tests/fixtures/kite_history). The saved strategy is
the 4-leg condor of test_strategy_store; the transport gives SELL 22800 CE the real 25000 CE body and the other three
legs the real NIFTY Nov FUT body, so the combined price per unit is 5.40 - 22841.10 + 22841.10 - 22841.10 = -22835.70
at 09:15 and every minute the option body lacks is a gap (83 of 375). The future finder answers the WING contract as a
stand-in row (the recorded catalogue has no FUT row); its label prints its own expiry.

Real PostgreSQL only (ADR-048); every test rolls back.
"""
from __future__ import annotations

import asyncio
import datetime
import io
import os
import threading
from decimal import Decimal
from http import HTTPStatus
from pathlib import Path

import pytest
from ofo.timeutil import IST
from ofo_app import broker_token_store as tokens
from ofo_app import held_switches, kite_history
from ofo_app import strategy_price_history as sph
from ofo_app import strategy_store as store
from ofo_app.broker_config import load_broker_config
from ofo_app.broker_crypto import TokenCipher
from ofo_app.catalogue_store import apply_update, parse_rows_naming_the_row
from ofo_app.kite_history import KiteHistory
from ofo_app.live_market import OWNER_REF
from ofo_app.routes import strategies as strategy_routes
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from test_strategy_followups import _ConnMaker
from test_strategy_store import (
    WING,
    _app,
    _client,
    _fixture_rows,
    _ids,
    _remove_own_rows,
    _saved_in,
    _user,
    _with_draft,
)

FIX = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "kite_history"
LEG_BODY = (FIX / "minute-NIFTY26N0325000CE-2026-10-14.json").read_text(encoding="utf-8")
FUT_BODY = (FIX / "minute-NIFTY26NOVFUT-2026-10-14.json").read_text(encoding="utf-8")
EMPTY_BODY = '{"status": "success", "data": {"candles": []}}'
SECRET = "SECRETTOKEN123"  # noqa: S105 - a fake token the replies and logs must never carry
NOW = datetime.datetime(2026, 10, 14, 15, 35, tzinfo=IST)
FUTURE_MINUTES, GAPS = 375, 83
NOT_FOUND_CODE = "USER_INPUT_003"


def _token(symbol: str) -> str:
    return str(_fixture_rows([symbol])[0].ref("zerodha").broker_token)


@pytest.fixture(autouse=True)
def _fresh_cache(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")  # the held flag is on only in development / test (held_switches)
    sph._cache.clear()
    yield
    sph._cache.clear()


def _transport(by_token: dict[str, tuple[int, str]], default: tuple[int, str], seen: list[str]):
    def fetch(url: str, headers: dict[str, str]) -> tuple[int, str]:
        seen.append(url)
        token = url.split("/historical/")[1].split("/", maxsplit=1)[0]
        return by_token.get(token, default)
    return fetch


def _app_with(conn, user, *, transport=None, session=True, future=True):
    app = _app(_ConnMaker(conn), user)

    async def opener(_db):
        if not session:
            return None
        return lambda listed: KiteHistory(listed, api_key="k", access_token=SECRET, transport=transport).minute_candles

    async def finder(_db, _underlying):
        return _fixture_rows([WING])[0] if future else None

    app.dependency_overrides[strategy_routes.get_history_opener] = lambda: opener
    app.dependency_overrides[strategy_routes.get_future_finder] = lambda: finder
    app.dependency_overrides[strategy_routes.get_history_now] = lambda: NOW
    return app


def _standard(seen, **override):
    by = {_token("NIFTY26O1322800CE"): (200, LEG_BODY), _token(WING): (200, FUT_BODY)} | override
    return _transport(by, (200, FUT_BODY), seen)


async def _get(conn, user, sid, query="", **kw):
    async with _client(_app_with(conn, user, **kw)) as ac:
        return await ac.get(f"/strategies/{sid}/price-history{query}")


async def test_available_on_the_real_bodies_and_invert_and_cache(app_engine):
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            _, stored = await _with_draft(conn, user := _user())
            seen: list[str] = []
            app = _app_with(conn, user, transport=_standard(seen))
            async with _client(app) as ac:
                body = (await ac.get(f"/strategies/{stored.id}/price-history")).json()
                inverted = (await ac.get(f"/strategies/{stored.id}/price-history?invert=true")).json()
            assert body["available"] is True and body["state"] == "available" and body["reason"] is None
            assert body["source"] == "Kite historical 1-minute candles"
            assert body["future_label"] == "NIFTY 13 Oct FUT"
            assert body["notes"] == [] and len(body["points"]) == FUTURE_MINUTES
            first = body["points"][0]
            assert first == {"t": "2026-10-14T09:15:00+05:30",
                             "strategy": {"value": "-22835.7", "display": "-22835.70"},
                             "future": {"value": "22841.1", "display": "22,841.10"}}
            assert sum(p["strategy"] is None for p in body["points"]) == GAPS
            assert body["as_of"] == "2026-10-14T15:29:00+05:30"
            assert Decimal(inverted["points"][0]["strategy"]["value"]) == Decimal("22835.7")
            assert inverted["points"][0]["future"] == first["future"]  # Invert flips the strategy only
            assert len(seen) == 5  # noqa: PLR2004 - 4 legs + the future, once: the Invert call read the cache
            assert all("/minute?" in u for u in seen)
            assert SECRET not in str(body) + str(inverted)
        finally:
            await trans.rollback()


async def test_another_users_strategy_answers_as_not_found(app_engine):
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            _, stored = await _with_draft(conn, _user())
            other = await _get(conn, _user(), stored.id, transport=_standard([]))
            missing = await _get(conn, _user(), 987654321, transport=_standard([]))
            assert other.status_code == missing.status_code == HTTPStatus.NOT_FOUND
            assert other.json() == missing.json() and NOT_FOUND_CODE in other.text
        finally:
            await trans.rollback()


async def test_flag_off_refuses_before_any_read(app_engine, monkeypatch):
    monkeypatch.setattr(held_switches, "held_on", lambda name, environ=None: False)
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            _, stored = await _with_draft(conn, user := _user())
            seen: list[str] = []
            resp = await _get(conn, user, stored.id, transport=_standard(seen))
            assert resp.status_code == HTTPStatus.CONFLICT
            assert "The strategy chart is not available." in resp.text and seen == []
        finally:
            await trans.rollback()


@pytest.mark.parametrize(("kw", "state", "reason"), [
    ({"session": False}, "no_session", "Connect Zerodha to see the strategy chart."),
    ({"future": False}, "future_not_in_catalogue", "No index future is listed in the stored instrument list."),
    ({"refuse": (429, "")}, "broker_refused", "Zerodha did not return the price history. Try again later."),
    ({"refuse": (500, "")}, "broker_refused", "Zerodha did not return the price history. Try again later."),
    ({"refuse": (200, "not json")}, "broker_refused", "Zerodha did not return the price history. Try again later."),
    ({"leg_empty": True}, "leg_not_listed", "NIFTY26O1322800CE has no prices in this window."),
    ({"future_empty": True}, "no_future_candles", "The index future has no prices in this window."),
])
async def test_answer_states(app_engine, caplog, kw, state, reason):
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            _, stored = await _with_draft(conn, user := _user())
            override = {}
            if "refuse" in kw:
                override = {_token("NIFTY26O1322800CE"): kw.pop("refuse")}
            if kw.pop("leg_empty", False):
                override = {_token("NIFTY26O1322800CE"): (200, EMPTY_BODY)}
            if kw.pop("future_empty", False):
                override = {_token(WING): (200, EMPTY_BODY)}
            resp = await _get(conn, user, stored.id, transport=_standard([], **override), **kw)
            body = resp.json()
            assert resp.status_code == HTTPStatus.OK, resp.text
            assert (body["available"], body["state"], body["reason"], body["points"], body["as_of"]) == (
                False, state, reason, [], None)
            assert SECRET not in resp.text and SECRET not in caplog.text and "api.kite" not in caplog.text
        finally:
            await trans.rollback()


async def test_days_outside_1_to_15_is_refused(app_engine):
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            _, stored = await _with_draft(conn, user := _user())
            for q in ("?days=0", "?days=16"):
                assert (await _get(conn, user, stored.id, q, transport=_standard([]))).status_code >= 400  # noqa: PLR2004
        finally:
            await trans.rollback()


# ---- S5-1: the production seams run for real (no opener / finder fake; only Kite's HTTP transport is faked) ----
# The route runs as in production: a real AsyncSession per request (a fresh connection, as ``get_db`` gives), the
# owner's session stored ENCRYPTED by the store's own write, the real token read and the real catalogue FUT pick. The
# rows are COMMITTED (the request's own session must see them) and removed after.

LIST_DAY = datetime.date(2026, 10, 8)
AS_OF = datetime.datetime(2026, 10, 8, 9, 0, tzinfo=IST)
FUT_CSV = Path(__file__).resolve().parent / "fixtures" / "zerodha_instruments_nifty_sensex_2026-10-02.csv"
NOV_FUT = "NIFTY26NOVFUT"  # real row: 15736578,61471,NIFTY26NOVFUT,NIFTY,0,2026-11-23,0,0.1,65,FUT,NFO-FUT,NFO
NO_SESSION_REASON = "Connect Zerodha to see the strategy chart."


def _nov_future():
    lines = [ln for ln in FUT_CSV.read_text(encoding="utf-8").splitlines() if not ln.startswith("#")]
    row = next(ln for ln in lines if f",{NOV_FUT}," in ln)
    return list(parse_rows_naming_the_row(io.StringIO(f"{lines[0]}\n{row}\n")))


async def _committed_seed(app_engine, user: str, *, session: str | None):
    """Commits the recorded catalogue + the real NIFTY Nov FUT row, one saved strategy and (``session``) the owner's
    session written by the store itself. Returns (strategy id, new contract ids, session id)."""
    async with app_engine.connect() as conn:
        before = {r[0] for r in await conn.execute(text("SELECT id FROM public.catalogue_contracts"))}
        await conn.rollback()  # end the read's autobegun transaction; the seed commits in its own
        async with conn.begin():
            await apply_update(conn, _fixture_rows() + _nov_future(), as_of=AS_OF)
            stored = await store.save_draft(conn, user, await _saved_in(conn, user, await _ids(conn)))
            session_id = None
            if session is not None:
                session_id = await tokens.store_session(conn, OWNER_REF, session,
                                                        TokenCipher(load_broker_config().token_key))
        after = {r[0] for r in await conn.execute(text("SELECT id FROM public.catalogue_contracts"))}
    return stored.id, sorted(after - before), session_id


async def _remove_seed(admin_engine, user: str, contract_ids: list[int], session_id: int | None) -> None:
    await _remove_own_rows(admin_engine, contract_ids, user)
    if session_id is not None:
        async with admin_engine.connect() as conn, conn.begin():
            await conn.execute(text("SET LOCAL session_replication_role = replica"))
            await conn.execute(text("DELETE FROM public.broker_sessions WHERE id = :id"), {"id": session_id})


def _real_app(app_engine, user: str):
    """The production dependencies except "now" (the recorded day): no opener, no finder override."""
    app = _app(async_sessionmaker(app_engine, class_=AsyncSession, expire_on_commit=False), user)
    app.dependency_overrides[strategy_routes.get_history_now] = lambda: NOW
    return app


@pytest.fixture
def real_kite_transport(monkeypatch):
    """Kite's HTTP transport is the ONLY fake: the real recorded F-64 bodies, by Kite instrument token."""
    monkeypatch.setenv("TEST_CATALOGUE_DATE", LIST_DAY.isoformat())  # the recorded list's own day (pinned clock)
    seen: list[str] = []
    monkeypatch.setattr(kite_history, "urllib_transport", _standard(seen))
    return seen


async def _real_get(app_engine, admin_engine, *, session: str | None, before_get=None):
    user = _user()
    cids, session_id = [], None
    try:
        sid, cids, session_id = await _committed_seed(app_engine, user, session=session)
        if before_get is not None:
            await before_get(admin_engine, session_id)
        async with _client(_real_app(app_engine, user)) as ac:
            resp = await ac.get(f"/strategies/{sid}/price-history")
        ended = None
        if session_id is not None:
            async with admin_engine.connect() as conn:
                ended = (await conn.execute(text("SELECT end_reason FROM public.broker_sessions WHERE id = :id"),
                                            {"id": session_id})).scalar_one()
        return resp, ended
    finally:
        await _remove_seed(admin_engine, user, cids, session_id)


async def test_s5_1_real_token_read_and_real_future_pick_answer_available(app_engine, admin_engine, caplog,
                                                                          real_kite_transport):
    """Core proof of S5-1: before the fix this answered 500 (token_read_needs_fresh_connection)."""
    resp, ended = await _real_get(app_engine, admin_engine, session=SECRET)
    assert resp.status_code == HTTPStatus.OK, resp.text
    body = resp.json()
    assert (body["available"], body["state"], body["reason"]) == (True, "available", None)
    assert body["future_label"] == "NIFTY 23 Nov FUT"  # the real nearest FUT row of the stored catalogue
    assert len(body["points"]) == FUTURE_MINUTES
    assert sum(p["strategy"] is None for p in body["points"]) == GAPS
    assert body["points"][0]["future"] == {"value": "22841.1", "display": "22,841.10"}
    assert len(real_kite_transport) == 5  # noqa: PLR2004 - 4 legs + the future, each once
    assert f"/historical/{_nov_future()[0].ref('zerodha').broker_token}/minute?" in "".join(real_kite_transport)
    assert ended is None  # the read did not end the live session
    assert SECRET not in resp.text and SECRET not in caplog.text


async def _past_expiry(admin_engine, session_id):
    async with admin_engine.connect() as conn, conn.begin():
        await conn.execute(text("SET LOCAL session_replication_role = replica"))
        await conn.execute(text("UPDATE public.broker_sessions SET expected_expiry = clock_timestamp() - "
                                "interval '1 minute' WHERE id = :id"), {"id": session_id})


def _no_session_answer(resp) -> None:
    assert resp.status_code == HTTPStatus.OK, resp.text
    body = resp.json()
    assert (body["available"], body["state"], body["reason"], body["points"]) == (
        False, "no_session", NO_SESSION_REASON, [])
    assert body["future_label"] == "NIFTY 23 Nov FUT"


async def test_s5_1_no_stored_session_answers_no_session(app_engine, admin_engine, real_kite_transport):
    resp, _ = await _real_get(app_engine, admin_engine, session=None)
    _no_session_answer(resp)
    assert real_kite_transport == []  # Kite is never called without a session


async def test_s5_1_a_session_past_expiry_is_ended_by_the_store_and_answers_no_session(app_engine, admin_engine,
                                                                                      real_kite_transport, caplog):
    resp, ended = await _real_get(app_engine, admin_engine, session=SECRET, before_get=_past_expiry)
    _no_session_answer(resp)
    assert ended == "expired"  # the store ended it, committed on the request's own (fresh) connection
    assert real_kite_transport == [] and SECRET not in resp.text and SECRET not in caplog.text


async def test_s5_1_a_token_store_error_answers_no_session_with_its_code_never_500(app_engine, admin_engine,
                                                                                    real_kite_transport, caplog,
                                                                                    monkeypatch):
    async def refuses(*_a, **_k):
        raise tokens.BrokerStoreError("token_read_needs_fresh_connection")
    monkeypatch.setattr(tokens, "access_token_for", refuses)
    resp, ended = await _real_get(app_engine, admin_engine, session=SECRET)
    _no_session_answer(resp)
    assert ended is None and real_kite_transport == []
    assert "store refused: token_read_needs_fresh_connection" in caplog.text  # the reason, by code only
    assert SECRET not in resp.text and SECRET not in caplog.text


# ---- F1 (GC-UI step 9 review round 1): no request DB connection is held while Kite answers --------------------------
# A REAL pooled engine (the API's shape: QueuePool, overflow 0) runs the production route; Kite's transport is a fake
# that BLOCKS until the test releases it. While it blocks, the pool must show 0 connections checked out and another
# DB request on the same pool must complete. Before the fix the route kept its connection until every call returned.

def _pooled(size: int):
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is unset")
    return create_async_engine(url, pool_size=size, max_overflow=0, pool_timeout=5,
                               connect_args={"server_settings": {"jit": "off"}})


def _blocking_transport(started, release, seen: list[str]):
    answer = _standard([])

    def fetch(url: str, headers: dict[str, str]) -> tuple[int, str]:
        seen.append(url)
        started.set()
        release.wait(20)
        return answer(url, headers)
    return fetch


@pytest.fixture
def blocking_kite(monkeypatch):
    monkeypatch.setenv("TEST_CATALOGUE_DATE", LIST_DAY.isoformat())
    started, release, seen = threading.Event(), threading.Event(), []
    monkeypatch.setattr(kite_history, "urllib_transport", _blocking_transport(started, release, seen))
    yield started, release, seen
    release.set()


async def _seeded(app_engine, admin_engine, run):
    user = _user()
    cids, session_id = [], None
    try:
        sid, cids, session_id = await _committed_seed(app_engine, user, session=SECRET)
        return await run(user, sid)
    finally:
        await _remove_seed(admin_engine, user, cids, session_id)


def _pooled_app(pooled, user):
    app = _app(async_sessionmaker(pooled, class_=AsyncSession, expire_on_commit=False), user)
    app.dependency_overrides[strategy_routes.get_history_now] = lambda: NOW
    return app


async def test_f1_no_connection_is_held_while_kite_answers(app_engine, admin_engine, blocking_kite):
    started, release, seen = blocking_kite
    pooled = _pooled(1)  # ONE connection: a held connection would starve every other request

    async def run(user, sid):
        async with _client(_pooled_app(pooled, user)) as ac:
            chart = asyncio.create_task(ac.get(f"/strategies/{sid}/price-history"))
            assert await asyncio.to_thread(started.wait, 15), "Kite was never called"
            held = pooled.pool.checkedout()
            async with pooled.connect() as conn:  # another request's DB work on the same one-connection pool
                other = await asyncio.wait_for(conn.scalar(text("SELECT 1")), 4)
            release.set()
            resp = await chart
        return held, other, resp
    try:
        held, other, resp = await _seeded(app_engine, admin_engine, run)
    finally:
        await pooled.dispose()
    assert held == 0, f"{held} connection(s) held while Kite answers"
    assert other == 1
    assert resp.status_code == HTTPStatus.OK, resp.text
    assert resp.json()["state"] == "available" and len(seen) == 5  # noqa: PLR2004


async def test_f1_two_identical_requests_share_one_fetch_per_contract(app_engine, admin_engine, blocking_kite):
    started, release, seen = blocking_kite
    pooled = _pooled(2)

    async def run(user, sid):
        async with _client(_pooled_app(pooled, user)) as ac:
            first = asyncio.create_task(ac.get(f"/strategies/{sid}/price-history"))
            assert await asyncio.to_thread(started.wait, 15)
            second = asyncio.create_task(ac.get(f"/strategies/{sid}/price-history?invert=true"))
            for _ in range(200):  # until the second request has joined the first's in-flight fetch
                if sph.joined_in_flight():
                    break
                await asyncio.sleep(0.02)
            release.set()
            return await first, await second
    try:
        one, two = await _seeded(app_engine, admin_engine, run)
    finally:
        await pooled.dispose()
    assert one.json()["state"] == two.json()["state"] == "available"
    assert sph.joined_in_flight() >= 1
    assert len(seen) == 5 and len(set(seen)) == 5  # noqa: PLR2004 - 4 legs + the future, each fetched ONCE


async def test_f1_a_fetch_past_the_deadline_answers_broker_refused(app_engine, admin_engine, blocking_kite,
                                                                   monkeypatch):
    _, _, seen = blocking_kite
    monkeypatch.setattr(sph, "FETCH_DEADLINE_SECONDS", 0.5)
    pooled = _pooled(1)

    async def run(user, sid):
        async with _client(_pooled_app(pooled, user)) as ac:
            return await ac.get(f"/strategies/{sid}/price-history")
    try:
        resp = await _seeded(app_engine, admin_engine, run)
    finally:
        await pooled.dispose()
    body = resp.json()
    assert resp.status_code == HTTPStatus.OK, resp.text
    assert (body["state"], body["reason"]) == ("broker_refused",
                                               "Zerodha did not return the price history. Try again later.")
    assert seen  # Kite was called; the deadline, not a refusal, ended it
