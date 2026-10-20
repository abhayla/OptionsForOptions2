"""#380-2 on the database (REQ-060 AC-6/AC-7; Q222; Q224; ADR-109 (2); fix-380 draft T3; #423): the ONE reconciler both
routes call, on the owner's REAL 2026-10-19 Kite replies, against stored strategies, plans and mismatches.

Real inputs (tests/fixtures/kite_replies/, README there): ``orders-2026-10-19-roundtrip.json`` (OFS9V1L0 BUY 65
NIFTY26OCT24000CE COMPLETE, OFS9V2L0 SELL 65 COMPLETE) and ``positions-2026-10-19-roundtrip.json`` (Zerodha's net row
quantity 0). The strategy here gets the database's id, so the real rows are re-tagged from ``OFS9V`` to its own prefix
(nothing else changes). Only plan 1 (BUY 65) is stored, as when the exit was done on Kite by hand: by hand from ADR-109
("Kite 0 -> blocked"), the strategy is blocked with ONE mismatch, expected 65, Zerodha 0.

What each route passes (read from the routes): the Execute route calls ``reconcile_account(..., source=None)`` and
blocks on ``attribution.blocked``; the return route calls it with ``source="after_execution"`` and blocks on
``Verdict.blocks``. Both calls are made here on one stored account and must give the same verdict.

Database tests need TEST_DATABASE_URL / TEST_ADMIN_DATABASE_URL and skip locally without them. All but the lock test
run in a rolled-back transaction; the lock test commits (a second connection sees only committed rows) and removes
exactly its own rows afterwards through the owner role.
"""
from __future__ import annotations

import asyncio
import datetime

import pytest
from ofo.engine import Action
from ofo.execution.basket import make_tag
from ofo.instruments.models import ZERODHA
from ofo.reconciliation.compare import MismatchKind
from ofo.strategy import stored_form as sf
from ofo_app import execution_plan_store as plans
from ofo_app import reconcile_attribution as ra
from ofo_app import reconciliation_store as rs
from ofo_app import route_reconciliation as rr
from ofo_app import strategy_store as store
from ofo_app.catalogue_store import apply_update, load_catalogue
from sqlalchemy import text
from test_execution_plan_store import SYMBOLS, _new_strategy, _remove_own_rows, _user
from test_route_reconciliation import AT, listed
from test_route_reconciliation import _recorded as recorded

SYMBOL = "NIFTY26OCT24000CE"
HELD = 65  # plan 1's real fill (OFS9V1L0 COMPLETE 65)
LOCK_WAIT_S = 1.0
FINISH_S = 10


def _clock() -> datetime.datetime:
    return AT


def _orders_for(sid: int) -> list:
    """The real order rows re-tagged to strategy ``sid`` (the stored strategy cannot have id 9)."""
    rows = recorded("orders-2026-10-19-roundtrip")
    return [{**row, "tag": row["tag"].replace("OFS9V", f"OFS{sid}V", 1)} for row in rows]


async def _hand_exit_account(conn, user: str) -> tuple[int, object]:
    """Strategy on the real contract with plan 1 (BUY 65) stored and closed filled 65 (Zerodha's own answer)."""
    await apply_update(conn, [listed()], as_of=datetime.datetime(2026, 10, 19, 9, 0, tzinfo=AT.tzinfo))
    catalogue = await load_catalogue(conn)
    (entry,) = catalogue.entries_for_broker_symbol(ZERODHA, SYMBOL)
    contract_id = (await conn.execute(text(
        "SELECT c.id FROM public.catalogue_contracts c JOIN public.broker_instruments b ON b.contract_id = c.id "
        "WHERE b.broker = 'zerodha' AND b.broker_symbol = :s AND NOT c.retired"), {"s": SYMBOL})).scalar_one()
    saved = await store.build_definition(conn, "NIFTY", [sf.LegChoice(int(contract_id), Action.BUY, HELD)])
    sid = (await store.save_draft(conn, user, saved)).id
    instrument = f"{entry.id.exchange_segment}:{entry.id.exchange_token}"
    tag = make_tag(sid, 1, 0)
    (row,) = [r for r in _orders_for(sid) if r["tag"] == tag]
    order = plans.PlanOrder(0, tag, instrument, SYMBOL, "BUY", HELD, row["price"])
    await plans.record_plan(conn, user, sid, 1, "ENTRY", (order,))
    await plans.close_plan(conn, user, sid, 1, reason="filled", filled={tag: HELD})
    return sid, catalogue


async def _reconcile(conn, user, catalogue, sid, source):
    return await rr.reconcile_account(conn, user, catalogue, recorded("positions-2026-10-19-roundtrip"),
                                      _orders_for(sid), at=AT, clock=_clock, source=source)


