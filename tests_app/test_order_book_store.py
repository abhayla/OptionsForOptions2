"""#313b: the order-book store - Zerodha's trades stored with every plan close, adopted holdings stored and counted.

Spec basis: issue #313 ("it must be stored (fills AND adopted holdings, in the same transaction as the strategy
version)"); ADR-109 (2) (a strategy owns exactly the fills of the orders this app placed, matched by tag); ADR-096
(adopted holdings count in the strategy's position exactly as a fill would); ADR-105 (held units = the net over every
stored plan); ADR-008 (money exact; NUMERIC(14,2) would round 7.005, so it is refused, never rounded).

Real input (the core): the GC-3L live trade of 2026-10-19, strategy 9 - ``tests/fixtures/kite_replies/
orders-gc3l-2026-10-19.json`` / ``trades-gc3l-2026-10-19.json``, copied from
``D:/Abhay/Ventures/ofo-kite-ticks/2026-10-19/replies-after-exit/`` (README there). Expected values are read by hand
from those files: entry OFS9V1L0 = order 261019170382597, trade 3428923, 65 @ 7 (stored 7.00); exit OFS9V2L0 = order
261019170402780, trade 3720169, 65 @ 6.65; net 65 - 65 = 0 held.

The pure tests run anywhere. Database tests need TEST_DATABASE_URL / TEST_ADMIN_DATABASE_URL and skip locally without
them (CI's PostgreSQL); the restart and the concurrency test commit and remove exactly their own rows afterwards.
"""

from __future__ import annotations

import asyncio
import copy
import dataclasses
import datetime
import json
from decimal import Decimal as D
from pathlib import Path

import pytest
from ofo.execution.basket import make_tag
from ofo.timeutil import IST
from ofo_app import execute_plan as ep
from ofo_app import execution_plan_store as plans
from ofo_app import execution_return as er
from ofo_app import order_book_store as books
from ofo_app import return_book as rb
from ofo_app.kite_replies import KiteReplyError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from test_execution_plan_store import (
    LOT,
    REAL_INSTRUMENT,
    REAL_SYMBOL,
    SYMBOLS,
    _new_strategy,
    _order,
    _refused,
    _Tx,
    _user,
    trades_for,
)
from test_order_book_migration import _remove_own_fills_and_rows

REPLIES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "kite_replies"
GC3L_STRATEGY = 9
GC3L_SYMBOL = "NIFTY26OCT24000CE"  # the recorded contract (NFO token 13156354)
ENTRY_ORDER, ENTRY_TRADE = "261019170382597", "3428923"
EXIT_ORDER, EXIT_TRADE = "261019170402780", "3720169"
ENTRY_PRICE, EXIT_PRICE = D("7.00"), D("6.65")
GC3L_DAY = datetime.date(2026, 10, 19)
AT = datetime.datetime(2026, 10, 19, 10, 34, 26, tzinfo=IST)
WAIT_SECONDS = 1.0


def _gc3l(name: str) -> list:
    """The recorded rows, parsed as live Kite REST sends them (JSON numbers)."""
    return json.loads((REPLIES / f"{name}-gc3l-2026-10-19.json").read_text(encoding="utf-8"))["data"]


def _rows(name: str, tag_map: dict[str, str], symbol: str) -> list:
    """The recorded rows with the GC-3L tags mapped to this test's tags and the contract to this test's catalogue
    symbol; order ids, trade ids, units and prices are kept exactly as recorded."""
    out = copy.deepcopy(_gc3l(name))
    for row in out:
        if "tag" in row:
            row["tag"] = tag_map.get(row["tag"], row["tag"])
            row["tags"] = [tag_map.get(t, t) for t in row.get("tags", [])]
        row["tradingsymbol"] = symbol
    return out


def _open_plan(strategy_id: int, number: int, action: str, side: str) -> plans.StoredPlan:
    order = plans.PlanOrder(0, make_tag(strategy_id, number, 0), "NSE_FO:47189", GC3L_SYMBOL, side, LOT, D("7.45"))
    return plans.StoredPlan(strategy_id, number, action, "open", (order,), AT, None, None)


