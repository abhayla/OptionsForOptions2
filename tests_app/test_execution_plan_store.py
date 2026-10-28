"""W-094 / REQ-073 AC-2: the persisted execution plan - one open plan per strategy, a plan number minted per Execute,
every order tag unique (ADR-050 item 4b: "persist the order intent before sending").

Spec basis (quoted): ADR-050 item 4 "(b) persist the order intent before sending"; REQ-073 AC-2 "Every order in the
basket carries our own tag (at most 20 alphanumeric characters) that identifies the strategy and plan version, so the
result is matched by tag, never by symbol (ADR-050 item 4a)."

Real rows (owner's real order of 2026-10-16, ofo-kite-ticks/2026-10-16/real-order/): ``basket-121848.json`` holds
tag OFS1V1L0, BUY 65 NIFTY26O1923650CE LIMIT 5.45; ``exit.html``'s basket holds SELL 65 NIFTY26O1923650CE LIMIT 3.1
(the exit, plan 2); ``orders-122104.json`` gives instrument_token 12080386 = exchange token 47189 (>> 8) on NFO.

Database tests need TEST_DATABASE_URL / TEST_ADMIN_DATABASE_URL and skip locally without them. All but the
concurrency test run in a rolled-back transaction. The concurrency test commits (a second connection sees only committed
rows) and removes exactly its own rows afterwards through the owner role.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from ofo.engine.legs import Action
from ofo.execution.basket import make_tag
from ofo.strategy import stored_form as sf
from ofo_app import execution_plan_store as plans
from ofo_app import order_book_store as books
from ofo_app import reconcile_attribution as ra
from ofo_app import strategy_store as store
from ofo_app.catalogue_store import apply_update, load_catalogue, parse_rows_naming_the_row
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError

IST = timezone(timedelta(hours=5, minutes=30))
AS_OF = datetime(2026, 10, 8, 9, 0, tzinfo=IST)
FIXTURE = (Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "kite_ws"
           / "instruments-2026-10-08-subscribed.csv")
SYMBOLS = ["NIFTY26O1322800CE", "NIFTY26O1323000CE", "NIFTY26O1322400PE", "NIFTY26O1322200PE"]
LOT = 65
CHECK_VIOLATION = "23514"
UNIQUE_VIOLATION = "23505"
INSUFFICIENT_PRIVILEGE = "42501"
PLAN_GUARD_SQLSTATE = "OF016"
REAL_SYMBOL = SYMBOLS[0]  # a catalogue contract of the recorded fixture (the plan checks its symbol against it)


def _instrument_of(symbol: str) -> str:
    """The plan's instrument_id ("<segment>:<exchange token>") of a fixture contract, as the catalogue stores it."""
    with FIXTURE.open(encoding="utf-8", newline="") as stream:
        row = next(r for r in parse_rows_naming_the_row(stream) if r.ref("zerodha").broker_symbol == symbol)
    return f"{row.id.exchange_segment}:{row.id.exchange_token}"


REAL_INSTRUMENT = _instrument_of(REAL_SYMBOL)


def _user() -> str:
    return "test-" + uuid.uuid4().hex


def _order(strategy_id: int, plan_number: int, side: str, px: str, leg: int = 0, **over) -> plans.PlanOrder:
    fields = dict(leg_index=leg, tag=make_tag(strategy_id, plan_number, leg), instrument_id=REAL_INSTRUMENT,
                  tradingsymbol=REAL_SYMBOL, transaction_type=side, quantity=LOT, price=Decimal(px))
    fields.update(over)
    return plans.PlanOrder(**fields)


async def _new_strategy(conn, user: str, *, catalogue: bool = True) -> int:
    with FIXTURE.open(encoding="utf-8", newline="") as stream:
        rows = [r for r in parse_rows_naming_the_row(stream) if r.ref("zerodha").broker_symbol in SYMBOLS]
    if catalogue:
        await apply_update(conn, rows, as_of=AS_OF)
    found = (await conn.execute(text(
        "SELECT b.broker_symbol, c.id FROM public.broker_instruments b JOIN public.catalogue_contracts c "
        "ON c.id = b.contract_id WHERE b.broker = 'zerodha' AND b.broker_symbol = ANY(:s) "
        "AND NOT c.retired AND NOT c.delisted"), {"s": SYMBOLS})).all()
    ids = {r[0]: int(r[1]) for r in found}
    sides = ["SELL", "BUY", "SELL", "BUY"]
    saved = await store.build_definition(conn, "NIFTY", [
        sf.LegChoice(ids[s], Action(side), LOT) for s, side in zip(SYMBOLS, sides, strict=True)])
    return (await store.save_draft(conn, user, saved)).id


class _Tx:
    """A rolled-back transaction as the app role, holding one strategy of ``self.user``."""

    def __init__(self, engine) -> None:
        self.engine = engine
        self.user = _user()

    async def __aenter__(self):
        self.conn = await self.engine.connect()
        self.trans = await self.conn.begin()
        self.strategy_id = await _new_strategy(self.conn, self.user)
        return self

    async def __aexit__(self, *_exc) -> None:
        await self.trans.rollback()
        await self.conn.close()

    async def enter(self, action: str, side: str, price: str) -> plans.StoredPlan:
        number = await plans.next_plan_number(self.conn, self.user, self.strategy_id)
        return await plans.record_plan(self.conn, self.user, self.strategy_id, number, action,
                                       (_order(self.strategy_id, number, side, price),))


async def _refused_sql(conn, sql: str, sqlstate: str, params: dict | None = None) -> None:
    savepoint = await conn.begin_nested()
    with pytest.raises(DBAPIError) as err:
        await conn.execute(text(sql), params or {})
    await savepoint.rollback()
    assert getattr(err.value.orig, "sqlstate", None) == sqlstate, err.value


def trades_for(filled: dict[str, int] | None, price: str = "7.00") -> tuple[plans.PlanFill, ...]:
    """#313b: one Zerodha trade per filled tag (illustrative ids "ord-<tag>" / "1", not a recording), so a close
    carries trades that sum exactly to its filled quantities, as ``close_plan`` requires."""
    return tuple(plans.PlanFill(tag, f"ord-{tag}", "1", units, Decimal(price))
                 for tag, units in sorted((filled or {}).items()) if units)


