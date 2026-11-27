"""#753 round 3: ``accepted_at`` stamps exactly per the owner's rule, through every ROUTE the plan page uses.

Spec basis: ADR-330 (45) (owner 27 Nov: "only the first save, accepting a playbook (also the same one again) and Reset
to playbook stamp a new acceptance; a plan-sheet edit never stamps"); owner question LJ-2 option 1 (an edit on the sheet
never stamps, also when it points an old plan with no playbook at the active one); ADR-250 (a plan saved before ADR-247
keeps its own stops: nothing under a live position changes without the user choosing it); ADR-252 addendum (switching
the playbook is a new acceptance); ADR-330 (32) (Reset to playbook).

Real case: strategy 82's shape (iron condor accepted before the ADR-247 version, margin stop "4" and T-16 on). The page
switches an EXISTING plan's playbook with PUT (PlanEntry.vue edit), so the request the sheet sends
for a selector pick carries ``accept: true``; a level edit never does. Same harness as test_adjustment_plan.py: scenario
ADJ-02, committed rows, the plan row backdated by the table owner with the guard off.
"""

from __future__ import annotations

import datetime
import functools
import json
import os
import pathlib
from http import HTTPStatus

import pytest
from ofo_app import adjustment_check as check
from ofo_app import db as app_db
from ofo_app import playbook_store as pbs
from ofo_app import settings_in_force as sif
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from test_adjustment_plan import (
    OK,
    USER,
    _call,
    _plan_path,
    _plan_row,
    _reset_engine,
    _seeded,
    _system_ic,
)

DAY = datetime.timedelta(days=1)


@pytest.fixture
async def app_db_url(app_engine, monkeypatch):
    """The route harness of test_adjustment_plan.py: the app's DATABASE_URL is the test application engine."""
    monkeypatch.setenv("DATABASE_URL", app_engine.url.render_as_string(hide_password=False))
    monkeypatch.setenv("APP_ENV", "test")
    _reset_engine()
    yield app_engine
    await app_db.close_db()
    _reset_engine()


_AT = text("SELECT accepted_at, playbook_id FROM public.strategy_adjustment_plans WHERE strategy_id = :s")
MARGIN = "stop_line_pct_of_margin"


async def _state(app_engine, sid: int):
    async with app_engine.connect() as conn:
        row = (await conn.execute(_AT, {"s": sid})).one()
        resolved = await check.resolve(conn, USER, sid, "ic")
        return row.accepted_at, row.playbook_id, resolved.saved_before_adr247, sif.credit_line_applies(resolved)


async def _old_plan(app_engine, admin_engine, sid: int, *, margin: bool = False, null_playbook: bool = False):
    """The owner's database: a plan accepted a day before the ADR-247 cutoff (optionally with its pre-ADR-247 stops and
    a deleted playbook), written by the table owner with the guard off."""
    system = await _system_ic(app_engine)
    status, out = await _call("POST", _plan_path(sid), json={"playbook_id": system.id})
    assert status == OK, out
    async with app_engine.connect() as conn:
        cutoff = await pbs.adr247_saved_at(conn)
        body = (await _plan_row(app_engine, sid)).body
    then = cutoff - DAY
    body = json.loads(body)
    if margin:
        body["guards"][MARGIN] = "4"
        body["triggers"]["T-16"]["on"] = True
    async with admin_engine.begin() as conn:
        await conn.execute(text("ALTER TABLE public.strategy_adjustment_plans DISABLE TRIGGER USER"))
        await conn.execute(
            text(
                "UPDATE public.strategy_adjustment_plans SET accepted_at = :t, "
                "body = CAST(:b AS JSONB), playbook_id = CASE WHEN :n THEN NULL ELSE playbook_id END "
                "WHERE strategy_id = :s"
            ),
            {"t": then, "b": json.dumps(body), "n": null_playbook, "s": sid},
        )
        await conn.execute(text("ALTER TABLE public.strategy_adjustment_plans ENABLE TRIGGER USER"))
    at, _, before, credit = await _state(app_engine, sid)
    assert (at, before, credit) == (then, True, False)
    return system, then


async def test_core_the_first_save_stamps(app_db_url, admin_engine, monkeypatch):
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-02")
    async with admin_engine.begin() as conn:
        await conn.execute(text("DELETE FROM public.strategy_adjustment_plans WHERE strategy_id = :s"), {"s": sid})
    system = await _system_ic(app_db_url)
    status, out = await _call("POST", _plan_path(sid), json={"playbook_id": system.id})
    assert status == OK, out
    async with app_db_url.connect() as conn:
        cutoff = await pbs.adr247_saved_at(conn)
    at, playbook, before, credit = await _state(app_db_url, sid)
    assert at >= cutoff and playbook == system.id and before is False and credit is True


