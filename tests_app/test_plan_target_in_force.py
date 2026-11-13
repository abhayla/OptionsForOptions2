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


# --- item A: a typed Target switches T-07 ON for the trade, as the plan's Stop does for T-06
# (orchestrator decision) ---

def plan_body_off(target, **trig) -> dict:
    body = plan_body(target)
    body["triggers"]["T-07"].update(trig)
    return body


def t07_result(body: dict, pnl: str):
    """T-07's result without asserting it was checked (an OFF trigger is skipped)."""
    state = pe.StrategyState(expiry_kind="weekly", days_left=7, hhmm="11:00", pnl=D(pnl), max_profit=MAX_PROFIT,
                             prices_fresh=True, spot=D("24000"), stops=None)
    ev = pe.evaluate(body, state, None, None, gap_until="09:30")
    return next((r for r in ev.results if r.rule_id == "T-07"), None)


async def test_t07_off_with_a_typed_target_flags_at_the_target(monkeypatch):
    body = (await resolved(monkeypatch, plan_body_off("1", on=False))).body
    assert body["triggers"]["T-07"]["on"] is True
    got = t07_result(body, "48.75")
    assert isinstance(got, pe.Flag) and got.threshold == D("1")


async def test_t07_off_with_a_target_equal_to_the_playbook_stays_silent(monkeypatch):
    body = (await resolved(monkeypatch, plan_body_off("50", on=False))).body
    assert body["triggers"]["T-07"]["on"] is False
    got = t07_result(body, "2000")  # 72 % of max profit, still no flag: the playbook has it off
    assert isinstance(got, pe.NotChecked) and got.code == "adjust_trigger_switched_off"


@pytest.mark.parametrize("raw", ["", "abc", "0", "-5", "101", None, 7])
async def test_t07_off_with_an_unusable_target_stays_off(monkeypatch, raw):
    body = (await resolved(monkeypatch, plan_body_off(raw, on=False))).body
    assert body["triggers"]["T-07"]["on"] is False


async def test_t07_with_no_on_key_and_a_typed_target_does_not_crash(monkeypatch):
    plan = plan_body("1")
    del plan["triggers"]["T-07"]["on"]
    assert (await resolved(monkeypatch, plan)).body["triggers"]["T-07"]["on"] is True


async def test_t07_missing_from_the_playbook_is_left_alone(monkeypatch):
    plan = plan_body("1")
    del plan["triggers"]["T-07"]
    assert "T-07" not in (await resolved(monkeypatch, plan)).body["triggers"]


async def test_plan_sheet_path_reads_the_target_through_triggers_of(monkeypatch):
    """routes/adjustment_plan.py:399 builds Resolved("plan", with_plan_target(body)) and hands it to triggers_of."""
    from ofo_app import settings_in_force
    res = check.Resolved("plan", check.with_plan_target(plan_body_off("1", on=False)), 3, None, False,
                         saved_before_adr247=False)
    trig = next(t for t in settings_in_force.triggers_of(res)[0] if t.id == "T-07")
    assert trig.on is True and trig.weekly[0] == D("1") and trig.weekly[-1] == D("1")


# --- item C: the alert line names the limit used and the basis (ADR-294) ---

def line(threshold, trigger="T-07", unit="%"):
    return check.condition_line(trigger, "Profit reaches this % of max profit", unit, "1.7700", threshold)


def test_t07_line_names_the_limit_and_before_charges():
    assert line("1.0000") == "Profit reaches this % of max profit: 1.7700 % before charges (rule 1.0000 %)"


def test_t07_line_with_the_playbook_value_has_the_same_sentence():
    assert line("50.0000") == "Profit reaches this % of max profit: 1.7700 % before charges (rule 50.0000 %)"


@pytest.mark.parametrize("bad", ["abc", "", "NaN", "Infinity"])
def test_t07_line_without_a_number_makes_no_before_charges_claim(bad):
    assert "before charges" not in str(line(bad))


def test_other_triggers_keep_their_line():
    assert "before charges" not in str(line("0.5000", trigger="T-01"))


async def test_t07_on_stays_on_with_an_equal_target(monkeypatch):
    assert (await resolved(monkeypatch, plan_body("50"))).body["triggers"]["T-07"]["on"] is True
