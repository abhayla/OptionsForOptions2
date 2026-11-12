"""Migration 0052 (GC-TRACK1 k06, ADR-292 (2), ADR-048): public.strategy_held_entries, an insert-only table.

The app role inserts and reads one row per strategy; it cannot update, delete or truncate; a future entry time, a broker
text over 40 characters or with a line break, and a second row for one strategy are refused by the table itself; the
downgrade is refused while a row exists and round-trips without one. Every test rolls back.
"""
from __future__ import annotations

import pytest
from _migration_replay import recorded, round_trip_sql
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_strategy_store import _user, _with_draft

MIGRATION = "0052_strategy_held_entries.py"
_INSERT = text("INSERT INTO public.strategy_held_entries (strategy_id, entry_at, broker_text) "
               "VALUES (:i, now() - interval '1 day', :b)")
_COUNT = text("SELECT count(*) FROM public.strategy_held_entries")
_TABLE = "SELECT to_regclass('public.strategy_held_entries') IS NOT NULL"


@pytest.fixture
async def db(app_engine):
    async with app_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


async def _strategy(conn) -> int:
    _, stored = await _with_draft(conn, _user())
    return stored.id


async def test_the_app_role_inserts_and_reads_one_row(db):
    sid = await _strategy(db)
    await db.execute(_INSERT, {"i": sid, "b": "Upstox"})
    row = (await db.execute(text("SELECT entry_at, broker_text, created_at FROM public.strategy_held_entries "
                                 "WHERE strategy_id = :i"), {"i": sid})).one()
    assert row.broker_text == "Upstox"
    assert row.entry_at < row.created_at


@pytest.mark.parametrize("sql", [
    "UPDATE public.strategy_held_entries SET broker_text = 'x' WHERE strategy_id = :i",
    "DELETE FROM public.strategy_held_entries WHERE strategy_id = :i",
    "TRUNCATE public.strategy_held_entries"])
async def test_the_app_role_cannot_update_delete_or_truncate(db, sql):
    sid = await _strategy(db)
    await db.execute(_INSERT, {"i": sid, "b": None})
    with pytest.raises(DBAPIError):
        async with db.begin_nested():
            await db.execute(text(sql), {"i": sid} if ":i" in sql else {})
    assert (await db.execute(_COUNT)).scalar_one() == 1


async def test_a_future_entry_time_is_refused_by_the_check(db):
    sid = await _strategy(db)
    with pytest.raises(DBAPIError, match="check"):
        async with db.begin_nested():
            await db.execute(text("INSERT INTO public.strategy_held_entries (strategy_id, entry_at) "
                                  "VALUES (:i, now() + interval '1 day')"), {"i": sid})


@pytest.mark.parametrize("broker", ["x" * 41, "", "a\nb", "a\rb"])
async def test_a_bad_broker_text_is_refused_by_the_check(db, broker):
    sid = await _strategy(db)
    with pytest.raises(DBAPIError, match="check"):
        async with db.begin_nested():
            await db.execute(_INSERT, {"i": sid, "b": broker})


async def test_a_second_row_for_one_strategy_is_refused(db):
    sid = await _strategy(db)
    await db.execute(_INSERT, {"i": sid, "b": None})
    with pytest.raises(DBAPIError):
        async with db.begin_nested():
            await db.execute(_INSERT, {"i": sid, "b": None})


async def test_downgrade_is_refused_with_a_row_and_round_trips_without_one(admin_engine):
    own_down = recorded(MIGRATION, "downgrade")
    _, own_up, down, up = round_trip_sql(MIGRATION)
    assert "'pre'" in own_up[0] and "'post'" in own_up[-1] and "'post'" in own_down[-1]
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            sid = await _strategy(conn)
            await conn.execute(_INSERT, {"i": sid, "b": None})
            with pytest.raises(DBAPIError, match=r"refusing to downgrade 0052_strategy_held_entries: 1 stored"):
                async with conn.begin_nested():
                    for sql in own_down:
                        await conn.execute(text(sql))
        finally:
            await trans.rollback()
        trans = await conn.begin()
        try:
            for sql in down:
                await conn.execute(text(sql))
            assert (await conn.execute(text(_TABLE))).scalar() is False
            for sql in up:
                await conn.execute(text(sql))
            assert (await conn.execute(text(_TABLE))).scalar() is True
        finally:
            await trans.rollback()
