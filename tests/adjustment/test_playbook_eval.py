# ruff: noqa: PLR2004, E501 - stage boundaries and scenario numbers are the point; one state input per line
"""playbook_eval against the whole scenario library (GC-ADJ2 step 1B core) plus F-71 memory, answer states and the
body guards. The scenario dict never reaches the module: ``state_of`` turns its numbers into a StrategyState here.

Spec basis: docs/design/playbook-body-v1.md; REQ-159 AC-1..AC-3; REQ-158 AC-2 + ADR-216 (ic approved, T-19 1x);
REQ-045 AC-3; REQ-160 AC-3; spec/findings.md F-71.
"""
from __future__ import annotations

import copy
import datetime
from dataclasses import replace
from decimal import ROUND_HALF_EVEN, Decimal

import pytest
from ofo.adjustment.playbook_eval import (
    ALREADY_TRUE,
    T14_PENDING,
    AlreadyTrue,
    Flag,
    NotChecked,
    ShortLeg,
    StrategyState,
    body_from_fixture,
    evaluate,
    reason_text,
    validate_body,
)
from ofo.engine import Action, Instrument, Leg, Strategy
from test_adjust_scenarios import IDS, PLAYBOOKS, load

D = Decimal
F71 = "ADJ-42"
Q4 = D("0.0001")


def _row(sc: dict, leg: dict) -> dict:
    if leg["type"] == "FUT":
        return sc["market"]["futures"][0]
    for c in sc["market"]["chains"]:
        if c["expiry"] == leg["expiry"]:
            for r in c["rows"]:
                if r["type"] == leg["type"] and D(r["strike"]) == D(leg["strike"]):
                    return r
    raise AssertionError(leg)


def _dec(text):
    return None if text is None else D(text)


def body_of(sc: dict) -> dict:
    """The family's body with the strategy plan's overrides applied (precedence plan > playbook, ADR-214 (4b))."""
    body = body_from_fixture(PLAYBOOKS, sc["family"])
    over = sc["playbook_ref"]["plan_overrides"]
    for tid, vals in over.get("triggers", {}).items():
        body["triggers"][tid].update(vals)
    for tid in over.get("triggers_on", []):
        if not body["triggers"][tid]["on"]:
            body["triggers"][tid]["on"] = True
            body["rules"].append({"id": tid, "any_of": [tid]})
    if "max_adjustments" in over:
        body["guards"]["max_adjustments"] = over["max_adjustments"]
    return body


def state_of(sc: dict) -> StrategyState:
    """A StrategyState from the scenario's own numbers (the same reads as tests/test_adjust_scenarios.py)."""
    clock = datetime.datetime.fromisoformat(sc["clock"]["ist"])
    hhmm = clock.strftime("%H:%M")
    rule = next((r for r in PLAYBOOKS["families"][sc["family"]].get("day_rules", PLAYBOOKS["day_rules"])
                 if r["when"] == "expiry" and r["on"] and "percent" in r), None)  # the family's tighten rule, if on
    tighten = D(rule["percent"]) if rule and clock.date().isoformat() == sc["expiry"] and hhmm >= rule["at"] else None
    legs = sc["position"]["legs"]
    unpriced = {q["tradingsymbol"] for q in sc["broker"]["quote"]["legs"] if q["state"] != "stated"}
    sign = {"BUY": 1, "SELL": -1}
    booked = D(sc["position"]["booked_pnl"])
    priced = not unpriced

    def ltp(x):
        return None if x["tradingsymbol"] in unpriced else D(_row(sc, x)["ltp"])
    shorts = tuple(ShortLeg(D(x["strike"]), abs(D(_row(sc, x)["delta"])), ltp(x))
                   for x in legs if x["side"] == "SELL" and x["type"] != "FUT")
    pnl = booked + sum(sign[x["side"]] * x["quantity"] * (ltp(x) - D(x["entry"])) for x in legs) if priced else None
    options = [x for x in legs if x["type"] != "FUT"]
    left = sum(-sign[x["side"]] * x["quantity"] * ltp(x) for x in options) if priced and options else None
    cost = sum((D(_row(sc, x)["ask"]) - D(_row(sc, x)["bid"])) * x["quantity"] + 40 for x in options) if options else None
    whole = sc["expected"]["at_expiry_whole_trade"]
    spot = None if sc["data_state"]["spot_source"] == "none" else D(sc["market"]["spot"])
    expiry_pnl = None
    if whole["exact"] and spot is not None:
        strat = Strategy(tuple(Leg(Action(x["side"]), Instrument(x["type"]), _dec(x["strike"]),
                                   datetime.date.fromisoformat(x["expiry"]), x["quantity"], D(x["entry"])) for x in legs))
        expiry_pnl = strat.expiry_pnl_at(spot) + booked
    margin = sc["broker"]["margin"]
    return StrategyState(
        expiry_kind=sc["expiry_kind"], days_left=sc["dte"], hhmm=hhmm, spot=spot, shorts=shorts, pnl=pnl,
        max_loss=(whole["max_loss"] if whole["max_loss"] == "UNLIMITED" else D(whole["max_loss"])) if whole["exact"] else None,
        max_profit=(whole["max_profit"] if whole["max_profit"] == "UNLIMITED" else D(whole["max_profit"])) if whole["exact"] else None,
        margin=D(margin["value"]) if margin["state"] == "stated" else None, premium_left=left, adjustment_cost=cost,
        atm_iv=D(sc["market"]["atm_iv"]), entry_atm_iv=D(sc["position"]["entry"]["atm_iv"]),
        day_open=_dec(sc["market"]["day_open"]), prev_close=_dec(sc["market"]["prev_close"]),
        adjustments_used=sc["position"]["adjustments_used"], expiry_pnl_at_spot=expiry_pnl, tighten_percent=tighten,
        prices_fresh=sc["data_state"]["prices"] == "fresh")


