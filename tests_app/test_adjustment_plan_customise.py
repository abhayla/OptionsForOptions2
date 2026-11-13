"""GC-ICFIX u161/u162 (issue 7, REQ-045, REQ-158 AC-5/AC-6, ADR-214 (4b)): "Customise triggers" from ONE trade edits
that trade's own plan copy, never a playbook other trades follow. Routes: GET / PUT /api/strategies/{id}/adjustment-plan/rules.
Class: every path from a trade's screen into editing rule values. The database is shared by this file's tests and the
app role may not delete plans, so the tests run in file order: ADJ-01 starts with no plan, ADJ-02 too."""
from __future__ import annotations

import copy
import importlib.util
import json
import pathlib

import pytest
from _scenario_catalogue import load_library
from httpx import ASGITransport, AsyncClient
from ofo.adjustment.playbook_types import SHOWN_NAMES
from ofo_app import adjustment_check, playbook_store
from ofo_app import db as app_db
from ofo_app.config import get_settings
from sqlalchemy import text

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("seed_scenario", ROOT / "scripts" / "seed_scenario.py")
seed_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed_mod)
USER = "owner"
NOTE = f"Rules for this trade only ({SHOWN_NAMES['ic']}). Your other trades and your playbooks are not changed."
_PLAN_SQL = text("SELECT playbook_id, strategy_type, body::text FROM public.strategy_adjustment_plans WHERE strategy_id = :id")
_PLAN_COUNT = text("SELECT count(*) FROM public.strategy_adjustment_plans WHERE strategy_id = :id")
_PB_SQL = text("SELECT id, user_ref, is_system, version, body::text FROM public.adjustment_playbooks ORDER BY id")


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
    await load_library(app_engine)
    return await seed_mod.seed(sid)


async def _call(method: str, path: str, overrides=None, **kw) -> tuple[int, dict]:
    from ofo_app.main import create_app  # noqa: PLC0415 - the env above must be set first
    _reset_engine()
    app = create_app()
    app.dependency_overrides.update(overrides or {})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.request(method, path, **kw)
    await app_db.close_db()
    return r.status_code, r.json()


plan_path = lambda sid: f"/api/strategies/{sid}/adjustment-plan"  # noqa: E731
rules_path = lambda sid: f"{plan_path(sid)}/rules"  # noqa: E731


async def _plan_row(engine, sid: int):
    async with engine.connect() as conn:
        return (await conn.execute(_PLAN_SQL, {"id": sid})).one_or_none()


async def _plan_count(engine, sid: int) -> int:
    async with engine.connect() as conn:
        return (await conn.execute(_PLAN_COUNT, {"id": sid})).scalar_one()


async def _playbook_rows(engine):
    async with engine.connect() as conn:
        return [tuple(r) for r in (await conn.execute(_PB_SQL)).all()]


async def _resolved(engine, sid: int):
    async with engine.connect() as conn:
        return await adjustment_check.resolve(conn, USER, sid, "ic")


def _changed(body: dict, value: str) -> dict:
    out = copy.deepcopy(body)
    out["triggers"]["T-01"]["weekly"][1] = value
    return out


def _t01(body: dict) -> str:
    return body["triggers"]["T-01"]["weekly"][1]


async def test_a_trade_with_no_plan_customises_its_own_copy_and_nothing_shared_moves(app_db_url, monkeypatch):
    a = await _seeded(app_db_url, monkeypatch, "ADJ-01")
    b = await _seeded(app_db_url, monkeypatch, "ADJ-02")
    assert a != b and await _plan_count(app_db_url, a) == 0 and await _plan_count(app_db_url, b) == 0
    playbooks, b_resolved = await _playbook_rows(app_db_url), await _resolved(app_db_url, b)
    monkeypatch.setenv("OFO_SCENARIO", "ADJ-01")  # the market the app reads is the trade's own scenario
    status, read = await _call("GET", rules_path(a))
    assert status == 200, read
    assert read["is_system"] is False and read["active"] is False  # the target is the trade's own copy, never a shared row
    assert read["name"] == NOTE  # the one plain line, from the catalogue
    assert await _plan_count(app_db_url, a) == 0  # opening (then cancelling) writes nothing
    status, saved = await _call("PUT", rules_path(a), json={"body": _changed(read["body"], "0.2")})
    assert status == 200, saved
    assert await _plan_count(app_db_url, a) == 1
    assert await _playbook_rows(app_db_url) == playbooks  # the system playbook the copy came from is unchanged
    assert await _plan_count(app_db_url, b) == 0 and await _resolved(app_db_url, b) == b_resolved  # B still follows the playbook


