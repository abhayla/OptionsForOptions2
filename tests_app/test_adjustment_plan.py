"""GC-ADJ2 step 4: GET / POST / PUT /api/strategies/{id}/adjustment-plan in scenario mode on a fresh migrated database
(REQ-161 AC-1..AC-4, REQ-158 AC-5). Same harness as test_adjustment_check.py: the scenario's contracts go in through the
catalogue store's writer and its strategy through ``seed_scenario.seed`` (the app's own stores); the plan is read back
with the store and with the check route. One scenario per strategy (the seed is idempotent per scenario), so the tests
that share ADJ-02 run in file order: the core proof first, the overrides next, the other user last.
"""
from __future__ import annotations

import copy
import dataclasses
import importlib.util
import json
import pathlib
from decimal import Decimal as D

import pytest
from _scenario_catalogue import load_library
from httpx import ASGITransport, AsyncClient
from ofo.adjustment.playbook_types import SHOWN_NAMES
from ofo_app import adjustment_check, adjustment_readers, playbook_store, settings_in_force
from ofo_app import db as app_db
from ofo_app.config import get_settings
from ofo_app.routes import adjustment_plan as route
from sqlalchemy import text

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("seed_scenario", ROOT / "scripts" / "seed_scenario.py")
seed_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed_mod)
OK, NOT_FOUND, CONFLICT, UNPROCESSABLE = 200, 404, 409, 422
GENERIC_TEXT = {"what_happened": "No playbook matches this strategy's shape, so only the generic triggers and "
                                 "approaches apply."}
USER = "owner"
IC_NAME = SHOWN_NAMES["ic"]
SYSTEM_MAX = 2  # the system iron condor playbook's max_adjustments guard
_PLAN_SQL = text("SELECT playbook_id, strategy_type, body::text FROM public.strategy_adjustment_plans "
                 "WHERE strategy_id = :id")
_PLAYBOOK_SQL = text("SELECT body::text, version FROM public.adjustment_playbooks WHERE id = :id")


def _t06(body: str) -> dict:
    """The plan body's T-06 (% of max loss) stage values per expiry kind, as decimals."""
    trig = json.loads(body)["triggers"]["T-06"]
    return {k: [D(str(x)) for x in trig[k]] for k in ("weekly", "monthly")}


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
    await load_library(app_engine)  # the whole library's list, once per database
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


def _without_rupees(prefill: dict) -> dict:
    """ADR-330 (5): the rupee figures of a level are asserted on their own (tests_app/test_plan_rupee_levels.py)."""
    return {k: v for k, v in prefill.items() if "rupee" not in k and "per_lot" not in k and not k.endswith("_source")}