ENTRY = _open_plan(GC3L_STRATEGY, 1, "ENTRY", "BUY")
EXIT = _open_plan(GC3L_STRATEGY, 2, "EXIT", "SELL")


def _book(orders: list, trades: list, *open_plans: plans.StoredPlan) -> er.TodaysBook:
    tags = frozenset(o.tag for p in open_plans for o in p.orders)
    return rb.read_book(orders, trades, open_plans[0].strategy_id, tags)


def _real_book(plan: plans.StoredPlan, trades: list | None = None) -> er.TodaysBook:
    return _book(_gc3l("orders"), _gc3l("trades") if trades is None else trades, plan)


# ---------------------------------------------------------------------------------------------------------------
# Core (pure part): the GC-3L replies become exactly the trades the close stores
# ---------------------------------------------------------------------------------------------------------------


def test_core_gc3l_replies_become_one_trade_per_tag_at_the_recorded_prices():
    """Core, pure: OFS9V1L0 filled 65 -> one trade 3428923 of order 261019170382597, 65 @ 7.00; OFS9V2L0 -> trade
    3720169, 65 @ 6.65 (by hand from the fixture); each passes the store's own trade check for its close."""
    book = _real_book(ENTRY)
    assert er.classify(ENTRY, book, GC3L_DAY) == er.PlanAnswer(er.FILLED, {"OFS9V1L0": LOT})
    entry = er.plan_fills(ENTRY, book)
    assert entry == (plans.PlanFill("OFS9V1L0", ENTRY_ORDER, ENTRY_TRADE, LOT, ENTRY_PRICE),)
    assert plans._checked_trades({"OFS9V1L0": LOT}, entry) == entry
    # the route reads the book with EVERY stored tag: the entry's trade is in it, and is never the exit's
    book = _book(_gc3l("orders"), _gc3l("trades"), ENTRY, EXIT)
    assert len(book.fills) == 2  # noqa: PLR2004 the entry's and the exit's trade
    assert er.classify(EXIT, book, GC3L_DAY) == er.PlanAnswer(er.FILLED, {"OFS9V2L0": LOT})
    assert er.plan_fills(EXIT, book) == (plans.PlanFill("OFS9V2L0", EXIT_ORDER, EXIT_TRADE, LOT, EXIT_PRICE),)


# ---------------------------------------------------------------------------------------------------------------
# Every answer state of Kite's trades reply for a plan (B4 d)
# ---------------------------------------------------------------------------------------------------------------


def test_answer_stated_the_same_trade_twice_identically_is_one_trade():
    """Stated: the trades reply repeats trade 3428923 byte for byte (a re-read) -> still one trade stored."""
    trades = _gc3l("trades")
    book = _real_book(ENTRY, trades + copy.deepcopy(trades))
    assert er.plan_fills(ENTRY, book) == (plans.PlanFill("OFS9V1L0", ENTRY_ORDER, ENTRY_TRADE, LOT, ENTRY_PRICE),)


def test_answer_absent_a_filled_order_without_its_trade_stays_open():
    """Absent: Zerodha says 65 filled but the trades reply lacks trade 3428923 -> reconciliation required, the plan
    stays open, nothing is stored; the store would refuse those trades anyway (0 units for 65 filled)."""
    only_exit = [t for t in _gc3l("trades") if t["order_id"] == EXIT_ORDER]
    book = _real_book(ENTRY, only_exit)
    assert er.classify(ENTRY, book, GC3L_DAY).state == er.RECONCILE
    assert er.plan_fills(ENTRY, book) == ()
    with pytest.raises(plans.PlanStoreError, match="sum to 0 units; Zerodha filled 65"):
        plans._checked_trades({"OFS9V1L0": LOT}, ())