async def test_core_two_trades_customised_differently_keep_their_own_rules(app_db_url, monkeypatch):
    """Proof 2: customising on trade A leaves trade B's resolved rules and plan row byte-for-byte as they were."""
    a = await _seeded(app_db_url, monkeypatch, "ADJ-01")  # has its customised plan from the test above
    b = await _seeded(app_db_url, monkeypatch, "ADJ-02")
    async with app_db_url.connect() as conn:
        active = await playbook_store.active_for(conn, USER, "ic")
    monkeypatch.setenv("OFO_SCENARIO", "ADJ-02")
    status, out = await _call("POST", plan_path(b), json={"playbook_id": active.id})  # B: "Use playbook as is"
    assert status == 200, out
    b_row, b_resolved, playbooks = await _plan_row(app_db_url, b), await _resolved(app_db_url, b), await _playbook_rows(app_db_url)
    _, read_b = await _call("GET", rules_path(b))
    monkeypatch.setenv("OFO_SCENARIO", "ADJ-01")
    status, read_a = await _call("GET", rules_path(a))
    assert status == 200 and _t01(read_a["body"]) == "0.2" and _t01(read_b["body"]) != "0.2"  # each shows its own values
    status, saved = await _call("PUT", rules_path(a), json={"body": _changed(read_a["body"], "0.25")})
    assert status == 200, saved
    assert _t01(json.loads((await _plan_row(app_db_url, a)).body)) == "0.25"
    assert _t01((await _resolved(app_db_url, a)).body) == "0.25"
    assert await _plan_row(app_db_url, b) == b_row  # byte-identical text
    assert await _resolved(app_db_url, b) == b_resolved
    assert await _playbook_rows(app_db_url) == playbooks  # no playbook row written, changed or added


async def test_customised_again_reopens_the_same_copy_and_keeps_one_plan(app_db_url, monkeypatch):
    a = await _seeded(app_db_url, monkeypatch, "ADJ-01")
    _, again = await _call("GET", rules_path(a))
    assert _t01(again["body"]) == "0.25"  # reopened on the customised copy, not on the playbook
    assert (await _call("PUT", rules_path(a), json={"body": _changed(again["body"], "0.3")}))[0] == 200
    assert await _plan_count(app_db_url, a) == 1 and _t01(json.loads((await _plan_row(app_db_url, a)).body)) == "0.3"


async def test_a_refused_save_tells_the_user_and_changes_nothing(app_db_url, monkeypatch):
    a = await _seeded(app_db_url, monkeypatch, "ADJ-01")
    before, playbooks = await _plan_row(app_db_url, a), await _playbook_rows(app_db_url)
    status, out = await _call("PUT", rules_path(a), json={"body": {"nonsense": 1}})
    assert 400 <= status < 500 and "what_happened" in json.dumps(out)
    assert await _plan_row(app_db_url, a) == before and await _playbook_rows(app_db_url) == playbooks


# --- round 2: the editor shows and saves what the check acts on (ADR-304: the plan Target overrides T-07) -------------
WEEKLY = ["30", "30", "30"]


async def _raw_plan(engine, sid: int, t07: list[str], target: str | None = "50", on: bool = True) -> None:
    """Writes the trade's plan body straight through the store: guard Target `target`, T-07 = `t07` in both kinds."""
    async with engine.connect() as conn:
        active = await playbook_store.active_for(conn, USER, "ic")
    body = copy.deepcopy(active.body)
    body["triggers"]["T-07"].update({"weekly": list(t07), "monthly": list(t07), "on": on})
    if target is None:
        body["guards"].pop("profit_target_pct_of_max_profit", None)
    else:
        body["guards"]["profit_target_pct_of_max_profit"] = target
    async with engine.begin() as conn:
        await playbook_store.accept_plan(conn, USER, sid, active.id, body)


def _t07(body: dict, kind: str = "weekly") -> list[str]:
    return [str(x) for x in body["triggers"]["T-07"][kind]]


