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


# ---- #743: a held episode ends by the LINE's band, not by the held step's band ----------------------------------------

def _held_run(start, values, state=None):
    state = state if state is not None else ag.initial_state()
    events = []
    candle = ag.INTRADAY.candle
    base = at(start)
    for i, v in enumerate(list(values) + [values[-1]]):  # the last extra step closes the final candle
        state, ev = ag.step(state, now=base + candle * i + timedelta(seconds=1), preset=ag.INTRADAY,
                            readings={SPEC.rule_id: (SPEC, D(v))})
        events += ev
    return events


def test_held_by_daily_cap_is_one_episode_while_the_close_stays_past_the_lines_band():
    state = ag.restore(ag.GateRows((), 6), at("11:00").date(), {})
    assert ag.INTRADAY.daily_cap <= 6
    events = _held_run("11:00", ["120", "160", "130", "160", "130", "160", "130", "160"], state)
    held = [e for e in events if isinstance(e, ag.Held)]
    # 120 holds at the line; 160 is one level worse (a new hold step); 130 is NOT beyond the band of the line (90), so
    # the episode goes on and the later 160s repeat nothing
    assert [e.level for e in held] == [0, 1]
    assert _count(events, ag.Opened) == 0


def test_held_by_quiet_time_is_one_episode_while_the_close_stays_past_the_lines_band():
    events = _held_run("09:05", ["120", "160", "130", "160", "130", "160", "130", "160"])
    held = [e for e in events if isinstance(e, ag.Held)]
    assert [e.level for e in held] == [0, 1]
    assert _count(events, ag.Opened) == 0
