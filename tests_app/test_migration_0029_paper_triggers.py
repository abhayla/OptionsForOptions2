"""GC-TP step 7a (REQ-109 AC-8; ADR-207 (5)): migration 0029 adds public.paper_triggers and public.paper_alerts.

Spec basis (quoted): REQ-109 AC-8 "fires each trigger once (also across a restart)"; ADR-048 (the limited application
role: SELECT, column-limited INSERT and UPDATE, nothing else). The guard makes a fire or a cancel write-once in the
database itself, so no code path (a second monitor, a restart) can un-fire or re-fire a trigger.

Real PostgreSQL only; every test rolls back. The round trip runs as the owner (admin_engine).
"""

from __future__ import annotations

import re

import pytest
from _migration_replay import round_trip_sql
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_migration_0028_paper_orders import _contracts, _privileges, _scalar
from test_strategy_store import _user, _with_draft

MIGRATION = "0029_paper_triggers.py"
GUARD_REFUSAL = "OF029"
MARKER = "-- 22. paper triggers"
TRIGGER_INSERT = {"strategy_id", "kind", "contract_id", "underlying", "direction", "level"}
TRIGGER_ALL = TRIGGER_INSERT | {"id", "created_at", "fired_at", "cancelled_at"}
ALERT_INSERT = {"strategy_id", "trigger_id", "title", "body"}
ALERT_ALL = ALERT_INSERT | {"id", "created_at", "read_at"}


async def _state(conn) -> dict:
    allowlist = ("SELECT prosrc FROM pg_proc WHERE oid = to_regprocedure("
                 "'public.ofo_assert_app_role_allowlist(text,text)')")
    return {
        "tables": await _scalar(conn, "SELECT count(*) FROM pg_class WHERE oid IN "
                                      "(to_regclass('public.paper_triggers'), to_regclass('public.paper_alerts'))"),
        "guards": await _scalar(conn, "SELECT count(*) FROM pg_trigger WHERE tgname IN "
                                      "('paper_triggers_guard', 'paper_alerts_guard') AND NOT tgisinternal"),
        "block": MARKER in await _scalar(conn, allowlist),
        "allowlist_md5": await _scalar(conn, allowlist.replace("prosrc", "md5(prosrc)")),
        "triggers": await _privileges(conn, "paper_triggers"),
        "alerts": await _privileges(conn, "paper_alerts"),
    }


def _expected(inserts: set[str], updates: set[str], every: set[str]) -> tuple[list[str], list[tuple[str, str]]]:
    return (["SELECT"], sorted([("INSERT", c) for c in inserts] + [("UPDATE", c) for c in updates]
                               + [("SELECT", c) for c in every]))


async def test_upgrade_creates_tables_guards_grants_downgrade_restores(admin_engine):
    _own_down, own_up, down, up = round_trip_sql(MIGRATION)
    assert "'post'" in own_up[-1] and "'pre'" in own_up[0]
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            head = await _state(conn)
            assert (head["tables"], head["guards"], head["block"]) == (2, 2, True)
            assert head["triggers"] == _expected(TRIGGER_INSERT, {"fired_at", "cancelled_at"}, TRIGGER_ALL)
            assert head["alerts"] == _expected(ALERT_INSERT, {"read_at"}, ALERT_ALL)
            for sql in down:
                await conn.execute(text(sql))
            before = await _state(conn)
            assert (before["tables"], before["guards"], before["block"]) == (0, 0, False)
            assert before["allowlist_md5"] != head["allowlist_md5"]
            for sql in up:
                await conn.execute(text(sql))
            assert await _state(conn) == head
        finally:
            await trans.rollback()


async def _trigger(conn, kind: str = "conditional_exit") -> tuple[int, int]:
    _, stored = await _with_draft(conn, _user())
    contract = (await _contracts(conn))[0] if kind == "leg_stop" else None
    tid = await _scalar(conn, "INSERT INTO public.paper_triggers (strategy_id, kind, contract_id, underlying, "
                              "direction, level) VALUES (:s, :k, :c, :u, 'below', 22850.00) RETURNING id",
                        {"s": stored.id, "k": kind, "c": contract, "u": None if contract else "NIFTY"})
    return stored.id, tid