def test_answer_not_found_a_trade_of_an_order_not_ours_is_never_taken():
    """Not found: the trade names an order id no row of ours carries -> ignored (never stored under our tag), so the
    filled order has no trade and the plan stays open; a trade for a tag outside the plan is refused by the store."""
    trades = _gc3l("trades")
    trades[0]["order_id"] = "261019170399999"
    book = _real_book(ENTRY, trades)
    assert er.plan_fills(ENTRY, book) == ()
    assert er.classify(ENTRY, book, GC3L_DAY).state == er.RECONCILE
    foreign = plans.PlanFill("OFS9V7L0", ENTRY_ORDER, ENTRY_TRADE, LOT, ENTRY_PRICE)
    with pytest.raises(plans.PlanStoreError, match="is not in this plan"):
        plans._checked_trades({"OFS9V1L0": LOT}, (foreign,))


def test_answer_failed_an_unreadable_trade_reply_refuses_the_whole_book():
    """Failed: a trade row without its trade id, or a row that is not a mapping, refuses the whole book (the route
    answers 409 ``gate_broker_unconfirmed`` and nothing changes); nothing reaches the store."""
    trades = _gc3l("trades")
    del trades[0]["trade_id"]
    with pytest.raises(KiteReplyError):
        _real_book(ENTRY, trades)
    with pytest.raises(ValueError, match="a trade row must be a mapping"):
        _real_book(ENTRY, ["not a row"])


def test_answer_empty_no_trades_closes_only_a_plan_nothing_filled():
    """Empty: no trades while Zerodha says 65 filled -> stays open; no trades and the order CANCELLED with 0 filled ->
    nothing_placed with no trade to store."""
    assert er.classify(ENTRY, _real_book(ENTRY, []), GC3L_DAY).state == er.RECONCILE
    orders = _gc3l("orders")
    orders[0].update(status="CANCELLED", filled_quantity=0, average_price=0)
    book = _book(orders, [], ENTRY)
    assert er.classify(ENTRY, book, GC3L_DAY) == er.PlanAnswer(er.NOTHING_PLACED, {"OFS9V1L0": 0})
    assert er.plan_fills(ENTRY, book) == ()
    assert plans._checked_trades({"OFS9V1L0": 0}, ()) == ()


def test_answer_ambiguous_one_trade_key_with_two_contents_stays_open():
    """Ambiguous: trade 3428923 appears twice with different prices -> the order is conflicting, the plan stays
    open (nothing stored); two PlanFills with one key are refused by the store."""
    trades = _gc3l("trades")
    other = copy.deepcopy(trades[0])
    other["average_price"] = 7.05
    book = _real_book(ENTRY, [*trades, other])
    assert ENTRY_ORDER in book.conflicting
    assert er.classify(ENTRY, book, GC3L_DAY).state == er.RECONCILE
    one = plans.PlanFill("OFS9V1L0", ENTRY_ORDER, ENTRY_TRADE, 30, ENTRY_PRICE)
    with pytest.raises(plans.PlanStoreError, match="appears twice"):
        plans._checked_trades({"OFS9V1L0": 60}, (one, dataclasses.replace(one, price=D("7.05"))))


# ---------------------------------------------------------------------------------------------------------------
# The store's trade check (allow-list) and the value objects
# ---------------------------------------------------------------------------------------------------------------


def _fill(**over) -> plans.PlanFill:
    fields = {"tag": "OFS9V1L0", "order": ENTRY_ORDER, "trade": ENTRY_TRADE, "units": LOT, "price": ENTRY_PRICE}
    fields.update(over)
    return plans.PlanFill(fields["tag"], fields["order"], fields["trade"], fields["units"], fields["price"])


def test_trades_must_sum_exactly_to_the_filled_quantity():
    """More trades than filled (65 + 1 > 65) and fewer (64 < 65) are both refused; exactly 65 in two trades passes."""
    with pytest.raises(plans.PlanStoreError, match="sum to 66 units"):
        plans._checked_trades({"OFS9V1L0": LOT}, (_fill(), _fill(trade="2", units=1)))
    with pytest.raises(plans.PlanStoreError, match="sum to 64 units"):
        plans._checked_trades({"OFS9V1L0": LOT}, (_fill(units=64),))
    two = (_fill(trade="3428924", units=25), _fill(units=40))
    assert plans._checked_trades({"OFS9V1L0": LOT}, two) == (two[1], two[0])  # sorted by (tag, order id, trade id)


