"""IC e2e retry of #661 / #662 (no DB): the pure layer of T-18 (the adjustment limit) and of T-11 on PATH-13.

- T-18 IS a raising rule, not a guard only: ``playbook_eval._t18`` answers a ``ge`` Hit (used vs the plan's
  ``guards.max_adjustments``), ``gate_readings.reading`` turns it into a one-rung ladder (the plan maximum; the
  playbook's T-18 has no per-stage values, so ``_later`` is empty), and ``alert_gate.step`` opens exactly one record
  when the count reaches the maximum. The C1 miss was the worker's stale ``Tracked`` (see test_ic_second_adjustment).
- T-11 on PATH-13 opens a level-0 record at frame 3's close (3 pts, the stage line) and ONE escalation at frame 4's
  close (4 pts = the later-stage rung, ladder 3 -> 4, alert_gate.py:267-268, worse = "last"); frames 5 to 8 hold the
  value and open nothing. The second record of b1-db7 is designed escalation, not a duplicate.
"""
from __future__ import annotations

import datetime
from dataclasses import replace
from decimal import Decimal as D

import pytest
import test_ic_path50_crossings as p50
from ofo.adjustment import alert_gate as gate
from ofo.adjustment import gate_readings as gr
from ofo.adjustment import playbook_eval as pe

PATH13 = p50.PATH.parent / "PATH-13"
MAX_ADJUSTMENTS = 2  # the fixture plan's guards.max_adjustments
CYCLES = 3  # checks per frame, one second apart (as the worker tests)


def _frames(path, k: int):
    old = p50.PATH
    p50.PATH = path
    try:
        return p50.state_at(k), datetime.datetime.fromisoformat(p50.frame(k)["clock"]["ist"])
    finally:
        p50.PATH = old


def _walk(path, frames, rule_id: str, adjust=None):
    """Steps the gate over ``frames`` (CYCLES checks per frame); -> {frame: [Opened events of rule_id]}."""
    st, out = gate.initial_state(), {}
    for k in frames:
        (body, s), clock = _frames(path, k)
        if adjust is not None:
            s = adjust(k, s)
        ev = pe.evaluate(body, s, {}, None, gap_until=p50.GAP_UNTIL)
        reading = gr.readings(ev)[rule_id]
        got = []
        for sec in range(CYCLES):
            st, events = gate.step(st, now=clock + datetime.timedelta(seconds=sec), preset=gate.INTRADAY,
                                   readings={rule_id: reading})
            got += [e for e in events if isinstance(e, gate.Opened)]
        out[k] = got
    return out


@pytest.mark.parametrize(("used", "fired"), [(0, False), (1, False), (2, True), (3, True)])
def test_t18_reads_the_count_against_the_plan_maximum_as_a_ge_rule(used, fired):
    (body, s), _clock = _frames(p50.PATH, p50.F_QUIET)
    assert body["guards"]["max_adjustments"] == MAX_ADJUSTMENTS and body["triggers"]["T-18"]["on"] is True
    ev = pe.evaluate(body, replace(s, adjustments_used=used), {}, None, gap_until=p50.GAP_UNTIL)
    spec, value = gr.readings(ev)["T-18"]
    assert (spec.cmp, spec.ladder, value) == ("ge", (D(MAX_ADJUSTMENTS),), D(used))
    assert (gate.level_of(spec, value) >= 0) is fired


def test_t18_count_not_readable_gives_no_reading_never_a_record():
    (body, s), _clock = _frames(p50.PATH, p50.F_QUIET)
    ev = pe.evaluate(body, replace(s, adjustments_used=None), {}, None, gap_until=p50.GAP_UNTIL)
    assert gr.readings(ev)["T-18"][1] is None


def test_t18_opens_exactly_one_record_when_the_count_reaches_the_maximum():
    """Frames 1..3 of PATH-50's quiet stretch: used 1 at the first, 2 from the second on (the second adjustment)."""
    frames = [p50.F_QUIET, p50.F_1420, p50.F_1429]
    def used(k, s):
        return replace(s, adjustments_used=1 if k == frames[0] else MAX_ADJUSTMENTS)
    got = _walk(p50.PATH, frames, "T-18", adjust=used)
    opened = [e for k in frames for e in got[k]]
    assert len(opened) == 1 and opened[0].value == D(MAX_ADJUSTMENTS) and opened[0].worse is None, got


def test_path13_t11_value_per_frame_and_one_escalation_by_design():
    got = _walk(PATH13, range(9), "T-11")
    values = [_frames(PATH13, k)[0][1].atm_iv for k in range(9)]
    assert values == [D("0.10"), D("0.11"), D("0.12"), D("0.13")] + [D("0.14")] * 5  # flat from frame 4
    assert {k: [(e.level, e.value, e.worse) for e in v] for k, v in got.items() if v} == {
        4: [(0, D("3.00"), None)],  # frame 3's close (3 pts = the stage line), seen at frame 4
        5: [(1, D("4.00"), "last")],  # frame 4's close (4 pts = the later-stage rung): one escalation
    }


def test_t18_is_never_already_true_at_the_baseline_taken_after_the_adjustment_that_reaches_the_limit():
    """#662 (RCA): after adjustment N the rule memory restarts and the first check is the baseline (ADR-258). T-18 is
    true at exactly that check (used == max), so it was held "already true" and never raised a record. A guard-only
    rule counts adjustments: reaching the limit is its crossing, however the baseline is taken."""
    (body, s), _clock = _frames(p50.PATH, p50.F_QUIET)
    at_limit = replace(s, adjustments_used=MAX_ADJUSTMENTS)
    flags = lambda ev: [r.rule_id for r in ev.results if isinstance(r, pe.Flag) and r.rule_id == "T-18"]  # noqa: E731
    ev = pe.evaluate(body, at_limit, {}, at_limit, gap_until=p50.GAP_UNTIL)  # baseline = this very check
    assert flags(ev) == ["T-18"]
    stored = {"T-18": {"held_at_entry": True, "seen_clear": False}}  # memory written before the fix
    assert flags(pe.evaluate(body, at_limit, stored, at_limit, gap_until=p50.GAP_UNTIL)) == ["T-18"]