def entry_of(sc: dict) -> StrategyState:
    """The entry state the scenario carries: entry clock, entry spot, the shorts' strikes; nothing else is known."""
    entry = datetime.datetime.fromisoformat(sc["position"]["entry"]["clock"])
    shorts = tuple(ShortLeg(D(x["strike"]), None, None)
                   for x in sc["position"]["legs"] if x["side"] == "SELL" and x["type"] != "FUT")
    return StrategyState(expiry_kind=sc["expiry_kind"], days_left=(datetime.date.fromisoformat(sc["expiry"]) - entry.date()).days,
                         hhmm=entry.strftime("%H:%M"), spot=D(sc["position"]["entry"]["spot"]), shorts=shorts,
                         prices_fresh=True)


def flags(ev) -> dict[str, Flag]:
    return {r.trigger_id: r for r in ev.results if isinstance(r, Flag)}


def _shown(value) -> str:
    return value if isinstance(value, str) else format(value.quantize(Q4, rounding=ROUND_HALF_EVEN), "f")


def _same(got, want: str) -> bool:
    if isinstance(got, str):
        return got == want
    return D(want) == got if "." not in want or len(want.split(".")[1]) != 4 else _shown(got) == want


# ---- core: every scenario ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("sid", IDS)
def test_every_scenario_flags_exactly_the_expected_triggers(sid):
    sc = load(sid)
    exp = sc["expected"]
    body, state = body_of(sc), state_of(sc)
    ev = evaluate(body, state, {}, entry_of(sc))
    assert (ev.stage_name, ev.stage_index) == (exp["stage"], exp["stage_index"])
    got = flags(ev)
    if not exp["suggest"]:
        assert not got and ev.withheld
        assert all(isinstance(r, NotChecked) for r in ev.results)
        return
    assert set(got) == {f["id"] for f in exp["triggers_fired"]}
    for f in exp["triggers_fired"]:
        assert _same(got[f["id"]].value, f["value"]), (f, got[f["id"]])
        assert _same(got[f["id"]].threshold, f["limit"]), (f, got[f["id"]])
    already = {r.trigger_id for r in ev.results if isinstance(r, AlreadyTrue)}
    assert already == set(exp.get("already_true_at_entry", []))
    # with no entry state nothing held at entry: the level answer is fired + already true (F-71 is the only difference)
    level = flags(evaluate(body, state, {}, None))
    assert set(level) == set(got) | already


def test_adj01_flags_nothing():
    sc = load("ADJ-01")
    ev = evaluate(body_of(sc), state_of(sc), {}, None)
    assert not flags(ev) and not [r for r in ev.results if isinstance(r, AlreadyTrue)]


def test_t14_is_not_checked_with_the_generator_reason():
    sc = load("ADJ-01")
    ev = evaluate(body_of(sc), state_of(sc), {}, None)
    t14 = [r for r in ev.results if r.trigger_id == "T-14"]
    assert t14 == [NotChecked("T-14", "T-14", T14_PENDING)]
    assert {"id": "T-14", "reason": reason_text(T14_PENDING)} in sc["expected"]["triggers_not_evaluated"]