def test_trades_are_inserted_in_one_global_order():
    """Deadlock guard (#313a review MINOR): two tags and two orders arrive in reverse order and leave sorted by (tag,
    order id, trade id), so two writers take the trigger's row and advisory locks in the same order."""
    a = _fill(tag="OFS9V1L0", order="261019170000002", trade="9")
    b = _fill(tag="OFS9V1L1", order="261019170000001", trade="1")
    assert plans._checked_trades({"OFS9V1L0": LOT, "OFS9V1L1": LOT}, (b, a)) == (a, b)


def test_one_zerodha_order_under_two_tags_is_refused():
    """ADR-109 (2): an order's trades belong to one tag; the store refuses before the database's trigger does."""
    with pytest.raises(plans.PlanStoreError, match="under two tags"):
        plans._checked_trades({"OFS9V1L0": LOT, "OFS9V1L1": LOT},
                              (_fill(), _fill(tag="OFS9V1L1", trade="2")))


def test_only_a_tuple_of_real_plan_fills_is_taken_and_a_forged_one_is_rechecked():
    """Allow-list: a mapping or a plain dict per trade is refused; a PlanFill whose price was forged to 7.005 after
    construction is refused by the re-check."""
    for bad in ({"OFS9V1L0": LOT}, ({"tag": "OFS9V1L0"},), "trades", frozenset({_fill()})):
        with pytest.raises(plans.PlanStoreError):
            plans._checked_trades({"OFS9V1L0": LOT}, bad)
    forged = _fill()
    object.__setattr__(forged, "price", D("7.005"))
    with pytest.raises(plans.PlanStoreError, match="at most 2 decimals"):
        plans._checked_trades({"OFS9V1L0": LOT}, (forged,))


@pytest.mark.parametrize("over", [{"price": D("7.005")}, {"price": D("0")}, {"price": D("-7")}, {"price": 7.0},
                                  {"price": D("NaN")}, {"units": 0}, {"units": True}, {"units": 65.0},
                                  {"order": ""}, {"trade": " 1"}, {"tag": ""}])
def test_a_bad_trade_cannot_be_built(over):
    with pytest.raises(plans.PlanStoreError):
        _fill(**over)


def _holding(**over) -> books.AdoptedHolding:
    fields = {"instrument_id": REAL_INSTRUMENT, "transaction_type": "BUY", "quantity": LOT, "product": "NRML",
              "average_price": D("7.00"), "reference": "adopt:test:1"}
    fields.update(over)
    return books.AdoptedHolding(**fields)


@pytest.mark.parametrize("over", [{"average_price": D("0")}, {"average_price": D("-7.025")},
                                  {"average_price": D("NaN")}, {"average_price": D("Infinity")},
                                  {"average_price": plans.PRICE_LIMIT}, {"average_price": 7.025},
                                  {"average_price": "7.025"}, {"quantity": 0},
                                  {"quantity": True}, {"transaction_type": "buy"}, {"product": "CNC"},
                                  {"reference": ""}, {"reference": "x" * 501}, {"instrument_id": ""}])
def test_a_bad_adopted_holding_cannot_be_built(over):
    """Allow-lists: side BUY/SELL, product NRML/MIS (ofo.engine.product), a price that is a finite Decimal in
    (0, 10^12) - never a float or a string."""
    with pytest.raises(books.OrderBookError) as err:
        _holding(**over)
    assert err.value.code == books.BAD_HOLDING


