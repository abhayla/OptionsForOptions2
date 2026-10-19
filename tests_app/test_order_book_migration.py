"""#313: migration 0020's database guards (fill prices, adopted holdings). Database tests: they need
TEST_DATABASE_URL / TEST_ADMIN_DATABASE_URL, skip locally without them, and every test runs in a rolled-back
transaction (CI's PostgreSQL only; never the shared VPS database).

Spec basis: issue #313; ADR-096 (adopted holdings count as a fill would); ADR-109 / Q224 (a strategy owns the fills of
orders this app placed, matched by tag; two holders of one contract stay separate); ADR-048; ADR-023.

Each test names the guard it would lose: remove the guard and the test fails.
"""

from __future__ import annotations

import asyncio

import pytest
from ofo.execution.basket import make_tag
from ofo_app import execution_plan_store as plans
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_execution_plan_store import (
    CHECK_VIOLATION,
    INSUFFICIENT_PRIVILEGE,
    LOT,
    REAL_INSTRUMENT,
    SYMBOLS,
    UNIQUE_VIOLATION,
    _new_strategy,
    _order,
    _refused_sql,
    _remove_own_rows,
    _Tx,
    _user,
)

GUARD_SQLSTATE = "OF020"
TWO_HOLDERS = 2  # two strategies of one user, each holding the same contract (Q224)
ORDER_ID = "251019000000001"  # a Zerodha order id (15 digits)
OTHER_ORDER_ID = "251019000000002"
DUPLICATE_UNITS = 20  # a stored trade of 20 of 65: the same trade again still fits the sum, so the key refuses it
RACE_UNITS = 40  # two trades of 40 units against 65 filled: each fits alone, both together (80) do not
WAIT_SECONDS = 1.0
_FILL = ("INSERT INTO public.execution_plan_fills (tag, broker_order_id, trade_id, quantity, price) "  # noqa: S608 constant
         f"VALUES (:tag, '{ORDER_ID}', :tid, :q, :px)")
_FILL_OF = ("INSERT INTO public.execution_plan_fills (tag, broker_order_id, trade_id, quantity, price) "
            "VALUES (:tag, :oid, :tid, :q, :px)")
_HOLD = ("INSERT INTO public.adopted_holdings (strategy_id, instrument_id, transaction_type, quantity, product, "
         "average_price, reference, version_number) VALUES (:s, :iid, 'BUY', :q, 'NRML', :px, :ref, 1)")


