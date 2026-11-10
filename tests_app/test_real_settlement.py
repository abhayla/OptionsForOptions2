"""GC-ICGUIDE g22 (audit C6): the real-strategy expiry step names every expired held leg; it never guesses a price.

Spec basis: ADR-083 (an expired leg is closed at the exchange settlement price; the source is unproven, so no price is
guessed), REQ-060 AC-2, ADR-016..019 (no silent fix). Real input: the recorded catalogue fixture of
test_execution_plan_store (REAL_SYMBOL NIFTY26O1322800CE, expiry 13 Oct 2026). DB tests need TEST_DATABASE_URL and
skip locally without it (CI's PostgreSQL); each runs inside a rolled-back transaction.
"""
from __future__ import annotations

import datetime
from decimal import Decimal as D

import pytest
from ofo.timeutil import IST
from ofo_app import order_book_store as books
from ofo_app import real_settlement as rs
from test_execution_plan_store import REAL_INSTRUMENT, _Tx
from test_order_book_store import _holding

AFTER = datetime.datetime(2026, 10, 14, 10, 0, tzinfo=IST)  # the day after the 13 Oct expiry
BEFORE = datetime.datetime(2026, 10, 1, 10, 0, tzinfo=IST)


async def _mine(tx, now, price_of=rs.no_stored_price):
    run = await rs.settle_expired_real(tx.conn, now, price_of)
    return run, [leg for leg in run.legs if leg.strategy_id == tx.strategy_id]


async def test_core_an_expired_real_leg_is_named_awaiting_settlement(app_engine):
    """Core: before the step nothing named the leg (0 callers); now one run names it AWAITING with the reason."""
    async with _Tx(app_engine) as tx:
        await books.record_adopted(tx.conn, tx.user, tx.strategy_id, _holding())
        _, mine = await _mine(tx, AFTER)
        assert [(leg.instrument_id, leg.units, leg.state, leg.reason) for leg in mine] == [
            (REAL_INSTRUMENT, 65, rs.AWAITING, rs.REASON_NO_PRICE)]
        assert mine[0].expiry == datetime.date(2026, 10, 13)


async def test_a_leg_on_a_live_contract_is_not_named(app_engine):
    async with _Tx(app_engine) as tx:
        await books.record_adopted(tx.conn, tx.user, tx.strategy_id, _holding())
        assert (await _mine(tx, BEFORE))[1] == []


async def test_price_stated_is_reported_priced_and_nothing_is_written(app_engine):
    async with _Tx(app_engine) as tx:
        await books.record_adopted(tx.conn, tx.user, tx.strategy_id, _holding())
        _, mine = await _mine(tx, AFTER, lambda _c: D("12.50"))
        assert [(leg.state, leg.reason) for leg in mine] == [(rs.PRICED, rs.REASON_NO_TABLE)]
        assert len(await books.adopted_for(tx.conn, tx.user, tx.strategy_id)) == 1


async def test_contract_not_in_the_catalogue_is_awaiting_with_its_own_reason(app_engine, monkeypatch):
    class Empty:
        def get(self, _id):
            return None

    async def empty(_conn):
        return Empty()

    async with _Tx(app_engine) as tx:
        await books.record_adopted(tx.conn, tx.user, tx.strategy_id, _holding())
        monkeypatch.setattr(rs, "load_catalogue", empty)
        _, mine = await _mine(tx, AFTER)
        assert [(leg.state, leg.reason) for leg in mine] == [(rs.AWAITING, rs.REASON_NO_CONTRACT)]


async def test_a_failed_read_writes_nothing_and_lists_the_strategy(app_engine, monkeypatch):
    async def boom(*_a):
        raise RuntimeError("db hiccup")

    async with _Tx(app_engine) as tx:
        await books.record_adopted(tx.conn, tx.user, tx.strategy_id, _holding())
        monkeypatch.setattr(rs.books, "adopted_for", boom)
        run, mine = await _mine(tx, AFTER)
        assert tx.strategy_id in run.failed and mine == []


async def test_a_second_run_answers_the_same_and_changes_nothing(app_engine):
    async with _Tx(app_engine) as tx:
        await books.record_adopted(tx.conn, tx.user, tx.strategy_id, _holding())
        first = (await _mine(tx, AFTER))[1]
        assert (await _mine(tx, AFTER))[1] == first


@pytest.mark.asyncio
async def test_main_starts_and_stops_the_real_step():
    import inspect  # noqa: PLC0415

    from ofo_app import main  # noqa: PLC0415
    src = inspect.getsource(main)
    assert "real_settlement.start_if(market)" in src and "real_settlement.stop(" in src
