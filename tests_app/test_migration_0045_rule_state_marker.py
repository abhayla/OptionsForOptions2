"""Migration 0045 (ADR-258, issue 65): the rule-state starting-point marker, on real PostgreSQL.

- round trip as the owner (head -> 0044 -> head): the marker column with its server-side default, the key
  (strategy, rule, adjustment_no), and the allow-list post check passing on both sides (the guard re-pinned up, the old
  pin restored down);
- the downgrade is refused with a count while a row started after an adjustment exists;
- the guard keeps the marker fixed; one rule at two starting points is two rows.
Every test rolls back.
"""
from __future__ import annotations

import pytest
from _migration_replay import round_trip_sql
from ofo_app import playbook_store as pb
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_strategy_store import _user, _with_draft

MIGRATION = "0045_rule_state_adjustment_no.py"
_STATE = text(
    "SELECT (SELECT column_default FROM information_schema.columns WHERE table_schema = 'public' "
    " AND table_name = 'adjustment_rule_state' AND column_name = 'adjustment_no') AS marker_default, "
    "(SELECT array_agg(a.attname::text ORDER BY array_position(c.conkey, a.attnum)) FROM pg_constraint c "
    " JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey) "
    " WHERE c.conname = 'adjustment_rule_state_pkey') AS key_columns, "
    "md5(pg_get_functiondef('public.adjustment_rule_state_guard()'::regprocedure)) AS guard")


async def _state(conn) -> tuple:
    return tuple((await conn.execute(_STATE)).one())


async def test_round_trip_adds_marker_and_key_and_downgrade_restores_0031(admin_engine):
    own_down, own_up, down, up = round_trip_sql(MIGRATION)
    assert "'pre'" in own_up[0] and "'post'" in own_up[-1] and "'post'" in own_down[-1]
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            head = await _state(conn)
            assert "current_setting('ofo.rule_adjustment_no'" in head[0]
            assert head[1] == ["strategy_id", "rule_id", "adjustment_no"]
            for sql in down:  # ends with the allow-list post check against 0043's pins (the old guard body)
                await conn.execute(text(sql))
            after = await _state(conn)
            assert after[:2] == (None, ["strategy_id", "rule_id"]) and after[2] != head[2]
            for sql in up:  # ends with the post check against the re-pinned guard
                await conn.execute(text(sql))
            assert await _state(conn) == head
        finally:
            await trans.rollback()


async def test_downgrade_is_refused_with_a_count_while_a_marked_row_exists(admin_engine):
    own_down, _, _, _ = round_trip_sql(MIGRATION)
    user = _user()
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            _, stored = await _with_draft(conn, user)
            await pb.put_rule_state(conn, user, stored.id, "T-01", held_at_entry=True, seen_clear=False)
            await pb.put_rule_state(conn, user, stored.id, "T-01", held_at_entry=False, seen_clear=False,
                                    adjustment_no=1)
            assert await pb.rule_states(conn, user, stored.id) == {0: {"T-01": (True, False)},
                                                                   1: {"T-01": (False, False)}}
            with pytest.raises(DBAPIError, match=r"refusing downgrade: 1 rule state rows"):
                async with conn.begin_nested():
                    for sql in own_down:
                        await conn.execute(text(sql))
            # the guard keeps adjustment_no fixed (asyncpg's message carries the text, not the SQLSTATE)
            with pytest.raises(DBAPIError, match="a rule state only records seen clear, once"):
                async with conn.begin_nested():
                    await conn.execute(text("UPDATE public.adjustment_rule_state SET adjustment_no = 2 "
                                            "WHERE strategy_id = :s AND adjustment_no = 1"), {"s": stored.id})
        finally:
            await trans.rollback()
