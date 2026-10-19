"""#313: migration 0020's database guards (fill prices, adopted holdings). Database tests: they need
TEST_DATABASE_URL / TEST_ADMIN_DATABASE_URL, skip locally without them, and every test runs in a rolled-back
transaction (CI's PostgreSQL only; never the shared VPS database).

Spec basis: issue #313; ADR-096 (adopted holdings count as a fill would); ADR-109 / Q224 (a strategy owns the fills of
orders this app placed, matched by tag; two holders of one contract stay separate); ADR-048; ADR-023.

Each test names the guard it would lose: remove the guard and the test fails.
"""

from __future__ import annotations

import pytest
from ofo.execution.basket import make_tag
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_execution_plan_store import (
    CHECK_VIOLATION,
    INSUFFICIENT_PRIVILEGE,
    LOT,
    REAL_INSTRUMENT,
    UNIQUE_VIOLATION,
    _close,
    _new_strategy,
    _refused_sql,
    _Tx,
)

GUARD_SQLSTATE = "OF020"
FK_VIOLATION = "23503"
TWO_HOLDERS = 2  # two strategies of one user, each holding the same contract (Q224)
_FILL = ("INSERT INTO public.execution_plan_fills (tag, broker_order_id, trade_id, quantity, price) "
         "VALUES (:tag, '251019000000001', :tid, :q, :px)")
_HOLD = ("INSERT INTO public.adopted_holdings (strategy_id, instrument_id, transaction_type, quantity, product, "
         "average_price, reference, version_number) VALUES (:s, :iid, 'BUY', :q, 'NRML', :px, :ref, 1)")


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
    """Guards: CHECK price > 0, PRIMARY KEY (tag, order id, trade id) (one row per trade), FOREIGN KEY to the tag, and
    the trigger's sum check (stored trades never exceed the order's filled quantity: 65 + 1 > 65)."""
    async with _Tx(app_engine) as tx:
        tag = await _filled_tag(tx)
        await _refused_sql(tx.conn, _FILL, CHECK_VIOLATION, {"tag": tag, "tid": "1", "q": LOT, "px": "0"})
        await tx.conn.execute(text(_FILL), {"tag": tag, "tid": "1", "q": LOT, "px": "7.00"})
        await _refused_sql(tx.conn, _FILL, UNIQUE_VIOLATION, {"tag": tag, "tid": "1", "q": LOT, "px": "6.65"})
        await _refused_sql(tx.conn, _FILL, GUARD_SQLSTATE, {"tag": tag, "tid": "2", "q": 1, "px": "7.00"})
        await _refused_sql(tx.conn, _FILL, FK_VIOLATION, {"tag": "OFS999999V1L0", "tid": "1", "q": LOT, "px": "7.00"})


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
