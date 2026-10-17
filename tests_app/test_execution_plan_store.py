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

import pytest
from ofo.engine.legs import Action
from ofo.execution.basket import make_tag
from ofo.strategy import stored_form as sf
from ofo_app import execution_plan_store as plans
from ofo_app import strategy_store as store
from ofo_app.catalogue_store import apply_update, parse_rows_naming_the_row
from sqlalchemy import text
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
REAL_SYMBOL = "NIFTY26O1923650CE"  # basket-121848.json
REAL_INSTRUMENT = "NSE_FO:47189"  # orders-122104.json instrument_token 12080386 >> 8


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


async def _close(conn, user: str, strategy_id: int, number: int, reason: str) -> plans.StoredPlan:
    """Closes a ONE-leg plan the way the caller must: a close that changes position carries the filled quantities."""
    tag = make_tag(strategy_id, number, 0)
    fills = {"filled": {tag: LOT}, "exited": {tag: LOT}, "partial": {tag: LOT // 2}, "nothing_placed": None}[reason]
    return await plans.close_plan(conn, user, strategy_id, number, reason=reason, filled=fills)


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
    assert make_tag(1, 1, 0) == "OFS1V1L0" and make_tag(1, 2, 0) == "OFS1V2L0"
    async with _Tx(app_engine) as tx:
        sid = tx.strategy_id
        entry = await tx.enter("ENTRY", "BUY", "5.45")
        assert (entry.strategy_id, entry.plan_number, entry.action, entry.status) == (sid, 1, "ENTRY", "open")
        assert [(o.tag, o.tradingsymbol, o.transaction_type, o.quantity, o.price) for o in entry.orders] == [
            (f"OFS{sid}V1L0", REAL_SYMBOL, "BUY", 65, Decimal("5.45"))]
        # a second Execute while plan 1 is open is refused, and nothing is minted
        await _refused(plans.PLAN_OPEN, plans.next_plan_number(tx.conn, tx.user, sid))
        assert (await plans.open_plan(tx.conn, tx.user, sid)).plan_number == 1
        closed = await _close(tx.conn, tx.user, sid, 1, "filled")
        assert (closed.status, closed.close_reason) == ("closed", "filled") and closed.closed_at is not None
        assert await plans.open_plan(tx.conn, tx.user, sid) is None
        exit_plan = await tx.enter("EXIT", "SELL", "3.10")
        assert exit_plan.plan_number == 2 and exit_plan.action == "EXIT"
        assert [(o.tag, o.transaction_type, o.quantity, o.price) for o in exit_plan.orders] == [
            (f"OFS{sid}V2L0", "SELL", 65, Decimal("3.10"))]
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
            (i, f"OFS{sid}V1L{i}", Decimal(p)) for i, p in enumerate(["101.05", "12.30", "99.00", "0.05"])]
        assert (await plans.open_plan(tx.conn, tx.user, sid)).orders == stored.orders


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
                 "tradingsymbol, transaction_type, quantity, price) VALUES (:s, :p, :l, :tag, 'NSE_FO:47189', 'X', "
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
            params["tag"] = f"OFS{s}V1L0"
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
                           {"s": other, "p": 1, "l": 1, "tag": f"OFS{a.strategy_id}V1L0", "side": "BUY",
                            "q": 65, "price": Decimal("5.45")})


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
        closed = await plans.close_plan(tx.conn, tx.user, tx.strategy_id, 1, reason="filled", filled={a: 65, b: 65})
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
        closed = await plans.close_plan(tx.conn, tx.user, tx.strategy_id, 1, reason="partial", filled={a: 65})
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


async def test_the_database_guards_the_filled_quantity(app_engine):
    async with _Tx(app_engine) as tx:
        a, _b = await _two_leg_plan(tx)
        s = tx.strategy_id
        set_fill = "UPDATE public.execution_plan_orders SET filled_quantity = :f WHERE tag = :t"
        await _refused_sql(tx.conn, set_fill, CHECK_VIOLATION, {"f": 66, "t": a})  # above quantity
        await _refused_sql(tx.conn, set_fill, CHECK_VIOLATION, {"f": -1, "t": a})
        await _refused_sql(tx.conn, "UPDATE public.execution_plan_orders SET filled_quantity = NULL WHERE tag = :t",
                           PLAN_GUARD_SQLSTATE, {"t": a})
        await tx.conn.execute(text(set_fill), {"f": 10, "t": a})
        await _refused_sql(tx.conn, set_fill, PLAN_GUARD_SQLSTATE, {"f": 20, "t": a})  # written once
        insert_filled = _ORDER_INSERT.replace("price)", "price, filled_quantity)", 1).replace(":price)", ":price, 1)")
        await _refused_sql(tx.conn, insert_filled, PLAN_GUARD_SQLSTATE,
                           {"s": s, "p": 1, "l": 2, "tag": f"OFS{s}V1L2", "side": "BUY", "q": 65,
                            "price": Decimal("5.45")})
