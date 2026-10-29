"""GC-TP step 1a (REQ-109 AC-4; ADR-207): migration 0028 adds public.paper_orders and copies every tracked leg and
paper exit into it, exactly, then makes the three old tables read-only for the application role.

Spec basis (quoted): REQ-109 AC-4 "The one engine derives the net position per contract from the orders"; ADR-048 (the
limited application role: SELECT and column-limited INSERT, nothing else); the threat model of the GC-TP 1a brief: the
migration must not lose, duplicate or re-price any tracked leg or exit.

Real PostgreSQL only; every test rolls back. The round trip runs as the owner (admin_engine) through the SQL the
migrations themselves execute (tests_app/_migration_replay.py).
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from _migration_replay import round_trip_sql
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_strategy_store import _user, _with_draft

MIGRATION = "0028_paper_orders.py"
GUARD_REFUSAL = "OF028"
UNIQUE_REFUSAL = "23505"
TABLE = "paper_orders"
INSERT_COLUMNS = {"strategy_id", "contract_id", "side", "quantity", "price", "kind", "placed_at", "reason",
                  "trigger_id"}
ALL_COLUMNS = INSERT_COLUMNS | {"id", "created_at"}
OLD_TABLES = ("strategy_tracking", "strategy_tracking_legs", "strategy_tracking_exits")
MARKER = "-- 21. paper orders"
AT = datetime.datetime(2026, 10, 28, 4, 48, 17, tzinfo=datetime.UTC)
SYMBOLS = ["NIFTY26O1322800CE", "NIFTY26O1323000CE", "NIFTY26O1322400PE", "NIFTY26O1322200PE"]


async def _scalar(conn, sql: str, params: dict | None = None):
    return (await conn.execute(text(sql), params or {})).scalar_one()


async def _count(conn, table: str) -> int:
    return await _scalar(conn, f"SELECT count(*) FROM public.{table}")  # noqa: S608 constant table names


async def _privileges(conn, table: str) -> tuple[list[str], list[tuple[str, str]]]:
    tables = sorted(r[0] for r in await conn.execute(text(
        "SELECT privilege_type FROM information_schema.table_privileges "
        "WHERE grantee = 'ofo_app' AND table_schema = 'public' AND table_name = :t"), {"t": table}))
    columns = sorted(tuple(r) for r in await conn.execute(text(
        "SELECT privilege_type, column_name FROM information_schema.column_privileges "
        "WHERE grantee = 'ofo_app' AND table_schema = 'public' AND table_name = :t"), {"t": table}))
    return tables, columns


async def _state(conn) -> dict:
    allowlist = ("SELECT prosrc FROM pg_proc WHERE oid = to_regprocedure("
                 "'public.ofo_assert_app_role_allowlist(text,text)')")
    return {
        "table": await _scalar(conn, "SELECT to_regclass('public.paper_orders') IS NOT NULL"),
        "guard": await _scalar(conn, "SELECT to_regprocedure('public.paper_orders_guard()') IS NOT NULL"),
        "trigger": await _scalar(conn, "SELECT count(*) FROM pg_trigger WHERE tgname = 'paper_orders_guard' "
                                       "AND NOT tgisinternal"),
        "block": MARKER in await _scalar(conn, allowlist),
        "allowlist_md5": await _scalar(conn, allowlist.replace("prosrc", "md5(prosrc)")),
        "privileges": await _privileges(conn, TABLE),
        "old_inserts": {t: [c for c in (await _privileges(conn, t))[1] if c[0] == "INSERT"] for t in OLD_TABLES},
    }


async def _contracts(conn) -> list[int]:
    rows = (await conn.execute(text(
        "SELECT b.broker_symbol, c.id FROM public.broker_instruments b JOIN public.catalogue_contracts c "
        "ON c.id = b.contract_id WHERE b.broker = 'zerodha' AND b.broker_symbol = ANY(:s)"), {"s": SYMBOLS})).all()
    ids = {r[0]: int(r[1]) for r in rows}
    return [ids[s] for s in SYMBOLS]


async def _seed_old(conn, legs: list[tuple[int, str, int, str]],
                    exits: list[tuple[int, str, datetime.datetime]]) -> int:
    """A tracked strategy in the 0021/0027 tables (as the owner): legs = (contract index, side, qty, entry price);
    exits = (leg index, exit price, exited_at)."""
    _, stored = await _with_draft(conn, _user())  # loads the catalogue too
    contracts = await _contracts(conn)
    await conn.execute(text(
        "INSERT INTO public.strategy_tracking (strategy_id, strategy_revision, price_health, prices_at) "
        "VALUES (:s, :r, 'available', :at)"), {"s": stored.id, "r": stored.revision, "at": AT})
    for i, (c, side, qty, price) in enumerate(legs):
        await conn.execute(text(
            "INSERT INTO public.strategy_tracking_legs (strategy_id, leg_index, contract_id, side, quantity, "
            "entry_price, price_at) VALUES (:s, :i, :c, :side, :q, :p, :at)"),
            {"s": stored.id, "i": i, "c": contracts[c], "side": side, "q": qty, "p": Decimal(price),
             "at": AT + datetime.timedelta(seconds=i)})
    for leg, price, at in exits:
        await conn.execute(text(
            "INSERT INTO public.strategy_tracking_exits (strategy_id, leg_index, exit_price, price_at, exited_at) "
            "VALUES (:s, :i, :p, :at, :at)"), {"s": stored.id, "i": leg, "p": Decimal(price), "at": at})
    return stored.id


async def _orders(conn, strategy_id: int) -> list[tuple]:
    rows = await conn.execute(text("SELECT contract_id, side, quantity, price, kind, placed_at "
                                   "FROM public.paper_orders "
                                   "WHERE strategy_id = :s ORDER BY id"), {"s": strategy_id})
    return [(int(r[0]), r[1], int(r[2]), r[3], r[4], r[5]) for r in rows]


async def test_upgrade_creates_table_guard_grants_and_old_tables_read_only_downgrade_restores(admin_engine):
    _own_down, own_up, down, up = round_trip_sql(MIGRATION)
    assert "'post'" in own_up[-1] and "'pre'" in own_up[0]
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            head = await _state(conn)
            assert (head["table"], head["guard"], head["trigger"], head["block"]) == (True, True, 1, True)
            assert head["privileges"] == (["SELECT"], sorted([("INSERT", c) for c in INSERT_COLUMNS]
                                                             + [("SELECT", c) for c in ALL_COLUMNS]))
            assert head["old_inserts"] == {t: [] for t in OLD_TABLES}  # read-only for the app role
            for sql in down:
                await conn.execute(text(sql))
            before = await _state(conn)
            assert (before["table"], before["guard"], before["trigger"], before["block"]) == (False, False, 0, False)
            assert before["privileges"] == ([], [])
            assert all(before["old_inserts"][t] for t in OLD_TABLES)  # the old column INSERT grants are back
            assert before["allowlist_md5"] != head["allowlist_md5"]
            for sql in up:
                await conn.execute(text(sql))
            assert await _state(conn) == head
            for sql in down + up:
                await conn.execute(text(sql))
            assert await _state(conn) == head
        finally:
            await trans.rollback()


async def test_upgrade_copies_every_leg_and_exit_exactly_in_leg_order(admin_engine):
    _, _, down, up = round_trip_sql(MIGRATION)
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            for sql in down:
                await conn.execute(text(sql))
            late, early = AT + datetime.timedelta(hours=3), AT + datetime.timedelta(hours=1)
            sid = await _seed_old(conn, [(0, "SELL", 65, "39.15"), (1, "BUY", 65, "12.95"),
                                                    (2, "SELL", 130, "82.73"), (3, "BUY", 65, "35.80")],
                                  [(0, "41.00", late), (2, "80.10", early)])
            other = await _seed_old(conn, [(3, "BUY", 75, "1.01")], [])
            counts = [await _count(conn, t) for t in OLD_TABLES]
            for sql in up:
                await conn.execute(text(sql))
            c = await _contracts(conn)
            assert await _orders(conn, sid) == [
                (c[0], "SELL", 65, Decimal("39.15"), "open", AT),
                (c[1], "BUY", 65, Decimal("12.95"), "open", AT + datetime.timedelta(seconds=1)),
                (c[2], "SELL", 130, Decimal("82.73"), "open", AT + datetime.timedelta(seconds=2)),
                (c[3], "BUY", 65, Decimal("35.80"), "open", AT + datetime.timedelta(seconds=3)),
                (c[2], "BUY", 130, Decimal("80.10"), "exit", early),  # exits in exited_at order
                (c[0], "BUY", 65, Decimal("41.00"), "exit", late),
            ]
            assert await _orders(conn, other) == [(c[3], "BUY", 75, Decimal("1.01"), "open", AT)]
            assert await _scalar(conn, "SELECT count(*) FROM public.paper_orders WHERE reason IS NOT NULL "
                                       "OR trigger_id IS NOT NULL") == 0
            # the old rows are untouched (read later by a backup check; dropped by a later migration)
            assert [await _count(conn, t) for t in OLD_TABLES] == counts
        finally:
            await trans.rollback()


async def test_upgrade_refuses_a_strategy_tracking_one_contract_on_two_legs(admin_engine):
    own_down, own_up, _, _ = round_trip_sql(MIGRATION)
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            for sql in own_down:
                await conn.execute(text(sql))
            await _seed_old(conn, [(0, "SELL", 65, "39.15"), (0, "BUY", 65, "40.00")], [])
            with pytest.raises(DBAPIError, match="a strategy tracks one contract on two legs"):
                async with conn.begin_nested():
                    for sql in own_up:
                        await conn.execute(text(sql))
        finally:
            await trans.rollback()


async def _one_order(conn, contract_index: int = 0, trigger_id: int | None = None, strategy_id: int | None = None
                     ) -> int:
    if strategy_id is None:
        _, stored = await _with_draft(conn, _user())
        strategy_id = stored.id
    contracts = await _contracts(conn)
    await conn.execute(text("INSERT INTO public.paper_orders (strategy_id, contract_id, side, quantity, price, kind, "
                            "placed_at, reason, trigger_id) VALUES (:s, :c, 'BUY', 65, 10.00, 'stop', :at, 'test', :t)"),  # noqa: E501
                       {"s": strategy_id, "c": contracts[contract_index], "at": AT, "t": trigger_id})
    return strategy_id


@pytest.mark.parametrize("sql", ["UPDATE public.paper_orders SET price = 1 WHERE strategy_id = :i",
                                 "DELETE FROM public.paper_orders WHERE strategy_id = :i"], ids=["update", "delete"])
async def test_the_guard_refuses_update_and_delete_even_for_the_owner(admin_engine, sql):
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            strategy_id = await _one_order(conn)
            with pytest.raises(DBAPIError) as err:
                async with conn.begin_nested():
                    await conn.execute(text(sql), {"i": strategy_id})
            assert getattr(err.value.orig, "sqlstate", None) == GUARD_REFUSAL
            assert await _scalar(conn, "SELECT price FROM public.paper_orders WHERE strategy_id = :i",
                                 {"i": strategy_id}) == Decimal("10.00")
        finally:
            await trans.rollback()


async def test_one_trigger_writes_one_order_per_contract_never_two_for_one_contract(admin_engine):
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            sid = await _one_order(conn, 0, trigger_id=7)
            await _one_order(conn, 1, trigger_id=7, strategy_id=sid)  # same trigger, another contract: accepted
            with pytest.raises(DBAPIError) as err:
                async with conn.begin_nested():
                    await _one_order(conn, 0, trigger_id=7, strategy_id=sid)
            assert getattr(err.value.orig, "sqlstate", None) == UNIQUE_REFUSAL
            await _one_order(conn, 0, trigger_id=None, strategy_id=sid)  # no trigger: no uniqueness
            await _one_order(conn, 0, trigger_id=None, strategy_id=sid)
            assert await _scalar(conn, "SELECT count(*) FROM public.paper_orders WHERE strategy_id = :s",
                                 {"s": sid}) == 4  # noqa: PLR2004 the four accepted orders above
        finally:
            await trans.rollback()


async def test_downgrade_is_refused_while_an_order_placed_after_the_copy_is_stored(admin_engine):
    own_down, _, _, _ = round_trip_sql(MIGRATION)
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await _one_order(conn)
            with pytest.raises(DBAPIError, match=r"refusing downgrade: public\.paper_orders holds paper orders "
                                                 r"placed after the copy"):
                async with conn.begin_nested():
                    await conn.execute(text(own_down[0]))
            assert (await _state(conn))["table"] is True
        finally:
            await trans.rollback()
