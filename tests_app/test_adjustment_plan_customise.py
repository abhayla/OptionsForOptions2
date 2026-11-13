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


async def _call(method: str, path: str, **kw) -> tuple[int, dict]:
    from ofo_app.main import create_app  # noqa: PLC0415 - the env above must be set first
    _reset_engine()
    app = create_app()
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
    status, out = await _call("POST", plan_path(b), json={"playbook_id": active.id})  # B: "Use playbook as is"
    assert status == 200, out
    b_row, b_resolved, playbooks = await _plan_row(app_db_url, b), await _resolved(app_db_url, b), await _playbook_rows(app_db_url)
    _, read_b = await _call("GET", rules_path(b))
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


async def test_zz_another_users_trade_is_not_found_and_nothing_is_written(app_db_url, monkeypatch):
    from ofo_app import adjustment_readers  # noqa: PLC0415
    a = await _seeded(app_db_url, monkeypatch, "ADJ-01")
    before = await _plan_row(app_db_url, a)
    monkeypatch.setattr(adjustment_readers, "current_user_ref", lambda: "someone-else")
    assert (await _call("GET", rules_path(a)))[0] == 404
    assert (await _call("PUT", rules_path(a), json={"body": {}}))[0] == 404
    assert await _plan_row(app_db_url, a) == before
