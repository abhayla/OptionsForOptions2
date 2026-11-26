"""P1c NEW-1: "no longer true" / "true again" are judged against the rule's LINE (ladder[0]) with its re-arm band, never
the escalated step (ADR-330 (3), ADR-237 (4))."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from ofo.adjustment import alert_gate as ag
from test_alert_gate import at

D = Decimal
SPEC = ag.RuleSpec("T-LINE", "ge", (D("100"), D("150")))  # INTRADAY band 10 percent: stops at or below 90


def _run(values):
    state, events = ag.initial_state(), []
    for i, v in enumerate(values):
        state, ev = ag.step(state, now=at("10:40") + timedelta(minutes=i), preset=ag.INTRADAY,
                            readings={SPEC.rule_id: (SPEC, D(v))})
        events += ev
    return events


def _count(events, cls):
    return len([e for e in events if isinstance(e, cls)])


def test_after_an_escalation_a_close_past_the_line_is_not_a_lapse_or_true_again():
    events = _run(["120", "120", "160", "160"] + ["130"] * 11)
    assert _count(events, ag.Escalated) == 1
    assert _count(events, ag.Lapsed) == 0
    assert _count(events, ag.TrueAgain) == 0


def test_a_close_inside_the_lines_rearm_band_gives_no_lapse():
    events = _run(["120", "120", "95", "95", "95"])
    assert _count(events, ag.Lapsed) == 0


def test_a_close_below_the_band_lapses_once_then_true_again_on_recrossing():
    events = _run(["120", "120", "80", "80", "80", "120", "120", "120"])
    assert _count(events, ag.Lapsed) == 1
    assert _count(events, ag.TrueAgain) == 1