def test_iron_condor_body_is_approved_with_t19_at_1x_and_others_draft():
    ic = body_from_fixture(PLAYBOOKS, "ic")
    assert ic["status"] == "approved"
    assert ic["triggers"]["T-19"]["weekly"] == ["1", "1", "1"] == ic["triggers"]["T-19"]["monthly"]
    strangle = body_from_fixture(PLAYBOOKS, "strangle")
    assert strangle["status"] == "draft" and strangle["triggers"]["T-19"]["weekly"] == ["2", "2", "2"]


# ---- F-71 memory -----------------------------------------------------------------------------------------------------
def _moved(state: StrategyState, spot: str) -> StrategyState:
    return StrategyState(**{**state.__dict__, "spot": D(spot)})


def test_f71_already_true_then_clear_then_flag():
    sc = load(F71)
    body, state, entry = body_of(sc), state_of(sc), entry_of(sc)
    short = D("23000")
    assert abs(short - state.spot) / state.spot * 100 == D("80") / D("22920") * 100  # 0.349% at entry and now
    first = evaluate(body, state, {}, entry)
    assert "T-01" not in flags(first)
    [held] = [r for r in first.results if isinstance(r, AlreadyTrue)]
    assert (held.rule_id, held.trigger_id, _shown(held.value), held.threshold) == ("T-01", "T-01", "0.3490", D("0.5"))
    assert first.memory["T-01"] == {"held_at_entry": True, "seen_clear": False}
    assert held.code == ALREADY_TRUE and reason_text(held.code) == "Already true when tracking started."
    # spot moves 1.0% past the short CE (235 / 23235 = 1.011%; the 22700 put is farther still)
    second = evaluate(body, _moved(state, "23235"), first.memory, entry)
    assert "T-01" not in flags(second) and "T-01" in second.clear
    assert second.memory["T-01"] == {"held_at_entry": True, "seen_clear": True}
    third = evaluate(body, _moved(state, "22920"), second.memory, entry)
    assert flags(third)["T-01"].threshold == D("0.5")
    assert not [r for r in third.results if isinstance(r, AlreadyTrue)]


def test_f71_held_and_never_cleared_never_flags_across_three_checks():
    sc = load(F71)
    body, state, entry = body_of(sc), state_of(sc), entry_of(sc)
    memory: dict = {}
    for spot in ("22920", "22930", "22910"):
        ev = evaluate(body, _moved(state, spot), memory, entry)
        assert "T-01" not in flags(ev)
        assert any(isinstance(r, AlreadyTrue) and r.rule_id == "T-01" for r in ev.results)
        memory = ev.memory


def test_f71_memory_is_not_mutated():
    sc = load(F71)
    memory = {"T-01": {"held_at_entry": True, "seen_clear": False}}
    before = copy.deepcopy(memory)
    evaluate(body_of(sc), _moved(state_of(sc), "23235"), memory, entry_of(sc))
    assert memory == before


def test_entry_without_a_computable_value_counts_as_not_held():
    sc = load(F71)
    no_spot = StrategyState(**{**entry_of(sc).__dict__, "spot": None})
    ev = evaluate(body_of(sc), state_of(sc), {}, no_spot)
    assert "T-01" in flags(ev) and ev.memory["T-01"]["held_at_entry"] is False


# ---- missing inputs ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("sid", ["ADJ-24b", "ADJ-19"])
def test_no_spot_or_stale_prices_never_flag(sid):
    sc = load(sid)
    ev = evaluate(body_of(sc), state_of(sc), {}, None)
    assert not flags(ev) and not ev.clear
    want = {"ADJ-24b": ("adjust_trigger_withheld_no_spot", "No suggestion: spot not available."),
            "ADJ-19": ("adjust_trigger_withheld_stale", "No suggestion: prices stale or missing.")}[sid]
    assert (ev.withheld, reason_text(ev.withheld)) == want
    assert {r.rule_id for r in ev.results} == {r["id"] for r in body_of(sc)["rules"]}


def test_unpriced_leg_is_not_checked_never_flagged_or_counted_clear():
    sc = load("ADJ-20c")  # long put wing quote "not found"
    ev = evaluate(body_of(sc), state_of(sc), {}, None)
    nc = {r.trigger_id: r.code for r in ev.results if isinstance(r, NotChecked)}
    for tid in ("T-06", "T-07", "T-16", "T-19"):
        assert tid in nc and nc[tid].startswith("adjust_trigger_missing_"), (tid, nc)
        assert tid not in flags(ev) and tid not in ev.clear