async def test_get_without_a_plan_prefills_from_the_active_system_playbook_and_pick_refills(app_db_url, monkeypatch):
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-01")
    system = await _system_ic(app_db_url)
    status, out = await _call("GET", _plan_path(sid))
    assert status == OK, out
    assert (out["type"], out["type_name"], out["generic"], out["generic_text"], out["plan"]) == (
        "ic", IC_NAME, False, None, None)
    assert (out["prefill"]["stop_rupees"], out["prefill"]["stop_per_lot"]) == ("10390.25", "5195.13")  # ADR-330 (5)
    assert _without_rupees(out["prefill"]) == {"playbook_id": system.id, "target": "50", "stop": "50", "max_adjustments": 2,  # noqa: E501
                              "time_exit": {"hour": 14, "minute": 30},  # ADR-216: the iron condor seed
                              "time_exit_on": None,
                              "target_words": "50 % of max profit",
                              "stop_words": "50 % of max loss or 2x the credit received, whichever comes first"}
    assert "rules_in_force" not in out  # GC-ICFIX u113 round 3: the limits come from the rule check only (ADR-304 (3))
    row = next(p for p in out["playbooks"] if p["id"] == system.id)
    assert (row["is_system"], row["active"], row["draft"]) == (True, True, False)
    assert out["labels"]["title"] == "When tracking starts: this strategy's plan"
    assert out["labels"]["use_as_is"] == "Use playbook as is" and out["labels"]["customise"] == "Customise triggers"
    body = copy.deepcopy(system.body)  # AC-2: another playbook refills every field from itself
    body["guards"] |= {"profit_target_pct_of_max_profit": "70", "max_adjustments": 4, "time_exit": "14:45"}
    for kind in ("weekly", "monthly"):  # ADR-252: the sheet's stop is the playbook's T-06 early-stage value
        body["triggers"]["T-06"][kind] = ["30", "30", "30"]
    async with app_db_url.begin() as conn:
        own = await playbook_store.create(conn, USER, "ic", "Plan pick", body)
    status, picked = await _call("GET", _plan_path(sid) + f"?playbook_id={own.id}")
    assert status == OK and _without_rupees(picked["prefill"]) == {"playbook_id": own.id, "target": "70", "stop": "30",
                                                  "max_adjustments": 4, "time_exit": {"hour": 14, "minute": 45},
                                                  "time_exit_on": None,
                                                  "target_words": "70 % of max profit",
                                                  "stop_words": "30 % of max loss or 2x the credit received, "
                                                                  "whichever comes first"}
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
    assert (guards["profit_target_pct_of_max_profit"], guards["max_adjustments"], guards["time_exit"]) == (
        "60", 3, "14:45")
    # ADR-252 addendum: the sheet's stop is written to T-06 (early/middle = V, last = min(V, its value)), no guard key
    assert _t06(row.body) == {k: [D("40")] * 3 for k in ("weekly", "monthly")}
    assert await _playbook_row(app_db_url, system) == before  # the playbook: body and version unchanged
    status, edited = await _call("PUT", _plan_path(sid), json={"playbook_id": system, "stop": "35"})
    assert status == OK and (edited["plan"]["stop"], edited["plan"]["target"], edited["plan"]["time_exit"]) == (
        "35", "60", {"hour": 14, "minute": 45})  # a PUT keeps what the plan already holds
    edited_body = (await _plan_row(app_db_url, sid)).body
    assert _t06(edited_body) == {k: [D("35")] * 3 for k in ("weekly", "monthly")}  # ADR-252: the stop edit is T-06
    assert ({k: v for k, v in json.loads(edited_body)["triggers"].items() if k != "T-06"}
            == {k: v for k, v in json.loads(row.body)["triggers"].items() if k != "T-06"})  # nothing else moves
    assert await _playbook_row(app_db_url, system) == before
    status, sheet_now = await _call("GET", _plan_path(sid))  # AC-3: opened again later, prefilled from the plan
    assert status == OK and sheet_now["prefill"]["stop"] == "35" and sheet_now["plan"]["playbook_name"] is not None


async def test_reset_to_playbook_goes_back_marks_what_differed_and_a_gone_playbook_refuses_it(app_db_url, monkeypatch):
    """P8 (ADR-330 (9)): the plan names the conditions it changed; one reset copies the playbook back; a plan whose
    playbook was deleted is refused with the not-found sentence and stays as it is."""
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-02")
    system = (await _system_ic(app_db_url)).id
    status, out = await _call("POST", _plan_path(sid), json={"playbook_id": system})
    assert status == OK and (out["plan"]["changed"], out["plan"]["switched_off"]) == ([], [])
    status, out = await _call("PUT", _plan_path(sid), json={"playbook_id": system, "stop": "35", "target": "60"})
    assert status == OK and out["plan"]["changed"] == ["triggers.T-06"]  # the sheet's levels are no conditions
    status, out = await _call("POST", _plan_path(sid) + "/reset")
    assert status == OK, out
    assert (out["plan"]["changed"], out["plan"]["switched_off"], out["plan"]["playbook_id"]) == ([], [], system)
    assert json.loads((await _plan_row(app_db_url, sid)).body) == (await _system_ic(app_db_url)).body
    async with app_db_url.begin() as conn:  # a plan of the user's own playbook, which is then deleted
        own = await playbook_store.duplicate(conn, USER, system, "Reset source")
    status, out = await _call("POST", _plan_path(sid), json={"playbook_id": own.id, "stop": "30"})
    assert status == OK and out["plan"]["changed"] == ["triggers.T-06"]
    async with app_db_url.begin() as conn:
        await playbook_store.delete(conn, USER, own.id)
    before = await _plan_row(app_db_url, sid)
    status, out = await _call("POST", _plan_path(sid) + "/reset")
    assert status == NOT_FOUND
    assert out["code"] == "USER_INPUT_156", out  # the catalogue row of "This playbook was not found."
    assert await _plan_row(app_db_url, sid) == before


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


