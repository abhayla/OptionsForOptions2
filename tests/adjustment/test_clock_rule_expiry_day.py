"""ADR-310 (GC-ICFIX issue 22): a clock-time rule (T-10b) raises its alert only on a day its action can be taken.

Pure evaluator tests, no database. Built from ADJ-14 (iron condor, last stage, T-10b limit 14:30) with the day and clock
moved. Real case: trades 142 / 143 alerted 2 minutes after entry (clock 13:56 already past) on a non-expiry day, with no
action beside the alert (A-35 is built on expiry day only).

Spec basis: ADR-310 (2)-(5); ADR-283 (2) on expiry day; ADR-238 (5).
"""
from __future__ import annotations

import datetime
from dataclasses import replace

import pytest
from ofo.adjustment.playbook_eval import AlreadyTrue, Flag, NotChecked
from ofo.errors import render
from ofo.errors.explanations import PLAN_SHEET_LABEL_TEXT, PLAYBOOK_GUARD_LABEL_TEXT
from test_adjust_scenarios import load
from test_playbook_eval import body_of, entry_of, evaluate, state_of

EXPIRY = datetime.date(2026, 11, 3)
WAITING = "adjust_trigger_waits_expiry_day"


def _t10b(ev):
    return next((r for r in ev.results if r.trigger_id == "T-10b" and not r.rule_id.startswith("day.")), None)


def _run(*, today, hhmm, expiry=EXPIRY, entry_hhmm="13:56", entry_today=None):
    sc = load("ADJ-14")
    state = replace(state_of(sc), today=today, expiry=expiry, hhmm=hhmm, days_left=(EXPIRY - today).days)
    entry = replace(entry_of(sc), today=entry_today or today, expiry=expiry, hhmm=entry_hhmm)
    return evaluate(body_of(sc), state, {}, entry)


@pytest.mark.parametrize("hhmm", ["13:56", "15:00"])
def test_ordinary_day_before_or_after_the_time_waits_and_raises_no_alert(hhmm):
    r = _t10b(_run(today=datetime.date(2026, 11, 2), hhmm=hhmm))
    assert isinstance(r, NotChecked), r
    assert (r.code, dict(r.slots)) == (WAITING, {"day": EXPIRY})


def test_waiting_text_carries_the_day_in_full():
    assert "03 Nov 2026" in render(WAITING, day=EXPIRY).what_happened


def test_expiry_day_before_the_time_is_checked_and_clear():
    ev = _run(today=EXPIRY, hhmm="14:00")
    assert "T-10b" in ev.clear and not [r for r in ev.results if r.trigger_id == "T-10b"]


def test_expiry_day_after_the_time_flags():
    r = _t10b(_run(today=EXPIRY, hhmm="14:45"))
    assert isinstance(r, Flag) and (r.value, r.threshold) == ("14:45", "14:30")


def test_trade_entered_after_the_time_on_expiry_day_warns_never_already_true():
    r = _t10b(_run(today=EXPIRY, hhmm="14:45", entry_hhmm="14:40"))
    assert isinstance(r, Flag) and not isinstance(r, AlreadyTrue)


def test_unreadable_expiry_cannot_be_checked_with_its_reason():
    r = _t10b(_run(today=EXPIRY, hhmm="14:45", expiry=None))
    assert isinstance(r, NotChecked) and r.code == "adjust_trigger_missing_expiry"


def test_unreadable_today_cannot_be_checked_with_its_reason():
    sc = load("ADJ-14")
    ev = evaluate(body_of(sc), replace(state_of(sc), today=None), {}, None)
    r = _t10b(ev)
    assert isinstance(r, NotChecked) and r.code == "adjust_trigger_missing_today"


def test_one_definition_of_expiry_day():
    from ofo.adjustment.approaches import is_expiry_day

    assert is_expiry_day(EXPIRY, EXPIRY) is True
    assert is_expiry_day(datetime.date(2026, 11, 2), EXPIRY) is False
    assert is_expiry_day(None, EXPIRY) is False and is_expiry_day(EXPIRY, None) is False


def test_the_rule_is_named_time_exit_on_expiry_day_wherever_the_server_sends_it():
    assert PLAN_SHEET_LABEL_TEXT["time_exit"] == "Time exit (on expiry day)"
    assert PLAYBOOK_GUARD_LABEL_TEXT["time_exit"] == "Time exit (on expiry day)"