def test_unpriced_short_is_not_checked_for_t09():
    sc = load("ADJ-01")
    s = state_of(sc)
    s = StrategyState(**{**s.__dict__, "shorts": (s.shorts[0], ShortLeg(s.shorts[1].strike, s.shorts[1].abs_delta, None))})
    ev = evaluate(body_of(sc), s, {}, None)
    assert NotChecked("T-09", "T-09", "adjust_trigger_missing_short_price") in ev.results


@pytest.mark.parametrize(("field", "value", "tid", "code", "text"), [
    ("margin", None, "T-16", "missing_margin", "Margin not available."),
    ("margin", D(0), "T-16", "margin_not_positive", "Margin not positive."),
    ("adjustment_cost", D(0), "T-19", "cost_not_positive", "Adjustment cost not positive."),
    ("premium_left", D(-1), "T-19", "net_long_premium", "No premium to earn (net long premium)."),
    ("atm_iv", None, "T-11", "missing_atm_iv", "ATM IV not available."),
    ("adjustments_used", None, "T-18", "missing_adjustments_used", "Adjustments used not available."),
    ("expiry_pnl_at_spot", None, "T-02", "missing_expiry_pnl", "Expiry P&L at spot not available (multi-expiry: no exact breakeven)."),
    ("max_loss", "UNLIMITED", "T-06", "max_loss_not_finite", "Max loss not finite (unlimited or multi-expiry)."),
    ("max_loss", D(0), "T-06", "max_loss_not_finite", "Max loss not finite (unlimited or multi-expiry)."),
    ("pnl", None, "T-07", "missing_pnl", "P&L not available (a leg unpriced)."),
    ("shorts", (), "T-01", "no_short_leg", "No short leg."),
    ("shorts", (), "T-03", "no_short_leg", "No short leg."),
    ("hhmm", None, "T-10b", "missing_clock", "Clock time not available."),
    ("days_left", None, "T-01", "missing_days_left", "Days left not available."),
])
def test_each_missing_input_is_not_checked_with_its_reason(field, value, tid, code, text):
    sc = load("ADJ-14")  # last day: T-10b has a value
    s = StrategyState(**{**state_of(sc).__dict__, field: value})
    ev = evaluate(body_of(sc), s, {}, None)
    assert NotChecked(tid, tid, "adjust_trigger_" + code) in ev.results
    assert reason_text("adjust_trigger_" + code) == text


def test_no_stage_covers_the_days_left():
    sc = load("ADJ-14")
    ev = evaluate(body_of(sc), StrategyState(**{**state_of(sc).__dict__, "days_left": -1}), {}, None)
    nc = next(r for r in ev.results if r.trigger_id == "T-03")
    assert (nc.code, nc.slots) == ("adjust_trigger_no_stage", (("days", -1),))
    assert reason_text(nc.code, nc.slots) == "No stage covers -1 days left."


def test_no_value_in_the_stage_is_not_checked():
    sc = load("ADJ-01")  # Early: T-10b has ""
    ev = evaluate(body_of(sc), state_of(sc), {}, None)
    assert NotChecked("T-10b", "T-10b", "adjust_trigger_no_stage_value") in ev.results
    assert reason_text("adjust_trigger_no_stage_value") == "No value in this stage."


def test_two_shorts_t01_uses_the_nearest_and_t03_the_largest_delta():
    sc = load("ADJ-01")
    s = StrategyState(**{**state_of(sc).__dict__, "spot": D("23000"),
                         "shorts": (ShortLeg(D("22900"), D("0.10"), D(10)), ShortLeg(D("23100"), D("0.45"), D(10)),
                                    ShortLeg(D("22950"), D("0.20"), D(10)))})
    got = flags(evaluate(body_of(sc), s, {}, None))
    assert _shown(got["T-01"].value) == "0.2174" and got["T-03"].value == D("0.45")  # 50 / 23000, not 100 / 23000


# ---- rules, comparison, body guards ------------------------------------------------------------------------------------
def _calm():
    sc = load("ADJ-01")
    return body_of(sc), state_of(sc)


def test_all_of_rule():
    body, s = _calm()
    body["rules"] = [{"id": "R-1", "all_of": ["T-01", "T-11"]}]
    near = StrategyState(**{**s.__dict__, "spot": D("23400")})  # 0.21% from the 23450 short: T-01 fires
    assert not flags(evaluate(body, near, {}, None))  # T-11 does not fire
    both = StrategyState(**{**near.__dict__, "atm_iv": D("0.20")})
    ev = evaluate(body, both, {}, None)
    assert [r.rule_id for r in ev.results if isinstance(r, Flag)] == ["R-1"]
    assert {h.trigger_id for h in ev.results[0].members} == {"T-01", "T-11"}
    one_missing = StrategyState(**{**both.__dict__, "entry_atm_iv": None})
    ev = evaluate(body, one_missing, {}, None)
    assert [type(r) for r in ev.results] == [NotChecked] and ev.results[0].rule_id == "R-1"


