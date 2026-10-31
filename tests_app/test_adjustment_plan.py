"""GC-ADJ2 step 4: GET / POST / PUT /api/strategies/{id}/adjustment-plan in scenario mode on a fresh migrated database
(REQ-161 AC-1..AC-4, REQ-158 AC-5). Same harness as test_adjustment_check.py: the scenario's contracts go in through the
catalogue store's writer and its strategy through ``seed_scenario.seed`` (the app's own stores); the plan is read back
with the store and with the check route. One scenario per strategy (the seed is idempotent per scenario), so the tests
that share ADJ-02 run in file order: the core proof first, the overrides next, the other user last.
"""
from __future__ import annotations

import copy
import datetime
import importlib.util
import json
import pathlib

import pytest
from httpx import ASGITransport, AsyncClient
from ofo.adjustment.playbook_types import SHOWN_NAMES
from ofo.timeutil import IST
from ofo_app import adjustment_check, adjustment_readers, catalogue_store, playbook_store, scenario_mode
from ofo_app import db as app_db
from ofo_app.config import get_settings
from sqlalchemy import text

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("seed_scenario", ROOT / "scripts" / "seed_scenario.py")
seed_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed_mod)
OK, NOT_FOUND, CONFLICT, UNPROCESSABLE = 200, 404, 409, 422
CATALOGUE_AS_OF = datetime.datetime(2026, 10, 31, 9, 0, tzinfo=IST)
GENERIC_TEXT = {"what_happened": "No playbook matches this strategy's shape, so only the generic triggers and "
                                 "approaches apply."}
USER = "owner"
IC_NAME = SHOWN_NAMES["ic"]
SYSTEM_MAX = 2  # the system iron condor playbook's max_adjustments guard
_PLAN_SQL = text("SELECT playbook_id, strategy_type, body::text FROM public.strategy_adjustment_plans "
                 "WHERE strategy_id = :id")
_PLAYBOOK_SQL = text("SELECT body::text, version FROM public.adjustment_playbooks WHERE id = :id")


def _reset_engine() -> None:
    app_db.get_sessionmaker.cache_clear()
    app_db.get_engine.cache_clear()
    get_settings.cache_clear()


