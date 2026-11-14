# ruff: noqa: E501, PLR0913, PLR2004, PLC0415, RUF059
"""GC-ICFIX u113 round 3 (ADR-252, ADR-295, ADR-304 pending): ``playbook_eval.limits_now`` is the ONE statement of the limit a rule
acts on for this trade, taken from the evaluator's own path; ``evaluate()`` carries it (``Evaluation.limits``) and the route sends
it. Real rows of ``system_playbooks.json`` (iron condor T-07 weekly 50/50/80, monthly 50/50/75, T-06 50/50/40, strangle day rule
"tighten 20 % from 13:00"). No database.

Class: every screen line that states a limit must be the limit the evaluator compares against at that moment, for every strategy
type, stage, tightening, finite/unlimited max loss, and rule memory.
"""
from __future__ import annotations

import copy
import datetime
import json
import pathlib
from decimal import Decimal as D

import pytest
from ofo.adjustment import playbook_eval as pe
from ofo.adjustment import stop_lines as sl
from ofo.engine import adjust_money
from ofo.engine.metrics import UNLIMITED as ENGINE_UNLIMITED
from ofo.errors.explanations import render_explanation
from ofo_app import adjustment_check as check
from ofo_app import settings_in_force as sif
from ofo_app.routes import adjustment_check as route

SEED = pathlib.Path(__file__).resolve().parent.parent / "backend" / "ofo" / "adjustment" / "system_playbooks.json"
PLAYBOOKS = json.loads(SEED.read_text(encoding="utf-8"))["playbooks"]
BODIES = {e["strategy_type"]: e["body"] for e in PLAYBOOKS}
IC, STRANGLE = BODIES["ic"], BODIES["strangle"]
MAX_PROFIT, MAX_LOSS, CREDIT = D("2753"), D("23897.04"), D("8918")
KEY = "profit_target_pct_of_max_profit"
NOW = datetime.datetime(2026, 11, 13, 7, 35, tzinfo=datetime.UTC)
AS_OF_TEXT = render_explanation("check_as_of", time=NOW)


def days_of_stage(body, kind, stage):
    return next(d for d in range(40) if pe.stage_of(body, kind, d) == stage)


def run(body, *, kind="weekly", stage=0, days=None, hhmm="11:00", pnl="100", max_profit=MAX_PROFIT, max_loss=MAX_LOSS,
        credit=CREDIT, tighten=None, fresh=True, spot="24000", plan=False, before=False, memory=None, used=0):
    """(state, evaluation) over the resolved body and the stop lines the settings in force give it."""
    resolved = check.Resolved("plan" if plan else "system", check.with_plan_target(body) if plan else body, 1, None,
                              not plan, saved_before_adr247=before)
    days = days_of_stage(resolved.body, kind, stage) if days is None else days
    money_loss = ENGINE_UNLIMITED if max_loss == pe.UNLIMITED else max_loss
    stops = sif.stops_of(resolved, sif.MoneyInputs(money_loss, credit, None), sif.StageAt(kind, days))
    state = pe.StrategyState(expiry_kind=kind, days_left=days, hhmm=hhmm, spot=None if spot is None else D(spot),
                             pnl=None if pnl is None else D(pnl), max_profit=max_profit, max_loss=max_loss,
                             prices_fresh=fresh, tighten_percent=tighten, stops=stops, adjustments_used=used)
    return state, pe.evaluate(resolved.body, state, memory, None, gap_until="09:30")


def row(ev, rule_id):
    return next(x for x in ev.limits if x.rule_id == rule_id)


def result(ev, rule_id):
    return next(r for r in ev.results if r.rule_id == rule_id)


# --- the pair table: iron condor per stage, weekly and monthly -------------------------------------------------------------
@pytest.mark.parametrize(("kind", "target", "stop"), [("weekly", (50, 50, 80), (50, 50, 40)),
                                                      ("monthly", (50, 50, 75), (50, 50, 40))])