def test_any_of_rule_fires_when_one_member_fires():
    body, s = _calm()
    body["rules"] = [{"id": "R-2", "any_of": ["T-11", "T-01"]}]
    ev = evaluate(body, StrategyState(**{**s.__dict__, "spot": D("23400")}), {}, None)
    assert [(r.rule_id, r.trigger_id) for r in ev.results] == [("R-2", "T-01")]


@pytest.mark.parametrize("limit", ["0.5", "0.50"])
def test_value_equal_to_the_limit_flags(limit):
    body, s = _calm()
    body["triggers"]["T-01"]["weekly"] = [limit, limit, limit]
    s = StrategyState(**{**s.__dict__, "spot": D("23000"), "shorts": (ShortLeg(D("23115"), D("0.1"), D(10)),)})
    assert flags(evaluate(body, s, {}, None))["T-01"].value == D("0.5")  # 115 / 23000 = 0.5% exactly


def test_just_outside_the_limit_does_not_flag():
    body, s = _calm()
    body["triggers"]["T-01"]["weekly"] = ["0.5", "0.5", "0.5"]
    s = StrategyState(**{**s.__dict__, "spot": D("23000"), "shorts": (ShortLeg(D("23115.05"), D("0.1"), D(10)),)})
    assert "T-01" not in flags(evaluate(body, s, {}, None))


def test_stage_list_length_mismatch_is_refused():
    body, _s = _calm()
    body["triggers"]["T-03"]["weekly"] = ["0.30", "0.35"]
    with pytest.raises(ValueError, match="T-03"):
        validate_body(body)


@pytest.mark.parametrize("where", ["value", "guard", "stage"])
def test_float_anywhere_is_refused(where):
    body, s = _calm()
    if where == "value":
        body["triggers"]["T-01"]["weekly"][0] = 0.75
    elif where == "guard":
        body["guards"]["profit_target_pct_of_max_profit"] = 50.0
    else:
        body["stages"]["weekly"][0]["from"] = 5.0
    with pytest.raises(ValueError, match="float"):
        evaluate(body, s, {}, None)


def test_unknown_trigger_is_not_checked_never_ignored():
    body, s = _calm()
    body["rules"].append({"id": "R-9", "any_of": ["T-99"]})
    body["triggers"]["T-98"] = {"on": True, "cmp": "ge", "data": "ok", "weekly": ["1", "1", "1"], "monthly": None}
    body["rules"].append({"id": "R-8", "any_of": ["T-98"]})
    ev = evaluate(body, s, {}, None)
    assert NotChecked("R-9", "T-99", "adjust_trigger_unknown") in ev.results
    assert NotChecked("R-8", "T-98", "adjust_trigger_not_evaluated") in ev.results
    assert reason_text("adjust_trigger_unknown") == "Unknown trigger: it is not checked."
    assert reason_text("adjust_trigger_not_evaluated") == "This trigger is not checked in this version."


def test_tighten_applies_to_tightened_triggers_only():
    sc = load("ADJ-08")  # expiry day 13:30; the iron condor has no tighten rule on (ADR-216), so state the 20% itself
    assert state_of(sc).tighten_percent is None
    ev = evaluate(body_of(sc), replace(state_of(sc), tighten_percent=D(20)), {}, None)
    assert flags(ev)["T-01"].threshold == D("0.36")  # 0.3 x 1.2
    assert flags(ev)["T-09"].threshold == D("2.4")


@pytest.mark.parametrize(("kind", "days", "stage"), [
    ("weekly", 5, "Early"), ("weekly", 4, "Middle"), ("weekly", 2, "Middle"), ("weekly", 1, "Last day"),
    ("weekly", 0, "Last day"), ("monthly", 10, "Early"), ("monthly", 9, "Middle"), ("monthly", 3, "Middle"),
    ("monthly", 2, "Last 2 days"), ("monthly", 0, "Last 2 days"),
])
def test_stage_boundaries(kind, days, stage):
    body, _s = _calm()
    ev = evaluate(body, StrategyState(expiry_kind=kind, days_left=days, prices_fresh=True, spot=D(23000)), {}, None)
    assert ev.stage_name == stage