async def test_editor_shows_what_the_check_acts_on_and_a_save_without_t07_keeps_the_target(app_db_url, monkeypatch):
    a = await _seeded(app_db_url, monkeypatch, "ADJ-01")
    await _raw_plan(app_db_url, a, WEEKLY)
    assert _t07((await _resolved(app_db_url, a)).body) == ["50", "50", "30"]  # what the check uses
    _, read = await _call("GET", rules_path(a))
    assert _t07(read["body"]) == ["50", "50", "30"]  # (1) the editor shows the applied view, not the raw 30
    raw_before = json.loads((await _plan_row(app_db_url, a)).body)
    status, _ = await _call("PUT", rules_path(a), json={"body": _changed(read["body"], "0.31")})  # another trigger only
    assert status == 200
    raw = json.loads((await _plan_row(app_db_url, a)).body)
    assert raw["guards"]["profit_target_pct_of_max_profit"] == "50" and raw["triggers"]["T-07"] == raw_before["triggers"]["T-07"]  # (3)
    assert _t07((await _resolved(app_db_url, a)).body) == ["50", "50", "30"]
    assert _t07((await _call("GET", rules_path(a)))[1]["body"]) == ["50", "50", "30"]


async def test_a_t07_change_in_the_editor_replaces_the_target_and_a_new_target_wins_again(app_db_url, monkeypatch):
    a = await _seeded(app_db_url, monkeypatch, "ADJ-01")
    await _raw_plan(app_db_url, a, WEEKLY)
    _, read = await _call("GET", rules_path(a))
    mine = copy.deepcopy(read["body"])
    mine["triggers"]["T-07"]["weekly"] = ["30", "40", "30"]
    status, _ = await _call("PUT", rules_path(a), json={"body": mine})
    assert status == 200
    assert "profit_target_pct_of_max_profit" not in json.loads((await _plan_row(app_db_url, a)).body)["guards"]
    assert _t07((await _resolved(app_db_url, a)).body) == ["30", "40", "30"]  # (2) the check acts on the saved value
    assert _t07((await _call("GET", rules_path(a)))[1]["body"]) == ["30", "40", "30"]
    status, sheet = await _call("GET", plan_path(a))  # (5) the plan route still answers; no Target typed = empty
    assert status == 200 and sheet["prefill"]["target"] is None
    plan = await _plan_row(app_db_url, a)
    status, out = await _call("PUT", plan_path(a), json={"playbook_id": plan.playbook_id, "target": "20"})
    assert status == 200, out
    assert _t07((await _resolved(app_db_url, a)).body) == ["20", "20", "20"]  # (4) a Target typed later wins again
    assert _t07((await _call("GET", rules_path(a)))[1]["body"]) == ["20", "20", "20"]


async def test_t07_switched_off_in_the_editor_stays_off_because_the_target_is_removed(app_db_url, monkeypatch):
    a = await _seeded(app_db_url, monkeypatch, "ADJ-01")
    await _raw_plan(app_db_url, a, WEEKLY)
    _, read = await _call("GET", rules_path(a))
    mine = copy.deepcopy(read["body"])
    mine["triggers"]["T-07"]["on"] = False
    assert (await _call("PUT", rules_path(a), json={"body": mine}))[0] == 200
    assert (await _resolved(app_db_url, a)).body["triggers"]["T-07"]["on"] is False
    assert "profit_target_pct_of_max_profit" not in json.loads((await _plan_row(app_db_url, a)).body)["guards"]


async def test_a_closed_trade_answers_a_conflict_on_get_and_put_and_nothing_is_written(app_db_url, monkeypatch):
    from ofo_app.adjustment_readers import TrackedExited  # noqa: PLC0415
    from ofo_app.routes.adjustment import get_tracked_reader  # noqa: PLC0415
    a = await _seeded(app_db_url, monkeypatch, "ADJ-01")
    before = await _plan_row(app_db_url, a)

    async def exited(_sid, _rates):
        raise TrackedExited("no open option leg")
    over = {get_tracked_reader: lambda: exited}
    assert (await _call("GET", rules_path(a), overrides=over))[0] == 409
    assert (await _call("PUT", rules_path(a), overrides=over, json={"body": {}}))[0] == 409
    assert await _plan_row(app_db_url, a) == before


async def test_zz_another_users_trade_is_not_found_and_nothing_is_written(app_db_url, monkeypatch):
    from ofo_app import adjustment_readers  # noqa: PLC0415
    a = await _seeded(app_db_url, monkeypatch, "ADJ-01")
    before = await _plan_row(app_db_url, a)
    monkeypatch.setattr(adjustment_readers, "current_user_ref", lambda: "someone-else")
    assert (await _call("GET", rules_path(a)))[0] == 404
    assert (await _call("PUT", rules_path(a), json={"body": {}}))[0] == 404
    assert await _plan_row(app_db_url, a) == before