def test_iron_condor_target_and_stop_per_stage(kind, target, stop):
    for stage in range(3):
        state, ev = run(IC, kind=kind, stage=stage)
        assert row(ev, "T-07").threshold == D(target[stage]) and row(ev, "T-07").state == "checked"
        assert row(ev, "T-06").threshold == D(stop[stage]) and row(ev, "T-06").state == "checked"
        assert row(ev, "T-06").amount == adjust_money.stop_at_pct(MAX_LOSS, D(stop[stage]))
        assert row(ev, "T-07").later == tuple(D(x) for x in target[stage + 1:])
        assert pe.limits_now(IC, state) == tuple(ev.limits)  # the pure door gives the same rows


def test_a_plan_target_of_1_is_1_at_every_stage_and_90_is_80_on_the_last_day():
    for stage in range(3):
        _, ev = run(with_target(IC, "1"), stage=stage, plan=True)
        assert row(ev, "T-07").threshold == D(1)
    early = run(with_target(IC, "90"), stage=0, plan=True)[1]
    last = run(with_target(IC, "90"), stage=2, plan=True)[1]
    assert row(early, "T-07").threshold == D(90) and row(early, "T-07").later == (D(90), D(80))
    assert row(last, "T-07").threshold == D(80)


def test_a_plan_target_equal_to_the_playbook_early_value_is_50_on_the_last_day_with_its_sentence():
    for kind in ("weekly", "monthly"):
        _, ev = run(with_target(IC, "50"), kind=kind, stage=2, plan=True)
        assert row(ev, "T-07").threshold == D(50)
    assert texts(ev)["T-07"] == "Target: profit of 50 % of max profit, before charges"


def with_target(body, target):
    out = copy.deepcopy(body)
    out["guards"][KEY] = target
    return out


# --- the 2x-credit stop ---------------------------------------------------------------------------------------------------
def test_t06_off_keeps_the_credit_line_with_its_rupee_amount_and_t06_not_checked():
    body = copy.deepcopy(IC)
    body["triggers"]["T-06"]["on"] = False
    _, ev = run(body)
    credit = row(ev, sl.CREDIT_RULE)
    assert credit.amount == adjust_money.stop_at_multiple(CREDIT, D(2)) == D("17836.00") and credit.state == "checked"
    t06 = row(ev, "T-06")
    nc = result(ev, "T-06")
    assert t06.state == "not_checked" and t06.reason == nc.code and t06.threshold is None


def test_a_plan_saved_before_adr247_has_percent_lines_only():
    _, ev = run(IC, plan=True, before=True)
    assert {x.rule_id for x in ev.limits} == {"T-07", "T-06"}


# --- expiry-day tightening and unlimited max loss -------------------------------------------------------------------------
def test_strangle_on_expiry_day_before_and_after_the_tightening_time():
    before = run(STRANGLE, stage=2, hhmm="12:59", days=0)[1]
    assert (row(before, "T-07").threshold, row(before, "T-06").threshold) == (D(80), D(40))
    assert row(before, "T-07").tightened_by is None
    after = run(STRANGLE, stage=2, hhmm="13:00", days=0, tighten=D(20))[1]
    assert (row(after, "T-07").threshold, row(after, "T-06").threshold) == (D("64.0"), D("32.0"))
    assert row(after, "T-07").tightened_by == D(20) and row(after, "T-06").tightened_by == D(20)
    assert row(after, "T-06").amount == adjust_money.stop_at_pct(MAX_LOSS, D("32.0"))  # the fire point moves with it


def test_a_strangle_with_unlimited_max_loss_has_no_stop_to_compare():
    _, ev = run(STRANGLE, stage=0, max_loss=pe.UNLIMITED)
    t06 = row(ev, "T-06")
    assert t06.state == "not_checked" and t06.reason == result(ev, "T-06").code and "max_loss_not_finite" in t06.reason
    assert t06.amount is None


