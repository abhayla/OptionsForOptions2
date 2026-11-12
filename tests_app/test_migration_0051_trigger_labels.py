"""Migration 0051 (issue #685 item 5a, REQ-169 AC-2): the four corrected trigger labels (T-09, T-11c, T-14t, T-19) reach
an EXISTING database as a NEW version of every system playbook that still holds an old label (copy of 0048's tests).

- head: every type's current version reads the new labels, nothing else in the body differs, older versions and
  user copies / saved plans are untouched; downgrade removes only the new rows;
- a type whose current body lacks the triggers or has the new words gets no version; upgrading twice adds none;
- an admin-saved newer version is the base (its other keys survive);
- a newer version saved on top refuses the downgrade (OF051).
A fresh database is seeded from the seed file, which already has the new words, so 0051 writes nothing there;
``_old_db`` saves a version with the old words on top of every type first (what a database seeded earlier holds).
Every test rolls back.
"""
from __future__ import annotations

import copy
import json

import pytest
from _migration_replay import own_step_sql
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

MIGRATION = "0051_trigger_label_words.py"
REASON = "Issue 685: trigger labels T-09, T-11c, T-14t and T-19 say at or below / reaches, as the compare does"
OLD = {
    "T-09": "A short leg's premium falls below Rs (close for pennies)",
    "T-11c": "IV percentile above",
    "T-14t": "Theta per day falls below this % of premium left",
    "T-19": "Premium still left to earn is below this many x the adjustment's cost",
}
NEW = {
    "T-09": "A short leg's premium falls to Rs or below (close for pennies)",
    "T-11c": "IV percentile reaches",
    "T-14t": "Theta per day falls to this % of premium left or below",
    "T-19": "Premium still left to earn is this many x the adjustment's cost or below",
}
PLAYBOOKS = 12  # system playbooks in the seed
_ALL = text("SELECT strategy_type, version, body, reason FROM public.system_playbook_versions "
            "ORDER BY strategy_type, version")
_MINE = text("SELECT strategy_type, version, body FROM public.system_playbook_versions WHERE reason = :r "
             "ORDER BY strategy_type")
_USER = text("SELECT count(*), md5(string_agg(id::text || body::text, ',' ORDER BY id)) "
             "FROM public.adjustment_playbooks")
_INSERT = text("INSERT INTO public.system_playbook_versions (strategy_type, version, status, body, reason, saved_by) "
               "SELECT :t, :v, status, CAST(:b AS jsonb), 'admin edit', 'admin' "
               "FROM public.system_playbook_versions WHERE strategy_type = :t AND version = :p")


def _body(value) -> dict:
    return value if isinstance(value, dict) else json.loads(value)


def _newest(rows) -> dict:
    """strategy_type -> (version, body) of its newest row."""
    out: dict = {}
    for row in rows:
        out[row.strategy_type] = (row.version, _body(row.body))
    return out


def _relabel(body: dict, words: dict) -> dict:
    body = copy.deepcopy(body)
    for trigger, label in words.items():
        if trigger in body["triggers"]:
            body["triggers"][trigger]["label"] = label
    return body


async def _save(conn, strategy_type: str, base_version: int, body: dict) -> None:
    await conn.execute(_INSERT, {"t": strategy_type, "v": base_version + 1, "b": json.dumps(body), "p": base_version})


async def _old_db(conn) -> dict:
    """Save a version with the old words on top of every type; strategy_type -> (version, body) of those."""
    saved = {}
    for strategy_type, (version, body) in _newest((await conn.execute(_ALL)).all()).items():
        old = _relabel(body, OLD)
        await _save(conn, strategy_type, version, old)
        saved[strategy_type] = (version + 1, old)
    return saved


async def _run(conn, sqls) -> None:
    for sql in sqls:
        await conn.execute(text(sql))