@pytest.mark.parametrize("average", ["7.025", "5.125", "7.016666666666667", "7.00"])
def test_an_adopted_average_finer_than_a_paisa_is_kept_exact(average):
    """ADR-126: Zerodha's average (7.025 = 65 at 7.00 + 65 at 7.05; 7.016666666666667 = Kite's float for 2 x 7.00 +
    1 x 7.05) is taken as given - not rounded, not refused - and survives str and the audit's canonical JSON."""
    from ofo.audit.models import canonical_json  # noqa: PLC0415

    holding = _holding(average_price=D(average), quantity=2 * LOT)
    assert str(holding.average_price) == average
    assert D(str(holding.average_price)) == D(average)
    wire = json.loads(canonical_json({"average_price": holding.average_price}))
    assert wire == {"average_price": {"$decimal": average}} and D(wire["average_price"]["$decimal"]) == D(average)
    assert D(json.loads(json.dumps(str(holding.average_price)))) == D(average)


def test_a_trade_price_finer_than_a_paisa_is_still_refused():
    """#313a / ADR-126 (4): a trade the app placed is whole paise - 7.005 is refused, not rounded, while an adopted
    average of the same shape is kept."""
    with pytest.raises(plans.PlanStoreError, match="at most 2 decimals"):
        _fill(price=D("7.005"))
    assert _holding(average_price=D("7.005")).average_price == D("7.005")
    forged = _holding()
    object.__setattr__(forged, "average_price", 7.025)  # a frozen dataclass forged to a float: the re-check refuses
    with pytest.raises(books.OrderBookError):
        forged.check()


def test_held_units_count_an_adopted_holding_exactly_as_a_fill():
    """ADR-096: BUY 65 adopted alone holds +65; with a closed EXIT that sold 65 it is flat; SELL adopted holds -65."""
    filled = dataclasses.replace(EXIT.orders[0], filled_quantity=LOT)  # the closed EXIT: SELL 65
    sold = dataclasses.replace(EXIT, status="closed", orders=(filled,))
    adopted = _holding(instrument_id="NSE_FO:47189")
    assert ep.held_units([], [adopted]) == {"NSE_FO:47189": LOT}
    assert ep.held_units([sold], [adopted]) == {}
    assert ep.held_units([], [_holding(instrument_id="NSE_FO:47189", transaction_type="SELL")]) == {
        "NSE_FO:47189": -LOT}


# ---------------------------------------------------------------------------------------------------------------
# Database: restart round trip (the core proof), close transaction, adopt
# ---------------------------------------------------------------------------------------------------------------


async def _settle(conn, user: str, sid: int, shape: tuple[str, str, str]) -> plans.StoredPlan:
    """Stores the next plan, then closes it from the recorded GC-3L replies exactly as the return route does:
    read_book -> classify -> close_plan(filled=..., fills=plan_fills(...)). ``shape`` = (action, side, recorded tag)."""
    action, side, recorded_tag = shape
    number = await plans.next_plan_number(conn, user, sid)
    plan = await plans.record_plan(conn, user, sid, number, action, (_order(sid, number, side, "7.45"),))
    rows = _rows("orders", {recorded_tag: plan.orders[0].tag}, REAL_SYMBOL)
    trades = _rows("trades", {}, REAL_SYMBOL)
    book = _book(rows, trades, plan)
    answer = er.classify(plan, book, plan.created_at.astimezone(IST).date())
    assert answer.state == er.FILLED, answer
    return await plans.close_plan(conn, user, sid, number, reason=answer.state, filled=dict(answer.filled),
                                  fills=er.plan_fills(plan, book))


async def _contract_ids(conn) -> list[int]:
    return [int(r[0]) for r in (await conn.execute(text(
        "SELECT c.id FROM public.broker_instruments b JOIN public.catalogue_contracts c ON c.id = b.contract_id "
        "WHERE b.broker = 'zerodha' AND b.broker_symbol = ANY(:s)"), {"s": SYMBOLS})).all()]


