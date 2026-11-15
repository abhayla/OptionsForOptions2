# ruff: noqa: E501, PLC0415
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


async def test_target_equal_to_the_playbook_early_value_applies_at_the_last_stage_too(monkeypatch):
    """Was (old): rewrites nothing, last stage kept 80 / 75. Now: 50 / 50 / 50 (weekly) and 50 / 50 / 50 (monthly)."""
    trig = (await resolved(monkeypatch, plan_body("50"))).body["triggers"]["T-07"]
    assert trig["weekly"] == ["50", "50", "50"] and trig["monthly"] == ["50", "50", "50"]


async def test_equal_target_flags_t07_at_60_percent_on_the_last_day(monkeypatch):
    body = (await resolved(monkeypatch, plan_body("50"))).body
    days = next(d for d in range(40) if pe.stage_of(body, "weekly", d) == len(body["triggers"]["T-07"]["weekly"]) - 1)
    state = pe.StrategyState(expiry_kind="weekly", days_left=days, hhmm="11:00", pnl=MAX_PROFIT * D("0.6"),
                             max_profit=MAX_PROFIT, prices_fresh=True, spot=D("24000"), stops=None)
    got = next((r for r in pe.evaluate(body, state, None, None, gap_until="09:30").results if r.rule_id == "T-07"), None)
    assert isinstance(got, pe.Flag) and got.threshold == D("50")  # before: 60 < 80, no flag


async def test_empty_and_absent_target_keep_their_meaning(monkeypatch):
    assert (await resolved(monkeypatch, plan_body(""))).body["triggers"]["T-07"]["on"] is False
    old = plan_body("1")
    del old["guards"][KEY]
    assert (await resolved(monkeypatch, old)).body["triggers"]["T-07"] == BODY["triggers"]["T-07"]


async def test_no_plan_follows_the_playbook(monkeypatch):
    body = (await resolved(monkeypatch, None)).body
    assert body["triggers"]["T-07"]["weekly"] == ["50", "50", "80"]
    assert t07(body, "48.75") is None


@pytest.mark.parametrize("raw", ["abc", "0", "-5", "101", None, 7])
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


async def test_t07_off_with_a_target_equal_to_the_playbook_switches_on(monkeypatch):
    """Round 3 (orchestrator decision): ANY usable Target switches T-07 on, the equal case included (was: stayed off)."""
    body = (await resolved(monkeypatch, plan_body_off("50", on=False))).body
    assert body["triggers"]["T-07"]["on"] is True
    got = t07_result(body, "2000")  # 72 % of max profit
    assert isinstance(got, pe.Flag) and got.threshold == D("50")


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


# --- ADR-305: an EMPTY Target (guard "") means no target alert for this trade; the box is what the app does ---

def limit_row(body: dict, pnl: str = "48.75"):
    state = pe.StrategyState(expiry_kind="weekly", days_left=7, hhmm="11:00", pnl=D(pnl), max_profit=MAX_PROFIT,
                             prices_fresh=True, spot=D("24000"), stops=None)
    return next(x for x in pe.evaluate(body, state, None, None, gap_until="09:30").limits if x.rule_id == "T-07")


async def test_empty_target_with_the_rule_on_switches_t07_off_for_this_trade(monkeypatch):
    body = (await resolved(monkeypatch, plan_body(""))).body
    assert body["triggers"]["T-07"]["on"] is False
    assert not isinstance(t07_result(body, "2000"), pe.Flag)  # 72 % of max profit: no alert
    row = limit_row(body)
    assert (row.state, row.threshold, row.reason) == ("not_checked", None, "adjust_trigger_switched_off")  # no number


async def test_empty_target_with_the_rule_off_stays_off(monkeypatch):
    body = (await resolved(monkeypatch, plan_body_off("", on=False))).body
    assert body["triggers"]["T-07"]["on"] is False and limit_row(body).state == "not_checked"


async def test_target_50_with_the_rule_off_is_checked_at_50(monkeypatch):
    row = limit_row((await resolved(monkeypatch, plan_body_off("50", on=False))).body, "2000")
    assert (row.state, row.threshold) == ("checked", D("50"))


async def test_absent_target_key_follows_the_rule_set(monkeypatch):
    body = plan_body("50")
    del body["guards"][KEY]
    assert limit_row((await resolved(monkeypatch, body)).body).state == "checked"  # rule on: as the playbook
    body = plan_body_off("50", on=False)
    del body["guards"][KEY]
    assert limit_row((await resolved(monkeypatch, body)).body).state == "not_checked"  # rule off: not checked


async def test_old_plan_with_the_copied_default_and_the_rule_off_still_alerts_at_it(monkeypatch):
    """ADR-305 cost, accepted: a plan saved before the decision holds "50" with the rule off and alerts at 50 until the
    user empties the box. Pinned so nobody 'fixes' it silently."""
    got = t07_result((await resolved(monkeypatch, plan_body_off("50", on=False))).body, "2000")
    assert isinstance(got, pe.Flag) and got.threshold == D("50")


def test_sheet_save_stores_empty_as_the_empty_guard_and_refuses_unusable_numbers():
    from ofo_app.routes import adjustment_plan as route
    out = route.with_overrides(plan_body("50"), route.PlanIn(playbook_id=3, target=""))
    assert out["guards"][KEY] == "" and route._values(out, False)["target"] is None
    assert route.with_overrides(plan_body("50"), route.PlanIn(playbook_id=3, target="50"))["guards"][KEY] == "50"
    for bad in ("0", "-5", "101", "abc", " "):
        with pytest.raises(Exception, match="target"):
            route.with_overrides(plan_body("50"), route.PlanIn(playbook_id=3, target=bad))


def test_editor_after_an_empty_save_shows_t07_off_and_an_unchanged_save_keeps_the_empty_guard():
    from ofo_app.routes import adjustment_plan as route
    base = plan_body("")
    shown = check.with_plan_target(base)
    assert shown["triggers"]["T-07"]["on"] is False  # what the editor shows = what the check acts on
    kept = route._rules_to_save(base, shown, True)
    assert kept["guards"][KEY] == "" and kept["triggers"]["T-07"] == base["triggers"]["T-07"]
    changed = copy.deepcopy(shown)
    changed["triggers"]["T-07"]["on"] = True  # a profit-trigger change saved in the editor wins: the Target guard goes
    assert KEY not in route._rules_to_save(base, changed, True)["guards"]


async def test_plan_card_limit_line_for_an_emptied_target_says_not_being_checked(monkeypatch):
    """ADR-305 (2): the card's limit line reads the rule check; no new sentence is needed (reason = the evaluator's)."""
    from ofo_app.routes import adjustment_check as route
    state = pe.StrategyState(expiry_kind="weekly", days_left=7, hhmm="11:00", pnl=D("48.75"), max_profit=MAX_PROFIT,
                             prices_fresh=True, spot=D("24000"), stops=None)
    ev = pe.evaluate((await resolved(monkeypatch, plan_body(""))).body, state, None, None, gap_until="09:30")
    text = next(x["text"] for x in route.limits_out(ev.limits) if x["rule_id"] == "T-07")
    assert str(text) == "Target: not being checked: This trigger is switched off in this playbook."
