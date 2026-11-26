"""Migration 0054 (ADR-330 (3)(4), ADR-048): kind, answer, answered_at, no_longer_true_since on adjustment_suggestions.

The four columns exist; their CHECKs refuse a bad value; the guard (0036's, extended) still refuses every old protection
(delete, a changed first-shown time, a shortened timeline) and the new ones (a record of a kind closing without an
answer, a rewritten answer, a value changed after the close, a note that is not History only); the downgrade is refused
while a row carries a kind and round-trips without one. Every test rolls back.
"""
from __future__ import annotations

import pytest
from _migration_replay import recorded, round_trip_sql
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_strategy_store import _user, _with_draft

MIGRATION = "0054_actionable_alert_answers.py"
_COLUMNS = ("kind", "answer", "answered_at", "no_longer_true_since")
_OPEN = text("INSERT INTO public.adjustment_suggestions (strategy_id, rule_id, trigger_id, stage, value, threshold, "
             "kind, timeline) VALUES (:i, :rule, 't', 's1', 15.5750, 15.4000, :kind, "
             "jsonb_build_array(jsonb_build_object('at', clock_timestamp(), 'outcome', 'open'))) RETURNING id")
_NOTE = text("INSERT INTO public.adjustment_suggestions (strategy_id, rule_id, kind, outcome, answer, answered_at, "
             "timeline) VALUES (:i, :rule, :kind, :outcome, :answer, now(), '[]'::jsonb) RETURNING id")
_CLOSE = text("UPDATE public.adjustment_suggestions SET outcome = :outcome, answer = :answer, "
              "answered_at = CASE WHEN CAST(:answer AS TEXT) IS NULL THEN NULL ELSE now() END, "
              "timeline = timeline || jsonb_build_array(jsonb_build_object('outcome', CAST(:outcome AS TEXT), "
              "'suggestion_id', id)) WHERE id = :id")
_SET = "UPDATE public.adjustment_suggestions SET {} WHERE id = :id"


@pytest.fixture
async def db(app_engine):
    async with app_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


async def _open(conn, kind: str | None = "plan_loss_stop", rule: str = "r1") -> tuple[int, int]:
    _, stored = await _with_draft(conn, _user())
    return stored.id, (await conn.execute(_OPEN, {"i": stored.id, "rule": rule, "kind": kind})).scalar_one()


async def _refused(conn, sql, params) -> None:
    with pytest.raises(DBAPIError):
        async with conn.begin_nested():
            await conn.execute(text(sql) if isinstance(sql, str) else sql, params)


