"""GC-SET core proof: the risk-free rate a priced route uses is the ``pricing.risk_free_rate`` setting in force at the
request, read from the store with no restart (REQ-167 AC-1; ADR-222 (1), (9)).

Spec basis: REQ-167 AC-1 "the value in force at a time is the newest row not after that time, else the default";
ADR-222 (9) a change applies at the next check, no restart.

The app is built ONCE per test and asked twice: no row (the default 0.065) -> figure A; a 0.07 row effective now is
inserted in the SAME rolled-back transaction -> figure B != A, and the rate the engine received is 0.07. The settings
read goes through the test's connection (``get_settings_reader`` overridden), so the row is seen and never committed
(app_settings rows can never be deleted).
"""

from __future__ import annotations

import datetime
import pathlib
import sys
import types
from decimal import Decimal
from http import HTTPStatus

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from marketdata._kite_fixture import all_instrument_ids, new_provider, replay  # noqa: E402
from ofo.marketdata.kite_provider import IST  # noqa: E402

VALUATION = datetime.datetime(2026, 10, 8, 9, 20, 9, tzinfo=IST)
CONDOR = (("NSE_FO:44624", "SELL"), ("NSE_FO:44632", "BUY"), ("NSE_FO:44604", "SELL"), ("NSE_FO:44595", "BUY"))
KEY = "pricing.risk_free_rate"


@pytest.fixture(scope="module")
def replayed():
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    replay(provider, clock)
    return provider


def _body(provider):
    legs = [{"instrument_id": iid, "action": action, "lots": 1,
             "planned_entry": f"{provider.book.get(iid, VALUATION).ltp:f}", "captured_at": VALUATION.isoformat()}
            for iid, action in CONDOR]
    return {"underlying": "NIFTY", "legs": legs}


def _live(provider, monkeypatch):
    """A live market whose context is built like ``LiveMarket.attach`` (the registry default rate)."""
    from ofo import settings  # noqa: PLC0415
    from ofo_app import live_market  # noqa: PLC0415
    from ofo_app.routes import outcome  # noqa: PLC0415

    ctx = outcome.MarketContext(provider, lambda: VALUATION, settings.defaults()[settings.RISK_FREE_RATE])
    monkeypatch.setattr(live_market, "_current", types.SimpleNamespace(context=lambda: ctx, feed=None,
                                                                    running=lambda: False))  # no margin session
    used: list[Decimal] = []
    real = outcome.read_snapshot

    def spy(provider_, underlying, ids, valuation, rate, *a, **k):
        used.append(rate)
        return real(provider_, underlying, ids, valuation, rate, *a, **k)

    monkeypatch.setattr(outcome, "read_snapshot", spy)
    return used


def _app(session_or_conn):
    from ofo_app import settings_store  # noqa: PLC0415
    from ofo_app.main import create_app  # noqa: PLC0415
    from ofo_app.routes.outcome import get_settings_reader  # noqa: PLC0415

    app = create_app()

    async def read():
        return await settings_store.settings_in_force(session_or_conn)

    app.dependency_overrides[get_settings_reader] = lambda: read
    return app


def _figures(out: dict) -> dict:
    """The rate-dependent part of the answer (everything but the times)."""
    return {k: v for k, v in out.items() if "at" not in k.split("_")}