async def _close(conn, _user: str, strategy_id: int, number: int, reason: str) -> None:
    """Closes a ONE-leg plan with the plan store's own two statements but WITHOUT its trades (#313b: ``close_plan``
    always stores them now), so these tests can insert trades by raw SQL against a filled order with none stored:
    the database guards must hold even when the store is bypassed."""
    filled = {"filled": LOT, "partial": LOT // 2, "nothing_placed": 0}[reason]
    tag = make_tag(strategy_id, number, 0)
    await conn.execute(plans._SET_FILLED, {"s": strategy_id, "p": number, "tag": tag, "f": filled})
    await conn.execute(plans._CLOSE, {"s": strategy_id, "p": number, "r": reason})


async def _filled_tag(tx, reason: str = "filled") -> str:
    plan = await tx.enter("ENTRY", "BUY", "7.00")
    await _close(tx.conn, tx.user, tx.strategy_id, plan.plan_number, reason)
    return make_tag(tx.strategy_id, plan.plan_number, 0)


async def test_fill_price_needs_an_order_that_filled(app_engine):
    """Guard: the fill trigger's filled_quantity > 0 check. A closed nothing_placed order (0 filled) and an open order
    (NULL) take no price; a filled one does, and its recorded_at is the database clock, not the caller's."""
    async with _Tx(app_engine) as tx:
        plan = await tx.enter("ENTRY", "BUY", "7.00")
        open_tag = make_tag(tx.strategy_id, plan.plan_number, 0)
        await _refused_sql(tx.conn, _FILL, GUARD_SQLSTATE, {"tag": open_tag, "tid": "1", "q": LOT, "px": "7.00"})
        await _close(tx.conn, tx.user, tx.strategy_id, plan.plan_number, "nothing_placed")
        await _refused_sql(tx.conn, _FILL, GUARD_SQLSTATE, {"tag": open_tag, "tid": "1", "q": LOT, "px": "7.00"})
        tag = await _filled_tag(tx)
        await tx.conn.execute(text(_FILL), {"tag": tag, "tid": "1", "q": LOT, "px": "7.00"})
        row = (await tx.conn.execute(text("SELECT price, recorded_at FROM public.execution_plan_fills "
                                          "WHERE tag = :t"), {"t": tag})).one()
        assert str(row.price) == "7.00" and row.recorded_at is not None


async def test_fill_price_is_positive_once_per_trade_and_only_for_a_known_tag(app_engine):
    """Guards: CHECK price > 0 and quantity >= 1, PRIMARY KEY (order id, trade id) (one row per trade), the trigger's
    unknown-tag refusal (it runs before the foreign key, which stays as a second layer), and the trigger's sum check
    (stored trades never exceed the order's filled quantity: 20 + 46 > 65). The duplicate trade is 20 units, so the
    sum check (which runs first, in the BEFORE trigger) passes and the PRIMARY KEY is what refuses it (#451 CI)."""
    async with _Tx(app_engine) as tx:
        tag = await _filled_tag(tx)
        await _refused_sql(tx.conn, _FILL, CHECK_VIOLATION, {"tag": tag, "tid": "1", "q": LOT, "px": "0"})
        await _refused_sql(tx.conn, _FILL, CHECK_VIOLATION, {"tag": tag, "tid": "1", "q": 0, "px": "7.00"})
        await tx.conn.execute(text(_FILL), {"tag": tag, "tid": "1", "q": DUPLICATE_UNITS, "px": "7.00"})
        await _refused_sql(tx.conn, _FILL, UNIQUE_VIOLATION, {"tag": tag, "tid": "1", "q": DUPLICATE_UNITS,
                                                             "px": "6.65"})
        await _refused_sql(tx.conn, _FILL, GUARD_SQLSTATE, {"tag": tag, "tid": "2", "q": LOT - DUPLICATE_UNITS + 1,
                                                            "px": "7.00"})
        await _refused_sql(tx.conn, _FILL, GUARD_SQLSTATE, {"tag": "OFS999999V1L0", "tid": "1", "q": LOT,
                                                            "px": "7.00"})


async def _filled_tag_of_another_strategy(tx) -> str:
    other = await _new_strategy(tx.conn, tx.user, catalogue=False)
    number = await plans.next_plan_number(tx.conn, tx.user, other)
    await plans.record_plan(tx.conn, tx.user, other, number, "ENTRY", (_order(other, number, "BUY", "7.00"),))
    await _close(tx.conn, tx.user, other, number, "filled")
    return make_tag(other, number, 0)


async def test_one_zerodha_trade_and_order_are_stored_under_one_tag_only(app_engine, admin_engine):
    """#313a finding 2 (ADR-109: a strategy owns exactly the fills of the orders this app placed). Guards: the
    trigger's one-tag-per-order check (a trade, or another trade of the same Zerodha order, under a second tag is
    refused) and the PRIMARY KEY (order id, trade id) without the tag (proved with the trigger off, as the owner, in a
    rolled-back transaction). A second trade of the same order under its own tag, and another order under tag B, are
    accepted."""
    async with _Tx(app_engine) as tx:
        tag_a = await _filled_tag(tx)
        tag_b = await _filled_tag_of_another_strategy(tx)
        await tx.conn.execute(text(_FILL), {"tag": tag_a, "tid": "1", "q": 20, "px": "7.00"})
        for tid in ("1", "2"):
            await _refused_sql(tx.conn, _FILL, GUARD_SQLSTATE, {"tag": tag_b, "tid": tid, "q": 20, "px": "7.00"})
        await tx.conn.execute(text(_FILL), {"tag": tag_a, "tid": "2", "q": 20, "px": "7.05"})
        await tx.conn.execute(text(_FILL_OF), {"tag": tag_b, "oid": OTHER_ORDER_ID, "tid": "1", "q": 20,
                                               "px": "7.00"})
        rows = (await tx.conn.execute(text("SELECT tag, broker_order_id, trade_id FROM public.execution_plan_fills "
                                           "WHERE tag IN (:a, :b) ORDER BY 1, 2, 3"),
                                      {"a": tag_a, "b": tag_b})).all()
        assert sorted(tuple(r) for r in rows) == sorted([(tag_a, ORDER_ID, "1"), (tag_a, ORDER_ID, "2"),
                                                         (tag_b, OTHER_ORDER_ID, "1")])
    async with _Tx(admin_engine) as tx:
        tag_a = await _filled_tag(tx)
        tag_b = await _filled_tag_of_another_strategy(tx)
        await tx.conn.execute(text(_FILL), {"tag": tag_a, "tid": "1", "q": 20, "px": "7.00"})
        await tx.conn.execute(text("ALTER TABLE public.execution_plan_fills DISABLE TRIGGER USER"))
        await _refused_sql(tx.conn, _FILL, UNIQUE_VIOLATION, {"tag": tag_b, "tid": "1", "q": 20, "px": "7.00"})


async def test_a_fill_outside_read_committed_is_refused(app_engine):
    """Guard: the trigger's isolation check. Under REPEATABLE READ the order lock would not make the sum see a
    concurrent writer's committed trade (the snapshot is the transaction's), so the insert is refused outright."""
    async with app_engine.connect() as conn:
        rr = await conn.execution_options(isolation_level="REPEATABLE READ")
        trans = await rr.begin()
        try:
            with pytest.raises(DBAPIError) as err:
                await rr.execute(text(_FILL), {"tag": "OFS999999V1L0", "tid": "1", "q": 1, "px": "7.00"})
            assert getattr(err.value.orig, "sqlstate", None) == GUARD_SQLSTATE
            assert "need READ COMMITTED" in str(err.value)
        finally:
            await trans.rollback()


async def _remove_own_fills_and_rows(admin_engine, contract_ids: list[int], user_ref: str) -> None:
    """This test's committed trades first (the insert-only guard off for one transaction, as the table owner), then
    the plan-store helper removes the rest."""
    async with admin_engine.connect() as conn:  # noqa: SIM117
        async with conn.begin():
            await conn.execute(text("ALTER TABLE public.execution_plan_fills DISABLE TRIGGER USER"))
            await conn.execute(text(
                "DELETE FROM public.execution_plan_fills WHERE tag IN (SELECT o.tag "
                "FROM public.execution_plan_orders o JOIN public.strategies s ON s.id = o.strategy_id "
                "WHERE s.user_ref = :u)"), {"u": user_ref})
            await conn.execute(text("ALTER TABLE public.execution_plan_fills ENABLE TRIGGER USER"))
    await _remove_own_rows(admin_engine, contract_ids, user_ref)


async def test_two_writers_cannot_store_more_than_the_order_filled(app_engine, admin_engine):
    """#313a finding 1, the core proof. Two connections each insert a 40-unit trade of one order that filled 65, in
    parallel transactions: the second WAITS on the order-row lock until the first commits, then sums the first's
    committed trade (40 + 40 > 65) and is refused. Mutation 'drop the lock' (or a share lock): the second returns at
    once and both commit 80 units. Commits; removes its own rows."""
    user, ids = _user(), []
    try:
        async with app_engine.connect() as setup:
            async with setup.begin():
                sid = await _new_strategy(setup, user)
                number = await plans.next_plan_number(setup, user, sid)
                await plans.record_plan(setup, user, sid, number, "ENTRY", (_order(sid, number, "BUY", "7.00"),))
                await _close(setup, user, sid, number, "filled")
            tag = make_tag(sid, number, 0)
            ids = [int(r[0]) for r in (await setup.execute(text(
                "SELECT c.id FROM public.broker_instruments b JOIN public.catalogue_contracts c "
                "ON c.id = b.contract_id WHERE b.broker = 'zerodha' AND b.broker_symbol = ANY(:s)"),
                {"s": SYMBOLS})).all()]
        async with app_engine.connect() as first, app_engine.connect() as second:
            t1, t2 = await first.begin(), await second.begin()
            # two Zerodha order ids under the one tag, so the order-id advisory lock cannot be what serialises them
            await first.execute(text(_FILL_OF), {"tag": tag, "oid": ORDER_ID, "tid": "1", "q": RACE_UNITS,
                                                 "px": "7.00"})
            waiter = asyncio.create_task(second.execute(text(_FILL_OF), {
                "tag": tag, "oid": OTHER_ORDER_ID, "tid": "2", "q": RACE_UNITS, "px": "7.05"}))
            await asyncio.sleep(WAIT_SECONDS)
            assert not waiter.done(), "the second insert must wait for the first transaction"
            await t1.commit()
            with pytest.raises(DBAPIError) as err:
                await asyncio.wait_for(waiter, 10)
            assert getattr(err.value.orig, "sqlstate", None) == GUARD_SQLSTATE
            assert "exceed the order's filled quantity" in str(err.value)
            await t2.rollback()
        async with app_engine.connect() as check:
            stored = (await check.execute(text("SELECT trade_id, quantity FROM public.execution_plan_fills "
                                               "WHERE tag = :t"), {"t": tag})).all()
        assert [tuple(r) for r in stored] == [("1", RACE_UNITS)]
    finally:
        await _remove_own_fills_and_rows(admin_engine, ids, user)


async def test_app_role_cannot_update_or_delete_and_the_owner_is_refused_by_the_guards(app_engine, admin_engine):
    """Guards: column-limited grants (the app role has no UPDATE/DELETE) AND the insert-only triggers (even the owner
    cannot UPDATE or DELETE a stored price or holding)."""
    async with _Tx(app_engine) as tx:
        tag = await _filled_tag(tx)
        await tx.conn.execute(text(_FILL), {"tag": tag, "tid": "1", "q": LOT, "px": "7.00"})
        await _refused_sql(tx.conn, "UPDATE public.execution_plan_fills SET price = 1 WHERE tag = :t",
                           INSUFFICIENT_PRIVILEGE, {"t": tag})
        await _refused_sql(tx.conn, "DELETE FROM public.adopted_holdings", INSUFFICIENT_PRIVILEGE)
    async with _Tx(admin_engine) as tx:
        tag = await _filled_tag(tx)
        await tx.conn.execute(text(_FILL), {"tag": tag, "tid": "1", "q": LOT, "px": "7.00"})
        await tx.conn.execute(text(_HOLD), {"s": tx.strategy_id, "iid": "NSE_FO:47189", "q": LOT, "px": "7.00",
                                            "ref": "adopt:1"})
        for sql in ("UPDATE public.execution_plan_fills SET price = 1",
                    "DELETE FROM public.execution_plan_fills",
                    "UPDATE public.adopted_holdings SET quantity = 1",
                    "DELETE FROM public.adopted_holdings"):
            await _refused_sql(tx.conn, sql, GUARD_SQLSTATE)


async def test_one_holding_per_strategy_and_contract_two_strategies_stay_separate(app_engine):
    """Guard: UNIQUE (strategy_id, instrument_id) and UNIQUE reference. A second holding of the same contract in the
    same strategy is refused (never netted); another strategy of the user may hold the same contract (Q224)."""
    async with _Tx(app_engine) as tx:
        params = {"s": tx.strategy_id, "iid": REAL_INSTRUMENT, "q": LOT, "px": "7.00", "ref": "adopt:a"}
        await tx.conn.execute(text(_HOLD), params)
        await _refused_sql(tx.conn, _HOLD, UNIQUE_VIOLATION, {**params, "ref": "adopt:b"})
        other = await _new_strategy(tx.conn, tx.user, catalogue=False)
        await _refused_sql(tx.conn, _HOLD, UNIQUE_VIOLATION, {**params, "s": other})  # same reference
        await tx.conn.execute(text(_HOLD), {**params, "s": other, "ref": "adopt:c"})
        n = (await tx.conn.execute(text("SELECT count(*) FROM public.adopted_holdings WHERE instrument_id = :i"),
                                   {"i": REAL_INSTRUMENT})).scalar_one()
        assert n == TWO_HOLDERS


async def test_holding_checks_refuse_bad_values(app_engine):
    """Guards: the CHECKs on units, product, price and contract key."""
    async with _Tx(app_engine) as tx:
        base = {"s": tx.strategy_id, "iid": REAL_INSTRUMENT, "q": LOT, "px": "7.00", "ref": "adopt:x"}
        for over in ({"q": 0}, {"px": "0"}, {"iid": "nse_fo:47189"}):
            await _refused_sql(tx.conn, _HOLD, CHECK_VIOLATION, {**base, **over})
        await _refused_sql(tx.conn, _HOLD.replace("'NRML'", "'CNC'"), CHECK_VIOLATION, base)


async def test_downgrade_is_refused_while_a_holding_is_stored(admin_engine):
    """Guard: the downgrade refuses once anything is stored (what a strategy holds is never dropped)."""
    from _migration_replay import recorded  # noqa: PLC0415

    own_down = recorded("0020_order_book_store.py", "downgrade")
    async with _Tx(admin_engine) as tx:
        await tx.conn.execute(text(_HOLD), {"s": tx.strategy_id, "iid": REAL_INSTRUMENT, "q": LOT, "px": "7.00",
                                            "ref": "adopt:d"})
        with pytest.raises(DBAPIError, match="order book records are stored"):
            async with tx.conn.begin_nested():
                await tx.conn.execute(text(own_down[0]))


async def test_downgrade_then_upgrade_round_trips(admin_engine):
    """0020 down leaves no table of the store; up restores it and the allow-list post check passes. Rolled back."""
    from _migration_replay import round_trip_sql  # noqa: PLC0415

    own_down, own_up, down, up = round_trip_sql("0020_order_book_store.py")
    assert "'pre'" in own_up[0] and "'post'" in own_up[-1] and "'post'" in own_down[-1]
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            for sql in down:
                await conn.execute(text(sql))
            gone = (await conn.execute(text("SELECT to_regclass('public.adopted_holdings')"))).scalar_one()
            assert gone is None
            for sql in up:
                await conn.execute(text(sql))
            back = (await conn.execute(text("SELECT to_regclass('public.adopted_holdings')"))).scalar_one()
            assert back is not None
        finally:
            await trans.rollback()
