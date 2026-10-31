"""GC-ADJ2 step 1A (REQ-158): migration 0031 creates the playbook store, seeds the 12 system playbooks, grants the
application role exactly its columns, and its downgrade refuses while user rows exist.

Spec basis (quoted): REQ-158 AC-1 "one read-only system playbook for each of the 12 strategy types"; AC-7 "Every
playbook value is stored data, not code". Real PostgreSQL only; every test rolls back. The round trip runs as the owner.
"""
from __future__ import annotations

import importlib.util

import pytest
from _migration_replay import VERSIONS, round_trip_sql
from ofo.adjustment import playbook_types
from ofo.errors import gate_slots
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_migration_0028_paper_orders import _privileges, _scalar

MIGRATION = "0031_adjustment_playbooks.py"
TABLES = ("adjustment_playbooks", "adjustment_playbook_active", "strategy_adjustment_plans", "adjustment_rule_state",
          "adjustment_suggestions")


def _module():
    found = importlib.util.spec_from_file_location("ofo_test_0031", VERSIONS / MIGRATION)
    module = importlib.util.module_from_spec(found)
    found.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def test_the_frozen_type_keys_and_name_limit_match_the_one_table():
    m = _module()
    assert m.TYPE_KEYS == playbook_types.TYPE_KEYS
    assert m.NAME_MAX == playbook_types.NAME_MAX == gate_slots._PLAYBOOK_NAME_MAX
    assert [r["strategy_type"] for r in m.seed_rows()] == list(playbook_types.TYPE_KEYS)


def test_a_seed_file_missing_a_type_or_holding_a_float_is_refused(tmp_path):
    m = _module()
    short = tmp_path / "short.json"
    short.write_text('{"playbooks": []}', encoding="utf-8")
    with pytest.raises(RuntimeError, match="12 strategy types"):
        m.seed_rows(short)
    floaty = tmp_path / "float.json"
    floaty.write_text('{"playbooks": [{"strategy_type": "ic", "x": 0.5}]}', encoding="utf-8")
    with pytest.raises(RuntimeError, match="float"):
        m.seed_rows(floaty)


async def _state(conn) -> dict:
    out = {}
    for table in TABLES:
        out[table] = await _scalar(conn, f"SELECT to_regclass('public.{table}') IS NOT NULL")
        if out[table]:
            out[f"{table} grants"] = await _privileges(conn, table)
    out["system rows"] = (await _scalar(conn, "SELECT count(*) FROM public.adjustment_playbooks WHERE is_system")
                          if out["adjustment_playbooks"] else None)
    return out


async def test_upgrade_creates_and_seeds_downgrade_drops_and_upgrade_again_restores(admin_engine):
    own_down, own_up, down, up = round_trip_sql(MIGRATION)
    assert "'pre'" in own_up[0] and "'post'" in own_up[-1] and "'post'" in own_down[-1]
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            head = await _state(conn)
            assert head["system rows"] == len(playbook_types.TYPE_KEYS)
            assert all(head[t] for t in TABLES)
            for sql in down:
                await conn.execute(text(sql))
            assert not any((await _state(conn))[t] for t in TABLES)
            for sql in up:
                await conn.execute(text(sql))
            assert await _state(conn) == head
        finally:
            await trans.rollback()


async def test_downgrade_is_refused_with_a_count_while_a_user_playbook_exists(admin_engine):
    own_down, _, _, _ = round_trip_sql(MIGRATION)
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            body = await _scalar(conn, "SELECT body::text FROM public.adjustment_playbooks "
                                       "WHERE is_system AND strategy_type = 'ic'")
            await conn.execute(text("INSERT INTO public.adjustment_playbooks (user_ref, strategy_type, name, body) "
                                    "VALUES ('test-down', 'ic', 'Mine', CAST(:b AS JSONB))"), {"b": body})
            with pytest.raises(DBAPIError, match=r"refusing downgrade: 1 user playbook"):
                async with conn.begin_nested():
                    for sql in own_down:
                        await conn.execute(text(sql))
            assert (await _state(conn))["adjustment_playbooks"]
        finally:
            await trans.rollback()