async def test_head_every_current_version_reads_the_new_words_and_downgrade_removes_only_them(admin_engine):
    own_down, own_up = own_step_sql(MIGRATION)
    assert "'post'" in own_up[-1] and "'post'" in own_down[-1]
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            assert (await conn.execute(_MINE, {"r": REASON})).all() == []  # fresh DB: the seed is already new
            old = await _old_db(conn)
            assert len(old) == PLAYBOOKS
            current = _newest((await conn.execute(_ALL)).all())
            assert any(b["triggers"]["T-09"]["label"] == OLD["T-09"] for _v, b in current.values())
            before = (await conn.execute(_ALL)).all()
            users = (await conn.execute(_USER)).one()
            await _run(conn, own_up)
            after = (await conn.execute(_ALL)).all()
            assert len(after) == len(before) + len(old)
            assert [r for r in after if r.reason != REASON] == before  # history untouched, nothing overwritten
            for strategy_type, (version, body) in _newest(after).items():
                assert version == old[strategy_type][0] + 1
                assert body == _relabel(old[strategy_type][1], NEW)  # only the four labels differ
            assert (await conn.execute(_USER)).one() == users  # user copies and saved plans unchanged
            await _run(conn, own_down)
            assert (await conn.execute(_MINE, {"r": REASON})).all() == []
            assert (await conn.execute(_ALL)).all() == before
        finally:
            await trans.rollback()


async def test_a_body_without_the_triggers_or_with_the_new_words_gets_no_version(admin_engine):
    _d, own_up = own_step_sql(MIGRATION)
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            total = len((await conn.execute(_ALL)).all())
            await _run(conn, own_up)  # fresh DB: every current body already has the new words
            assert len((await conn.execute(_ALL)).all()) == total
            ic_version, ic_body = _newest((await conn.execute(_ALL)).all())["ic"]
            bare = copy.deepcopy(ic_body)
            for trigger in OLD:
                bare["triggers"].pop(trigger, None)
            await _save(conn, "ic", ic_version, bare)
            await _run(conn, own_up)
            rows = (await conn.execute(_ALL)).all()
            assert len(rows) == total + 1 and _newest(rows)["ic"][0] == ic_version + 1  # no empty version appended
        finally:
            await trans.rollback()


async def test_upgrade_twice_is_a_no_op(admin_engine):
    _d, own_up = own_step_sql(MIGRATION)
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            old = await _old_db(conn)
            total = len((await conn.execute(_ALL)).all())
            await _run(conn, own_up)
            await _run(conn, own_up)
            assert len((await conn.execute(_ALL)).all()) == total + len(old)  # one version per type, never two
        finally:
            await trans.rollback()


async def test_admin_version_is_the_base_and_keeps_its_other_keys(admin_engine):
    _own_down, own_up = own_step_sql(MIGRATION)
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            old = await _old_db(conn)
            version, body = old["ic"]
            admin = copy.deepcopy(body)
            admin["admin_marker"] = "kept"
            admin["triggers"]["T-09"]["on"] = False
            await _save(conn, "ic", version, admin)
            await _run(conn, own_up)
            mine = {r.strategy_type: r for r in (await conn.execute(_MINE, {"r": REASON})).all()}
            assert mine["ic"].version == version + 2  # built on the latest, never on a number
            new = _body(mine["ic"].body)
            assert new == _relabel(admin, NEW)
            assert new["admin_marker"] == "kept" and new["triggers"]["T-09"]["on"] is False
        finally:
            await trans.rollback()


async def test_downgrade_refuses_when_a_newer_version_was_saved_on_top(admin_engine):
    own_down, own_up = own_step_sql(MIGRATION)
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await _old_db(conn)
            await _run(conn, own_up)
            mine = (await conn.execute(_MINE, {"r": REASON})).all()
            await _save(conn, "ic", next(r.version for r in mine if r.strategy_type == "ic"),
                        _body(next(r.body for r in mine if r.strategy_type == "ic")))
            await conn.execute(text("SAVEPOINT s"))
            with pytest.raises(DBAPIError, match="OF051"):
                await _run(conn, own_down)
            await conn.execute(text("ROLLBACK TO SAVEPOINT s"))
            assert len((await conn.execute(_MINE, {"r": REASON})).all()) == len(mine)
        finally:
            await trans.rollback()
