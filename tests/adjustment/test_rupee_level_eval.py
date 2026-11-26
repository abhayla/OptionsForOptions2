"""ADR-330 (5): a rupee level is evaluated like every other plan level: a hit is a Flag (an alert), nothing exits.

Real case: loss stop Rs 400 on the ADJ-01 trade; pnl -400.00 flags ``plan.rupee_loss``, -399.95 does not, no pnl is not
checked (never a pass), a level typed unreadable is not checked.
Spec basis: ADR-330 (5) and its Q3 answer (whole trade, before charges).
"""
from __future__ import annotations

import copy
from dataclasses import replace
from decimal import Decimal

import pytest
from ofo.adjustment import stop_lines as sl
from ofo.adjustment.playbook_eval import Flag, NotChecked
from ofo.alerts import allowed_answers, is_actionable, kind_of
from test_playbook_eval import _stops, body_of, evaluate, load, state_of

D = Decimal


def _run(guards: dict, pnl):
    sc = load("ADJ-01")
    body = copy.deepcopy(body_of(sc))
    body.setdefault("guards", {}).update(guards)
    return evaluate(body, replace(state_of(sc), pnl=pnl), {}, None)


def _only(ev, rid):
    return [r for r in ev.results if r.rule_id == rid]


def test_loss_level_hit_is_one_flag_of_kind_plan_rupee_loss():
    [f] = _only(_run({sl.RUPEE_LOSS_KEY: "400"}, D("-400.00")), sl.RUPEE_LOSS_RULE)
    assert isinstance(f, Flag) and (f.value, f.threshold, f.cmp) == (D("400.00"), D("400"), "ge")
    assert kind_of(f.trigger_id) == "plan_rupee_loss" and is_actionable("plan_rupee_loss")
    assert allowed_answers("plan_rupee_loss") == ("exit", "continue")  # the user decides; nothing exits by itself


def test_loss_level_one_paisa_short_is_no_flag():
    ev = _run({sl.RUPEE_LOSS_KEY: "400"}, D("-399.95"))
    assert _only(ev, sl.RUPEE_LOSS_RULE) == [] and sl.RUPEE_LOSS_RULE in ev.clear


def test_profit_level_hit_and_kind():
    [f] = _only(_run({sl.RUPEE_PROFIT_KEY: "1000"}, D("1000.00")), sl.RUPEE_PROFIT_RULE)
    assert isinstance(f, Flag) and kind_of(f.trigger_id) == "plan_rupee_profit"


def test_no_pnl_is_not_checked_never_a_pass():
    ev = _run({sl.RUPEE_LOSS_KEY: "400"}, None)
    r = _only(ev, sl.RUPEE_LOSS_RULE)
    assert r and all(isinstance(x, NotChecked) for x in r) and sl.RUPEE_LOSS_RULE not in ev.clear


@pytest.mark.parametrize("raw", ["0", "-5", "NaN", "abc", 400])
def test_unreadable_level_is_not_checked(raw):
    ev = _run({sl.RUPEE_LOSS_KEY: raw}, D("-9999"))
    [r] = _only(ev, sl.RUPEE_LOSS_RULE)
    assert isinstance(r, NotChecked) and r.code == sl.NOT_CHECKED_OTHER


@pytest.mark.parametrize("raw", ["", None])
def test_blank_or_absent_level_makes_no_rule(raw):
    ev = _run({sl.RUPEE_LOSS_KEY: raw, sl.RUPEE_PROFIT_KEY: raw}, D("-9999"))
    assert [r for r in ev.results if r.rule_id in (sl.RUPEE_LOSS_RULE, sl.RUPEE_PROFIT_RULE)] == []
    assert sl.RUPEE_LOSS_RULE not in ev.clear


def _one_stop_run(guards: dict, pnl, max_loss="2600", pct="10"):
    """The S-21 base (max loss 2,600) with T-06 left at a percent that a Rs 400 loss also passes (10 % = Rs 260)."""
    sc = load("ADJ-01")
    body = copy.deepcopy(body_of(sc))
    body.setdefault("guards", {}).update(guards)
    for kind in ("weekly", "monthly"):
        body["triggers"][sl.TRIGGER_MAX_LOSS][kind] = [pct if x not in (None, "") else x
                                                       for x in body["triggers"][sl.TRIGGER_MAX_LOSS][kind]]
    state = replace(state_of(sc), pnl=pnl, max_loss=D(max_loss), stop_max_loss=D(max_loss))
    return evaluate(body, replace(state, stops=_stops(body, state)), {}, None)


def _plan_loss_flags(ev):
    kinds = ("plan_loss_stop", "plan_rupee_loss")
    return [r for r in ev.results if isinstance(r, Flag) and kind_of(r.trigger_id) in kinds]


def test_rupee_stop_is_the_plans_only_stop_alert_not_a_second_one_from_t06():
    """ADR-330 (5)(a): ONE loss stop per plan. Typed in rupees, the T-06 percent line is not a second stop."""
    flags = _plan_loss_flags(_one_stop_run({sl.RUPEE_LOSS_KEY: "400"}, D("-400.00")))
    assert [kind_of(f.trigger_id) for f in flags] == ["plan_rupee_loss"]


def test_percent_stop_alone_still_fires_t06_once():
    flags = _plan_loss_flags(_one_stop_run({}, D("-400.00")))
    assert [kind_of(f.trigger_id) for f in flags] == ["plan_loss_stop"]


def test_rupee_stop_unreadable_keeps_t06_checking():
    flags = _plan_loss_flags(_one_stop_run({sl.RUPEE_LOSS_KEY: "abc"}, D("-400.00")))
    assert [kind_of(f.trigger_id) for f in flags] == ["plan_loss_stop"]


def test_f6_t06_in_a_mixed_rule_is_replaced_by_the_rupee_loss_never_dropped():
    """P4 review F6: {"all_of": ["T-06","T-07"]} must need BOTH the loss and the profit condition; dropping T-06 left
    T-07 alone, so the rule fired more often. With a profit and no loss of Rs 400 it does not fire."""
    sc = load("ADJ-01")
    body = copy.deepcopy(body_of(sc))
    body["rules"].append({"id": "R-X", "all_of": ["T-06", "T-07"]})
    body.setdefault("guards", {})[sl.RUPEE_LOSS_KEY] = "400"
    ev = evaluate(body, replace(state_of(sc), pnl=D("100000")), {}, None)
    mine = _only(ev, "R-X")
    assert mine and not any(isinstance(r, Flag) for r in mine)
    assert "R-X" not in [r.rule_id for r in ev.results if isinstance(r, Flag)]