# --- ADR-245: the strategy layer (``settings``) through the plan write routes (cfg step 1 fix round 1) ----------------
CARRY_KEY = "other.carry_gap_percent"


async def test_plan_settings_accepted_refused_with_a_named_reason_and_removable(app_db_url, monkeypatch):
    """POST/PUT carry ``settings`` (the strategy's own overrides): a registry-accepted value is stored in the plan
    body (never dropped); an out-of-range value, an unknown key, an admin-only key, "" and a number are refused naming
    the field and write nothing; an edit leaving settings out keeps them; ``{}`` removes the override."""
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-02")  # ADJ-01's contracts are delisted by the ADJ-02 tests above
    system = await _system_ic(app_db_url)
    before = await _plan_row(app_db_url, sid)  # the strategy may already carry a plan from the earlier tests
    refused = [({CARRY_KEY: "99"}, f"settings.{CARRY_KEY}"), ({"other.unknown_key": "1"}, "settings.other.unknown_key"),
               ({"speeds.open_strategy_seconds": "5"}, "settings.speeds.open_strategy_seconds"),
               ({CARRY_KEY: ""}, f"settings.{CARRY_KEY}")]
    for settings, field in refused:
        status, out = await _call("POST", _plan_path(sid), json={"playbook_id": system.id, "settings": settings})
        assert (status, out["what_happened"]) == (UNPROCESSABLE, f"The playbook value {field} is not valid."), settings
    status, _ = await _call("POST", _plan_path(sid), json={"playbook_id": system.id, "settings": {CARRY_KEY: 1.5}})
    assert status == UNPROCESSABLE  # strict: a number is not the text the sheet sends
    assert await _plan_row(app_db_url, sid) == before  # nothing written by any refusal

    def stored(row) -> dict:
        return json.loads(row.body)["settings"]
    status, out = await _call("POST", _plan_path(sid), json={"playbook_id": system.id, "settings": {CARRY_KEY: "1.5"}})
    assert status == OK, out
    assert stored(await _plan_row(app_db_url, sid)) == {CARRY_KEY: "1.5"}
    status, out = await _call("PUT", _plan_path(sid), json={"playbook_id": system.id, "target": "50"})
    assert status == OK, out  # an edit that leaves settings out keeps them
    assert stored(await _plan_row(app_db_url, sid)) == {CARRY_KEY: "1.5"}
    status, out = await _call("PUT", _plan_path(sid), json={"playbook_id": system.id, "settings": {CARRY_KEY: "99"}})
    assert (status, out["what_happened"]) == (UNPROCESSABLE, f"The playbook value settings.{CARRY_KEY} is not valid.")
    assert stored(await _plan_row(app_db_url, sid)) == {CARRY_KEY: "1.5"}  # unchanged
    status, out = await _call("PUT", _plan_path(sid), json={"playbook_id": system.id, "settings": {}})
    assert status == OK, out
    assert stored(await _plan_row(app_db_url, sid)) == {}


# --- ADR-305: the box opens empty when the rule set has the profit rule (T-07) off; an empty Target saves ------------