async def _refused(conn, sql: str, params: dict, match: str = GUARD_REFUSAL) -> None:
    """Refused by the guard (its SQLSTATE) or, with another ``match``, by a constraint whose message matches."""
    with pytest.raises(DBAPIError) as err:
        async with conn.begin_nested():
            await conn.execute(text(sql), params)
    if match == GUARD_REFUSAL:
        assert getattr(err.value.orig, "sqlstate", None) == GUARD_REFUSAL, err.value
    else:
        assert re.search(match, str(err.value)), err.value


@pytest.mark.parametrize("kind", ["conditional_exit", "leg_stop"])
async def test_a_trigger_fires_once_and_never_un_fires(admin_engine, kind):
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            _, tid = await _trigger(conn, kind)
            fire = ("UPDATE public.paper_triggers SET fired_at = clock_timestamp() WHERE id = :i AND fired_at IS NULL "
                    "AND cancelled_at IS NULL RETURNING id")
            assert (await conn.execute(text(fire), {"i": tid})).all() == [(tid,)]
            assert (await conn.execute(text(fire), {"i": tid})).all() == []  # the second fire finds no row
            await _refused(conn, "UPDATE public.paper_triggers SET fired_at = NULL WHERE id = :i", {"i": tid})
            await _refused(conn, "UPDATE public.paper_triggers SET fired_at = clock_timestamp() WHERE id = :i",
                           {"i": tid})
            await _refused(conn, "UPDATE public.paper_triggers SET cancelled_at = clock_timestamp() WHERE id = :i",
                           {"i": tid}, "check")  # never both fired and cancelled
        finally:
            await trans.rollback()


@pytest.mark.parametrize("sql", ["UPDATE public.paper_triggers SET level = 1 WHERE id = :i",
                                 "UPDATE public.paper_triggers SET direction = 'above' WHERE id = :i",
                                 "DELETE FROM public.paper_triggers WHERE id = :i"],
                         ids=["level", "direction", "delete"])
async def test_the_guard_refuses_any_other_change_even_for_the_owner(admin_engine, sql):
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            _, tid = await _trigger(conn)
            await _refused(conn, sql, {"i": tid})
        finally:
            await trans.rollback()


async def test_a_trigger_starts_armed_and_kind_matches_its_target(admin_engine):
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            sid, _ = await _trigger(conn)
            await _refused(conn, "INSERT INTO public.paper_triggers (strategy_id, kind, underlying, direction, level, "
                                 "fired_at) VALUES (:s, 'conditional_exit', 'NIFTY', 'below', 1, now())", {"s": sid})
            await _refused(conn, "INSERT INTO public.paper_triggers (strategy_id, kind, direction, level) "
                                 "VALUES (:s, 'leg_stop', 'below', 1)", {"s": sid}, "check")
            await _refused(conn, "INSERT INTO public.paper_triggers (strategy_id, kind, underlying, direction, level) "
                                 "VALUES (:s, 'conditional_exit', 'NIFTY', 'below', 0)", {"s": sid}, "check")
        finally:
            await trans.rollback()


async def test_an_alert_is_marked_read_once_and_never_deleted(admin_engine):
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            sid, tid = await _trigger(conn)
            aid = await _scalar(conn, "INSERT INTO public.paper_alerts (strategy_id, trigger_id, title, body) "
                                      "VALUES (:s, :t, 'a', 'b') RETURNING id", {"s": sid, "t": tid})
            await conn.execute(text("UPDATE public.paper_alerts SET read_at = now() WHERE id = :i"), {"i": aid})
            await _refused(conn, "UPDATE public.paper_alerts SET read_at = NULL WHERE id = :i", {"i": aid})
            await _refused(conn, "UPDATE public.paper_alerts SET body = 'x' WHERE id = :i", {"i": aid})
            await _refused(conn, "DELETE FROM public.paper_alerts WHERE id = :i", {"i": aid})
            await _refused(conn, "INSERT INTO public.paper_alerts (strategy_id, trigger_id, title, body) "
                                 "VALUES (:s, :t, 'a', 'b')", {"s": sid, "t": tid}, "unique|duplicate")
        finally:
            await trans.rollback()