async def test_core_a_stored_rate_changes_the_priced_answer_with_no_restart(app_engine: AsyncEngine, replayed,
                                                                             monkeypatch):
    """Core: no row -> the default 0.065 prices the answer; a 0.07 row effective now -> the next request on the SAME
    app prices with 0.07 and the figures differ."""
    from ofo_app import settings_store  # noqa: PLC0415

    used = _live(replayed, monkeypatch)
    conn = await app_engine.connect()
    trans = await conn.begin()
    try:
        session = AsyncSession(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
        app = _app(session)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            first = await ac.post("/api/strategies/outcome", json=_body(replayed))
            assert first.status_code == HTTPStatus.OK, first.text
            assert used == [Decimal("0.065")]
            await settings_store.add_setting(session, KEY, "0.07", set_by="admin-test", correlation_id="gcset-core-1")
            second = await ac.post("/api/strategies/outcome", json=_body(replayed))
            assert second.status_code == HTTPStatus.OK, second.text
        assert used == [Decimal("0.065"), Decimal("0.07")]
        a, b = _figures(first.json()), _figures(second.json())
        assert a != b, "the stored rate did not change any figure"
        changed = sorted(k for k in a if a[k] != b.get(k))
        print("figures changed by the rate:", changed)  # the evidence line (pytest -s)
    finally:
        await trans.rollback()
        await conn.close()


async def test_the_live_feed_context_starts_at_the_registry_default(replayed):
    """ADR-222 (1): ``LiveMarket.attach`` takes its rate from the registry default (no literal in code); the priced
    REST reads replace it per request."""
    import asyncio  # noqa: PLC0415

    from ofo import settings  # noqa: PLC0415
    from ofo_app import live_market  # noqa: PLC0415

    class WaitingSocket:
        async def run(self):
            await asyncio.Event().wait()

        def stop(self):  # LiveMarket._halt calls it without awaiting
            return None

    market = live_market.LiveMarket()
    market.attach(replayed, WaitingSocket(), lambda: VALUATION)
    try:
        assert market.context().rate == settings.registry()[KEY].default == Decimal("0.065")
    finally:
        await market.stop()


async def test_no_live_market_reads_no_setting(monkeypatch):
    """No context: the dependency answers None and never reads the store (the "not connected" answer never waits on
    the database)."""
    from ofo_app import live_market  # noqa: PLC0415
    from ofo_app.routes.outcome import get_market_context  # noqa: PLC0415

    monkeypatch.setattr(live_market, "_current", None)

    async def must_not_read():
        raise AssertionError("read the store with no context")

    assert await get_market_context(must_not_read) is None


async def test_a_store_that_cannot_answer_fails_closed(replayed, monkeypatch):
    """SettingsError (a stored value the registry refuses) or a database error: the route answers an error, never
    a price with the default rate."""
    from ofo_app.main import create_app  # noqa: PLC0415
    from ofo_app.routes.outcome import get_settings_reader  # noqa: PLC0415
    from ofo_app.settings_store import SettingsError  # noqa: PLC0415

    used = _live(replayed, monkeypatch)
    for exc in (SettingsError("stored setting refused"), ConnectionRefusedError("db down")):
        app = create_app()

        async def broken(exc=exc):
            raise exc

        app.dependency_overrides[get_settings_reader] = lambda broken=broken: broken
        async with AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False),
                               base_url="http://test") as ac:
            resp = await ac.post("/api/strategies/outcome", json=_body(replayed))
        assert resp.status_code == HTTPStatus.INTERNAL_SERVER_ERROR, resp.text
        assert "0.065" not in resp.text
    assert used == []  # nothing was priced


async def test_the_production_reader_reads_the_store_through_the_app_database(app_engine, monkeypatch):
    """The un-overridden reader opens the app's own session (``db.get_sessionmaker``) and answers the registry
    defaults on an empty table (the conftest default patch is undone here)."""
    import os  # noqa: PLC0415

    from ofo_app import config, db  # noqa: PLC0415
    from ofo_app.routes import outcome  # noqa: PLC0415

    monkeypatch.undo()  # drop the conftest's "defaults, no database" patch for this test
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    for cached in (config.get_settings, db.get_engine, db.get_sessionmaker):
        cached.cache_clear()
    try:
        assert outcome.get_settings_reader() is outcome._settings_in_force_now
        assert (await outcome._settings_in_force_now())[KEY] == Decimal("0.065")
    finally:
        await db.get_engine().dispose()
        for cached in (config.get_settings, db.get_engine, db.get_sessionmaker):
            cached.cache_clear()


def test_a_rate_replaced_copy_is_the_same_feed_for_the_streaming_rule(replayed):
    """Issue #206's rule compares the request's context with the live feed's: the per-request copy with only the rate
    replaced is the same feed; another clock or owner is not."""
    import dataclasses  # noqa: PLC0415

    from ofo_app.routes.outcome import MarketContext, same_feed  # noqa: PLC0415

    def clock():
        return VALUATION

    live = MarketContext(replayed, clock, Decimal("0.065"), "owner")
    assert same_feed(dataclasses.replace(live, rate=Decimal("0.07")), live)
    assert not same_feed(dataclasses.replace(live, feed_owner="other"), live)
    assert not same_feed(dataclasses.replace(live, clock=lambda: VALUATION), live)
    assert not same_feed(live, None)


async def settings_add(session, value: str, correlation_id: str) -> None:
    from ofo_app import settings_store  # noqa: PLC0415

    await settings_store.add_setting(session, KEY, value, set_by="admin-test", correlation_id=correlation_id)