# --- the evaluator's own reasons ------------------------------------------------------------------------------------------
@pytest.mark.parametrize("edit", [{"fresh": False}, {"fresh": None}, {"spot": None}, {"pnl": None}])
def test_data_missing_rows_are_not_checked_with_the_evaluators_reason(edit):
    _, ev = run(IC, **edit)
    for rid in ("T-07", "T-06", sl.CREDIT_RULE):
        got, nc = row(ev, rid), result(ev, rid)
        assert got.state == "not_checked" and got.reason == nc.code


def test_already_true_after_an_adjustment():
    memory = {"T-07": {"held_at_entry": True, "seen_clear": False}}
    _, ev = run(IC, pnl="2000", memory=memory)  # 72.6 % of max profit
    assert isinstance(result(ev, "T-07"), pe.AlreadyTrue)
    assert row(ev, "T-07").state == "already_true" and row(ev, "T-07").threshold == D(50)


def test_a_flag_is_checked():
    _, ev = run(IC, pnl="2000")
    assert isinstance(result(ev, "T-07"), pe.Flag) and row(ev, "T-07").state == "checked"


# --- limits_now and the comparison can never disagree ----------------------------------------------------------------------
def test_threshold_equals_the_one_the_evaluator_compared_for_every_real_playbook_and_stage():
    seen = 0
    for stype, body in BODIES.items():
        for kind in ("weekly", "monthly"):
            for stage in range(len(body["stages"][kind])):
                if body["triggers"]["T-07"][kind][stage] == "":
                    continue
                state, ev = run(body, kind=kind, stage=stage, pnl="1")
                for v in ev.values:
                    if v.rule_id in ("T-07", "T-06"):
                        assert row(ev, v.rule_id).threshold == v.threshold, (stype, kind, stage, v.rule_id)
                        seen += 1
                    if v.rule_id == sl.CREDIT_RULE:
                        assert row(ev, v.rule_id).amount == v.threshold
    assert seen >= 40


# --- the reply carries it --------------------------------------------------------------------------------------------------
def test_a_reason_with_values_renders_in_the_reply():
    _, ev = run(IC, days=-1)  # no stage covers -1 days left: the reason names the days
    out = route.limits_out(ev.limits)
    assert out and all(x["state"] == "not_checked" and x["reason"] for x in out if x["rule_id"] == "T-07")


def test_the_route_sends_the_rows():
    _, ev = run(STRANGLE, stage=2, hhmm="13:00", days=0, tighten=D(20))
    out = route.limits_out(ev.limits)
    t07 = next(x for x in out if x["rule_id"] == "T-07")
    assert t07["threshold"] == D("64.0000") and t07["tightened_by"] == D("20.0000") and t07["state"] == "checked"
    assert t07["reason"] is None and t07["later"] == []
    _, ev = run(IC, pnl=None)
    assert next(x for x in route.limits_out(ev.limits) if x["rule_id"] == "T-07")["reason"] is not None
    route.AdjustmentCheckOut.model_validate({"strategy_id": 1, "as_of": NOW, "as_of_text": AS_OF_TEXT,
                                             "strategy_type": "ic", "type_name": None,
                                             "playbook": {"source": "system", "id": 1, "status": None, "draft": False},
                                             "stage": {"name": None, "index": None}, "withheld": None, "results": [],
                                             "limits": route.limits_out(ev.limits)})


# --- the sentence each row carries (ADR-304 (3): the card prints it, no glue text in the browser) ---------------------------
def texts(ev):
    return {x["rule_id"]: (None if x["text"] is None else str(x["text"])) for x in route.limits_out(ev.limits)}


def rupees(v):
    from ofo.engine.display import format_rupees
    return format_rupees(v)


def test_text_iron_condor_weekly_early_stage_target_stop_and_the_credit_line():
    got = texts(run(IC, stage=0)[1])
    assert got["T-07"] == "Target: profit of 50 % of max profit, before charges; 80 % nearer expiry"
    assert got["T-06"] == f"Stop: loss of 50 % of max loss ({rupees(D('11948.52'))}); 40 % nearer expiry"
    assert got[sl.CREDIT_RULE] == f"Stop: loss of 2 x credit ({rupees(D('17836.00'))}), whichever comes first"