async def test_prefill_target_is_empty_when_the_rule_set_has_t07_off_and_the_rule_set_value_when_on(
        app_db_url, monkeypatch):
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-01")
    system = await _system_ic(app_db_url)
    body = copy.deepcopy(system.body)
    body["triggers"]["T-07"]["on"] = False
    async with app_db_url.begin() as conn:
        off = await playbook_store.create(conn, USER, "ic", "Rule off", body)
        on = await playbook_store.create(conn, USER, "ic", "Rule on", copy.deepcopy(system.body))
    status, out = await _call("GET", _plan_path(sid) + f"?playbook_id={off.id}")
    assert status == OK and out["prefill"]["target"] is None and out["prefill"]["target_words"] is None, out
    status, out = await _call("GET", _plan_path(sid) + f"?playbook_id={on.id}")
    assert status == OK and out["prefill"]["target"] == "50", out  # T-07 on 50/50/80: as today


async def test_saving_the_box_with_an_empty_target_stores_no_target_and_t07_is_not_checked(app_db_url, monkeypatch):
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-02")
    system = await _system_ic(app_db_url)
    status, out = await _call("POST", _plan_path(sid), json={"playbook_id": system.id, "target": "50", "stop": "40"})
    assert status == OK and out["plan"]["target"] == "50", out
    status, out = await _call("PUT", _plan_path(sid), json={"playbook_id": system.id, "target": ""})  # emptied
    assert status == OK and out["plan"]["target"] is None and out["plan"]["target_words"] is None, out
    assert out["plan"]["stop"] == "40"  # the other fields are kept
    body = json.loads((await _plan_row(app_db_url, sid)).body)
    assert body["guards"]["profit_target_pct_of_max_profit"] == ""  # no number stored
    assert adjustment_check.with_plan_target(body)["triggers"]["T-07"]["on"] is False  # the check does not act on it
    for bad in ("0", "-5", "101", "abc"):  # an unusable number is still refused, naming the field
        status, refused = await _call("PUT", _plan_path(sid), json={"playbook_id": system.id, "target": bad})
        assert status == UNPROCESSABLE and "target" in json.dumps(refused), refused


# --- ADR-330 (5) / LP-2: the levels preview says the same stop sentence the saved plan says (P4b) ---------------------


async def test_levels_preview_gives_the_stop_sentence_the_saved_plan_gives_and_writes_nothing(app_db_url, monkeypatch):
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-01")
    system = await _system_ic(app_db_url)
    levels = _plan_path(sid) + "/levels"
    for typed in ({"stop": "40"}, {"stop_rupees": "4000"}):
        before = await _plan_row(app_db_url, sid)
        status, preview = await _call("GET", levels, params=typed)
        assert status == OK, preview
        assert await _plan_row(app_db_url, sid) == before  # a preview writes nothing: the stored body is unchanged
        status, saved = await _call("PUT" if before is not None else "POST", _plan_path(sid),
                                    json={"playbook_id": system.id, **typed})
        assert status == OK, saved
        assert preview["stop"]["words"] == saved["plan"]["stop_words"], typed
        assert "2x the credit received" in preview["stop"]["words"]
        assert preview["stop"]["words"].endswith(", whichever comes first")
    assert preview["stop"]["words"].startswith("a loss of Rs 4000.00 (")


def _own_with_credit(body: dict, multiple: str) -> dict:
    body = copy.deepcopy(body)
    body["guards"]["stop_line_x_credit"] = multiple
    return body