async def test_core_both_routes_give_the_same_verdict_and_store_exactly_one_mismatch(app_engine):
    """T3 core on the database: Execute's call (source None) and the return's call (after_execution) on one stored
    account give the same blocked set and the same mismatch row; Execute stores nothing; the return stores ONE row
    (expected 65, Zerodha 0, missing platform position), and a second return keeps the same id (Q222, sticky);
    Execute after it is still blocked by the stored row."""
    user = _user()
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            sid, catalogue = await _hand_exit_account(conn, user)
            execute = await _reconcile(conn, user, catalogue, sid, None)
            assert execute.stored_ids == () and await rs.mismatches_for(conn, user, sid) == ()
            returned = await _reconcile(conn, user, catalogue, sid, "after_execution")
            assert execute.attribution.blocked == returned.attribution.blocked == frozenset({str(sid)})
            assert execute.blocks(sid) and returned.blocks(sid)
            expected_row = rr.StoredRow(sid, execute.rows[0].contract_key, HELD, 0,
                                        MismatchKind.MISSING_PLATFORM_POSITION)
            assert execute.rows == returned.rows == (expected_row,)
            (stored,) = await rs.mismatches_for(conn, user, sid)
            assert (stored.id,) == returned.stored_ids
            assert (stored.expected_units, stored.zerodha_units, stored.source) == (HELD, 0, "after_execution")
            assert stored.report["code"] == "recon_missing_platform_position"
            again = await _reconcile(conn, user, catalogue, sid, "after_execution")
            assert again.stored_ids == returned.stored_ids
            assert len(await rs.mismatches_for(conn, user, sid)) == 1
            later = await _reconcile(conn, user, catalogue, sid, None)
            assert later.blocks(sid)  # the stored row blocks the next Execute press (Q222)
        finally:
            await trans.rollback()


async def test_a_forged_net_or_verdict_cannot_reach_the_store(app_engine):
    """Finding caller-supplied-verdict-trusted: the routes' call has no parameter for a net, held units or a verdict
    (a forged one is a TypeError before anything is read), and the stored Zerodha units are the reply's own 0."""
    user = _user()
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            sid, catalogue = await _hand_exit_account(conn, user)
            for forged in ({"net": {}}, {"zerodha_net": {}}, {"verdict": None}, {"blocked": frozenset()}):
                with pytest.raises(TypeError):
                    await rr.reconcile_account(conn, user, catalogue, recorded("positions-2026-10-19-roundtrip"),
                                               _orders_for(sid), at=AT, clock=_clock, source="after_execution",
                                               **forged)
            assert await rs.mismatches_for(conn, user, sid) == ()
            with pytest.raises(ra.AttributionError):  # a source outside the closed list stores nothing
                await _reconcile(conn, user, catalogue, sid, "forged_source")
            await _reconcile(conn, user, catalogue, sid, "after_execution")
            (stored,) = await rs.mismatches_for(conn, user, sid)
            assert (stored.expected_units, stored.zerodha_units) == (HELD, 0)
        finally:
            await trans.rollback()


async def test_two_requests_of_one_user_on_two_strategies_wait_on_the_user_lock_never_deadlock(app_engine,
                                                                                              admin_engine):
    """Q224 / #423 item 2: each route takes ``lock_user`` before its strategy row lock, and the reconciler row-locks
    every strategy of the user. Request 1 (strategy A) holds the user lock and every strategy row; request 2
    (strategy B) waits at the user lock (mutation 'drop lock_user': it would take B's row lock at once and then
    deadlock against request 1's reconciliation), then finishes once request 1 commits."""
    user, ids = _user(), []
    empty = {"net": [], "day": []}
    try:
        async with app_engine.connect() as setup:
            async with setup.begin():
                first_sid = await _new_strategy(setup, user)
                second_sid = await _new_strategy(setup, user, catalogue=False)
            ids = [int(r[0]) for r in (await setup.execute(text(
                "SELECT c.id FROM public.broker_instruments b JOIN public.catalogue_contracts c "
                "ON c.id = b.contract_id WHERE b.broker = 'zerodha' AND b.broker_symbol = ANY(:s)"),
                {"s": SYMBOLS})).all()]
        async with app_engine.connect() as first, app_engine.connect() as second:
            t1, t2 = await first.begin(), await second.begin()
            catalogue = await load_catalogue(first)

            async def request(conn, sid):
                await rr.lock_user(conn, user)  # the route's order: the user lock, then the strategy row lock
                await store.lock_strategy(conn, user, sid)
                return await rr.reconcile_account(conn, user, catalogue, empty, [], at=AT, clock=_clock,
                                                  source="after_execution")

            one = await request(first, first_sid)
            waiter = asyncio.create_task(request(second, second_sid))
            await asyncio.sleep(LOCK_WAIT_S)
            assert not waiter.done(), "the second request must wait at the user lock"
            await t1.commit()
            two = await asyncio.wait_for(waiter, FINISH_S)
            assert one.attribution.blocked == two.attribution.blocked == frozenset()
            await t2.rollback()
    finally:
        await _remove_own_rows(admin_engine, ids, user)