def test_text_last_stage_has_no_later_note():
    got = texts(run(IC, stage=2)[1])
    assert got["T-07"] == "Target: profit of 80 % of max profit, before charges"
    assert got["T-06"] == f"Stop: loss of 40 % of max loss ({rupees(adjust_money.stop_at_pct(MAX_LOSS, D(40)))})"


def test_text_t06_off_says_not_checked_with_the_reason_and_no_number_and_the_credit_line_stands_alone():
    body = copy.deepcopy(IC)
    body["triggers"]["T-06"]["on"] = False
    _, ev = run(body)
    got = texts(ev)
    reason = next(x for x in route.limits_out(ev.limits) if x["rule_id"] == "T-06")["reason"].what_happened
    assert got["T-06"] == f"Stop: not being checked: {reason}"
    assert got[sl.CREDIT_RULE] == f"Stop: loss of 2 x credit ({rupees(D('17836.00'))})"  # no percent stop to race: no closing words


def test_text_a_plan_saved_before_adr247_has_no_credit_line_and_no_closing_words():
    got = texts(run(IC, plan=True, before=True)[1])
    assert set(got) == {"T-07", "T-06"} and "whichever" not in got["T-06"]


def test_text_strangle_expiry_day_tightened_by_20():
    got = texts(run(STRANGLE, stage=2, hhmm="13:00", days=0, tighten=D(20))[1])
    assert got["T-07"] == "Target: profit of 64 % of max profit, before charges; tightened by 20 % today"
    assert got["T-06"].startswith("Stop: loss of 32 % of max loss (") and got["T-06"].endswith("); tightened by 20 % today")
    assert rupees(adjust_money.stop_at_pct(MAX_LOSS, D("32.0"))) in got["T-06"]


def test_text_unlimited_max_loss_stop_is_not_checked_with_its_reason():
    _, ev = run(STRANGLE, stage=0, max_loss=pe.UNLIMITED)
    reason = next(x for x in route.limits_out(ev.limits) if x["rule_id"] == "T-06")["reason"].what_happened
    assert texts(ev)["T-06"] == f"Stop: not being checked: {reason}"


def test_text_a_not_checked_row_that_still_carries_numbers_prints_none_of_them():
    _, ev = run(IC, pnl="-30000")  # a loss larger than the max loss: inconsistent prices
    row_ = row(ev, "T-06")
    assert row_.state == "not_checked" and row_.threshold == D(50) and row_.amount == D("11948.52")
    text = texts(ev)["T-06"]
    assert text.startswith("Stop: not being checked: ") and not any(ch.isdigit() for ch in text.replace("2x", ""))


def test_text_already_true_keeps_the_limit_and_says_so_in_the_adr296_words():
    memory = {"T-07": {"held_at_entry": True, "seen_clear": False}}
    _, ev = run(IC, pnl="2000", memory=memory)
    text = texts(ev)["T-07"]
    assert text.startswith("Target: profit of 50 % of max profit, before charges") and text.endswith(
        "Already true: alerts after it clears and crosses again")


def test_text_an_unknown_state_or_a_checked_row_with_nothing_to_compare_has_no_text():
    for state, threshold in (("weird", D(50)), ("checked", None)):
        bad = pe.LimitNow("T-07", "T-07", threshold, None, (), None, state, None)
        assert route.limits_out((bad,))[0]["text"] is None


# --- GC-ICFIX u141-u143 (Issue 5): the read time, the stop warning's rupee sentence, "after adjustment N", an emptied Target ----
def test_u141_the_reply_carries_the_checks_own_time_in_both_forms_and_refuses_a_reply_without_it():


    assert AS_OF_TEXT == "As of 01:05:00 PM IST"
    body = {"strategy_id": 1, "strategy_type": None, "type_name": None, "playbook": {"source": "none", "id": None, "status": None, "draft": False},
            "stage": {"name": None, "index": None}, "withheld": None, "results": []}
    with pytest.raises(ValueError):
        route.AdjustmentCheckOut.model_validate(body)
    out = route.AdjustmentCheckOut.model_validate({**body, "as_of": NOW, "as_of_text": AS_OF_TEXT})
    assert out.as_of == NOW and out.as_of_text == "As of 01:05:00 PM IST"


