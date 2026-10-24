"""REQ-134 AC-1/AC-3 (W-157, part 29b): migration 0025 stores a strategy's name beside its definition.

Spec basis (quoted): REQ-134 AC-1 "1 to 40 characters after trimming spaces"; "Two strategies of one user may share a name";
AC-3 "Renaming changes only the name; it adds a history entry ... and never changes legs, prices, tracking state or
version"; ADR-048 (the limited application role keeps what it had, plus the name column).

Core proof (first three tests): the limited ofo_app role writes a name on INSERT, a name-only UPDATE passes the guard
trigger and leaves the definition, the revision and the last-saved time alone, and an UPDATE of any other column is
still refused. Real PostgreSQL only; every test rolls back. The downgrade round trip runs as the owner (admin_engine)
through the SQL the migrations themselves execute (tests_app/_migration_replay.py).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from _migration_replay import VERSIONS, round_trip_sql
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

MIGRATION = "0025_strategy_name.py"
CHECK_VIOLATION = "23514"
GUARD_REFUSAL = "OF008"
NO_PRIVILEGE = "42501"
INSERT = ("INSERT INTO public.strategies (user_ref, underlying, definition, definition_schema_version, name) "
          "VALUES (:u, 'NIFTY', CAST(:d AS JSONB), 1, :n) RETURNING id")
INSERT_NO_NAME = ("INSERT INTO public.strategies (user_ref, underlying, definition, definition_schema_version) "
                  "VALUES (:u, 'NIFTY', CAST(:d AS JSONB), 1) RETURNING id")
INSERT_HISTORY = ("INSERT INTO public.strategy_history (strategy_id, change_summary, definition, "
                  "definition_schema_version) VALUES (:id, CAST(:s AS JSONB), CAST(:d AS JSONB), 1)")
SNAPSHOT = text("SELECT name, revision, updated_at, definition::text AS definition FROM public.strategies WHERE id = :id")
LEG = {"contract_id": 1001, "action": "SELL", "instrument": "CE", "strike": "23000", "expiry": "2026-10-29",
       "quantity": 75}
DEFINITION = json.dumps({"schema_version": 1, "underlying": "NIFTY", "legs": [LEG], "rules_ref": None,
                         "risk_limits": {}, "preferences": {}})


def _migration():
    found = importlib.util.spec_from_file_location("ofo_migration_0025_under_test", VERSIONS / MIGRATION)
    module = importlib.util.module_from_spec(found)
    found.loader.exec_module(module)  # type: ignore[union-attr]
    return module


async def _verdict(conn, sql: str, params: dict) -> tuple[str | None, str]:
    """(sqlstate, message) when PostgreSQL refuses the write, (None, '') when it accepts it. Always rolled back."""
    savepoint = await conn.begin_nested()
    try:
        await conn.execute(text(sql), params)
        return None, ""
    except DBAPIError as err:
        return getattr(err.orig, "sqlstate", None), str(err.orig)
    finally:
        await savepoint.rollback()


async def _new_strategy(conn, user: str, name: str = "NIFTY Oct condor") -> int:
    return (await conn.execute(text(INSERT), {"u": user, "d": DEFINITION, "n": name})).scalar_one()


# --- core proof ------------------------------------------------------------------------------------------------------


async def test_core_1_the_app_role_inserts_a_strategy_with_a_name(app_engine):
    """CORE (a): INSERT of a strategy row with a name by the limited role is accepted and reads back as written."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            strategy_id = await _new_strategy(conn, "test-0025-insert")
            row = (await conn.execute(SNAPSHOT, {"id": strategy_id})).one()
            assert (row.name, row.revision) == ("NIFTY Oct condor", 1)
        finally:
            await trans.rollback()


