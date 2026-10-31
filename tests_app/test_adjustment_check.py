"""GC-ADJ2 step 1C: GET /api/strategies/{id}/adjustment-check in scenario mode on a fresh migrated database (REQ-158
AC-5, REQ-159 AC-2, REQ-160 AC-3, REQ-045 AC-1, F-71). The scenario's contracts go into the catalogue through the
catalogue store's own writer (``apply_update``) and the strategy through ``scripts/seed_scenario.py``'s ``seed`` (the
app's own stores); nothing is written with raw SQL. Tests run in file order: the plan-precedence test is last because
the plan it accepts stays on the ADJ-02 strategy.
"""
from __future__ import annotations

import copy
import datetime
import importlib.util
import json
import pathlib

import pytest
from httpx import ASGITransport, AsyncClient
from ofo.adjustment.playbook_eval import validate_body
from ofo.adjustment.playbook_types import TYPE_KEYS
from ofo.timeutil import IST
from ofo_app import adjustment_readers, catalogue_store, playbook_store, scenario_mode
from ofo_app import db as app_db
from ofo_app.config import get_settings
from sqlalchemy import text

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("seed_scenario", ROOT / "scripts" / "seed_scenario.py")
seed_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed_mod)
OK, NOT_FOUND = 200, 404
#: one list date before every scenario's expiry, so a forced reload retires nothing (ADR-057)
CATALOGUE_AS_OF = datetime.datetime(2026, 10, 31, 9, 0, tzinfo=IST)


def _reset_engine() -> None:
    app_db.get_sessionmaker.cache_clear()
    app_db.get_engine.cache_clear()
    get_settings.cache_clear()


@pytest.fixture
async def app_db_url(app_engine, monkeypatch):
    """The app's own engine pointed at the fresh test database (one engine per test: pytest-asyncio's loop per test)."""
    monkeypatch.setenv("DATABASE_URL", app_engine.url.render_as_string(hide_password=False))
    monkeypatch.setenv("APP_ENV", "test")
    _reset_engine()
    yield app_engine
    await app_db.close_db()
    _reset_engine()


async def _seeded(app_engine, monkeypatch, sid: str) -> int:
    """The scenario's contracts into the catalogue (the store's writer), then its strategy (seed_scenario.seed)."""
    monkeypatch.setenv("OFO_SCENARIO", sid)
    scn = scenario_mode.load(sid)
    async with app_engine.begin() as conn:
        await catalogue_store.apply_update(conn, scn.provider.instrument_master(),
                                           as_of=CATALOGUE_AS_OF,
                                           force=True, reason=f"test: scenario {sid} contracts", actor="test")
        # forced: each scenario is its own instrument list, so the previous one's contracts leave (ADR-058 guard)
    return await seed_mod.seed(sid)


async def _check(sid: str, strategy_id: int) -> tuple[int, dict]:
    from ofo_app.main import create_app  # noqa: PLC0415 - the env above must be set first
    _reset_engine()
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get(f"/api/strategies/{strategy_id}/adjustment-check")
    await app_db.close_db()
    return r.status_code, r.json()


def _by_kind(body: dict, kind: str) -> list[tuple]:
    return sorted((x["trigger_id"], x["value"], x["threshold"], x["cmp"]) for x in body["results"] if x["kind"] == kind)


async def test_adj02_flags_exactly_t01_t03_t09_with_the_system_wording(app_db_url, monkeypatch):
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-02")
    status, body = await _check("ADJ-02", sid)
    assert status == OK, body
    assert (body["strategy_type"], body["type_name"], body["stage"]) == ("ic", "Iron condor",
                                                                       {"name": "Middle", "index": 1})
    assert body["playbook"]["source"] == "system" and body["playbook"]["status"] == "approved"
    flags = [x for x in body["results"] if x["kind"] == "flag"]
    # GC-ADJ2 step 5 item 1: rounded half-up to 4 places, as the fixture writes them (ADJ-02.json triggers_fired)
    assert sorted((x["trigger_id"], x["value"], x["threshold"], x["cmp"]) for x in flags) == [
        ("T-01", "0.3416", "0.5000", "le"), ("T-03", "0.4103", "0.3500", "ge"), ("T-09", "2.7000", "3.0000", "le")]
    by_trigger = {x["trigger_id"]: x for x in flags}
    assert by_trigger["T-01"]["condition"] == "Spot within this % of a short strike: 0.3416 % (rule 0.5000 %)"
    assert by_trigger["T-03"]["condition"] == "Tested short's delta reaches: 0.4103 delta (rule 0.3500 delta)"
    assert not any("T-0" in x["condition"] for x in flags)
    assert {x["wording"] for x in flags} == {"Adjustment opportunity detected"}
    assert all(x["reason"] for x in body["results"] if x["kind"] == "not_checked")