async def test_post_accept_of_the_same_playbook_and_of_another_one_each_stamp(app_db_url, admin_engine, monkeypatch):
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-02")
    system, then = await _old_plan(app_db_url, admin_engine, sid)
    status, out = await _call("POST", _plan_path(sid), json={"playbook_id": system.id})  # the same one again
    assert status == OK, out
    same_at, playbook, before, credit = await _state(app_db_url, sid)
    assert same_at > then and playbook == system.id and before is False and credit is True
    await _old_plan(app_db_url, admin_engine, sid)
    async with app_db_url.begin() as conn:
        own = await pbs.duplicate(conn, USER, system.id, "POST other")
    status, out = await _call("POST", _plan_path(sid), json={"playbook_id": own.id})  # another one
    assert status == OK, out
    other_at, playbook, before, credit = await _state(app_db_url, sid)
    assert other_at > then and playbook == own.id and before is False and credit is True


async def test_the_sheets_playbook_pick_on_an_existing_plan_is_a_put_with_accept_and_stamps(
    app_db_url, admin_engine, monkeypatch
):
    """The real request: PlanEntry opens the sheet with edit=true, so a pick of another playbook then Save is PUT with
    ``accept`` (strategy 82's shape: the switch kept accepted_at, credit line False, before this fix)."""
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-02")
    system, then = await _old_plan(app_db_url, admin_engine, sid, margin=True)
    async with app_db_url.begin() as conn:
        own = await pbs.duplicate(conn, USER, system.id, "Sheet pick")
    status, out = await _call("PUT", _plan_path(sid), json={"playbook_id": own.id, "accept": True})
    assert status == OK, out
    at, playbook, before, credit = await _state(app_db_url, sid)
    assert at > then and playbook == own.id and before is False and credit is True
    body = json.loads((await _plan_row(app_db_url, sid)).body)  # the chosen playbook's conditions
    assert MARGIN not in body["guards"] or body["guards"][MARGIN] != "4"


async def test_use_as_is_on_the_same_playbook_from_the_sheet_stamps(app_db_url, admin_engine, monkeypatch):
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-02")
    system, then = await _old_plan(app_db_url, admin_engine, sid)
    status, out = await _call("PUT", _plan_path(sid), json={"playbook_id": system.id, "accept": True})
    assert status == OK, out
    at, _, before, credit = await _state(app_db_url, sid)
    assert at > then and before is False and credit is True


async def test_a_put_naming_another_playbook_without_accept_is_refused_and_changes_nothing(
    app_db_url, admin_engine, monkeypatch
):
    """A switch is a choice and must say so: no half-switch (new body, old accepted_at)."""
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-02")
    system, then = await _old_plan(app_db_url, admin_engine, sid, margin=True)
    before = (await _plan_row(app_db_url, sid)).body
    async with app_db_url.begin() as conn:
        own = await pbs.duplicate(conn, USER, system.id, "Pointer only")
    status, out = await _call("PUT", _plan_path(sid), json={"playbook_id": own.id})
    assert status == HTTPStatus.UNPROCESSABLE_ENTITY, out
    at, playbook, before_247, credit = await _state(app_db_url, sid)
    assert (at, playbook, before_247, credit) == (then, system.id, True, False)
    assert (await _plan_row(app_db_url, sid)).body == before


async def test_a_put_level_edit_keeps_accepted_at_and_the_old_stops(app_db_url, admin_engine, monkeypatch):
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-02")
    system, then = await _old_plan(app_db_url, admin_engine, sid, margin=True)
    status, out = await _call("PUT", _plan_path(sid), json={"playbook_id": system.id, "target": "35", "stop": "40"})
    assert status == OK, out
    at, playbook, before, credit = await _state(app_db_url, sid)
    assert (at, playbook, before, credit) == (then, system.id, True, False)
    body = json.loads((await _plan_row(app_db_url, sid)).body)
    assert body["guards"][MARGIN] == "4" and body["triggers"]["T-16"]["on"] is True  # its own stops stay


