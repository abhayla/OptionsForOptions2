"""The plan's own stop / target / time exit is never held by the strategy's daily alert cap (ADR-267 class, #200).

Real case 2026-11-27 (paper trade A-D #200, weekly style, cap 4): the plan's stop was typed in rupees, guards
``loss_stop_rupees`` "100" (a string), body status "draft", time exit 11:03, max adjustments 2, T-06 in the rules. The
loss passed Rs 100 from about 11:00 (162.5 on screen) to the exit at 11:23. T-03, T-14, T-01 and T-10b opened
records; the rupee loss stop opened none: the evaluator flagged it, the gate held it as "daily limit" because the
four automatic records had used the weekly cap of 4. The 09:55 % stop passed on another trade with the cap not used.
Spec basis: ADR-267 and its amendment (a level the user asked for is never the one suppressed; no crossing dropped),
ADR-330 (5)(a) (the rupee level IS the plan's one loss stop), ADR-237 (7) (the cap per strategy).
"""
from __future__ import annotations

import copy
from dataclasses import replace
from datetime import date, datetime, time
from decimal import Decimal

import pytest
from ofo.adjustment import alert_gate as ag
from ofo.adjustment import gate_readings
from ofo.adjustment import stop_lines as sl
from ofo.adjustment.cap_scope import cap_exempt, count_capped
from ofo.adjustment.playbook_eval import Flag
from test_playbook_eval import body_of, evaluate, load, state_of

NO_STOPS: frozenset[str] = frozenset()  # no plan read: the fixed loss-stop set only

D = Decimal
DAY = date(2026, 11, 27)
PRESET = replace(ag.WEEKLY, quiet_until=time(9, 30))  # the weekly preset as the PC ran it: cap 4
AUTO = ("T-03", "T-14", "T-01", "T-10b")  # the four records #200 opened
FULL = ("T-03", "T-14", "T-01", "T-02")  # four automatic records: the weekly cap of 4 is used
PLAN_EXITS = (sl.RUPEE_LOSS_RULE, sl.RUPEE_PROFIT_RULE, sl.TRIGGER_MAX_LOSS, sl.TRIGGER_MARGIN, sl.CREDIT_RULE)


def at(hhmm: str) -> datetime:
    return datetime.combine(DAY, time.fromisoformat(hhmm), tzinfo=ag.IST)


def _spec(rule_id: str) -> ag.RuleSpec:
    return ag.RuleSpec(rule_id, "ge", (D("100"),))


def _cross(rule_id: str, auto=FULL):
    """The automatic rules open at the 10:55 close (using the weekly cap of 4); ``rule_id`` crosses from 11:00."""
    state, events = ag.initial_state(), []
    steps = [("10:49:59", D("1"), D("1")), ("10:55:01", D("101"), D("1")), ("11:00:01", D("101"), D("1")),
             ("11:05:01", D("101"), D("162.5")), ("11:10:01", D("101"), D("162.5")),
             ("11:15:01", D("101"), D("162.5"))]
    for hhmm, auto_v, other_v in steps:
        readings = {r: (_spec(r), auto_v) for r in auto}
        readings[rule_id] = (_spec(rule_id), other_v)
        state, ev = ag.step(state, now=at(hhmm), preset=PRESET, readings=readings)
        events += ev
    return state, [e for e in events if e.rule_id == rule_id]


def _body_200() -> dict:
    """#200's plan body shape: status draft, the rupee stop as the STRING "100", a time exit, max adjustments 2."""
    body = copy.deepcopy(body_of(load("ADJ-01")))
    body["status"] = "draft"
    body.setdefault("guards", {}).update({sl.RUPEE_LOSS_KEY: "100", "max_adjustments": 2})
    assert any(r["id"] == sl.TRIGGER_MAX_LOSS for r in body["rules"])  # T-06 is in the rules, as on #200
    return body


def test_200_evaluator_flags_the_rupee_stop_at_loss_162_5():
    sc = load("ADJ-01")
    ev = evaluate(_body_200(), replace(state_of(sc), pnl=D("-162.5")), {}, None)
    [f] = [r for r in ev.results if r.rule_id == sl.RUPEE_LOSS_RULE]
    assert isinstance(f, Flag) and (f.value, f.threshold, f.cmp) == (D("162.5"), D("100"), "ge")
    assert not [r for r in ev.results if r.rule_id == sl.TRIGGER_MAX_LOSS]  # one loss stop, not a second T-06
    spec, value = gate_readings.readings(ev, stops=NO_STOPS)[sl.RUPEE_LOSS_RULE]
    assert (spec.cmp, spec.ladder, value) == ("ge", (D("100"),), D("162.5"))


def test_200_rupee_stop_opens_after_t03_t14_t01_and_the_time_exit():
    state, got = _cross(sl.RUPEE_LOSS_RULE, auto=AUTO)
    assert [type(e) for e in got] == [ag.Opened] and got[0].value == D("162.5")
    assert state.opened_today == 3  # noqa: PLR2004 - T-10b is the plan's time exit: not counted


@pytest.mark.parametrize("rule_id", (*PLAN_EXITS, sl.TRIGGER_TIME_EXIT))
def test_plan_exit_opens_when_the_cap_is_used_and_is_not_counted(rule_id):
    state, got = _cross(rule_id)
    assert [type(e) for e in got] == [ag.Opened] and got[0].value == D("162.5")
    assert state.opened_today == len(FULL)


@pytest.mark.parametrize("rule_id", ["T-03", "T-02", "sit.S-03", "plan.other", "T-06b"])
def test_automatic_rule_is_still_held_by_the_cap(rule_id):
    _state, got = _cross(rule_id, auto=("T-01", "T-09", "T-13", "T-14"))
    assert [(type(e), e.reason) for e in got] == [(ag.Held, ag.HELD_DAILY_LIMIT)]


def test_restore_counts_no_plan_exit_against_the_cap():
    assert count_capped(["T-03", "T-14", "T-01", sl.TRIGGER_TIME_EXIT, sl.RUPEE_LOSS_RULE, "T-06"], stops=NO_STOPS) == 3  # noqa: PLR2004
    assert all(cap_exempt(r) for r in (*PLAN_EXITS, sl.TRIGGER_TIME_EXIT))