async def test_adj01_no_flag(app_db_url, monkeypatch):
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-01")
    status, body = await _check("ADJ-01", sid)
    assert status == OK and body["strategy_type"] == "ic" and _by_kind(body, "flag") == []


async def test_user_active_playbook_is_read_when_the_strategy_has_no_plan(app_db_url, monkeypatch):
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-01")
    async with app_db_url.begin() as conn:
        system = await playbook_store.active_for(conn, "owner", "ic")
        own = await playbook_store.duplicate(conn, "owner", system.id, "Mine")
        await playbook_store.make_active(conn, "owner", own.id)
    status, out = await _check("ADJ-01", sid)
    assert status == OK and (out["playbook"]["source"], out["playbook"]["id"]) == ("active", own.id)


async def test_adj42_f71_already_true_at_entry_then_flags_after_a_clear_check(app_db_url, monkeypatch):
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-42")
    status, body = await _check("ADJ-42", sid)
    assert status == OK
    assert [x[0] for x in _by_kind(body, "already_true")] == ["T-01"] and _by_kind(body, "flag") == []
    assert [x[3] for x in _by_kind(body, "already_true")] == ["le"]  # GC-ADJ2 step 5: cmp filled on already_true
    assert {x["wording"]["what_happened"] for x in body["results"] if x["kind"] == "already_true"} == {
        "Already true when tracking started."}
    async with app_db_url.begin() as conn:  # a later check found T-01 false (the memory the store writes, F-71)
        assert (await playbook_store.rule_state(conn, "owner", sid))["T-01"] == (True, False)
        await playbook_store.put_rule_state(conn, "owner", sid, "T-01", held_at_entry=True, seen_clear=True)
    status, body = await _check("ADJ-42", sid)
    assert status == OK and [x[0] for x in _by_kind(body, "flag")] == ["T-01"]
    assert _by_kind(body, "already_true") == []


async def test_adj24b_no_spot_every_rule_not_checked_with_its_reason_never_a_flag(app_db_url, monkeypatch):
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-24b")
    status, body = await _check("ADJ-24b", sid)
    assert status == OK and body["strategy_type"] == "ic"
    assert body["results"] and {x["kind"] for x in body["results"]} == {"not_checked"}
    assert all(x["reason"] for x in body["results"]) and body["withheld"]


async def test_another_users_strategy_is_not_found(app_db_url, monkeypatch):
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-01")
    monkeypatch.setattr(adjustment_readers, "current_user_ref", lambda: "someone-else")
    status, _ = await _check("ADJ-01", sid)
    assert status == NOT_FOUND
    status, _ = await _check("ADJ-01", 987654321)
    assert status == NOT_FOUND


async def test_seed_twelve_system_rows_ic_approved_t19_one_rest_draft_every_body_valid(app_db_url):
    async with app_db_url.connect() as conn:
        rows = (await conn.execute(text("SELECT strategy_type, status, body::text FROM public.adjustment_playbooks "
                                        "WHERE is_system"))).all()
    assert sorted(r[0] for r in rows) == sorted(TYPE_KEYS)
    for stype, status, raw in rows:
        body = json.loads(raw)
        validate_body(body)
        assert status == ("approved" if stype == "ic" else "draft")
        if stype == "ic":
            assert body["triggers"]["T-19"]["weekly"] == body["triggers"]["T-19"]["monthly"] == ["1", "1", "1"]


async def test_zz_plan_precedence_t01_middle_03_is_not_flagged_and_editing_the_playbook_changes_nothing(
        app_db_url, monkeypatch):
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-02")
    async with app_db_url.begin() as conn:
        system = await playbook_store.active_for(conn, "owner", "ic")
        body = copy.deepcopy(system.body)
        body["triggers"]["T-01"]["weekly"][1] = "0.3"  # Middle stage: 0.3416 > 0.3, so T-01 must not flag
        await playbook_store.accept_plan(conn, "owner", sid, system.id, body)
        own = await playbook_store.duplicate(conn, "owner", system.id, "Mine 2")
        await playbook_store.make_active(conn, "owner", own.id)  # a later active playbook never overrides the plan
    status, out = await _check("ADJ-02", sid)
    assert status == OK and out["playbook"]["source"] == "plan"
    assert [x[0] for x in _by_kind(out, "flag")] == ["T-03", "T-09"]
    assert {x["wording"] for x in out["results"] if x["kind"] == "flag"} == {"Your rule was triggered"}