async def test_core_gc3l_trades_survive_a_restart_and_read_back_by_tag(app_engine, admin_engine):
    """Core proof: the GC-3L entry (65 @ 7.00) and exit (65 @ 6.65) stored at return, committed; the engine is
    disposed and a NEW one reads back one trade row per tag at those prices, and held units 0. Mutation 'close
    without the trades' (fills dropped in close_plan): fills_for is empty after the restart."""
    user, ids, sid = _user(), [], None
    try:
        async with app_engine.connect() as conn:
            async with conn.begin():
                sid = await _new_strategy(conn, user)
                entry = await _settle(conn, user, sid, ("ENTRY", "BUY", "OFS9V1L0"))
                exit_ = await _settle(conn, user, sid, ("EXIT", "SELL", "OFS9V2L0"))
            ids = await _contract_ids(conn)
        entry_tag, exit_tag = entry.orders[0].tag, exit_.orders[0].tag
        await app_engine.dispose()
        fresh = create_async_engine(app_engine.url, poolclass=NullPool)
        try:
            async with fresh.connect() as conn:
                stored = await books.fills_for(conn, user, sid)
                history = await plans.plans_for(conn, user, sid)
                adopted = await books.adopted_for(conn, user, sid)
        finally:
            await fresh.dispose()
        assert stored == {entry_tag: (plans.PlanFill(entry_tag, ENTRY_ORDER, ENTRY_TRADE, LOT, ENTRY_PRICE),),
                          exit_tag: (plans.PlanFill(exit_tag, EXIT_ORDER, EXIT_TRADE, LOT, EXIT_PRICE),)}
        assert [str(f.price) for t in (entry_tag, exit_tag) for f in stored[t]] == ["7.00", "6.65"]
        assert [(p.close_reason, p.orders[0].filled_quantity) for p in history] == [("filled", LOT), ("filled", LOT)]
        assert adopted == ()
        assert ep.held_units(history, adopted) == {}
    finally:
        await _remove_own_fills_and_rows(admin_engine, ids, user)


async def test_a_refused_close_stores_no_trade_and_leaves_the_plan_open(app_engine):
    """Same transaction: a close whose trades sum to 64 of 65 is refused before anything is written - the plan stays
    open with no filled quantity and no trade; the corrected close then stores the trade (read back exact)."""
    async with _Tx(app_engine) as tx:
        plan = await tx.enter("ENTRY", "BUY", "7.45")
        tag = plan.orders[0].tag
        await _refused(plans.BAD_PLAN, plans.close_plan(tx.conn, tx.user, tx.strategy_id, plan.plan_number,
                                                        reason="filled", filled={tag: LOT},
                                                        fills=trades_for({tag: LOT - 1})))
        (still,) = await plans.plans_for(tx.conn, tx.user, tx.strategy_id)
        assert (still.status, still.orders[0].filled_quantity) == ("open", None)
        assert await books.fills_for(tx.conn, tx.user, tx.strategy_id) == {}
        await plans.close_plan(tx.conn, tx.user, tx.strategy_id, plan.plan_number, reason="filled",
                               filled={tag: LOT}, fills=trades_for({tag: LOT}, "6.65"))
        assert await books.fills_for(tx.conn, tx.user, tx.strategy_id) == {
            tag: (plans.PlanFill(tag, f"ord-{tag}", "1", LOT, D("6.65")),)}


async def test_a_zerodha_order_already_stored_is_refused_before_the_database(app_engine):
    """Guard: the store's stored-trades check. Plan 1 stores order ord-X; plan 2's close naming the same Zerodha
    order (any trade id) is refused with a clear error (the trigger and the key stay as the second layer)."""
    async with _Tx(app_engine) as tx:
        first = await tx.enter("ENTRY", "BUY", "7.45")
        tag1 = first.orders[0].tag
        same = plans.PlanFill(tag1, "261019170382597", "1", LOT, D("7.00"))
        await plans.close_plan(tx.conn, tx.user, tx.strategy_id, 1, reason="filled", filled={tag1: LOT},
                               fills=(same,))
        second = await tx.enter("EXIT", "SELL", "6.65")
        tag2 = second.orders[0].tag
        with pytest.raises(plans.PlanStoreError, match="already has stored trades"):
            await plans.close_plan(tx.conn, tx.user, tx.strategy_id, 2, reason="filled", filled={tag2: LOT},
                                   fills=(dataclasses.replace(same, tag=tag2, trade_id="2"),))
        assert [p.status for p in await plans.plans_for(tx.conn, tx.user, tx.strategy_id)] == ["closed", "open"]


