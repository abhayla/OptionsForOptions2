
"""Evaluation -> alert-gate readings (GC-ALERT1 wire-a core; REQ-170 AC-1..AC-3, ADR-237 (1)/(2), ADR-217).

Core proof: the REAL ``playbook_eval.evaluate`` on scenario ADJ-02 (a weekly NIFTY iron condor, 3 days left = the
Middle stage, as tests_app/test_background_worker.py seeds it) gives a value reading for every checked rule, true AND
false, with the escalation ladder from the playbook's later-stage thresholds; the readings drive ``alert_gate.step``.
"""
from __future__ import annotations

import datetime
from dataclasses import replace
from decimal import Decimal

import pytest
from ofo.adjustment import alert_gate as gate
from ofo.adjustment import gate_readings
from ofo.adjustment.playbook_eval import Evaluation, NotChecked, RuleValue
from ofo.timeutil import IST
from test_adjust_scenarios import load
from test_playbook_eval import body_of, entry_of, evaluate, state_of

D = Decimal


def _adj02():
    sc = load("ADJ-02")
    body, state = body_of(sc), state_of(sc)
    return body, state, evaluate(body, state, None, entry_of(sc))


def test_core_adj02_every_checked_rule_has_a_value_and_its_ladder():
    _, _, ev = _adj02()
    assert ev.stage_name == "Middle"
    got = gate_readings.readings(ev)
    t03_spec, t03 = got["T-03"]
    assert t03_spec == gate.RuleSpec("T-03", "ge", (D("0.35"), D("0.40")))  # Middle 0.35, then Last day 0.40
    assert t03 >= D("0.35")
    t01_spec, t01 = got["T-01"]
    assert t01_spec == gate.RuleSpec("T-01", "le", (D("0.5"), D("0.3")))
    assert t01 <= D("0.5")
    # a rule FALSE at this check still reads its value (before this step ev.clear held ids only)
    assert "stop.max_loss_pct" in ev.clear
    t06_spec, t06 = got["T-06"]
    assert t06_spec == gate.RuleSpec("T-06", "ge", (D("50"),))  # Last day 40 is not more severe for ge: dropped
    assert isinstance(t06, Decimal) and t06 < D("50")
    for v in ev.values:
        assert v.rule_id in got and got[v.rule_id][1] is not None
    # a NotChecked rule reads None (ADR-217: neither clears nor opens)
    for r in ev.results:
        if isinstance(r, NotChecked):
            assert got[r.rule_id][1] is None


def test_core_adj02_readings_drive_the_gate_to_open_on_the_close():
    _, _, ev = _adj02()
    got = gate_readings.readings(ev)
    t0 = datetime.datetime(2026, 11, 6, 11, 40, tzinfo=IST)
    state, events = gate.step(gate.initial_state(), now=t0, preset=gate.WEEKLY, readings=got)
    assert events == []  # no close yet: the 11:40-11:45 candle is open
    state, events = gate.step(state, now=t0 + datetime.timedelta(minutes=5), preset=gate.WEEKLY, readings={})
    opened = {e.rule_id: e for e in events if isinstance(e, gate.Opened)}
    assert set(opened) == {f.rule_id for f in ev.results if f.__class__.__name__ == "Flag"}
    assert opened["T-03"].threshold == (D("0.40") if got["T-03"][1] >= D("0.40") else D("0.35"))
    assert "T-06" not in opened


def test_early_stage_ladder_is_the_three_weekly_thresholds():
    body, state, _ = _adj02()
    ev = evaluate(body, replace(state, days_left=5), None, None)
    assert ev.stage_name == "Early"
    spec, _ = gate_readings.readings(ev)["T-03"]
    assert spec.ladder == (D("0.30"), D("0.35"), D("0.40"))


def test_last_stage_has_no_later_threshold():
    body, state, _ = _adj02()
    ev = evaluate(body, replace(state, days_left=1), None, None)
    spec, _ = gate_readings.readings(ev)["T-03"]
    assert spec.ladder == (D("0.40"),)


def test_withheld_check_reads_every_rule_none():
    body, state, _ = _adj02()
    ev = evaluate(body, replace(state, prices_fresh=False), None, None)
    got = gate_readings.readings(ev)
    assert got and all(v is None for _, v in got.values())
    assert ev.values == ()


def test_already_true_at_entry_reads_none_until_seen_clear():
    body, state, _ = _adj02()
    ev = evaluate(body, state, None, state)  # entry = now: every firing rule held at entry (F-71)
    got = gate_readings.readings(ev)
    assert got["T-03"][1] is None


def _ev(*values: RuleValue) -> Evaluation:
    return Evaluation("Middle", 1, (), {}, tuple(v.rule_id for v in values if not v.fired), values=values)


def test_compound_rule_is_a_yes_no_reading():
    ev = _ev(RuleValue("R1", "T-01", D("0.4"), D("0.5"), "le", True, 2, (D("0.3"),)))
    assert gate_readings.readings(ev)["R1"] == (gate.RuleSpec("R1", "bool", ()), True)


def test_lt_and_clock_rules_are_yes_no_readings():
    ev = _ev(RuleValue("T-02", "T-02", D("-5"), D("0"), "lt", True, 1),
             RuleValue("T-10b", "T-10b", "14:00", "14:30", "ge", False, 1))
    got = gate_readings.readings(ev)
    assert got["T-02"] == (gate.RuleSpec("T-02", "bool", ()), True)
    assert got["T-10b"] == (gate.RuleSpec("T-10b", "bool", ()), False)


def test_unknown_cmp_is_refused_not_guessed():
    ev = _ev(RuleValue("X", "T-99", D("1"), D("1"), "eq", True, 1))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="cmp"):
        gate_readings.readings(ev)


def test_value_disagreeing_with_the_flag_is_refused():
    ev = _ev(RuleValue("T-03", "T-03", D("0.30"), D("0.35"), "ge", True, 1))  # says fired, value below the line
    with pytest.raises(ValueError, match="disagrees"):
        gate_readings.readings(ev)


def test_ladder_for_an_unknown_cmp_is_refused():
    with pytest.raises(ValueError, match="cmp"):
        gate.ladder_for("eq", D("1"), ())  # type: ignore[arg-type]
