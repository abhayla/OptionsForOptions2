"""Clock boundaries inside a day (live test day 27 Nov 2026; Lane Q2 gap 3): an alert style's candle close and the
5-minute at-entry quiet period of the pop-up. Pure; every time is passed in.

Candle: a non-stop rule that crosses mid-candle opens at the candle's close, once, for every style; a sample one
second before the close opens nothing and the first check after it opens exactly one record. Quiet: a plan loss stop
that was already crossed at entry opens its RECORD at once (REQ-170 AC-5) and its pop-up is due exactly at entry + 5
minutes, not 4:59, never later (ADR-326 (5), popup_quiet).
Spec basis: REQ-170 AC-1/AC-5, ADR-236, ADR-326 (5).
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest
from ofo.adjustment import alert_gate as ag
from ofo.adjustment.popup_quiet import QUIET_PERIOD, popup_due

D = Decimal
HAS_SECONDS = 2
DAY = date(2026, 11, 27)
STYLES = {"intraday": ag.INTRADAY, "weekly": ag.WEEKLY, "monthly": ag.MONTHLY}


def at(hhmm: str) -> datetime:
    clock = hhmm if hhmm.count(":") == HAS_SECONDS else hhmm + ":00"
    return datetime.combine(DAY, time.fromisoformat(clock), tzinfo=ag.IST)


def _read(rule_id: str, value: str):
    return {rule_id: (ag.RuleSpec(rule_id, "ge", (D("10"),)), D(value))}


@pytest.mark.parametrize("style", STYLES)
def test_a_crossing_opens_at_the_candle_close_not_before_and_once(style):
    preset = STYLES[style]
    anchor = datetime.combine(DAY, time(9, 15), tzinfo=ag.IST)
    end = anchor + preset.candle * ((at("10:00:30") - anchor) // preset.candle + 1)
    state, opened = ag.initial_state(), []
    t = at("10:00:30")
    while t < end + preset.candle:
        state, ev = ag.step(state, now=t, preset=preset, readings=_read("T-03", "11"))
        opened += [(t, e) for e in ev if isinstance(e, ag.Opened)]
        if t < end:
            assert not opened, (style, t)  # nothing before the close, not even one second before
        t += timedelta(seconds=1)
    assert len(opened) == 1
    assert opened[0][0] >= end, (style, end, [x[0] for x in opened])


@pytest.mark.parametrize("style", STYLES)
def test_a_loss_stop_crossed_before_the_quiet_time_opens_at_once(style):
    """ADR-330 (47) (replaces the ADR-236 hold of this guard): a plan's loss stop alerts at once, no quiet time."""
    preset = STYLES[style]
    _state, ev = ag.step(ag.initial_state(), now=at("09:16:00"), preset=preset, readings=_read("T-06", "11"))
    assert [(type(e), e.at) for e in ev] == [(ag.Opened, at("09:16:00"))]


ENTRY = at("10:00:00")


def test_quiet_period_is_five_minutes():
    assert timedelta(minutes=5) == QUIET_PERIOD


@pytest.mark.parametrize(("seconds", "due"), [(0, False), (10, False), (299, False), (300, True), (301, True)])
def test_a_stop_already_crossed_at_entry_pops_up_exactly_when_the_quiet_period_ends(seconds, due):
    shown = ENTRY + timedelta(seconds=10)  # the record opened at once, 10 s after entry
    now = ENTRY + timedelta(seconds=seconds)
    assert popup_due(entry_at=ENTRY, shown_at=shown, seen_clear=False, now=now) is due


def test_a_stop_that_crossed_after_entry_pops_up_at_once():
    assert popup_due(entry_at=ENTRY, shown_at=ENTRY + timedelta(minutes=7), seen_clear=False,
                     now=ENTRY + timedelta(minutes=7)) is True