async def test_a_close_that_fills_nothing_takes_no_trade(app_engine):
    """nothing_placed (0 filled) with a trade is refused: a trade needs units the order filled."""
    async with _Tx(app_engine) as tx:
        plan = await tx.enter("ENTRY", "BUY", "7.45")
        tag = plan.orders[0].tag
        await _refused(plans.BAD_PLAN, plans.close_plan(tx.conn, tx.user, tx.strategy_id, 1,
                                                        reason="nothing_placed", fills=trades_for({tag: 1})))
        closed = await plans.close_plan(tx.conn, tx.user, tx.strategy_id, 1, reason="nothing_placed")
        assert closed.close_reason == "nothing_placed"
        assert await books.fills_for(tx.conn, tx.user, tx.strategy_id) == {}


async def test_two_concurrent_closes_of_one_plan_store_its_trades_once(app_engine, admin_engine):
    """Concurrent closes: the second waits on the strategy row lock until the first commits, then finds the plan
    closed (bad_plan) - the trades are stored once. Mutation 'drop the strategy/plan locks': the second does not wait.
    Commits; removes its own rows."""
    user, ids = _user(), []
    try:
        async with app_engine.connect() as setup:
            async with setup.begin():
                sid = await _new_strategy(setup, user)
                number = await plans.next_plan_number(setup, user, sid)
                await plans.record_plan(setup, user, sid, number, "ENTRY", (_order(sid, number, "BUY", "7.45"),))
            ids = await _contract_ids(setup)
        tag = make_tag(sid, number, 0)
        close = {"reason": "filled", "filled": {tag: LOT}, "fills": trades_for({tag: LOT})}
        async with app_engine.connect() as first, app_engine.connect() as second:
            t1, t2 = await first.begin(), await second.begin()
            await plans.close_plan(first, user, sid, number, **close)
            waiter = asyncio.create_task(plans.close_plan(second, user, sid, number, **close))
            await asyncio.sleep(WAIT_SECONDS)
            assert not waiter.done(), "the second close must wait for the first transaction"
            await t1.commit()
            with pytest.raises(plans.PlanStoreError) as err:
                await asyncio.wait_for(waiter, 10)
            assert err.value.code == plans.BAD_PLAN and "already closed" in str(err.value)
            await t2.rollback()
        async with app_engine.connect() as check:
            assert await books.fills_for(check, user, sid) == {
                tag: (plans.PlanFill(tag, f"ord-{tag}", "1", LOT, D("7.00")),)}
    finally:
        await _remove_own_fills_and_rows(admin_engine, ids, user)


async def test_record_adopted_stores_the_strategys_own_version_and_counts_as_held(app_engine):
    """ADR-096: the holding is stored with the strategy's revision read under the lock (never a caller's number),
    read back exactly, and held_units counts it; a holding naming its own version number is refused."""
    async with _Tx(app_engine) as tx:
        revision = int((await tx.conn.execute(text("SELECT revision FROM public.strategies WHERE id = :s"),
                                              {"s": tx.strategy_id})).scalar_one())
        stored = await books.record_adopted(tx.conn, tx.user, tx.strategy_id, _holding())
        assert stored == dataclasses.replace(_holding(), version_number=revision)
        assert await books.adopted_for(tx.conn, tx.user, tx.strategy_id) == (stored,)
        assert str(stored.average_price) == "7.00"
        history = await plans.plans_for(tx.conn, tx.user, tx.strategy_id)
        assert ep.held_units(history, (stored,)) == {REAL_INSTRUMENT: LOT}
        with pytest.raises(books.OrderBookError) as err:
            await books.record_adopted(tx.conn, tx.user, tx.strategy_id,
                                       _holding(reference="adopt:test:2", version_number=revision + 1))
        assert err.value.code == books.BAD_HOLDING


