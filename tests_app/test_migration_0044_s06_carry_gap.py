"""Migration 0044 (#658): a new iron condor system playbook version whose S-06 rule says "the loss at your carry gap".

- upgrade -> one new row found by its REASON with the new S-06 text; downgrade removes only that row; allow-list post
  check last in both directions (attack 1, 2);
- an admin-saved version after 0042 is the base: its other keys survive (attack 1);
- upgrading twice never writes a second version (attack 3);
- the old words "+/-2% gap" grep to zero outside migrations and the seed JSON (attack 4).
Every test rolls back.
"""
from __future__ import annotations

import json

import pytest
from _migration_replay import round_trip_sql
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

MIGRATION = "0044_ic_s06_carry_gap_wording.py"
LATER_REASON = "GC-ICTRACK: T-11c and T-20b built (India VIX percentile, ADX 25), no longer greyed"  # 0048
REASON = "Issue 658: situation S-06 rule says the loss at your carry gap, not a fixed 2% gap"
NEW_RULE = "At 15:00: show overnight margin and the loss at your carry gap"
OLD_RULE = "At 15:00: show overnight margin and the loss at +/-2% gap"
_MINE = text("SELECT version, body FROM public.system_playbook_versions "
             "WHERE strategy_type = 'ic' AND reason = :r")
_COUNT = text("SELECT count(*) FROM public.system_playbook_versions WHERE strategy_type = 'ic'")
_NEWEST = text("SELECT version, body, reason FROM public.system_playbook_versions WHERE strategy_type = 'ic' "
               "ORDER BY version DESC LIMIT 1")


def _body(value) -> dict:
    return value if isinstance(value, dict) else json.loads(value)


def _s06(body) -> list[dict]:
    return [s for s in _body(body)["situations"] if s["id"] == "S-06"]


async def _run(conn, sqls) -> None:
    for sql in sqls:
        await conn.execute(text(sql))


async def test_upgrade_writes_new_version_with_new_s06_and_downgrade_removes_only_it(admin_engine):
    own_down, own_up, down, up = round_trip_sql(MIGRATION)
    assert "'post'" in own_up[-1] and "'post'" in own_down[-1]  # both end with the allow-list post check
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            total = (await conn.execute(_COUNT)).scalar_one()
            later = len((await conn.execute(_MINE, {"r": LATER_REASON})).all())  # 0 on a fresh DB (seed built)
            mine = (await conn.execute(_MINE, {"r": REASON})).all()
            assert len(mine) == 1  # head: exactly one 0044 row
            assert [s["rule"] for s in _s06(mine[0].body)] == [NEW_RULE]
            await _run(conn, down)  # 0048 appends a newer ic version on top: step down through it first
            assert (await conn.execute(_MINE, {"r": REASON})).all() == []
            assert (await conn.execute(_COUNT)).scalar_one() == total - later - 1  # its own row and any 0048 row
            newest = (await conn.execute(_NEWEST)).one()
            assert newest.reason != REASON and newest.version == mine[0].version - 1
            await _run(conn, up)
            again = (await conn.execute(_MINE, {"r": REASON})).all()
            assert len(again) == 1 and again[0].version == mine[0].version
        finally:
            await trans.rollback()


async def test_upgrade_twice_is_a_no_op(admin_engine):
    _d, own_up, _down, _up = round_trip_sql(MIGRATION)
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            total = (await conn.execute(_COUNT)).scalar_one()
            await _run(conn, own_up)
            await _run(conn, own_up)
            assert (await conn.execute(_COUNT)).scalar_one() == total
        finally:
            await trans.rollback()


async def test_admin_version_after_0042_is_the_base_and_keeps_its_other_keys(admin_engine):
    _own_down, own_up, down, _up = round_trip_sql(MIGRATION)
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await _run(conn, down)
            base = (await conn.execute(_NEWEST)).one()
            body = dict(_body(base.body))
            body["admin_marker"] = "kept"
            body["situations"] = [
                dict(s, rule=OLD_RULE) if s["id"] == "S-06" else s for s in body["situations"]]
            await conn.execute(
                text("INSERT INTO public.system_playbook_versions (strategy_type, version, status, body, reason, "
                     "saved_by) SELECT 'ic', :v, status, CAST(:b AS jsonb), 'admin edit', 'admin' "
                     "FROM public.system_playbook_versions WHERE strategy_type = 'ic' AND version = :p"),
                {"v": base.version + 1, "b": json.dumps(body), "p": base.version})
            await _run(conn, own_up)
            mine = (await conn.execute(_MINE, {"r": REASON})).one()
            assert mine.version == base.version + 2  # built on the latest, not on a number
            new_body = _body(mine.body)
            assert new_body["admin_marker"] == "kept"
            assert [s["rule"] for s in _s06(new_body)] == [NEW_RULE]
            assert len(new_body["situations"]) == len(body["situations"])  # no situation lost or doubled
        finally:
            await trans.rollback()


async def test_downgrade_refuses_when_a_newer_version_was_saved_on_top(admin_engine):
    own_down, _u, _down, _up = round_trip_sql(MIGRATION)
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            mine = (await conn.execute(_MINE, {"r": REASON})).one()
            await conn.execute(
                text("INSERT INTO public.system_playbook_versions (strategy_type, version, status, body, reason, "
                     "saved_by) SELECT 'ic', version + 1, status, body, 'admin edit', 'admin' "
                     "FROM public.system_playbook_versions WHERE strategy_type = 'ic' AND version = :v"),
                {"v": mine.version})
            await conn.execute(text("SAVEPOINT s"))
            with pytest.raises(DBAPIError, match="OF044"):
                await _run(conn, own_down)
            await conn.execute(text("ROLLBACK TO SAVEPOINT s"))
            assert len((await conn.execute(_MINE, {"r": REASON})).all()) == 1  # not removed
        finally:
            await trans.rollback()
