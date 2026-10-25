"""REQ-070 AC-6 (W-156, part 28b): migration 0026 adds strategies.deleted_at (hide a never-executed draft, keep its rows).

Spec basis (quoted): REQ-070 AC-6 "the draft is hidden from every list and kept on the server with its history for
audit"; ADR-118 "Deleting never erases history or audit rows"; ADR-048 (the limited application role keeps what it had,
plus one column UPDATE).

Real PostgreSQL only; every test rolls back. The round trip runs as the owner (admin_engine) through the SQL the
migrations themselves execute (tests_app/_migration_replay.py).
"""

from __future__ import annotations

import json

import pytest
from _migration_replay import later_than, recorded, round_trip_sql
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

MIGRATION = "0026_strategy_deleted_at.py"
GUARD_REFUSAL = "OF008"
NO_PRIVILEGE = "42501"
LEG = {"contract_id": 1001, "action": "SELL", "instrument": "CE", "strike": "23000", "expiry": "2026-10-29",
       "quantity": 75}
DEFINITION = json.dumps({"schema_version": 1, "underlying": "NIFTY", "legs": [LEG], "rules_ref": None,
                         "risk_limits": {}, "preferences": {}})
INSERT = ("INSERT INTO public.strategies (user_ref, underlying, definition, definition_schema_version) "
          "VALUES (:u, 'NIFTY', CAST(:d AS JSONB), 1) RETURNING id")
SNAPSHOT = text("SELECT revision, updated_at, deleted_at, definition::text AS definition FROM public.strategies "
                "WHERE id = :id")


async def _new(conn, user: str) -> int:
    return (await conn.execute(text(INSERT), {"u": user, "d": DEFINITION})).scalar_one()


async def test_core_a_deleted_at_only_update_keeps_updated_at_and_revision_and_back(app_engine):
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            strategy_id = await _new(conn, "test-0026-hide")
            before = (await conn.execute(SNAPSHOT, {"id": strategy_id})).one()
            assert before.deleted_at is None
            await conn.execute(text("UPDATE public.strategies SET deleted_at = clock_timestamp() WHERE id = :id"),
                               {"id": strategy_id})
            hidden = (await conn.execute(SNAPSHOT, {"id": strategy_id})).one()
            assert hidden.deleted_at is not None
            assert (hidden.revision, hidden.updated_at, hidden.definition) == (
                before.revision, before.updated_at, before.definition)
            await conn.execute(text("UPDATE public.strategies SET deleted_at = NULL WHERE id = :id"),
                               {"id": strategy_id})
            assert tuple((await conn.execute(SNAPSHOT, {"id": strategy_id})).one()) == tuple(before)
        finally:
            await trans.rollback()


async def test_the_app_role_cannot_insert_deleted_at(app_engine):
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            point = await conn.begin_nested()
            with pytest.raises(DBAPIError) as err:
                await conn.execute(text(
                    "INSERT INTO public.strategies (user_ref, underlying, definition, definition_schema_version, "
                    "deleted_at) VALUES ('test-0026-born', 'NIFTY', CAST(:d AS JSONB), 1, now())"), {"d": DEFINITION})
            await point.rollback()
            assert getattr(err.value.orig, "sqlstate", None) == NO_PRIVILEGE
        finally:
            await trans.rollback()


@pytest.mark.parametrize("column,value", [("status", "'draft'"), ("user_ref", "'someone-else'"),
                                          ("underlying", "'SENSEX'"), ("revision", "9"),
                                          ("created_at", "now()"), ("definition_schema_version", "2")])
async def test_any_other_fixed_column_is_still_refused_for_the_app_role(app_engine, column, value):
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            strategy_id = await _new(conn, "test-0026-fixed")
            point = await conn.begin_nested()
            with pytest.raises(DBAPIError) as err:
                await conn.execute(text(f"UPDATE public.strategies SET {column} = {value} WHERE id = :id"),  # noqa: S608
                                   {"id": strategy_id})
            await point.rollback()
            assert getattr(err.value.orig, "sqlstate", None) in {NO_PRIVILEGE, GUARD_REFUSAL}
        finally:
            await trans.rollback()


async def test_the_guard_itself_refuses_a_fixed_column_alongside_deleted_at_for_the_owner(admin_engine):
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            strategy_id = await _new(conn, "test-0026-owner")
            point = await conn.begin_nested()
            with pytest.raises(DBAPIError) as err:
                await conn.execute(text("UPDATE public.strategies SET deleted_at = now(), revision = 9 "
                                        "WHERE id = :id"), {"id": strategy_id})
            await point.rollback()
            assert getattr(err.value.orig, "sqlstate", None) == GUARD_REFUSAL
        finally:
            await trans.rollback()


async def _grants(conn) -> list[tuple]:
    rows = await conn.execute(text(
        "SELECT 'table', table_name, privilege_type, column_name FROM information_schema.column_privileges "
        "WHERE grantee = 'ofo_app' AND table_name = 'strategies' ORDER BY 1, 2, 3, 4"))
    return [tuple(r) for r in rows]


async def test_the_app_role_gains_exactly_update_on_deleted_at(admin_engine):
    own_down, own_up, _, _ = round_trip_sql(MIGRATION)
    assert "'post'" in own_up[-1] and "'post'" in own_down[-1]
    later_down = [sql for n in reversed(later_than(MIGRATION)) for sql in recorded(n, "downgrade")]
    later_up = [sql for n in later_than(MIGRATION) for sql in recorded(n, "upgrade")]
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            for sql in later_down:
                await conn.execute(text(sql))
            now = await _grants(conn)
            for sql in own_down:
                await conn.execute(text(sql))
            before = await _grants(conn)
            assert set(before) < set(now)
            assert set(now) - set(before) == {("table", "strategies", "SELECT", "deleted_at"),
                                              ("table", "strategies", "UPDATE", "deleted_at")}
            for sql in own_up + later_up:
                await conn.execute(text(sql))
            assert sorted(await _grants(conn)) == sorted(now)
        finally:
            await trans.rollback()


async def test_downgrade_is_refused_while_a_row_is_hidden(admin_engine):
    own_down, _, _, _ = round_trip_sql(MIGRATION)
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            strategy_id = await _new(conn, "test-0026-down")
            await conn.execute(text("UPDATE public.strategies SET deleted_at = now() WHERE id = :id"),
                               {"id": strategy_id})
            with pytest.raises(DBAPIError, match=r"public\.strategies is hidden"):
                async with conn.begin_nested():
                    await conn.execute(text(own_down[0]))
        finally:
            await trans.rollback()