async def test_a_put_on_a_null_playbook_plan_with_the_prefill_keeps_accepted_at_and_its_own_stops(
    app_db_url, admin_engine, monkeypatch
):
    """LJ-2 option 1 and R1/R2-MAJOR-2: the sheet's prefill points the plan at the active playbook; that is no choice.
    It does not stamp, the plan still reads as saved before ADR-247 (no credit line), and keeps its margin stop "4" and
    T-16 (before: the edit replaced the whole body with the playbook's)."""
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-02")
    system, then = await _old_plan(app_db_url, admin_engine, sid, margin=True, null_playbook=True)
    assert (await _plan_row(app_db_url, sid)).playbook_id is None
    status, out = await _call("PUT", _plan_path(sid), json={"playbook_id": system.id, "target": "35"})
    assert status == OK, out
    at, playbook, before, credit = await _state(app_db_url, sid)
    assert (at, playbook, before, credit) == (then, system.id, True, False)
    body = json.loads((await _plan_row(app_db_url, sid)).body)
    assert body["guards"][MARGIN] == "4" and body["triggers"]["T-16"]["on"] is True
    assert body["guards"]["profit_target_pct_of_max_profit"] == "35"  # the edit did save


async def test_a_null_playbook_plan_where_the_user_picks_a_playbook_stamps_and_takes_its_body(
    app_db_url, admin_engine, monkeypatch
):
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-02")
    system, then = await _old_plan(app_db_url, admin_engine, sid, margin=True, null_playbook=True)
    status, out = await _call("PUT", _plan_path(sid), json={"playbook_id": system.id, "accept": True})
    assert status == OK, out
    at, playbook, before, credit = await _state(app_db_url, sid)
    assert at > then and playbook == system.id and before is False and credit is True
    assert json.loads((await _plan_row(app_db_url, sid)).body)["guards"].get(MARGIN) != "4"


async def test_reset_to_playbook_stamps_and_the_strategy_82_shape_gains_the_credit_line(
    app_db_url, admin_engine, monkeypatch
):
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-02")
    system, then = await _old_plan(app_db_url, admin_engine, sid, margin=True)
    status, out = await _call("POST", _plan_path(sid) + "/reset")
    assert status == OK, out
    at, playbook, before, credit = await _state(app_db_url, sid)
    assert at > then and playbook == system.id and before is False and credit is True


async def test_the_levels_preview_reads_the_same_body_the_save_will_with_the_pick(
    app_db_url, admin_engine, monkeypatch
):
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-02")
    system, _ = await _old_plan(app_db_url, admin_engine, sid, margin=True, null_playbook=True)
    status, kept = await _call("GET", _plan_path(sid) + "/levels", params={"stop": "40", "playbook_id": system.id})
    assert status == OK, kept
    status, picked = await _call(
        "GET", _plan_path(sid) + "/levels", params={"stop": "40", "playbook_id": system.id, "accept": "true"}
    )
    assert status == OK, picked
    status, saved = await _call("PUT", _plan_path(sid), json={"playbook_id": system.id, "stop": "40"})
    assert status == OK and kept["stop"]["words"] == saved["plan"]["stop_words"], (kept, saved)


@pytest.mark.parametrize("method", ["POST", "PUT"], ids=["accepts_true", "accepts_false"])
async def test_a_lock_timeout_on_the_plan_row_answers_the_busy_refusal_not_a_25P02(
    app_db_url, admin_engine, monkeypatch, method
):
    """R2-MINOR-3: the error path keeps the ORIGINAL error (55P03 -> the busy answer) with accepts True and False."""
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-02")
    system, then = await _old_plan(app_db_url, admin_engine, sid)
    timed = create_async_engine(
        os.environ["TEST_DATABASE_URL"],
        poolclass=NullPool,
        connect_args={"server_settings": {"jit": "off", "lock_timeout": "300"}},
    )

    monkeypatch.setattr(app_db, "get_engine", functools.lru_cache(lambda: timed))  # keeps cache_clear / cache_info
    try:
        async with admin_engine.connect() as holder:
            trans = await holder.begin()
            await holder.execute(
                text("SELECT strategy_id FROM public.strategy_adjustment_plans WHERE strategy_id = :s FOR UPDATE"),
                {"s": sid},
            )
            try:
                status, out = await _call(method, _plan_path(sid), json={"playbook_id": system.id})
            finally:
                await trans.rollback()
    finally:
        await timed.dispose()
    assert status == HTTPStatus.CONFLICT and out["code"] == "STRATEGY_VALIDATION_522", (status, out)
    assert "ERR-" not in json.dumps(out)
    monkeypatch.undo()
    at, *_ = await _state(app_db_url, sid)
    assert at == then  # nothing written


def test_the_request_field_is_documented_in_the_openapi_file():
    spec = json.loads((pathlib.Path(__file__).resolve().parents[1] / "docs/api/openapi.json").read_text("utf-8"))
    assert "accept" in spec["components"]["schemas"]["PlanIn"]["properties"]