async def test_the_leg_picker_strikes_and_futures_price_with_the_stored_rate(app_engine: AsyncEngine, monkeypatch):
    """Finding 1 (Tier A review, MAJOR): ``/api/leg-picker/strikes`` (Greeks) and ``/futures`` (forward) price with the
    setting in force, not the feed's registry default. Same app, no row -> figures A; a 0.07 row -> figures B != A."""
    import test_leg_picker_routes as lp  # noqa: PLC0415
    from ofo_app import live_market  # noqa: PLC0415
    from ofo_app.routes import leg_picker, outcome  # noqa: PLC0415

    _provider, feed = lp.priced_provider()
    monkeypatch.setattr(live_market, "_current", types.SimpleNamespace(context=lambda: feed.ctx, feed=feed,
                                                                    running=lambda: False))
    conn = await app_engine.connect()
    trans = await conn.begin()
    try:
        session = AsyncSession(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
        app = _app(session)

        async def reader(_u, _e):
            return lp.catalogue()

        async def futures_reader(_u):
            return lp.futures_catalogue()

        app.dependency_overrides[leg_picker.get_feed] = lambda: feed
        app.dependency_overrides[outcome.get_answer_clock] = lambda: (lambda: lp.T0)
        app.dependency_overrides[leg_picker.get_picker_reader] = lambda: reader
        app.dependency_overrides[leg_picker.get_futures_reader] = lambda: futures_reader
        strikes_q = {"underlying": "NIFTY", "expiry": lp.EXPIRY.isoformat(), "width": 10}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            s1 = await ac.get("/api/leg-picker/strikes", params=strikes_q)
            f1 = await ac.get("/api/leg-picker/futures", params={"underlying": "NIFTY"})
            await settings_add(session, "0.07", "gcset-core-lp")
            s2 = await ac.get("/api/leg-picker/strikes", params=strikes_q)
            f2 = await ac.get("/api/leg-picker/futures", params={"underlying": "NIFTY"})
        for resp in (s1, f1, s2, f2):
            assert resp.status_code == HTTPStatus.OK, resp.text
        assert s1.json()["rows"] != s2.json()["rows"], "strikes ignored the stored rate"
        assert [f["forward"] for f in f1.json()["forwards"]] != [f["forward"] for f in f2.json()["forwards"]], \
            "futures forward ignored the stored rate"
    finally:
        await trans.rollback()
        await conn.close()


async def test_the_production_reader_returns_a_stored_row_not_only_defaults(app_engine, monkeypatch):
    """Finding 6: a reader that always answered the defaults would pass the empty-table test. Here a 0.07 row is added
    on a rolled-back connection; the un-overridden reader (its sessionmaker bound to that connection) returns 0.07."""
    from ofo_app import db  # noqa: PLC0415
    from ofo_app.routes import outcome  # noqa: PLC0415

    conn = await app_engine.connect()
    trans = await conn.begin()
    try:
        def bound_maker():
            return lambda: AsyncSession(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)

        monkeypatch.undo()  # drop the conftest's "defaults, no database" patch
        monkeypatch.setattr(db, "get_sessionmaker", bound_maker)
        assert outcome.get_settings_reader() is outcome._settings_in_force_now
        assert (await outcome._settings_in_force_now())[KEY] == Decimal("0.065")  # no row yet: the default
        async with AsyncSession(bind=conn, join_transaction_mode="create_savepoint",
                                expire_on_commit=False) as writer:
            await settings_add(writer, "0.07", "gcset-core-reader")
            await writer.commit()  # releases the savepoint into the test transaction (closing would roll it back)
        assert (await outcome._settings_in_force_now())[KEY] == Decimal("0.07")
    finally:
        await trans.rollback()
        await conn.close()


async def test_the_context_carries_the_stored_forward_quality_width(app_engine: AsyncEngine, replayed, monkeypatch):
    """REQ-167 AC-5: ``get_market_context`` hands the request a ``forward_quality`` whose width is the
    ``pricing.forward_quality_width`` setting in force: the default 0.05 with no row, the stored 0.08 after a row."""
    from ofo import settings  # noqa: PLC0415
    from ofo_app import settings_store  # noqa: PLC0415
    from ofo_app.routes.outcome import get_market_context  # noqa: PLC0415

    _live(replayed, monkeypatch)
    width_key = "pricing.forward_quality_width"
    conn = await app_engine.connect()
    trans = await conn.begin()
    try:
        session = AsyncSession(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)

        async def read():
            return await settings_store.settings_in_force(session)

        before = await get_market_context(read)
        assert before is not None
        assert before.forward_quality.width == settings.registry()[width_key].default == Decimal("0.05")
        await settings_store.add_setting(session, width_key, "0.08", set_by="admin-test",
                                         correlation_id="gcset-fwd-width")
        after = await get_market_context(read)
        assert after is not None
        assert after.forward_quality.width == Decimal("0.08")
    finally:
        await trans.rollback()
        await conn.close()
