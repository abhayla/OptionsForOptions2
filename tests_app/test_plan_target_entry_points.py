"""The plan sheet's Target reaches T-07 through the REAL entry points (GC-ICFIX u102 item B; ADR-252, ADR-245, ADR-294).

Real case, paper strategy 141: plan Target 1 %, profit Rs 32-49, nothing fired. Here scenario ADJ-01 (profit Rs 32.50 of
max profit Rs 5,219.50 = 0.62 %, a system playbook whose T-07 is 50 / 50 / 80) with a plan Target of 0.5:
- the rule-check route (``routes/adjustment_check.py``) flags T-07 at 0.5 and its line names the limit and the basis;
- the watcher's lister (``background.owner_lister`` -> ``check.resolve``) hands the evaluator a body whose T-07 is 0.5
  (the evaluator is then run on that body with the scenario's own numbers; the worker's cycle is not driven here);
- T-07 switched OFF in the playbook still fires at the typed Target (the plan's Target switches it on for the trade).
"""
from __future__ import annotations

import copy
import importlib.util
import pathlib
from decimal import Decimal as D

import pytest
from _scenario_catalogue import load_library
from httpx import ASGITransport, AsyncClient
from ofo.adjustment import playbook_eval as pe
from ofo_app import background, playbook_store, scenario_mode
from ofo_app import db as app_db
from ofo_app.config import get_settings

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("seed_scenario", ROOT / "scripts" / "seed_scenario.py")
seed_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed_mod)
KEY = "profit_target_pct_of_max_profit"
PNL, MAX_PROFIT = D("32.5"), D("5219.5")  # ADJ-01: pnl_now and max_profit


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


async def _seeded_with_plan(app_engine, monkeypatch, target: str, *, t07_on: bool = True) -> int:
    monkeypatch.setenv("OFO_SCENARIO", "ADJ-01")
    await load_library(app_engine)
    sid = await seed_mod.seed("ADJ-01")
    async with app_engine.begin() as conn:
        system = await playbook_store.active_for(conn, "owner", "ic")
        body = copy.deepcopy(system.body)
        body["guards"][KEY] = target
        body["triggers"]["T-07"]["on"] = t07_on
        await playbook_store.accept_plan(conn, "owner", sid, system.id, body)
    return sid


async def _check(strategy_id: int) -> dict:
    from ofo_app.main import create_app  # noqa: PLC0415 - the env above must be set first
    _reset_engine()
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://t") as ac:
        r = await ac.get(f"/api/strategies/{strategy_id}/adjustment-check")
    await app_db.close_db()
    assert r.status_code == 200, r.text  # noqa: PLR2004
    return r.json()


@pytest.mark.parametrize("t07_on", [True, False])
async def test_the_rule_check_route_flags_t07_at_the_plan_target(app_db_url, monkeypatch, t07_on):
    sid = await _seeded_with_plan(app_db_url, monkeypatch, "0.5", t07_on=t07_on)
    out = await _check(sid)
    t07 = next(x for x in out["results"] if x["trigger_id"] == "T-07")
    assert (t07["kind"], t07["threshold"]) == ("flag", "0.5000"), t07  # before the fix: threshold 50, no flag
    assert "target of 0.5%" in t07["condition"] and "before charges" in t07["condition"]  # item C: value + basis


async def test_the_watcher_lister_hands_the_evaluator_the_plan_target(app_db_url, monkeypatch):
    sid = await _seeded_with_plan(app_db_url, monkeypatch, "0.5", t07_on=False)
    scn = scenario_mode.load("ADJ-01")
    watched = next(x for x in await background.owner_lister(scn.provider) if x.strategy_id == sid)
    t07 = watched.body["triggers"]["T-07"]
    assert t07["on"] is True and t07["weekly"][0] == "0.5"
    state = pe.StrategyState(expiry_kind="weekly", days_left=7, hhmm="11:00", pnl=PNL, max_profit=MAX_PROFIT,
                             prices_fresh=True, spot=D("24000"), stops=None)
    ev = pe.evaluate(watched.body, state, None, None, gap_until="09:30")
    flag = next(r for r in ev.results if r.rule_id == "T-07")
    assert isinstance(flag, pe.Flag) and flag.threshold == D("0.5")
