"""GC-BP step 5 (REQ-109 AC-4): migration 0027 adds public.strategy_tracking_exits (one insert-only paper exit row per
leg). GC-BP step 8 review M3: the round trip, the guard, the grants and the downgrade refusal, as 0024-0026 have.

Spec basis (quoted): REQ-109 AC-4 "Paper exit records each leg's exit price at that moment on the same basis and
freezes the paper P&L"; ADR-048 (the limited application role: SELECT and column-limited INSERT, nothing else);
the migration's own docstring "downgrade: refuses while any exit row is stored (a paper exit is a record)".

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
from test_strategy_store import _ids, _user, _with_draft

MIGRATION = "0027_strategy_tracking_exits.py"
GUARD_REFUSAL = "OF027"
TABLE = "strategy_tracking_exits"
INSERT_COLUMNS = {"strategy_id", "leg_index", "exit_price", "price_at"}
ALL_COLUMNS = INSERT_COLUMNS | {"exited_at"}
MARKER = "-- 20. strategy tracking exits"
FEED_KEYS = ["NSE_FO:44624", "NSE_FO:44632", "NSE_FO:44604", "NSE_FO:44595"]
AT = datetime.datetime(2026, 10, 8, 3, 50, tzinfo=datetime.UTC)


async def _state(conn) -> dict:
    """What 0027 makes, read from the catalogs: the table, its guard function and trigger, the allow-list's block 20,
    the app role's table and column privileges, and the allow-list function's body hash."""
    one = conn.execute
    return {
        "table": (await one(text(f"SELECT to_regclass('public.{TABLE}') IS NOT NULL"))).scalar_one(),
        "guard": (await one(text("SELECT to_regprocedure('public.strategy_tracking_exits_guard()') IS NOT NULL"))
                  ).scalar_one(),
        "trigger": (await one(text("SELECT count(*) FROM pg_trigger WHERE tgname = 'strategy_tracking_exits_guard' "
                                   "AND NOT tgisinternal"))).scalar_one(),
        "block": MARKER in (await one(text(
            "SELECT prosrc FROM pg_proc WHERE oid = to_regprocedure('public.ofo_assert_app_role_allowlist(text,text)')"
        ))).scalar_one(),
        "allowlist_md5": (await one(text(
            "SELECT md5(prosrc) FROM pg_proc WHERE oid = to_regprocedure('public.ofo_assert_app_role_allowlist("
            "text,text)')"))).scalar_one(),
        "table_privileges": sorted(r[0] for r in await one(text(
            "SELECT privilege_type FROM information_schema.table_privileges "
            "WHERE grantee = 'ofo_app' AND table_schema = 'public' AND table_name = :t"), {"t": TABLE})),
        "column_privileges": sorted(tuple(r) for r in await one(text(
            "SELECT privilege_type, column_name FROM information_schema.column_privileges "
            "WHERE grantee = 'ofo_app' AND table_schema = 'public' AND table_name = :t"), {"t": TABLE})),
    }


def _expected_privileges() -> list[tuple[str, str]]:
    return sorted([("INSERT", c) for c in INSERT_COLUMNS] + [("SELECT", c) for c in ALL_COLUMNS])


async def test_upgrade_creates_the_table_guard_and_grants_downgrade_restores_and_upgrade_replays(admin_engine):
    _own_down, own_up, down, up = round_trip_sql(MIGRATION)
    assert "'post'" in own_up[-1] and "'pre'" in own_up[0]
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            head = await _state(conn)
            assert (head["table"], head["guard"], head["trigger"], head["block"]) == (True, True, 1, True)
            assert head["table_privileges"] == ["SELECT"]  # no UPDATE / DELETE / TRUNCATE / table-wide INSERT
            assert head["column_privileges"] == _expected_privileges()
            for sql in down:
                await conn.execute(text(sql))
            before = await _state(conn)
            assert (before["table"], before["guard"], before["trigger"], before["block"]) == (False, False, 0, False)
            assert (before["table_privileges"], before["column_privileges"]) == ([], [])
            assert before["allowlist_md5"] != head["allowlist_md5"]
            for sql in up:
                await conn.execute(text(sql))
            assert await _state(conn) == head
            for sql in down + up:  # a second round trip replays to the same state
                await conn.execute(text(sql))
            assert await _state(conn) == head
        finally:
            await trans.rollback()


async def _one_exit(conn, user: str) -> int:
    """A tracked strategy with leg 0 exited, written as the owner straight into the 0021/0027 tables (read-only for
    the application role since migration 0028; the old tracking_store writers are deleted, GC-TP 1a part 4)."""
    _, stored = await _with_draft(conn, user)
    assert len(await _ids(conn)) >= len(FEED_KEYS)
    await conn.execute(text("INSERT INTO public.strategy_tracking (strategy_id, strategy_revision, price_health, "
                            "prices_at) VALUES (:s, :r, 'available', :at)"),
                       {"s": stored.id, "r": stored.revision, "at": AT})
    for i, (contract_id, leg) in enumerate(zip(stored.saved.contract_ids, stored.saved.definition.legs, strict=True)):
        await conn.execute(text("INSERT INTO public.strategy_tracking_legs (strategy_id, leg_index, contract_id, side, "
                                "quantity, entry_price, price_at) VALUES (:s, :i, :c, :side, :q, 10.00, :at)"),
                           {"s": stored.id, "i": i, "c": contract_id, "side": leg.action.value, "q": leg.quantity,
                            "at": AT})
    await conn.execute(text("INSERT INTO public.strategy_tracking_exits (strategy_id, leg_index, exit_price, "
                            "price_at) VALUES (:s, 0, 11.00, :at)"), {"s": stored.id, "at": AT})
    return stored.id


@pytest.mark.parametrize("sql", ["UPDATE public.strategy_tracking_exits SET exit_price = 1 WHERE strategy_id = :i",
                                 "DELETE FROM public.strategy_tracking_exits WHERE strategy_id = :i"],
                         ids=["update", "delete"])
async def test_the_guard_refuses_update_and_delete_even_for_the_owner(admin_engine, sql):
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            strategy_id = await _one_exit(conn, _user())
            with pytest.raises(DBAPIError) as err:
                async with conn.begin_nested():
                    await conn.execute(text(sql), {"i": strategy_id})
            assert getattr(err.value.orig, "sqlstate", None) == GUARD_REFUSAL
            rows = (await conn.execute(text("SELECT leg_index, exit_price FROM public.strategy_tracking_exits "
                                            "WHERE strategy_id = :i"), {"i": strategy_id})).all()
            assert [(int(r[0]), r[1]) for r in rows] == [(0, Decimal("11.00"))]
        finally:
            await trans.rollback()


async def test_downgrade_is_refused_while_any_exit_row_is_stored(admin_engine):
    own_down, _, _, _ = round_trip_sql(MIGRATION)
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await _one_exit(conn, _user())
            with pytest.raises(DBAPIError, match=r"refusing downgrade: public\.strategy_tracking_exits holds paper "
                                                 r"exits"):
                async with conn.begin_nested():
                    await conn.execute(text(own_down[0]))
            assert (await _state(conn))["table"] is True
        finally:
            await trans.rollback()