async def _close(conn, user: str, strategy_id: int, number: int, reason: str) -> plans.StoredPlan:
    """Closes a ONE-leg plan the way the caller must: a close that changes position carries the filled quantities
    and the trades that make them up."""
    tag = make_tag(strategy_id, number, 0)
    fills = {"filled": {tag: LOT}, "exited": {tag: LOT}, "partial": {tag: LOT // 2}, "nothing_placed": None}[reason]
    return await plans.close_plan(conn, user, strategy_id, number, reason=reason, filled=fills,
                                  fills=trades_for(fills))


async def _refused(code: str, awaitable) -> None:
    with pytest.raises(plans.PlanStoreError) as err:
        await awaitable
    assert err.value.code == code, err.value


# ---------------------------------------------------------------------------------------------------------------
# Core proof
# ---------------------------------------------------------------------------------------------------------------


async def test_core_real_order_plan_numbers(app_engine):
    """The owner's real order: entry = plan 1 (tag OFS<id>V1L0, BUY 65 @ 5.45), a second open plan is refused, and after
    close_plan the exit = plan 2 (tag OFS<id>V2L0, SELL 65 @ 3.10). The strategy id is whatever the database assigned
    (the real one was 1); the literal tags of the real order are pinned through make_tag below."""
    assert make_tag(1, 1, 0) == "Q0001010" and make_tag(1, 2, 0) == "Q0001020"  # the 8-char basket grammar (0018)
    async with _Tx(app_engine) as tx:
        sid = tx.strategy_id
        entry = await tx.enter("ENTRY", "BUY", "5.45")
        assert (entry.strategy_id, entry.plan_number, entry.action, entry.status) == (sid, 1, "ENTRY", "open")
        assert [(o.tag, o.tradingsymbol, o.transaction_type, o.quantity, o.price) for o in entry.orders] == [
            (make_tag(sid, 1, 0), REAL_SYMBOL, "BUY", 65, Decimal("5.45"))]
        # a second Execute while plan 1 is open is refused, and nothing is minted
        await _refused(plans.PLAN_OPEN, plans.next_plan_number(tx.conn, tx.user, sid))
        assert (await plans.open_plan(tx.conn, tx.user, sid)).plan_number == 1
        closed = await _close(tx.conn, tx.user, sid, 1, "filled")
        assert (closed.status, closed.close_reason) == ("closed", "filled") and closed.closed_at is not None
        assert await plans.open_plan(tx.conn, tx.user, sid) is None
        exit_plan = await tx.enter("EXIT", "SELL", "3.10")
        assert exit_plan.plan_number == 2 and exit_plan.action == "EXIT"
        assert [(o.tag, o.transaction_type, o.quantity, o.price) for o in exit_plan.orders] == [
            (make_tag(sid, 2, 0), "SELL", 65, Decimal("3.10"))]
        assert [(p.plan_number, p.status) for p in await plans.plans_for(tx.conn, tx.user, sid)] == [
            (1, "closed"), (2, "open")]


# ---------------------------------------------------------------------------------------------------------------
# The store's rules
# ---------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("floor, stored, expected", [(0, 0, 1), (2, 0, 3), (0, 1, 2), (1, 1, 2), (5, 1, 6)])
async def test_floor_is_honoured(app_engine, floor, stored, expected):
    """Mutation 'floor ignored': floor 2 with no stored plans must give 3 (Zerodha already holds plan 2's tags)."""
    async with _Tx(app_engine) as tx:
        if stored:
            await tx.enter("ENTRY", "BUY", "5.45")
            await _close(tx.conn, tx.user, tx.strategy_id, 1, "filled")
        assert await plans.next_plan_number(tx.conn, tx.user, tx.strategy_id, floor=floor) == expected


@pytest.mark.parametrize("floor", [-1, 1.5, True, "2", None])
async def test_bad_floor_is_refused(app_engine, floor):
    async with _Tx(app_engine) as tx:
        await _refused(plans.BAD_PLAN, plans.next_plan_number(tx.conn, tx.user, tx.strategy_id, floor=floor))


async def test_another_users_or_missing_strategy_is_not_found(app_engine):
    async with _Tx(app_engine) as tx:
        missing = tx.strategy_id + 10**6
        for who, sid in [("someone-else", tx.strategy_id), (tx.user, missing), (tx.user, 0), (tx.user, True)]:
            await _refused(plans.NOT_FOUND, plans.next_plan_number(tx.conn, who, sid))
            await _refused(plans.NOT_FOUND, plans.plans_for(tx.conn, who, sid))
            await _refused(plans.NOT_FOUND, plans.open_plan(tx.conn, who, sid))
            await _refused(plans.NOT_FOUND, plans.close_plan(tx.conn, who, sid, 1, reason="filled"))
        await tx.enter("ENTRY", "BUY", "5.45")
        await _refused(plans.NOT_FOUND, plans.record_plan(tx.conn, "someone-else", tx.strategy_id, 2, "EXIT", (
            _order(tx.strategy_id, 2, "SELL", "3.10"),)))
        await _refused(plans.NOT_FOUND, plans.close_plan(tx.conn, tx.user, tx.strategy_id, 7, reason="filled"))


@pytest.mark.parametrize("make, label", [
    (lambda s: _order(s, 1, "BUY", "5.45", tag="OFS999V1L0"), "a tag that is not make_tag of its own row"),
    (lambda s: _order(s, 1, "BUY", "5.45", tag="ofs1v1l0"), "lower case"),
    (lambda s: _order(s, 1, "BUY", "5.45", tag=make_tag(s, 2, 0)), "another plan's tag"),
], ids=lambda v: v if isinstance(v, str) else "")
async def test_a_foreign_tag_is_refused_as_bad_plan(app_engine, make, label):
    async with _Tx(app_engine) as tx:
        number = await plans.next_plan_number(tx.conn, tx.user, tx.strategy_id)
        await _refused(plans.BAD_PLAN, plans.record_plan(tx.conn, tx.user, tx.strategy_id, number, "ENTRY",
                                                         (make(tx.strategy_id),)))
        assert await plans.plans_for(tx.conn, tx.user, tx.strategy_id) == ()


@pytest.mark.parametrize("over", [
    {"price": 5.45}, {"price": Decimal("0")}, {"price": Decimal("-1")}, {"price": Decimal("5.455")},
    {"price": Decimal("NaN")}, {"price": Decimal("Infinity")}, {"price": Decimal("1000000000000")}, {"price": "5.45"},
    {"quantity": 0}, {"quantity": -65}, {"quantity": True}, {"quantity": 65.0}, {"quantity": 2**31},
    {"transaction_type": "HOLD"}, {"transaction_type": "buy"}, {"instrument_id": ""}, {"tradingsymbol": ""},
    {"leg_index": -1}, {"leg_index": True},
])
def test_an_invalid_order_cannot_be_built(over):
    with pytest.raises(plans.PlanStoreError) as err:
        _order(1, 1, "BUY", "5.45", **over)
    assert err.value.code == plans.BAD_PLAN


async def test_a_bypassed_order_is_refused_again_on_record(app_engine):
    """A frozen dataclass can still be forged with object.__setattr__: record_plan checks the order itself again."""
    async with _Tx(app_engine) as tx:
        forged = _order(tx.strategy_id, 1, "BUY", "5.45")
        object.__setattr__(forged, "price", 5.45)
        await _refused(plans.BAD_PLAN, plans.record_plan(tx.conn, tx.user, tx.strategy_id, 1, "ENTRY", (forged,)))
        object.__setattr__(forged, "price", Decimal("0"))
        await _refused(plans.BAD_PLAN, plans.record_plan(tx.conn, tx.user, tx.strategy_id, 1, "ENTRY", (forged,)))


async def test_bad_plan_shapes_are_refused(app_engine):
    async with _Tx(app_engine) as tx:
        sid, one = tx.strategy_id, _order(tx.strategy_id, 1, "BUY", "5.45")
        for action, orders in [("ENTRY", ()), ("HEDGE", (one,)), ("ENTRY", (one, one)), ("ENTRY", [one]),
                               ("ENTRY", ("not an order",)), ("ENTRY", (_order(sid, 1, "BUY", "5.45", leg=1),))]:
            await _refused(plans.BAD_PLAN, plans.record_plan(tx.conn, tx.user, sid, 1, action, orders))
        for number in (0, -1, True, 1.0, 2**31):
            await _refused(plans.BAD_PLAN, plans.record_plan(tx.conn, tx.user, sid, number, "ENTRY", (one,)))


async def test_a_plan_number_that_was_already_used_is_tag_taken_and_one_below_the_highest_is_bad(app_engine):
    async with _Tx(app_engine) as tx:
        sid = tx.strategy_id
        await tx.enter("ENTRY", "BUY", "5.45")
        await _close(tx.conn, tx.user, sid, 1, "filled")
        await tx.enter("EXIT", "SELL", "3.10")
        await _close(tx.conn, tx.user, sid, 2, "exited")
        again = (_order(sid, 2, "SELL", "3.10"),)
        await _refused(plans.TAG_TAKEN, plans.record_plan(tx.conn, tx.user, sid, 2, "EXIT", again))
        await _refused(plans.BAD_PLAN, plans.record_plan(tx.conn, tx.user, sid, 0, "EXIT", again))
        # a number Kite already holds (floor) may be skipped, never reused: 4 is fine after floor 3
        number = await plans.next_plan_number(tx.conn, tx.user, sid, floor=3)
        assert number == 4
        await plans.record_plan(tx.conn, tx.user, sid, number, "EXIT", (_order(sid, 4, "SELL", "3.10"),))


async def test_record_without_next_plan_number_still_refuses_a_second_open_plan(app_engine):
    async with _Tx(app_engine) as tx:
        sid = tx.strategy_id
        await tx.enter("ENTRY", "BUY", "5.45")
        await _refused(plans.PLAN_OPEN, plans.record_plan(tx.conn, tx.user, sid, 2, "EXIT",
                                                          (_order(sid, 2, "SELL", "3.10"),)))
        assert [p.plan_number for p in await plans.plans_for(tx.conn, tx.user, sid)] == [1]


async def test_closing_rules(app_engine):
    async with _Tx(app_engine) as tx:
        sid = tx.strategy_id
        await tx.enter("ENTRY", "BUY", "5.45")
        for reason in ("done", "", None, "FILLED", 1):
            await _refused(plans.BAD_PLAN, plans.close_plan(tx.conn, tx.user, sid, 1, reason=reason))
        assert (await plans.open_plan(tx.conn, tx.user, sid)).plan_number == 1
        await _close(tx.conn, tx.user, sid, 1, "nothing_placed")
        await _refused(plans.BAD_PLAN, plans.close_plan(tx.conn, tx.user, sid, 1, reason="filled"))
        stored = (await plans.plans_for(tx.conn, tx.user, sid))[0]
        assert stored.close_reason == "nothing_placed"  # the second close changed nothing


@pytest.mark.parametrize("reason", ["filled", "exited", "nothing_placed", "partial"])
async def test_every_close_reason_is_accepted(app_engine, reason):
    async with _Tx(app_engine) as tx:
        await tx.enter("ENTRY", "BUY", "5.45")
        assert (await _close(tx.conn, tx.user, tx.strategy_id, 1, reason)).close_reason == reason


async def test_a_multi_leg_plan_keeps_its_order_and_exact_prices(app_engine):
    async with _Tx(app_engine) as tx:
        sid = tx.strategy_id
        legs = tuple(_order(sid, 1, side, price, leg=i)
                     for i, (side, price) in enumerate(
                         [("SELL", "101.05"), ("BUY", "12.30"), ("SELL", "99"), ("BUY", "0.05")]))
        stored = await plans.record_plan(tx.conn, tx.user, sid, await plans.next_plan_number(tx.conn, tx.user, sid),
                                         "ENTRY", legs)
        assert [(o.leg_index, o.tag, o.price) for o in stored.orders] == [
            (i, make_tag(sid, 1, i), Decimal(p)) for i, p in enumerate(["101.05", "12.30", "99.00", "0.05"])]
        assert (await plans.open_plan(tx.conn, tx.user, sid)).orders == stored.orders


async def test_the_symbol_is_checked_against_and_read_back_from_the_catalogue(app_engine):
    """No symbol column on the plan (identity rule): a wrong symbol or an unknown instrument is bad_plan, nothing is
    stored, and the stored plan's symbol is the catalogue's ZERODHA symbol for the instrument_id."""
    async with _Tx(app_engine) as tx:
        sid = tx.strategy_id
        number = await plans.next_plan_number(tx.conn, tx.user, sid)
        for over in ({"tradingsymbol": SYMBOLS[1]}, {"tradingsymbol": "NOSUCH"}, {"instrument_id": "NSE_FO:1"},
                     {"instrument_id": "garbage"}, {"instrument_id": "NSE_FO:x"}):
            await _refused(plans.BAD_PLAN, plans.record_plan(tx.conn, tx.user, sid, number, "ENTRY",
                                                             (_order(sid, number, "BUY", "5.45", **over),)))
        assert await plans.plans_for(tx.conn, tx.user, sid) == ()
        stored = await plans.record_plan(tx.conn, tx.user, sid, number, "ENTRY", (_order(sid, number, "BUY", "5.45"),))
        assert [(o.instrument_id, o.tradingsymbol) for o in stored.orders] == [(REAL_INSTRUMENT, REAL_SYMBOL)]
        columns = {r[0] for r in await tx.conn.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'execution_plan_orders'"))}
        assert "tradingsymbol" not in columns


# ---------------------------------------------------------------------------------------------------------------
# The database enforces the rules too (raw SQL as the application role, bypassing the store)
# ---------------------------------------------------------------------------------------------------------------


async def test_the_database_refuses_a_second_open_plan_by_raw_sql(app_engine):
    """Mutation 'drop the partial unique index' makes this insert succeed."""
    async with _Tx(app_engine) as tx:
        await tx.enter("ENTRY", "BUY", "5.45")
        await _refused_sql(tx.conn, "INSERT INTO public.execution_plans (strategy_id, plan_number, action) "
                                    "VALUES (:s, 2, 'EXIT')", UNIQUE_VIOLATION, {"s": tx.strategy_id})
        # once closed, the same insert is fine
        await _close(tx.conn, tx.user, tx.strategy_id, 1, "filled")
        await tx.conn.execute(text("INSERT INTO public.execution_plans (strategy_id, plan_number, action) "
                                   "VALUES (:s, 2, 'EXIT')"), {"s": tx.strategy_id})


@pytest.mark.parametrize("sql, sqlstate", [
    ("DELETE FROM public.execution_plans WHERE strategy_id = :s", INSUFFICIENT_PRIVILEGE),
    ("TRUNCATE public.execution_plans", INSUFFICIENT_PRIVILEGE),
    ("DELETE FROM public.execution_plan_orders WHERE strategy_id = :s", INSUFFICIENT_PRIVILEGE),
    ("UPDATE public.execution_plan_orders SET price = 1 WHERE strategy_id = :s", INSUFFICIENT_PRIVILEGE),
    ("UPDATE public.execution_plan_orders SET tag = 'X1' WHERE strategy_id = :s", INSUFFICIENT_PRIVILEGE),
    ("UPDATE public.execution_plans SET plan_number = 9 WHERE strategy_id = :s", INSUFFICIENT_PRIVILEGE),
    ("UPDATE public.execution_plans SET closed_at = NULL WHERE strategy_id = :s", INSUFFICIENT_PRIVILEGE),
    ("UPDATE public.execution_plans SET status = 'open', close_reason = NULL WHERE strategy_id = :s",
     PLAN_GUARD_SQLSTATE),
    ("UPDATE public.execution_plans SET status = 'closed' WHERE strategy_id = :s", CHECK_VIOLATION),
    ("UPDATE public.execution_plans SET close_reason = 'filled' WHERE strategy_id = :s", PLAN_GUARD_SQLSTATE),
])
async def test_the_database_refuses_deleting_or_rewriting_a_plan(app_engine, sql, sqlstate):
    async with _Tx(app_engine) as tx:
        await tx.enter("ENTRY", "BUY", "5.45")
        await _refused_sql(tx.conn, sql, sqlstate, {"s": tx.strategy_id})


async def test_a_closed_plan_cannot_be_reopened_and_closed_at_is_the_database_clock(app_engine):
    async with _Tx(app_engine) as tx:
        await tx.enter("ENTRY", "BUY", "5.45")
        closed = await _close(tx.conn, tx.user, tx.strategy_id, 1, "filled")
        now = (await tx.conn.execute(text("SELECT clock_timestamp()"))).scalar_one()
        assert closed.created_at <= closed.closed_at <= now
        await _refused_sql(tx.conn, "UPDATE public.execution_plans SET status = 'open', close_reason = NULL "
                                    "WHERE strategy_id = :s", PLAN_GUARD_SQLSTATE, {"s": tx.strategy_id})
        await _refused_sql(tx.conn, "UPDATE public.execution_plans SET close_reason = 'partial' WHERE strategy_id = :s",
                           PLAN_GUARD_SQLSTATE, {"s": tx.strategy_id})


_ORDER_INSERT = ("INSERT INTO public.execution_plan_orders (strategy_id, plan_number, leg_index, tag, instrument_id, "
                 "transaction_type, quantity, price) VALUES (:s, :p, :l, :tag, 'NSE_FO:47189', "
                 ":side, :q, :price)")


@pytest.mark.parametrize("over, sqlstate", [
    ({"tag": "OFS999V1L0"}, CHECK_VIOLATION),          # not the row's own tag
    ({"tag": "OFS{s}V1L0 "}, CHECK_VIOLATION),          # padding
    ({"side": "HOLD"}, CHECK_VIOLATION),
    ({"q": 0}, CHECK_VIOLATION),
    ({"price": 0}, CHECK_VIOLATION),
    ({"price": -1}, CHECK_VIOLATION),
    ({"l": -1, "tag": "OFS{s}V1L-1"}, CHECK_VIOLATION),
    ({"l": 0}, UNIQUE_VIOLATION),                       # the same tag again
    ({"p": 2, "tag": "OFS{s}V2L0"}, PLAN_GUARD_SQLSTATE),  # no such open plan
])
async def test_the_database_refuses_a_bad_order_row(app_engine, over, sqlstate):
    async with _Tx(app_engine) as tx:
        s = tx.strategy_id
        await tx.enter("ENTRY", "BUY", "5.45")
        params = {"s": s, "p": 1, "l": 1, "tag": f"OFS{s}V1L1", "side": "BUY", "q": 65, "price": Decimal("5.45")}
        params.update({k: v.format(s=s) if isinstance(v, str) else v for k, v in over.items()})
        if over.get("l") == 0:
            params["tag"] = make_tag(s, 1, 0)
        await _refused_sql(tx.conn, _ORDER_INSERT, sqlstate, params)


async def test_the_database_refuses_an_order_added_to_a_closed_plan(app_engine):
    async with _Tx(app_engine) as tx:
        s = tx.strategy_id
        await tx.enter("ENTRY", "BUY", "5.45")
        await _close(tx.conn, tx.user, s, 1, "filled")
        await _refused_sql(tx.conn, _ORDER_INSERT, PLAN_GUARD_SQLSTATE,
                           {"s": s, "p": 1, "l": 1, "tag": f"OFS{s}V1L1", "side": "BUY", "q": 65,
                            "price": Decimal("5.45")})


async def test_a_duplicate_tag_across_strategies_is_impossible(app_engine):
    """A tag must equal OFS<its own strategy>V<plan>L<leg>, and the tag column is UNIQUE: the other strategy's tag
    cannot be copied onto a row of this one."""
    async with _Tx(app_engine) as a:
        other = await _new_strategy(a.conn, a.user, catalogue=False)
        await a.enter("ENTRY", "BUY", "5.45")
        number = await plans.next_plan_number(a.conn, a.user, other)
        await plans.record_plan(a.conn, a.user, other, number, "ENTRY", (_order(other, number, "BUY", "5.45"),))
        assert other != a.strategy_id
        await _refused_sql(a.conn, _ORDER_INSERT, CHECK_VIOLATION,
                           {"s": other, "p": 1, "l": 1, "tag": make_tag(a.strategy_id, 1, 0), "side": "BUY",
                            "q": 65, "price": Decimal("5.45")})


#: _ORDER_INSERT with the catalogued real instrument, so the store can read the rows back (0018 tests).
_REAL_ORDER_INSERT = _ORDER_INSERT.replace("'NSE_FO:47189'", f"'{REAL_INSTRUMENT}'")


async def test_the_database_accepts_the_8_char_tag_of_its_own_row_only(app_engine):
    """0018: a new-grammar tag is accepted only when it encodes the row's own (strategy, plan, leg); another
    strategy's, plan's or leg's new-grammar tag is a CHECK violation."""
    async with _Tx(app_engine) as tx:
        s = tx.strategy_id
        await tx.enter("ENTRY", "BUY", "5.45")
        row = {"s": s, "p": 1, "side": "BUY", "q": 65, "price": Decimal("5.45")}
        for wrong in (make_tag(s + 1, 1, 1), make_tag(s, 2, 1), make_tag(s, 1, 2)):
            await _refused_sql(tx.conn, _REAL_ORDER_INSERT, CHECK_VIOLATION, {**row, "l": 1, "tag": wrong})
        await tx.conn.execute(text(_REAL_ORDER_INSERT), {**row, "l": 1, "tag": make_tag(s, 1, 1)})
        stored = (await plans.plans_for(tx.conn, tx.user, s))[0]
        assert [o.tag for o in stored.orders] == [make_tag(s, 1, 0), make_tag(s, 1, 1)]


async def test_a_plan_stored_with_legacy_tags_still_loads_and_closes(app_engine):
    """Rows written before 0018 carry OFS<s>V<p>L<l> (ofo_dev strategy 11 plan 1: OFS11V1L0); they stay valid, load
    through the store and close with fills keyed by their legacy tags."""
    async with _Tx(app_engine) as tx:
        s = tx.strategy_id
        await tx.conn.execute(text("INSERT INTO public.execution_plans (strategy_id, plan_number, action) "
                                   "VALUES (:s, 1, 'ENTRY')"), {"s": s})
        legacy = [f"OFS{s}V1L0", f"OFS{s}V1L1"]
        for leg, tag in enumerate(legacy):
            await tx.conn.execute(text(_REAL_ORDER_INSERT), {"s": s, "p": 1, "l": leg, "tag": tag, "side": "BUY",
                                                            "q": 65, "price": Decimal("5.45")})
        loaded = await plans.open_plan(tx.conn, tx.user, s)
        assert [o.tag for o in loaded.orders] == legacy
        # #313b: a close that changes position carries the trades that make up its fills, keyed by the legacy tags
        filled = dict.fromkeys(legacy, 65)
        closed = await plans.close_plan(tx.conn, tx.user, s, 1, reason="filled", filled=filled,
                                        fills=trades_for(filled))
        assert (closed.status, [o.filled_quantity for o in closed.orders]) == ("closed", [65, 65])
        assert await books.fills_for(tx.conn, tx.user, s) == {t: trades_for({t: 65}) for t in legacy}
        # a legacy tag that is not its row's own is still refused (the plan is closed now: use a fresh open plan)
        await tx.conn.execute(text("INSERT INTO public.execution_plans (strategy_id, plan_number, action) "
                                   "VALUES (:s, 2, 'EXIT')"), {"s": s})
        await _refused_sql(tx.conn, _REAL_ORDER_INSERT, CHECK_VIOLATION,
                           {"s": s, "p": 2, "l": 0, "tag": f"OFS{s + 1}V2L0", "side": "SELL", "q": 65,
                            "price": Decimal("5.45")})


async def test_the_application_role_cannot_insert_a_closed_plan_or_a_backdated_one(app_engine):
    """The INSERT grants are column-limited (status, closed_at, close_reason, created_at are not insertable)."""
    async with _Tx(app_engine) as tx:
        s = tx.strategy_id
        await _refused_sql(tx.conn, "INSERT INTO public.execution_plans (strategy_id, plan_number, action, status, "
                                    "closed_at, close_reason) VALUES (:s, 1, 'ENTRY', 'closed', now(), 'filled')",
                           INSUFFICIENT_PRIVILEGE, {"s": s})
        await _refused_sql(tx.conn, "INSERT INTO public.execution_plans (strategy_id, plan_number, action, created_at) "
                                    "VALUES (:s, 1, 'ENTRY', now())", INSUFFICIENT_PRIVILEGE, {"s": s})


async def test_the_owner_role_cannot_insert_a_closed_plan_either(admin_engine):
    """The guard (not only the grants) refuses a plan INSERTed closed. Mutation 'drop the INSERT branch of the plan
    guard' makes this insert succeed for the owner."""
    async with _Tx(admin_engine) as tx:
        await _refused_sql(tx.conn, "INSERT INTO public.execution_plans (strategy_id, plan_number, action, status, "
                                    "closed_at, close_reason) VALUES (:s, 1, 'ENTRY', 'closed', now(), 'filled')",
                           PLAN_GUARD_SQLSTATE, {"s": tx.strategy_id})


@pytest.mark.parametrize("column, value", [("plan_number", "9"), ("strategy_id", "strategy_id + 1000000"),
                                           ("action", "'EXIT'"), ("created_at", "now()")])
async def test_the_plan_guard_refuses_an_identity_change_even_by_the_owner(admin_engine, column, value):
    """The identity checks in the plan guard are unreachable for the application role (no UPDATE grant on those
    columns) but not for the owner: mutation 'drop that check' lets the owner rewrite a plan's identity."""
    async with _Tx(admin_engine) as tx:
        await tx.enter("ENTRY", "BUY", "5.45")
        await _refused_sql(tx.conn, "UPDATE public.execution_plans SET status = 'closed', closed_at = now(), "  # noqa: S608 test-constant column names
                                    f"close_reason = 'filled', {column} = {value} WHERE strategy_id = :s",
                           PLAN_GUARD_SQLSTATE, {"s": tx.strategy_id})


def test_only_the_tag_constraint_maps_to_tag_taken():
    """A plan primary-key clash is bad_plan with its own message (never tag_taken); the open index is plan_open."""
    clash = plans._unique_violation('duplicate key value violates unique constraint "execution_plans_pkey"')
    assert (clash.code, "plan number already stored" in clash.detail) == (plans.BAD_PLAN, True)
    tag = plans._unique_violation('duplicate key value violates unique constraint "execution_plan_orders_tag_key"')
    assert tag.code == plans.TAG_TAKEN
    assert plans._unique_violation('... "execution_plans_one_open"').code == plans.PLAN_OPEN
    assert plans._unique_violation('... "something_else"').code == plans.BAD_PLAN


# ---------------------------------------------------------------------------------------------------------------
# Two connections (commits; removes its own rows)
# ---------------------------------------------------------------------------------------------------------------


async def _remove_own_rows(admin_engine, contract_ids: list[int], user_ref: str) -> None:
    """Removes exactly this test's committed rows as the OWNER role (no superuser needed): the table owner may disable
    the USER triggers (the append-only guards) of the tables it deletes from, inside one transaction that re-enables
    them before it commits; foreign-key triggers are internal and stay on, so the order below is the one the keys
    allow. A row left behind fails the test loudly (a leftover plan would make a later replay downgrade refuse)."""
    async with admin_engine.connect() as conn:  # noqa: SIM117
        async with conn.begin():
            mine = "(SELECT id FROM public.strategies WHERE user_ref = :u)"
            tables = [r[0] for r in await conn.execute(text(
                "SELECT table_name FROM information_schema.columns WHERE table_schema = 'public' "
                "AND column_name = 'contract_id' ORDER BY 1"))]
            touched = ["execution_plan_orders", "execution_plans", "strategy_history", "strategies", *tables,
                       "catalogue_contracts"]
            for table in touched:
                await conn.execute(text(f'ALTER TABLE public."{table}" DISABLE TRIGGER USER'))
            for table in ("execution_plan_orders", "execution_plans", "strategy_history"):
                await conn.execute(text(f"DELETE FROM public.{table} WHERE strategy_id IN {mine}"), {"u": user_ref})  # noqa: S608
            await conn.execute(text("DELETE FROM public.strategies WHERE user_ref = :u"), {"u": user_ref})
            for table in tables:
                await conn.execute(text(f'DELETE FROM public."{table}" WHERE contract_id = ANY(:ids)'),  # noqa: S608
                                   {"ids": contract_ids})
            await conn.execute(text("DELETE FROM public.catalogue_contracts WHERE id = ANY(:ids)"),
                               {"ids": contract_ids})
            for table in touched:
                await conn.execute(text(f'ALTER TABLE public."{table}" ENABLE TRIGGER USER'))
            left = (await conn.execute(text("SELECT count(*) FROM public.strategies WHERE user_ref = :u"),
                                       {"u": user_ref})).scalar_one()
            assert left == 0, f"{left} strategies of this test could not be removed"


async def test_two_connections_cannot_both_pass_next_plan_number(app_engine, admin_engine):
    """Mutation 'drop the row lock': the second call would return at once instead of waiting for the first to commit."""
    user, ids = _user(), []
    try:
        async with app_engine.connect() as setup:
            async with setup.begin():
                sid = await _new_strategy(setup, user)
            ids = [int(r[0]) for r in (await setup.execute(text(
                "SELECT c.id FROM public.broker_instruments b JOIN public.catalogue_contracts c "
                "ON c.id = b.contract_id "
                "WHERE b.broker = 'zerodha' AND b.broker_symbol = ANY(:s)"), {"s": SYMBOLS})).all()]
        async with app_engine.connect() as first, app_engine.connect() as second:
            t1, t2 = await first.begin(), await second.begin()
            number = await plans.next_plan_number(first, user, sid)
            assert number == 1
            waiter = asyncio.create_task(plans.next_plan_number(second, user, sid))
            await asyncio.sleep(1.0)
            assert not waiter.done(), "the second call must wait for the first transaction"
            await plans.record_plan(first, user, sid, number, "ENTRY", (_order(sid, 1, "BUY", "5.45"),))
            await t1.commit()
            with pytest.raises(plans.PlanStoreError) as err:
                await asyncio.wait_for(waiter, 10)
            assert err.value.code == plans.PLAN_OPEN
            await t2.rollback()
    finally:
        await _remove_own_rows(admin_engine, ids, user)


# ---------------------------------------------------------------------------------------------------------------
# Filled quantities at close (the position per strategy comes from the database)
# ---------------------------------------------------------------------------------------------------------------


async def _two_leg_plan(tx) -> tuple[str, str]:
    sid = tx.strategy_id
    legs = (_order(sid, 1, "SELL", "101.05", leg=0), _order(sid, 1, "BUY", "12.30", leg=1))
    await plans.record_plan(tx.conn, tx.user, sid, await plans.next_plan_number(tx.conn, tx.user, sid), "ENTRY", legs)
    return legs[0].tag, legs[1].tag


async def test_closing_with_every_order_filled_stores_the_quantities(app_engine):
    async with _Tx(app_engine) as tx:
        a, b = await _two_leg_plan(tx)
        closed = await plans.close_plan(tx.conn, tx.user, tx.strategy_id, 1, reason="filled", filled={a: 65, b: 65},
                                        fills=trades_for({a: 65, b: 65}))
        assert [o.filled_quantity for o in closed.orders] == [65, 65]
        again = (await plans.plans_for(tx.conn, tx.user, tx.strategy_id))[0]
        assert [o.filled_quantity for o in again.orders] == [65, 65]


async def test_nothing_placed_without_fills_stores_zero(app_engine):
    async with _Tx(app_engine) as tx:
        await tx.enter("ENTRY", "BUY", "5.45")
        closed = await plans.close_plan(tx.conn, tx.user, tx.strategy_id, 1, reason="nothing_placed")
        assert [o.filled_quantity for o in closed.orders] == [0]


@pytest.mark.parametrize("reason", ["filled", "exited", "partial"])
async def test_a_position_changing_close_without_fills_is_refused(app_engine, reason):
    """Mutation 'allow filled=None': the plan would close with no quantities and a restart could not rebuild the
    position."""
    async with _Tx(app_engine) as tx:
        await tx.enter("ENTRY", "BUY", "5.45")
        await _refused(plans.BAD_PLAN, plans.close_plan(tx.conn, tx.user, tx.strategy_id, 1, reason=reason))
        stored = (await plans.plans_for(tx.conn, tx.user, tx.strategy_id))[0]
        assert (stored.status, [o.filled_quantity for o in stored.orders]) == ("open", [None])


@pytest.mark.parametrize("reason", ["filled", "exited"])
async def test_filled_and_exited_need_every_order_filled_in_full(app_engine, reason):
    async with _Tx(app_engine) as tx:
        a, b = await _two_leg_plan(tx)
        for fills in ({a: 65}, {a: 65, b: 64}, {}):
            await _refused(plans.BAD_PLAN, plans.close_plan(tx.conn, tx.user, tx.strategy_id, 1, reason=reason,
                                                            filled=fills))
        assert (await plans.open_plan(tx.conn, tx.user, tx.strategy_id)) is not None


async def test_partial_needs_some_filled_and_some_short(app_engine):
    async with _Tx(app_engine) as tx:
        a, b = await _two_leg_plan(tx)
        for fills in ({a: 65, b: 65}, {}, {a: 0, b: 0}):
            await _refused(plans.BAD_PLAN, plans.close_plan(tx.conn, tx.user, tx.strategy_id, 1, reason="partial",
                                                            filled=fills))
        closed = await plans.close_plan(tx.conn, tx.user, tx.strategy_id, 1, reason="partial", filled={a: 65},
                                        fills=trades_for({a: 65}))
        assert [o.filled_quantity for o in closed.orders] == [65, 0]  # the missing tag counts as 0


async def test_nothing_placed_needs_every_fill_zero(app_engine):
    async with _Tx(app_engine) as tx:
        a, _b = await _two_leg_plan(tx)
        await _refused(plans.BAD_PLAN, plans.close_plan(tx.conn, tx.user, tx.strategy_id, 1, reason="nothing_placed",
                                                        filled={a: 1}))
        closed = await plans.close_plan(tx.conn, tx.user, tx.strategy_id, 1, reason="nothing_placed", filled={})
        assert [o.filled_quantity for o in closed.orders] == [0, 0]


@pytest.mark.parametrize("fills", [{"OFS1V1L9": 1}, {"{a}": -1}, {"{a}": 66}, {"{a}": True}, {"{a}": 1.0}, {"{a}": "1"},
                                   ["x"]])
async def test_a_foreign_tag_or_impossible_quantity_is_refused(app_engine, fills):
    async with _Tx(app_engine) as tx:
        a, _ = await _two_leg_plan(tx)
        if isinstance(fills, dict):
            fills = {k.replace("{a}", a): v for k, v in fills.items()}
        await _refused(plans.BAD_PLAN, plans.close_plan(tx.conn, tx.user, tx.strategy_id, 1, reason="partial",
                                                        filled=fills))


async def test_the_database_guards_the_filled_quantity(app_engine, admin_engine):
    async with _Tx(app_engine) as tx:
        a, _b = await _two_leg_plan(tx)
        set_fill = "UPDATE public.execution_plan_orders SET filled_quantity = :f WHERE tag = :t"
        await _refused_sql(tx.conn, set_fill, CHECK_VIOLATION, {"f": 66, "t": a})  # above quantity
        await _refused_sql(tx.conn, set_fill, CHECK_VIOLATION, {"f": -1, "t": a})
        await _refused_sql(tx.conn, "UPDATE public.execution_plan_orders SET filled_quantity = NULL WHERE tag = :t",
                           PLAN_GUARD_SQLSTATE, {"t": a})
        await tx.conn.execute(text(set_fill), {"f": 10, "t": a})
        await _refused_sql(tx.conn, set_fill, PLAN_GUARD_SQLSTATE, {"f": 20, "t": a})  # written once
        insert_filled = _ORDER_INSERT.replace("price)", "price, filled_quantity)", 1).replace(":price)", ":price, 1)")
        params = {"s": tx.strategy_id, "p": 1, "l": 2, "tag": f"OFS{tx.strategy_id}V1L2", "side": "BUY", "q": 65,
                  "price": Decimal("5.45")}
        # the application role has no INSERT grant on filled_quantity: PostgreSQL refuses before the guard runs
        await _refused_sql(tx.conn, insert_filled, INSUFFICIENT_PRIVILEGE, params)
    async with _Tx(admin_engine) as owner:  # the owner role reaches the guard itself
        await _two_leg_plan(owner)
        params = {**params, "s": owner.strategy_id, "tag": f"OFS{owner.strategy_id}V1L2"}
        await _refused_sql(owner.conn, insert_filled, PLAN_GUARD_SQLSTATE, params)


# ---------------------------------------------------------------------------------------------------------------
# GC-BP F-3: every plan of many strategies in a fixed number of queries (GET /positions took 13-18 s at ~47
# strategies: 1 + ~3 queries per strategy over a 136 ms link)
# ---------------------------------------------------------------------------------------------------------------


class _Queries:
    """Counts the statements the engine sends while the block runs (SQLAlchemy before_cursor_execute)."""

    def __init__(self, engine) -> None:
        self.target, self.count = engine.sync_engine, 0

    def _seen(self, *_args) -> None:
        self.count += 1

    def __enter__(self):
        event.listen(self.target, "before_cursor_execute", self._seen)
        return self

    def __exit__(self, *_exc) -> None:
        event.remove(self.target, "before_cursor_execute", self._seen)


TWO_LEG = 2  # _mixed_strategies: the kind holding one open two-leg plan
MAX_POSITIONS_QUERIES = 6  # list strategies + owned, orders, symbols, plans (+ slack): never per strategy


async def _mixed_strategies(tx: _Tx, count: int) -> list[int]:
    """``count`` strategies of tx.user (tx.strategy_id first), plans by position modulo 4: 0 = entry closed filled +
    exit open (two plans, mixed statuses), 1 = no plan, 2 = one open two-leg plan (two instruments), 3 = one plan
    closed nothing_placed."""
    ids = [tx.strategy_id] + [await _new_strategy(tx.conn, tx.user, catalogue=False) for _ in range(count - 1)]
    second = _instrument_of(SYMBOLS[1])
    for n, sid in enumerate(ids):
        kind = n % 4
        if kind in (0, 3):
            await plans.record_plan(tx.conn, tx.user, sid, 1, "ENTRY", (_order(sid, 1, "BUY", "5.45"),))
            await _close(tx.conn, tx.user, sid, 1, "filled" if kind == 0 else "nothing_placed")
        if kind == 0:
            await plans.record_plan(tx.conn, tx.user, sid, 2, "EXIT", (_order(sid, 2, "SELL", "3.10"),))
        if kind == TWO_LEG:
            await plans.record_plan(tx.conn, tx.user, sid, 1, "ENTRY", (
                _order(sid, 1, "BUY", "5.45"),
                _order(sid, 1, "SELL", "4.00", leg=1, instrument_id=second, tradingsymbol=SYMBOLS[1])))
    return ids


async def test_f3_batched_read_equals_plans_for_per_strategy(app_engine):
    """F-3 equivalence: plans_for_strategies answers exactly what plans_for answers per strategy (same plans, same
    order, same orders and symbols), keys in the asked order, () for a strategy with no plan; no ids -> {}."""
    async with _Tx(app_engine) as tx:
        ids = await _mixed_strategies(tx, 6)
        asked = [ids[3], ids[0], ids[5], ids[1], ids[2], ids[4]]
        batched = await plans.plans_for_strategies(tx.conn, tx.user, asked)
        assert list(batched) == asked
        assert batched == {sid: await plans.plans_for(tx.conn, tx.user, sid) for sid in asked}
        assert batched[ids[1]] == () and [p.plan_number for p in batched[ids[0]]] == [1, 2]
        assert [(o.leg_index, o.tradingsymbol) for o in batched[ids[2]][0].orders] == [(0, SYMBOLS[0]),
                                                                                      (1, SYMBOLS[1])]
        assert await plans.plans_for_strategies(tx.conn, tx.user, []) == {}


async def test_f3_batched_read_refuses_like_plans_for(app_engine):
    """F-3 REQ-125: another user's, a missing or a malformed strategy id among the asked ids is not_found, exactly as
    plans_for refuses it; an order whose instrument has no Zerodha symbol is bad_plan, as plans_for."""
    async with _Tx(app_engine) as tx:
        ids = await _mixed_strategies(tx, 2)
        for who, asked in [("someone-else", ids), (tx.user, [ids[0], ids[1] + 10**6]), (tx.user, [ids[0], 0]),
                           (tx.user, [True])]:
            await _refused(plans.NOT_FOUND, plans.plans_for_strategies(tx.conn, who, asked))


class _SymbolRows:
    """A connection fake answering only the batched symbol query with fixed catalogue rows (no database)."""

    def __init__(self, rows) -> None:
        self.rows, self.calls = rows, 0

    async def execute(self, statement, params):
        assert statement is plans._SYMBOLS_MANY
        self.calls += 1
        return SimpleNamespace(all=lambda: [r for r in self.rows if r.exchange_token in params["toks"]])


def _row(seg: str, tok: int, symbol: str, live: bool) -> SimpleNamespace:
    return SimpleNamespace(exchange_segment=seg, exchange_token=tok, broker_symbol=symbol, live=live)


@pytest.mark.parametrize("ids, rows, message", [
    (["NFO-OPT:1", "bad", "NFO-OPT:2"], [_row("NFO-OPT", 1, "A", True)], "'bad' is not"),  # malformed id, in turn
    (["NFO-OPT:2", "bad"], [], "'NFO-OPT:2' has 0"),  # an earlier id with no row fails first
    (["NFO-OPT:1"], [_row("NFO-OPT", 1, "A", False), _row("NFO-OPT", 1, "B", False)], "has 2"),  # two, none live
    (["NFO-OPT:1"], [_row("BFO-OPT", 1, "A", True)], "has 0"),  # same token, other segment: not this instrument
])
async def test_f3_batched_symbols_refuse_like_zerodha_symbol(ids, rows, message):
    """F-3 answer state "a plan row that cannot be read": the one-query symbol read refuses as bad_plan exactly where
    a zerodha_symbol loop over the same ids would, first failure first (route: strategy_stored_unreadable)."""
    with pytest.raises(plans.PlanStoreError, match=message) as err:
        await plans._symbols_of(_SymbolRows(rows), ids)
    assert err.value.code == plans.BAD_PLAN


async def test_f3_batched_symbols_one_query_live_first():
    """F-3: every id in one query; a live symbol wins over a retired one, as zerodha_symbol picks."""
    conn = _SymbolRows([_row("NFO-OPT", 1, "OLD", False), _row("NFO-OPT", 1, "NEW", True),
                        _row("NFO-OPT", 2, "B", True)])
    assert await plans._symbols_of(conn, ["NFO-OPT:2", "NFO-OPT:1", "NFO-OPT:2"]) == {"NFO-OPT:2": "B",
                                                                                    "NFO-OPT:1": "NEW"}
    assert conn.calls == 1
    assert await plans._symbols_of(conn, []) == {} and conn.calls == 1


async def test_f3_attribution_query_count_does_not_grow_with_strategies(app_engine):
    """F-3 detection for the class: attribute_and_compare (the GET /positions read) sends the same number of
    statements for 2 strategies as for 6 (old code: 1 + ~3 per strategy), and still counts every strategy's plans."""
    def clock():
        return datetime.now(IST)

    counts, held = {}, {}
    for k in (2, 6):
        async with _Tx(app_engine) as tx:
            ids = await _mixed_strategies(tx, k)
            sources = ra.Sources(await load_catalogue(tx.conn), clock)
            with _Queries(app_engine) as seen:
                result = await ra.attribute_and_compare(ra.Account(tx.conn, tx.user), {}, {}, (), sources,
                                                        at=clock())
            counts[k] = seen.count
            held[k] = {int(sid) for sid in result.held} | {int(p.strategy_id) for e in result.pending.values()
                                                            for p in e}
            expected = {sid for n, sid in enumerate(ids) if n % 4 in (0, 2)}  # a fill or an open plan
            assert held[k] == expected
    assert counts[2] == counts[6] <= MAX_POSITIONS_QUERIES, counts
