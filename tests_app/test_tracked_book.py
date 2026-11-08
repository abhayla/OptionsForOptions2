"""GC-ICTRACK task 4/5 (ADR-276) and the REQ-073 AC-6 fix: the READ-ONLY real book (``tracked_book.real_book``) reads
a strategy's stored Zerodha trades with plain SELECTs, owner-checked, on the live contract ids. Database test (rolled
back)."""
from __future__ import annotations

from decimal import Decimal as D

from ofo_app import catalogue_store, tracked_book
from ofo_app import execution_plan_store as plans
from test_execution_plan_store import LOT, REAL_INSTRUMENT, _Tx, _user, trades_for


async def test_real_book_turns_stored_trades_into_order_rows_on_the_live_contract(app_engine):
    """GC-ICTRACK task 4/5 (ADR-276): an ENTRY filled by two trades and a later EXIT read back through ``real_book`` as
    one order row per trade on the live contract id, kinds open / exit, at each plan's time; another user's strategy
    answers not found (owner check), and a strategy with no plan answers ()."""
    async with _Tx(app_engine) as tx:
        assert await tracked_book.real_book(tx.conn, tx.user, tx.strategy_id) == ()
        entry = await tx.enter("ENTRY", "SELL", "7.45")
        tag = entry.orders[0].tag
        await plans.close_plan(tx.conn, tx.user, tx.strategy_id, 1, reason="filled", filled={tag: LOT},
                               fills=(plans.PlanFill(tag, "o1", "1", 40, D("7.00")),
                                      plans.PlanFill(tag, "o1", "2", LOT - 40, D("7.10"))))
        exit_ = await tx.enter("EXIT", "BUY", "6.65")
        await plans.close_plan(tx.conn, tx.user, tx.strategy_id, 2, reason="filled",
                               filled={exit_.orders[0].tag: LOT}, fills=trades_for({exit_.orders[0].tag: LOT}, "6.65"))
        live = await catalogue_store.live_contract_ids(tx.conn, [tracked_book.instrument_key(REAL_INSTRUMENT)])
        cid = live[tracked_book.instrument_key(REAL_INSTRUMENT)]
        rows = await tracked_book.real_book(tx.conn, tx.user, tx.strategy_id)
        assert [(o.contract_id, o.side, o.quantity, str(o.price), o.kind) for o in rows] == [
            (cid, "SELL", 40, "7.00", "open"), (cid, "SELL", LOT - 40, "7.10", "open"),
            (cid, "BUY", LOT, "6.65", "exit")]
        assert await tracked_book.real_book(tx.conn, _user(), tx.strategy_id) is None  # another user's: not found