async def test_the_four_columns_exist_and_a_row_without_a_kind_keeps_null(db):
    found = {r[0] for r in (await db.execute(text(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'adjustment_suggestions'"))).all()}
    assert set(_COLUMNS) <= found
    _, rid = await _open(db, kind=None)
    row = (await db.execute(text("SELECT kind, answer, answered_at, no_longer_true_since "
                                 "FROM public.adjustment_suggestions WHERE id = :id"), {"id": rid})).one()
    assert tuple(row) == (None, None, None, None)


async def test_checks_refuse_a_bad_kind_a_bad_answer_and_an_unpaired_answer(db):
    sid, rid = await _open(db)
    with pytest.raises(DBAPIError, match="check"):
        async with db.begin_nested():
            await db.execute(_OPEN, {"i": sid, "rule": "r2", "kind": "nonsense"})
    await _refused(db, _SET.format("answer = 'maybe', answered_at = now()"), {"id": rid})
    await _refused(db, _SET.format("answer = 'exit'"), {"id": rid})


async def test_the_old_protections_still_hold(db):
    _, rid = await _open(db)
    await _refused(db, "DELETE FROM public.adjustment_suggestions WHERE id = :id", {"id": rid})
    await _refused(db, _SET.format("shown_at = shown_at + interval '1 minute'"), {"id": rid})
    await _refused(db, _SET.format("timeline = '[]'::jsonb"), {"id": rid})
    await _refused(db, _SET.format("kind = 'settled'"), {"id": rid})


async def test_a_record_of_a_kind_leaves_open_only_with_its_answer(db):
    _, rid = await _open(db)
    await _refused(db, _CLOSE, {"id": rid, "outcome": "dismissed", "answer": None})
    await _refused(db, _CLOSE, {"id": rid, "outcome": "lapsed", "answer": "continue"})
    await _refused(db, _CLOSE, {"id": rid, "outcome": "dismissed", "answer": "closed_by_system"})
    await db.execute(_CLOSE, {"id": rid, "outcome": "lapsed", "answer": "closed_by_system"})
    await _refused(db, _SET.format("answer = 'exit'"), {"id": rid})


async def test_a_record_without_a_kind_still_closes_as_before(db):
    _, rid = await _open(db, kind=None)
    await db.execute(_CLOSE, {"id": rid, "outcome": "lapsed", "answer": None})


async def test_value_and_no_longer_true_since_change_only_while_open(db):
    _, rid = await _open(db)
    await db.execute(text(_SET.format("value = 16.0000, no_longer_true_since = now()")), {"id": rid})
    await db.execute(text(_SET.format("no_longer_true_since = NULL")), {"id": rid})
    await db.execute(_CLOSE, {"id": rid, "outcome": "acted_on", "answer": "exit"})
    await _refused(db, _SET.format("value = 17"), {"id": rid})
    await _refused(db, _SET.format("no_longer_true_since = now()"), {"id": rid})


async def test_a_note_is_history_only_and_nothing_else_is_stored_closed(db):
    sid, _ = await _open(db)
    ok = {"i": sid, "rule": "info:settled:1", "kind": "settled", "outcome": "dismissed", "answer": "noted"}
    await db.execute(_NOTE, ok)
    for change in ({"outcome": "open"}, {"answer": "exit"}, {"outcome": "lapsed"}, {"kind": None}):
        await _refused(db, _NOTE, {**ok, "rule": "info:x", **change})
    open_count = (await db.execute(text("SELECT count(*) FROM public.adjustment_suggestions "
                                        "WHERE strategy_id = :i AND outcome = 'open'"), {"i": sid})).scalar_one()
    assert open_count == 1


async def test_a_suggestion_may_carry_its_event_time_but_never_one_in_the_future(db):
    sid, _ = await _open(db)
    insert = ("INSERT INTO public.adjustment_suggestions (strategy_id, rule_id, kind, shown_at, timeline) "
              "VALUES (:i, :rule, 'plan_loss_stop', now() + :shift * interval '1 hour', '[]'::jsonb)")
    await db.execute(text(insert), {"i": sid, "rule": "r_past", "shift": -24})
    await _refused(db, insert, {"i": sid, "rule": "r_future", "shift": 1})


async def test_downgrade_is_refused_with_a_kind_and_round_trips_without_one(admin_engine):
    own_down = recorded(MIGRATION, "downgrade")
    _, own_up, down, up = round_trip_sql(MIGRATION)
    assert "'pre'" in own_up[0] and "'post'" in own_up[-1] and "'post'" in own_down[-1]
    cols = ("SELECT count(*) FROM information_schema.columns WHERE table_name = 'adjustment_suggestions' "
            "AND column_name = ANY(:c)")
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await _open(conn)
            with pytest.raises(DBAPIError, match=r"refusing to downgrade 0054_actionable_alert_answers: 1 "):
                async with conn.begin_nested():
                    for sql in own_down:
                        await conn.execute(text(sql))
        finally:
            await trans.rollback()
        trans = await conn.begin()
        try:
            for sql in down:
                await conn.execute(text(sql))
            assert (await conn.execute(text(cols), {"c": list(_COLUMNS)})).scalar() == 0
            for sql in up:
                await conn.execute(text(sql))
            assert (await conn.execute(text(cols), {"c": list(_COLUMNS)})).scalar() == len(_COLUMNS)
        finally:
            await trans.rollback()
