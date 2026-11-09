"""Migration 0048 (GC-ICTRACK 21m, ADR-277 (5), ADR-280 (12)): a new iron condor system playbook version in which
T-11c and T-20b are not greyed and T-20b compares ADX >= 25 (copy of 0044's tests).

- head: exactly one 0048 row; downgrade removes only it; both directions end with the allow-list post check;
- an admin-saved version is the base: its other keys and T-20b's ``on`` survive;
- upgrading twice never writes a second version;
- a newer version saved on top refuses the downgrade (OF048).
A fresh database is seeded (0031) from the regenerated seed file, which is already built, so 0048 writes nothing
there; a database seeded before task 21 (ofo_dev) holds a greyed version. ``_old_db`` saves such a greyed version on
top first, so each test sees the case 0048 exists for. Every test rolls back.
"""
from __future__ import annotations

import json

import pytest
from _migration_replay import round_trip_sql
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

MIGRATION = "0048_ic_t11c_t20b_built.py"
REASON = "GC-ICTRACK: T-11c and T-20b built (India VIX percentile, ADX 25), no longer greyed"
LIMITS = ["25", "25", "25"]
_MINE = text("SELECT version, body FROM public.system_playbook_versions WHERE strategy_type = 'ic' AND reason = :r")
_COUNT = text("SELECT count(*) FROM public.system_playbook_versions WHERE strategy_type = 'ic'")
_NEWEST = text("SELECT version, body, reason FROM public.system_playbook_versions WHERE strategy_type = 'ic' "
               "ORDER BY version DESC LIMIT 1")
_INSERT = text("INSERT INTO public.system_playbook_versions (strategy_type, version, status, body, reason, saved_by) "
               "SELECT 'ic', :v, status, CAST(:b AS jsonb), 'admin edit', 'admin' "
               "FROM public.system_playbook_versions WHERE strategy_type = 'ic' AND version = :p")


def _body(value) -> dict:
    return value if isinstance(value, dict) else json.loads(value)


def _built(body: dict) -> None:
    t11c, t20b = body["triggers"]["T-11c"], body["triggers"]["T-20b"]
    assert "greyed" not in t11c and "greyed" not in t20b
    assert (t20b["cmp"], t20b["unit"], t20b["weekly"], t20b["monthly"]) == ("ge", "ADX", LIMITS, LIMITS)


async def _old_db(conn) -> int:
    """Save a pre-task-21 iron condor version (T-11c / T-20b greyed, T-20b with no limit) on top; its version."""
    base = (await conn.execute(_NEWEST)).one()
    body = dict(_body(base.body))
    triggers = dict(body["triggers"])
    triggers["T-11c"] = dict(triggers["T-11c"], greyed="Needs price history (not in V1)")
    triggers["T-20b"] = dict(triggers["T-20b"], greyed="Needs price history (not in V1)", cmp="", unit="",
                             weekly=None, monthly=None)
    body["triggers"] = triggers
    await conn.execute(_INSERT, {"v": base.version + 1, "b": json.dumps(body), "p": base.version})
    return base.version + 1


async def _run(conn, sqls) -> None:
    for sql in sqls:
        await conn.execute(text(sql))


async def test_head_has_one_built_version_and_downgrade_removes_only_it(admin_engine):
    own_down, own_up, _down, _up = round_trip_sql(MIGRATION)
    assert "'post'" in own_up[-1] and "'post'" in own_down[-1]
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            assert (await conn.execute(_MINE, {"r": REASON})).all() == []  # fresh DB: the seed is already built
            _built(_body((await conn.execute(_NEWEST)).one().body))
            old = await _old_db(conn)
            total = (await conn.execute(_COUNT)).scalar_one()
            await _run(conn, own_up)
            mine = (await conn.execute(_MINE, {"r": REASON})).one()
            assert mine.version == old + 1 and (await conn.execute(_COUNT)).scalar_one() == total + 1
            _built(_body(mine.body))
            await _run(conn, own_down)
            assert (await conn.execute(_MINE, {"r": REASON})).all() == []
            assert (await conn.execute(_COUNT)).scalar_one() == total  # only its own row went
            assert "greyed" in _body((await conn.execute(_NEWEST)).one().body)["triggers"]["T-11c"]
        finally:
            await trans.rollback()


async def test_upgrade_twice_is_a_no_op(admin_engine):
    _d, own_up, _down, _up = round_trip_sql(MIGRATION)
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await _old_db(conn)
            total = (await conn.execute(_COUNT)).scalar_one()
            await _run(conn, own_up)
            await _run(conn, own_up)
            assert (await conn.execute(_COUNT)).scalar_one() == total + 1  # one version, never two
        finally:
            await trans.rollback()


async def test_admin_version_is_the_base_and_keeps_its_other_keys(admin_engine):
    _own_down, own_up, _down, _up = round_trip_sql(MIGRATION)
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await _old_db(conn)
            base = (await conn.execute(_NEWEST)).one()
            body = dict(_body(base.body))
            body["admin_marker"] = "kept"
            body["triggers"] = dict(body["triggers"], **{"T-20b": dict(body["triggers"]["T-20b"], on=True)})
            await conn.execute(_INSERT, {"v": base.version + 1, "b": json.dumps(body), "p": base.version})
            await _run(conn, own_up)
            mine = (await conn.execute(_MINE, {"r": REASON})).one()
            assert mine.version == base.version + 2  # built on the latest, never on a number
            new = _body(mine.body)
            _built(new)
            assert new["admin_marker"] == "kept" and new["triggers"]["T-20b"]["on"] is True
            assert set(new["triggers"]) == set(body["triggers"])  # no trigger lost or added
        finally:
            await trans.rollback()


async def test_downgrade_refuses_when_a_newer_version_was_saved_on_top(admin_engine):
    own_down, _u, _down, _up = round_trip_sql(MIGRATION)
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await _old_db(conn)
            await _run(conn, _u)
            mine = (await conn.execute(_MINE, {"r": REASON})).one()
            await conn.execute(_INSERT, {"v": mine.version + 1, "b": json.dumps(_body(mine.body)), "p": mine.version})
            await conn.execute(text("SAVEPOINT s"))
            with pytest.raises(DBAPIError, match="OF048"):
                await _run(conn, own_down)
            await conn.execute(text("ROLLBACK TO SAVEPOINT s"))
            assert len((await conn.execute(_MINE, {"r": REASON})).all()) == 1
        finally:
            await trans.rollback()