async def test_core_2_a_name_only_update_by_the_app_role_passes_the_guard_and_leaves_the_definition_alone(app_engine):
    """CORE (b): UPDATE of ONLY the name is accepted; definition, revision and the last-saved time are unchanged."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            strategy_id = await _new_strategy(conn, "test-0025-rename")
            before = (await conn.execute(SNAPSHOT, {"id": strategy_id})).one()
            await conn.execute(text("UPDATE public.strategies SET name = 'Condor wider' WHERE id = :id"),
                               {"id": strategy_id})
            after = (await conn.execute(SNAPSHOT, {"id": strategy_id})).one()
            assert after.name == "Condor wider"
            assert (after.definition, after.revision, after.updated_at) == (
                before.definition, before.revision, before.updated_at)
        finally:
            await trans.rollback()


@pytest.mark.parametrize("column,value", [("status", "'draft'"), ("user_ref", "'someone-else'"),
                                          ("underlying", "'SENSEX'"), ("revision", "9"),
                                          ("created_at", "now()"), ("definition_schema_version", "2")])
async def test_core_3_an_update_of_any_other_column_is_still_refused_for_the_app_role(app_engine, column, value):
    """CORE (c): the app role has column UPDATE on definition, updated_at and name only; the rest is refused (42501)."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            strategy_id = await _new_strategy(conn, "test-0025-other")
            state, _ = await _verdict(conn, f"UPDATE public.strategies SET {column} = {value} WHERE id = :id",
                                      {"id": strategy_id})
            assert state == NO_PRIVILEGE, f"{column}: {state}"
            state, _ = await _verdict(conn, f"UPDATE public.strategies SET name = 'x', {column} = {value} "
                                            "WHERE id = :id", {"id": strategy_id})
            assert state == NO_PRIVILEGE, f"name + {column}: {state}"
        finally:
            await trans.rollback()


@pytest.mark.parametrize("column,value", [("user_ref", "'someone-else'"), ("underlying", "'SENSEX'"),
                                          ("revision", "9"), ("definition_schema_version", "2")])
async def test_the_guard_itself_refuses_every_fixed_column_even_for_the_owner(admin_engine, column, value):
    """Attack 3: the guard trigger (not only the grants) still refuses a change to a fixed column beside the name."""
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            strategy_id = await _new_strategy(conn, "test-0025-guard")
            state, message = await _verdict(
                conn, f"UPDATE public.strategies SET name = 'renamed', {column} = {value} WHERE id = :id",
                {"id": strategy_id})
            assert state in (GUARD_REFUSAL, CHECK_VIOLATION), f"{column}: {state} {message}"
            assert (await conn.execute(SNAPSHOT, {"id": strategy_id})).one().name == "NIFTY Oct condor"
        finally:
            await trans.rollback()


# --- the name rule in the database --------------------------------------------------------------------------------


async def test_a_row_saved_without_a_name_gets_the_default(app_engine):
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            strategy_id = (await conn.execute(text(INSERT_NO_NAME), {"u": "test-0025-default", "d": DEFINITION})
                           ).scalar_one()
            assert (await conn.execute(SNAPSHOT, {"id": strategy_id})).one().name == _migration().DEFAULT_NAME
        finally:
            await trans.rollback()


@pytest.mark.parametrize("name,ok", [("a", True), ("x" * 40, True), ("", False), ("   ", False), ("x" * 41, False),
                                     ("two\nlines", False), ("tab\there", False), ("nul\x7fdel", False),
                                     ("<b>You should buy now</b>", True)])
async def test_name_boundaries_in_the_database(app_engine, name, ok):
    """Attack 4 (database side): 1 and 40 characters pass, 0, spaces only, 41 and control characters are refused;
    markup is just text."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            state, _ = await _verdict(conn, INSERT, {"u": "test-0025-bounds", "d": DEFINITION, "n": name})
            assert state == (None if ok else CHECK_VIOLATION), (name, state)
        finally:
            await trans.rollback()


async def test_duplicate_names_are_allowed(app_engine):
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            first = await _new_strategy(conn, "test-0025-dupe", "Same")
            second = await _new_strategy(conn, "test-0025-dupe", "Same")
            assert first != second
        finally:
            await trans.rollback()


# --- the rename history item -------------------------------------------------------------------------------------


@pytest.mark.parametrize("summary,ok", [
    ([{"kind": "renamed", "from": "Old", "to": "New"}], True),
    ([{"kind": "renamed", "from": "You should buy now", "to": "x" * 40}], True),
    ([{"kind": "renamed", "from": "Old"}], False),
    ([{"kind": "renamed", "from": "Old", "to": "New", "extra": "1"}], False),
    ([{"kind": "renamed", "from": "Old", "to": ""}], False),
    ([{"kind": "renamed", "from": "Old", "to": "x" * 41}], False),
    ([{"kind": "renamed", "from": " Old", "to": "New"}], False),
    ([{"kind": "renamed", "from": "Old", "to": 5}], False),
    ([{"kind": "renamed", "from": "Old", "to": "line\nbreak"}], False),
    ([{"kind": "renamed_by_someone", "from": "Old", "to": "New"}], False),
])
async def test_the_renamed_history_item_is_a_closed_shape(app_engine, summary, ok):
    """AC-3: the history item is exactly kind, from, to - two trimmed 1..40 character strings; anything else is refused."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            strategy_id = await _new_strategy(conn, "test-0025-history")
            state, _ = await _verdict(conn, INSERT_HISTORY, {"id": strategy_id, "s": json.dumps(summary),
                                                             "d": DEFINITION})
            assert state == (None if ok else CHECK_VIOLATION), (summary, state)
        finally:
            await trans.rollback()


