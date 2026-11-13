"""The plan sheet's Target is the T-07 value the live check reads (ADR-252 pattern, for T-07). No DB.

Real case, paper strategy 141 (13 Nov 2026): plan Target 1 on playbook 3 "Iron condor: system default" (T-07 weekly
50 / 50 / 80), max profit about 2,753, P&L +48.75 (1.77 % of max profit) raised no T-07 flag.

Spec basis: REQ-158 AC-5 (plan, then playbook); REQ-161 AC-3 (the accepted sheet is the strategy's plan); ADR-245 (the
flag names the value used); ADR-252 addendum (a save that leaves the value untouched rewrites nothing).
"""
from __future__ import annotations

import copy
import datetime
import json
import pathlib
from decimal import Decimal as D

import pytest
from ofo.adjustment import playbook_eval as pe
from ofo.timeutil import IST
from ofo_app import adjustment_check as check
from ofo_app import playbook_store

SEED = json.loads((pathlib.Path(__file__).parent.parent / "backend/ofo/adjustment/system_playbooks.json")
                  .read_text(encoding="utf-8"), parse_float=D)
BODY = next(p["body"] for p in SEED["playbooks"] if p["body"]["strategy_type"] == "ic")
KEY = "profit_target_pct_of_max_profit"
MAX_PROFIT = D("2753")


def plan_body(target) -> dict:
    body = copy.deepcopy(BODY)
    body["guards"][KEY] = target
    return body


async def resolved(monkeypatch, body: dict | None) -> check.Resolved:
    """``check.resolve`` (the one door of the screen check, the worker and the plan sheet) over a stored plan."""
    plan = None if body is None else playbook_store.Plan(141, 3, "ic", body,
                                                          datetime.datetime(2026, 11, 13, 9, 0, tzinfo=IST))

    async def plan_for(conn, user_ref, strategy_id):
        return plan

    async def active_for(conn, user_ref, stype):
        return type("PB", (), {"body": copy.deepcopy(BODY), "id": 3, "status": None, "is_system": True})()

    async def before(conn, p):
        return False

    monkeypatch.setattr(playbook_store, "plan_for", plan_for)
    monkeypatch.setattr(playbook_store, "active_for", active_for)
    monkeypatch.setattr(check, "plan_saved_before_adr247", before)
    return await check.resolve(None, "owner", 141, "ic")


def t07(body: dict, pnl: str):
    """The evaluator's answer for rule T-07 at the strategy's first stage (weekly, 7 days left)."""
    state = pe.StrategyState(expiry_kind="weekly", days_left=7, hhmm="11:00", pnl=D(pnl), max_profit=MAX_PROFIT,
                             prices_fresh=True, spot=D("24000"),
                             stops=None)
    ev = pe.evaluate(body, state, None, None, gap_until="09:30")
    assert "T-07" in {*ev.clear, *(r.rule_id for r in ev.results)}, ev  # T-07 was checked, not skipped
    return next((r for r in ev.results if r.rule_id == "T-07"), None)


async def test_core_plan_target_1_flags_t07_at_1_77_percent(monkeypatch):
    got = t07((await resolved(monkeypatch, plan_body("1"))).body, "48.75")
    assert isinstance(got, pe.Flag) and got.threshold == D("1")  # before: no flag (threshold 50)


async def test_core_plan_target_1_is_clear_at_0_73_percent(monkeypatch):
    got = t07((await resolved(monkeypatch, plan_body("1"))).body, "20")
    assert got is None  # 0.73 % < 1 %


async def test_target_equal_to_the_playbook_early_value_rewrites_nothing(monkeypatch):
    body = (await resolved(monkeypatch, plan_body("50"))).body
    assert body["triggers"]["T-07"] == BODY["triggers"]["T-07"]  # last stage keeps 80 / 75


async def test_no_plan_follows_the_playbook(monkeypatch):
    body = (await resolved(monkeypatch, None)).body
    assert body["triggers"]["T-07"]["weekly"] == ["50", "50", "80"]
    assert t07(body, "48.75") is None


@pytest.mark.parametrize("raw", ["", "abc", "0", "-5", "101", None, 7])
async def test_unusable_target_leaves_the_playbook_value(monkeypatch, raw):
    body = (await resolved(monkeypatch, plan_body(raw))).body
    assert body["triggers"]["T-07"] == BODY["triggers"]["T-07"]


async def test_last_stage_is_never_looser_and_other_triggers_are_untouched(monkeypatch):
    body = (await resolved(monkeypatch, plan_body("60"))).body
    assert body["triggers"]["T-07"]["weekly"] == ["60", "60", "60"]  # 60 < 80
    assert body["triggers"]["T-07"]["monthly"] == ["60", "60", "60"]
    body = (await resolved(monkeypatch, plan_body("90"))).body
    assert body["triggers"]["T-07"]["weekly"] == ["90", "90", "80"]  # last stays stricter
    assert {k: v for k, v in body["triggers"].items() if k != "T-07"} == \
        {k: v for k, v in BODY["triggers"].items() if k != "T-07"}
