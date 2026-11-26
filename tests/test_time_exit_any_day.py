"""ADR-330 (7): a plan's time exit can be set for any trading day and time; blank date = expiry day (Q9).

Pure tests, no database. Real case: trade opened 25 Nov 2026, legs expire 1 Dec 2026, time exit 15:15 on 25 Nov ->
the check is met at 15:15 IST that day (before this, it waited for expiry day). Nothing exits by itself: the check
only flags the rule.

Spec basis: ADR-330 (7) and its Q9 answer; SPEC CHANGE to ADR-310 (2).
"""
from __future__ import annotations

import datetime
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "adjustment"))  # the evaluator tests' own builders
from ofo.adjustment.playbook_eval import Flag
from test_adjust_scenarios import load
from test_playbook_eval import body_of, entry_of, evaluate, state_of

OPENED = datetime.date(2026, 11, 25)
EXPIRY = datetime.date(2026, 12, 1)


def _t10b(ev):
    return next((r for r in ev.results if r.trigger_id == "T-10b" and not r.rule_id.startswith("day.")), None)


def _run(*, today, hhmm, time_exit, expiry=EXPIRY):
    sc = load("ADJ-14")
    body = body_of(sc)
    body = {**body, "guards": {**body.get("guards", {}), "time_exit": time_exit}}
    state = replace(state_of(sc), today=today, expiry=expiry, hhmm=hhmm, days_left=(expiry - today).days)
    entry = replace(entry_of(sc), today=OPENED, expiry=expiry, hhmm="10:00")
    return evaluate(body, state, {}, entry)


def _on(day):
    return {"at": "15:15", "on": day}


def test_real_case_15_15_today():
    r = _t10b(_run(today=OPENED, hhmm="15:15", time_exit=_on("2026-11-25")))
    assert isinstance(r, Flag) and (r.value, r.threshold) == ("15:15", "15:15")


def test_on_a_date_before_the_time_is_not_met():
    ev = _run(today=OPENED, hhmm="15:14", time_exit=_on("2026-11-25"))
    assert not isinstance(_t10b(ev), Flag) and "T-10b" in ev.clear


@pytest.mark.parametrize("hhmm", ["15:16", "15:29"])
def test_after_the_time_same_day_stays_met(hhmm):
    r = _t10b(_run(today=OPENED, hhmm=hhmm, time_exit=_on("2026-11-25")))
    assert isinstance(r, Flag) and r.threshold == "15:15"


def test_next_day_after_the_date_passed_is_not_met():
    ev = _run(today=datetime.date(2026, 11, 26), hhmm="15:20", time_exit=_on("2026-11-25"))
    assert not isinstance(_t10b(ev), Flag)


def test_a_date_before_its_day_is_not_met_even_after_the_time():
    ev = _run(today=OPENED, hhmm="15:20", time_exit=_on("2026-11-27"))
    assert not isinstance(_t10b(ev), Flag)


def test_on_expiry_is_unchanged():
    ev = _run(today=OPENED, hhmm="15:20", time_exit={"at": "15:15", "on": "expiry"})
    assert not isinstance(_t10b(ev), Flag)  # waits for expiry day, as before
    r = _t10b(_run(today=EXPIRY, hhmm="15:20", time_exit={"at": "15:15", "on": "expiry"}))
    assert isinstance(r, Flag)


def test_old_plain_hhmm_reads_as_expiry_day():
    ev = _run(today=OPENED, hhmm="15:20", time_exit="15:15")
    assert not isinstance(_t10b(ev), Flag)


_SHAPES = [pytest.param({"at": "15:15", "on": "expiry"}, id="mapping"), pytest.param("15:15", id="plain")]


@pytest.mark.parametrize("te", _SHAPES)
def test_plan_time_beats_the_playbook_stage_time_on_expiry(te):
    """The plan's own time decides; the playbook's T-10b stage value (14:30 in ADJ-14) is only for a plan without one."""
    assert "14:30" in str(body_of(load("ADJ-14")))
    assert not isinstance(_t10b(_run(today=EXPIRY, hhmm="14:40", time_exit=te)), Flag)
    r = _t10b(_run(today=EXPIRY, hhmm="15:15", time_exit=te))
    assert isinstance(r, Flag) and r.threshold == "15:15"


@pytest.mark.parametrize("te", _SHAPES)
def test_a35_agrees_with_the_evaluator(te):
    from types import SimpleNamespace

    from ofo.adjustment.approaches import _time_exit_due
    from ofo.adjustment.playbook_eval import exit_inputs

    sc = load("ADJ-14")
    pos = SimpleNamespace(today=EXPIRY, legs=[SimpleNamespace(expiry=EXPIRY)])
    early = exit_inputs(body_of(sc), {"time_exit": te}, replace(state_of(sc), today=EXPIRY, expiry=EXPIRY, hhmm="14:40"))
    on_time = exit_inputs(body_of(sc), {"time_exit": te}, replace(state_of(sc), today=EXPIRY, expiry=EXPIRY, hhmm="15:15"))
    assert early.time_exit == on_time.time_exit == "15:15"
    _time_exit_due(pos, on_time)
    with pytest.raises(Exception):  # noqa: B017, PT011 - the A-35 refusal type is private
        _time_exit_due(pos, early)