async def test_levels_preview_follows_the_picked_playbook_not_the_active_one(app_db_url, monkeypatch):
    """P4b round 2: the picked playbook's credit multiple (3x) is in the preview, exactly as in the saved plan."""
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-01")
    system = await _system_ic(app_db_url)
    async with app_db_url.begin() as conn:
        own = await playbook_store.duplicate(conn, USER, system.id, "Three x credit")
        await conn.execute(text("UPDATE public.adjustment_playbooks SET body = CAST(:b AS jsonb) WHERE id = :id"),
                           {"b": json.dumps(_own_with_credit(own.body, "3")), "id": own.id})
    levels = _plan_path(sid) + "/levels"
    status, preview = await _call("GET", levels, params={"stop_rupees": "400", "playbook_id": own.id})
    assert status == OK, preview
    status, saved = await _call("POST", _plan_path(sid), json={"playbook_id": own.id, "stop_rupees": "400"})
    assert status == OK, saved
    assert "3x the credit received" in saved["plan"]["stop_words"]
    assert preview["stop"]["words"] == saved["plan"]["stop_words"]
    status, edited = await _call("PUT", _plan_path(sid), json={"playbook_id": own.id, "stop_rupees": "500"})
    status2, again = await _call("GET", levels, params={"stop_rupees": "500", "playbook_id": own.id})
    assert (status, status2) == (OK, OK) and again["stop"]["words"] == edited["plan"]["stop_words"]  # editing keeps it
    assert (await _call("GET", levels, params={"stop_rupees": "400", "playbook_id": 0}))[0] == UNPROCESSABLE
    missing = {"stop_rupees": "400", "playbook_id": 999999999}  # in range, not there: the refusal the save gives
    assert (await _call("GET", levels, params=missing))[0] == (await _call("POST", _plan_path(sid), json={
        "playbook_id": 999999999, "stop_rupees": "400"}))[0] == NOT_FOUND


async def test_levels_preview_of_a_generic_shape_has_no_stop_words_not_the_partial_sentence(app_db_url, monkeypatch):
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-42")
    real = route._type_of

    async def no_type(*args):
        return (None, (await real(*args))[1])  # no playbook matches and no plan: no body to read the lines from
    monkeypatch.setattr(route, "_type_of", no_type)
    status, out = await _call("GET", _plan_path(sid) + "/levels", params={"stop": "40"})
    assert status == OK, out
    assert out["stop"]["percent"] == "40" and out["stop"]["words"] is None


async def _preview_and_saved(app_db_url, monkeypatch, pick_body=None, typed=None):
    """Seed ADJ-01, pick the system playbook (or the user's own copy holding ``pick_body``), return the levels preview
    and the saved plan's stop sentence for the same typed level."""
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-01")
    system = await _system_ic(app_db_url)
    pick = system.id
    if pick_body is not None:
        async with app_db_url.begin() as conn:
            own = await playbook_store.duplicate(conn, USER, system.id, "Regression copy")
            await conn.execute(text("UPDATE public.adjustment_playbooks SET body = CAST(:b AS jsonb) WHERE id = :id"),
                               {"b": json.dumps(pick_body(own.body)), "id": own.id})
        pick = own.id
    typed = typed or {"stop_rupees": "400"}
    status, preview = await _call("GET", _plan_path(sid) + "/levels", params={**typed, "playbook_id": pick})
    assert status == OK, preview
    status, saved = await _call("POST", _plan_path(sid), json={"playbook_id": pick, **typed})
    assert status == OK, saved
    return preview["stop"]["words"], saved["plan"]["stop_words"]


async def test_levels_preview_equals_saved_when_the_rupee_stop_replaces_the_credit_line(app_db_url, monkeypatch):
    monkeypatch.setattr(settings_in_force, "RUPEE_STOP_KEEPS_CREDIT", False)
    preview, saved = await _preview_and_saved(app_db_url, monkeypatch)
    assert preview == saved and "credit" not in preview


async def test_levels_preview_equals_saved_for_a_body_with_no_credit_line(app_db_url, monkeypatch):
    monkeypatch.setattr(settings_in_force, "credit_line_applies", lambda resolved: False)
    preview, saved = await _preview_and_saved(app_db_url, monkeypatch)
    assert preview == saved and "credit" not in preview


async def test_levels_preview_equals_saved_with_no_stored_base(app_db_url, monkeypatch):
    real = route.bases_of
    monkeypatch.setattr(route, "bases_of", lambda *a, **k: dataclasses.replace(real(*a, **k), max_loss=None))
    monkeypatch.setattr(route, "_stored_loss", lambda stored, bases: None)
    preview, saved = await _preview_and_saved(app_db_url, monkeypatch)
    assert preview == saved == "a loss of Rs 400.00 or 2x the credit received, whichever comes first"
