"""P1 round 3 F1/F2: an UNANSWERED actionable record stays open in the gate's memory (ADR-330 (3), (4); REQ-170 AC-3).

Spec basis: ADR-330 (3) "does not close, lapse or leave the Active list until the user himself acknowledges it ... if
its condition later stops being true it adds 'no longer true since HH:MM' and still stays"; REQ-170 AC-3 (a worse
record says it is worse). One open alert per rule: a re-cross neither re-opens it nor spends the daily cap, the first
close past the line again says "true again" at once (no cool-down, cap or quiet time), a worse close is an
``Escalated`` event. A restart (``restore``) gives the same memory.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

from ofo.adjustment import alert_gate as ag
from ofo.adjustment.gate_rows import GateRow, GateRows
from test_alert_gate import DAY, at

D = Decimal
T06 = ag.RuleSpec("T-06", "ge", (D("15.4000"),))  # the S-16 stop (a stop rule: judged at the first sample beyond)
T07 = ag.RuleSpec("T-07", "ge", (D("15.4000"), D("18")))
T03 = ag.RuleSpec("T-03", "ge", (D("0.30"),))


def _kinds(events):
    return [type(e).__name__ for e in events]


def _step(state, hhmm, readings, preset=ag.INTRADAY):
    return ag.step(state, now=at(hhmm), preset=preset, readings=readings)


def test_f1_s16_first_close_past_the_line_again_says_true_again_at_once():
    state, seen = ag.initial_state(), {}
    for hhmm, value in [("11:02:20", D("15.9")), ("11:03:20", D("13.0")), ("11:04:20", D("15.9")),
                        ("11:05:20", D("15.9")), ("11:06:20", D("15.9"))]:
        state, ev = _step(state, hhmm, {"T-06": (T06, value)})
        seen[hhmm] = ev
    assert _kinds(seen["11:02:20"]) == ["Opened"]
    # the 11:03 candle closed clear: stopped once; the 11:04:20 sample is beyond the line again: true again, NOW
    assert _kinds(seen["11:04:20"]) == ["Lapsed", "TrueAgain"]
    assert seen["11:04:20"][1].at == at("11:04:20")
    assert seen["11:05:20"] == [] and seen["11:06:20"] == []  # nothing on later closes: no re-open, no timeline growth


def test_f1_a_non_stop_rule_says_true_again_at_the_first_close_past_the_line():
    state, events = ag.initial_state(), []
    for hhmm, value in [("11:02:20", D("15.9")), ("11:03:20", D("13.0")), ("11:04:20", D("13.0")),
                        ("11:05:20", D("15.9")), ("11:06:20", D("15.9")), ("11:07:20", D("15.9"))]:
        state, ev = _step(state, hhmm, {"T-07": (T07, value)})
        events += [(hhmm, e) for e in ev]
    assert [(h, type(e).__name__) for h, e in events] == [
        ("11:03:20", "Opened"), ("11:05:20", "Lapsed"), ("11:06:20", "TrueAgain")]
    assert events[2][1].at == at("11:06:00")  # the close of the 11:05 candle, the first one past the line again


def test_f2_a_rule_flipping_every_3_minutes_for_an_hour_opens_once_and_the_cap_is_not_spent():
    state, events = ag.initial_state(), []
    base = at("11:02")
    for i in range(60):
        value = D("15.9") if (i // 3) % 2 == 0 else D("13.0")
        state, ev = ag.step(state, now=base + timedelta(minutes=i, seconds=20), preset=ag.INTRADAY,
                            readings={"T-07": (T07, value)})
        events += ev
    assert len([e for e in events if isinstance(e, ag.Opened)]) == 1
    assert state.opened_today == 1
    assert [e for e in events if isinstance(e, ag.Held)] == []
    state, ev = _step(state, "12:16:20", {"T-07": (T07, D("15.9")), "T-03": (T03, D("0.31"))})
    state, ev2 = _step(state, "12:17:20", {"T-07": (T07, D("15.9")), "T-03": (T03, D("0.31"))})
    assert [type(e).__name__ for e in ev + ev2 if e.rule_id == "T-03"] == ["Opened"]  # not Held daily_limit
    assert state.opened_today == 2


def test_a_worse_close_while_open_is_an_escalation_not_a_new_record_and_not_counted():
    state, events = ag.initial_state(), []
    for hhmm, value in [("11:02:20", D("15.9")), ("11:03:20", D("15.9")), ("11:04:20", D("18.5")),
                        ("11:05:20", D("18.5"))]:
        state, ev = _step(state, hhmm, {"T-07": (T07, value)})
        events += ev
    assert _kinds(events) == ["Opened", "Escalated"]
    assert events[1].level == 1 and events[1].threshold == D("18") and events[1].value == D("18.5")
    assert state.opened_today == 1


def test_a_worse_close_after_a_dismissal_is_still_a_new_record():
    state, _ = _step(ag.initial_state(), "11:02:20", {"T-07": (T07, D("15.9"))})
    state, _ = _step(state, "11:03:20", {"T-07": (T07, D("15.9"))})
    state = ag.dismiss(state, "T-07")
    state, ev = _step(state, "11:04:20", {"T-07": (T07, D("18.5"))})
    state, ev2 = _step(state, "11:05:20", {"T-07": (T07, D("18.5"))})
    assert _kinds(ev + ev2) == ["Opened"] and (ev + ev2)[0].worse == "dismissed"


def test_a_restart_gives_the_same_memory_stopped_row_then_true_again_and_the_same_count():
    row = GateRow("T-07", at("11:02"), D("15.4000"), dismissed=False, open=True, id=5, stopped=True)
    state = ag.restore(GateRows((row,), 1), DAY, {"T-07": T07})
    assert state.opened_today == 1
    state, ev = _step(state, "11:20:20", {"T-07": (T07, D("15.9"))})
    state, ev2 = _step(state, "11:21:20", {"T-07": (T07, D("15.9"))})
    assert _kinds(ev + ev2) == ["TrueAgain"] and (ev + ev2)[0].at == at("11:21:00")
    quiet = ag.restore(GateRows((replace(row, stopped=False),), 1), DAY, {"T-07": T07})
    quiet, ev3 = _step(quiet, "11:20:20", {"T-07": (T07, D("15.9"))})
    quiet, ev4 = _step(quiet, "11:21:20", {"T-07": (T07, D("15.9"))})
    assert ev3 + ev4 == []  # an open, not-stopped row: nothing to say


def test_an_answered_record_still_re_arms_by_band_and_cooldown():
    state = ag.initial_state()
    for hhmm, value in [("11:02:20", D("15.9")), ("11:03:20", D("15.9"))]:
        state, _ = _step(state, hhmm, {"T-07": (T07, value)})
    state = ag.answered(state, "T-07", None)
    events = []
    for hhmm, value in [("11:04:20", D("13.0")), ("11:05:20", D("13.0")), ("11:20:20", D("15.9")),
                        ("11:21:20", D("15.9"))]:
        state, ev = _step(state, hhmm, {"T-07": (T07, value)})
        events += ev
    assert _kinds(events) == ["Opened"]