@pytest.fixture
async def app_db_url(app_engine, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", app_engine.url.render_as_string(hide_password=False))
    monkeypatch.setenv("APP_ENV", "test")
    _reset_engine()
    yield app_engine
    await app_db.close_db()
    _reset_engine()


async def _seeded(app_engine, monkeypatch, sid: str) -> int:
    monkeypatch.setenv("OFO_SCENARIO", sid)
    scn = scenario_mode.load(sid)
    async with app_engine.begin() as conn:
        await catalogue_store.apply_update(conn, scn.provider.instrument_master(), as_of=CATALOGUE_AS_OF, force=True,
                                           reason=f"test: scenario {sid} contracts", actor="test")
    return await seed_mod.seed(sid)


async def _call(method: str, path: str, **kw) -> tuple[int, dict]:
    from ofo_app.main import create_app  # noqa: PLC0415 - the env above must be set first
    _reset_engine()
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.request(method, path, **kw)
    await app_db.close_db()
    return r.status_code, r.json()


def _plan_path(strategy_id: int) -> str:
    return f"/api/strategies/{strategy_id}/adjustment-plan"


async def _plan_row(engine, strategy_id: int):
    async with engine.connect() as conn:
        return (await conn.execute(_PLAN_SQL, {"id": strategy_id})).one_or_none()


async def _playbook_row(engine, playbook_id: int):
    async with engine.connect() as conn:
        return (await conn.execute(_PLAYBOOK_SQL, {"id": playbook_id})).one()


async def _system_ic(engine) -> playbook_store.Playbook:
    async with engine.connect() as conn:
        return await playbook_store.active_for(conn, USER, "ic")


# --- AC-1: the sheet's prefill ---------------------------------------------------------------------------------------


async def test_get_without_a_plan_prefills_from_the_active_system_playbook_and_pick_refills(app_db_url, monkeypatch):
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-01")
    system = await _system_ic(app_db_url)
    status, out = await _call("GET", _plan_path(sid))
    assert status == OK, out
    assert (out["type"], out["type_name"], out["generic"], out["generic_text"], out["plan"]) == (
        "ic", IC_NAME, False, None, None)
    assert out["prefill"] == {"playbook_id": system.id, "target": "50", "stop": "50", "max_adjustments": 2,
                              "time_exit": None}
    row = next(p for p in out["playbooks"] if p["id"] == system.id)
    assert (row["is_system"], row["active"], row["draft"]) == (True, True, False)
    assert out["labels"]["title"] == "When tracking starts: this strategy's plan"
    assert out["labels"]["use_as_is"] == "Use playbook as is" and out["labels"]["customise"] == "Customise triggers"
    body = copy.deepcopy(system.body)  # AC-2: another playbook refills every field from itself
    body["guards"] |= {"profit_target_pct_of_max_profit": "70", "stop_line_pct_of_max_loss": "30",
                       "max_adjustments": 4, "time_exit": "14:45"}
    async with app_db_url.begin() as conn:
        own = await playbook_store.create(conn, USER, "ic", "Plan pick", body)
    status, picked = await _call("GET", _plan_path(sid) + f"?playbook_id={own.id}")
    assert status == OK and picked["prefill"] == {"playbook_id": own.id, "target": "70", "stop": "30",
                                                  "max_adjustments": 4, "time_exit": {"hour": 14, "minute": 45}}
    assert (await _call("GET", _plan_path(sid) + "?playbook_id=999999999"))[0] == UNPROCESSABLE


async def test_no_spot_still_reads_the_type_from_the_strikes_and_prefills(app_db_url, monkeypatch):
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-24b")
    status, out = await _call("GET", _plan_path(sid))
    assert status == OK and out["type"] == "ic" and out["generic"] is False
    assert out["prefill"]["playbook_id"] == (await _system_ic(app_db_url)).id and out["plan"] is None


# --- refusals write nothing (attack 3 and 4 of the brief, AC-4) -------------------------------------------------------


async def test_invalid_values_a_wrong_type_and_put_without_a_plan_write_nothing(app_db_url, monkeypatch):
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-01")
    system = await _system_ic(app_db_url)
    async with app_db_url.connect() as conn:
        other = (await conn.execute(text("SELECT id FROM public.adjustment_playbooks WHERE is_system AND "
                                         "strategy_type = 'strangle'"))).scalar_one()
    cases = [({"target": "abc"}, "target"), ({"target": "0"}, "target"), ({"stop": "101"}, "stop"),
             ({"max_adjustments": "11"}, "max_adjustments"), ({"max_adjustments": "-1"}, "max_adjustments"),
             ({"time_exit": "24:00"}, "time_exit"), ({"time_exit": "9:60"}, "time_exit")]
    for extra, field in cases:
        status, out = await _call("POST", _plan_path(sid), json={"playbook_id": system.id, **extra})
        assert (status, out["what_happened"]) == (UNPROCESSABLE, f"The playbook value {field} is not valid."), extra
    status, out = await _call("POST", _plan_path(sid), json={"playbook_id": other})  # a playbook of another type
    assert (status, out["what_happened"]) == (UNPROCESSABLE, "The playbook value playbook_id is not valid.")
    status, _ = await _call("POST", _plan_path(sid), json={"playbook_id": system.id, "max_adjustments": 3})
    assert status == UNPROCESSABLE  # strict: a number is not the text the sheet sends
    status, _ = await _call("PUT", _plan_path(sid), json={"playbook_id": system.id})  # nothing to edit yet
    assert status == NOT_FOUND
    assert await _plan_row(app_db_url, sid) is None


async def test_untyped_shape_is_generic_and_post_is_refused_with_the_same_text(app_db_url, monkeypatch):
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-42")
    monkeypatch.setattr(adjustment_check, "strategy_type", lambda *a, **k: None)  # an unmapped shape
    system = await _system_ic(app_db_url)
    status, out = await _call("GET", _plan_path(sid))
    assert status == OK and (out["type"], out["generic"], out["plan"], out["prefill"], out["playbooks"]) == (
        None, True, None, None, [])
    assert out["generic_text"]["what_happened"] == GENERIC_TEXT["what_happened"]
    for method in ("POST", "PUT"):
        status, out = await _call(method, _plan_path(sid), json={"playbook_id": system.id})
        assert (status, out["what_happened"]) == (CONFLICT, GENERIC_TEXT["what_happened"])
    assert await _plan_row(app_db_url, sid) is None


# --- AC-2 / AC-3 core: one click copies the active playbook; the playbook's later edit never reaches the plan -------


async def test_core_use_as_is_copies_the_active_playbook_and_a_later_save_in_place_leaves_the_plan_identical(
        app_db_url, monkeypatch):
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-02")
    async with app_db_url.begin() as conn:  # the user's own active iron condor playbook
        system = await playbook_store.active_for(conn, USER, "ic")
        own = await playbook_store.duplicate(conn, USER, system.id, "Core own")
        await playbook_store.make_active(conn, USER, own.id)
    status, out = await _call("GET", _plan_path(sid))
    assert status == OK and out["prefill"]["playbook_id"] == own.id  # prefilled from the user's active playbook
    status, out = await _call("POST", _plan_path(sid), json={"playbook_id": own.id})  # "Use playbook as is"
    assert status == OK, out
    assert out["plan"]["playbook_id"] == own.id and out["plan"]["target"] == "50" and out["plan"]["stop"] == "50"
    before = await _plan_row(app_db_url, sid)
    assert before.strategy_type == "ic" and json.loads(before.body) == own.body  # the plan IS a copy of the body
    async with app_db_url.begin() as conn:  # a later save in place of the playbook
        changed = copy.deepcopy(own.body)
        changed["triggers"]["T-01"]["weekly"][1] = "0.2"
        changed["guards"]["max_adjustments"] = 9
        saved = await playbook_store.save_in_place(conn, USER, own.id, changed, own.version)
    assert saved.version == own.version + 1 and saved.body != own.body
    after = await _plan_row(app_db_url, sid)
    assert after.body == before.body and after.playbook_id == own.id  # byte-identical text
    status, out = await _call("GET", _plan_path(sid))
    assert status == OK and out["plan"]["max_adjustments"] == out["prefill"]["max_adjustments"] == SYSTEM_MAX
    status, check = await _call("GET", f"/api/strategies/{sid}/adjustment-check")  # the check route reads the plan
    assert status == OK and (check["playbook"]["source"], check["playbook"]["id"]) == ("plan", own.id)


async def test_overrides_land_in_the_copy_only_and_an_edit_keeps_them(app_db_url, monkeypatch):
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-02")
    async with app_db_url.connect() as conn:
        system = (await conn.execute(text("SELECT id FROM public.adjustment_playbooks WHERE is_system AND "
                                          "strategy_type = 'ic'"))).scalar_one()
    before = await _playbook_row(app_db_url, system)
    sheet = {"playbook_id": system, "target": "60", "stop": "40", "max_adjustments": "3",
             "time_exit": "14:45"}
    status, out = await _call("POST", _plan_path(sid), json=sheet)  # replaces the strategy's own plan
    assert status == OK, out
    assert (out["plan"]["playbook_id"], out["plan"]["target"], out["plan"]["stop"], out["plan"]["max_adjustments"],
            out["plan"]["time_exit"]) == (system, "60", "40", 3, {"hour": 14, "minute": 45})
    row = await _plan_row(app_db_url, sid)
    guards = json.loads(row.body)["guards"]
    assert (guards["profit_target_pct_of_max_profit"], guards["stop_line_pct_of_max_loss"], guards["max_adjustments"],
            guards["time_exit"]) == ("60", "40", 3, "14:45")
    assert await _playbook_row(app_db_url, system) == before  # the playbook: body and version unchanged
    status, edited = await _call("PUT", _plan_path(sid), json={"playbook_id": system, "stop": "35"})
    assert status == OK and (edited["plan"]["stop"], edited["plan"]["target"], edited["plan"]["time_exit"]) == (
        "35", "60", {"hour": 14, "minute": 45})  # a PUT keeps what the plan already holds
    assert json.loads((await _plan_row(app_db_url, sid)).body)["triggers"] == json.loads(row.body)["triggers"]
    assert await _playbook_row(app_db_url, system) == before
    status, sheet_now = await _call("GET", _plan_path(sid))  # AC-3: opened again later, prefilled from the plan
    assert status == OK and sheet_now["prefill"]["stop"] == "35" and sheet_now["plan"]["playbook_name"] is not None


async def test_zz_another_users_strategy_is_not_found_on_get_post_and_put_and_nothing_is_written(
        app_db_url, monkeypatch):
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-02")
    system = await _system_ic(app_db_url)
    before = await _plan_row(app_db_url, sid)
    assert before is not None  # the earlier tests left ADJ-02's plan
    monkeypatch.setattr(adjustment_readers, "current_user_ref", lambda: "someone-else")
    for method in ("GET", "POST", "PUT"):
        kw = {} if method == "GET" else {"json": {"playbook_id": system.id, "target": "99"}}
        assert (await _call(method, _plan_path(sid), **kw))[0] == NOT_FOUND, method
        assert (await _call(method, _plan_path(987654321), **kw))[0] == NOT_FOUND, method
    assert await _plan_row(app_db_url, sid) == before