def test_u143_an_already_true_row_carries_its_adjustment_number_and_the_decision_is_unchanged():
    memory = {"T-07": {"held_at_entry": True, "seen_clear": False}}
    _, ev = run(IC, pnl="2000", memory=memory, used=2)
    assert isinstance(result(ev, "T-07"), pe.AlreadyTrue) and result(ev, "T-07").after == 2
    assert row(ev, "T-07").state == "already_true" and row(ev, "T-07").after == 2
    out = route.limits_out(ev.limits)
    t07 = next(x for x in out if x["rule_id"] == "T-07")
    assert t07["after"] == 2
    assert t07["text"] == ("Target: profit of 50 % of max profit, before charges; 80 % nearer expiry. Already true after adjustment 2: "
                           "alerts after it clears and crosses again")
    _, entry = run(IC, pnl="2000", memory=memory, used=0)  # N not known (the entry): the generic sentence stays
    assert next(x for x in route.limits_out(entry.limits) if x["rule_id"] == "T-07")["after"] is None
    assert row(entry, "T-07").after == 0


def test_u142_a_fired_stop_states_the_loss_and_the_stop_line_in_rupees_and_percent_and_when_it_fired():
    state, ev = run(IC, pnl="-12000")
    flag = next(r for r in ev.results if isinstance(r, pe.Flag) and r.trigger_id == "T-06")
    at = {flag.rule_id: datetime.datetime(2026, 11, 13, 7, 28, tzinfo=datetime.UTC)}
    text = route.stop_text(flag, ev.limits, state.pnl, at)
    assert text == ("Stop reached: loss now \u20b912,000.00 (50.2154 % of max loss); stop line \u20b911,948.52 (50 % of max loss); "
                    "reached at 12:58 IST")
    assert route.stop_text(flag, ev.limits, state.pnl, {}) == text.removesuffix("; reached at 12:58 IST")  # no record yet: no time invented
    assert route.stop_text(flag, ev.limits, None, at) is None  # a figure missing: no sentence
    target = next(r for r in run(IC, pnl="2000")[1].results if isinstance(r, pe.Flag))
    assert route.stop_text(target, run(IC, pnl="2000")[1].limits, D("2000"), at) is None  # a target flag is not a stop


def test_u142_the_stop_sentence_follows_the_value_between_two_checks():
    texts_ = []
    for pnl in ("-12000", "-17000"):
        state, ev = run(IC, pnl=pnl)
        flag = next(r for r in ev.results if isinstance(r, pe.Flag) and r.trigger_id == "T-06")
        texts_.append(route.stop_text(flag, ev.limits, state.pnl, {}))
    assert texts_[0] != texts_[1] and "12,000.00" in texts_[0] and "17,000.00" in texts_[1]


def test_u145_an_emptied_target_has_its_own_sentence_and_reason_code_the_playbook_off_case_keeps_its_own():
    body = copy.deepcopy(IC)
    body.setdefault("guards", {})[KEY] = ""
    _, ev = run(body, plan=True)
    assert row(ev, "T-07").state == "not_checked"
    emptied = next(x for x in route.limits_out(ev.limits, True) if x["rule_id"] == "T-07")
    assert emptied["text"] == "Target: no target is set for this trade" and emptied["reason_code"] == "target_unset"
    other = next(x for x in route.limits_out(ev.limits) if x["rule_id"] == "T-07")
    assert other["reason_code"] is None and other["text"].startswith("Target: not being checked:")
    stop = next(x for x in route.limits_out(ev.limits, True) if x["rule_id"] != "T-07" and x["state"] != "not_checked")
    assert stop["reason_code"] is None