async def test_record_adopted_refuses_a_second_holding_of_a_contract_and_a_used_reference(app_engine):
    """Guards: one holding per (strategy, contract) - adopted before, or held by the strategy's stored fills - and a
    unique reference (also across strategies); a contract the catalogue cannot name is refused; another user's
    strategy is not_found. Each refusal leaves the stored holdings unchanged."""
    async with _Tx(app_engine) as tx:
        sid = tx.strategy_id
        first = await books.record_adopted(tx.conn, tx.user, sid, _holding())
        for code, holding in ((books.ALREADY_HELD, _holding(reference="adopt:test:2")),
                              (books.BAD_HOLDING, _holding(instrument_id="NSE_FO:999999999", reference="adopt:x"))):
            with pytest.raises(books.OrderBookError) as err:
                await books.record_adopted(tx.conn, tx.user, sid, holding)
            assert err.value.code == code
        other = await _new_strategy(tx.conn, tx.user, catalogue=False)
        with pytest.raises(books.OrderBookError) as err:
            await books.record_adopted(tx.conn, tx.user, other, _holding())
        assert err.value.code == books.REFERENCE_TAKEN
        number = await plans.next_plan_number(tx.conn, tx.user, other)
        await plans.record_plan(tx.conn, tx.user, other, number, "ENTRY", (_order(other, number, "BUY", "7.45"),))
        tag = make_tag(other, number, 0)
        await plans.close_plan(tx.conn, tx.user, other, number, reason="filled", filled={tag: LOT},
                               fills=trades_for({tag: LOT}))
        with pytest.raises(books.OrderBookError) as err:
            await books.record_adopted(tx.conn, tx.user, other, _holding(reference="adopt:test:3"))
        assert err.value.code == books.ALREADY_HELD
        for call in (books.record_adopted(tx.conn, _user(), sid, _holding(reference="adopt:test:4")),
                     books.adopted_for(tx.conn, _user(), sid), books.fills_for(tx.conn, _user(), sid)):
            with pytest.raises(books.OrderBookError) as err:
                await call
            assert err.value.code == books.NOT_FOUND
        assert await books.adopted_for(tx.conn, tx.user, sid) == (first,)
        assert await books.adopted_for(tx.conn, tx.user, other) == ()


async def test_core_adopted_average_7_025_survives_a_restart_exactly(app_engine, admin_engine):
    """Core proof (ADR-126): record_adopted with Zerodha's average 7.025 for 130 units, committed; the engine is
    disposed and a NEW one reads back Decimal("7.025") exactly (a NUMERIC(14,2) column would give 7.03), while a
    trade fill at 7.005 is still refused. Commits; removes its own rows."""
    user, ids, sid = _user(), [], None
    units = 2 * LOT
    try:
        async with app_engine.connect() as conn:
            async with conn.begin():
                sid = await _new_strategy(conn, user)
                stored = await books.record_adopted(conn, user, sid, _holding(average_price=D("7.025"),
                                                                              quantity=units,
                                                                              reference=f"adopt:{user}:core"))
            ids = await _contract_ids(conn)
        assert stored.average_price == D("7.025") and str(stored.average_price) == "7.025"
        await app_engine.dispose()
        fresh = create_async_engine(app_engine.url, poolclass=NullPool)
        try:
            async with fresh.connect() as conn:
                (back,) = await books.adopted_for(conn, user, sid)
        finally:
            await fresh.dispose()
        assert type(back.average_price) is D and str(back.average_price) == "7.025"
        assert (back.quantity, back.instrument_id) == (units, REAL_INSTRUMENT)
        with pytest.raises(plans.PlanStoreError, match="at most 2 decimals"):
            _fill(price=D("7.005"))
    finally:
        await _remove_own_fills_and_rows(admin_engine, ids, user)