# --- grants, downgrade, constants ---------------------------------------------------------------------------------


async def _grants(conn) -> list:
    rows = await conn.execute(text(
        "SELECT 'table', table_name, privilege_type, column_name FROM information_schema.column_privileges "
        "WHERE grantee = 'ofo_app' AND table_name IN ('strategies', 'strategy_history') "
        "UNION ALL SELECT 'function', p.proname, 'EXECUTE', has_function_privilege('ofo_app', p.oid, 'EXECUTE')::text "
        "FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = 'public' AND p.proname LIKE 'ofo_strategy_%' ORDER BY 1, 2, 3, 4"))
    return [tuple(r) for r in rows]


async def test_the_app_role_gains_exactly_insert_and_update_on_name(admin_engine):
    """ADR-048: against the state before 0025, the only new grants are INSERT and UPDATE on strategies.name (plus the
    table-level SELECT every column inherits); the allow-list 'post' check inside each step passes."""
    own_down, own_up, down, up = round_trip_sql(MIGRATION)
    assert "'post'" in own_up[-1] and "'post'" in own_down[-1]
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            now = await _grants(conn)
            for sql in down:
                await conn.execute(text(sql))
            before = await _grants(conn)
            assert set(before) < set(now)
            assert set(now) - set(before) == {("table", "strategies", "SELECT", "name"),
                                              ("table", "strategies", "INSERT", "name"),
                                              ("table", "strategies", "UPDATE", "name")}
            for sql in up:
                await conn.execute(text(sql))
            assert await _grants(conn) == now
        finally:
            await trans.rollback()


async def test_downgrade_is_refused_while_a_chosen_name_or_a_rename_entry_is_stored(admin_engine):
    """The downgrade refuses (naming the table) while a strategy holds a name other than the default, and while
    a history entry holds a renamed item."""
    own_down, _, _, _ = round_trip_sql(MIGRATION)
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            strategy_id = await _new_strategy(conn, "test-0025-down", "Chosen")
            with pytest.raises(DBAPIError, match=r"public\.strategies has a name the user chose"):
                async with conn.begin_nested():
                    await conn.execute(text(own_down[0]))
            await conn.execute(text("UPDATE public.strategies SET name = 'New Strategy' WHERE id = :id"),
                               {"id": strategy_id})
            await conn.execute(text(INSERT_HISTORY), {"id": strategy_id, "d": DEFINITION, "s": json.dumps(
                [{"kind": "renamed", "from": "A", "to": "B"}])})
            with pytest.raises(DBAPIError, match=r"public\.strategy_history holds a rename entry"):
                async with conn.begin_nested():
                    await conn.execute(text(own_down[0]))
        finally:
            await trans.rollback()


def test_the_migration_constants_equal_the_domains():
    """A migration never imports application code; this pins its copies to ofo.strategy.stored_form's."""
    from ofo.strategy import stored_form as sf

    migration = _migration()
    assert (migration.NAME_MAX, migration.DEFAULT_NAME) == (sf.STRATEGY_NAME_MAX, sf.DEFAULT_STRATEGY_NAME)
    assert Path(VERSIONS / MIGRATION).exists()
