"""I-82 (test plan 28 Nov 2026), pop-up order around the 5-minute quiet period
(``popup_due``, ADR-326 (5), ADR-330 (47)).
Real case 23 Nov 2026, condor C10: gamma already true at entry (quiet until entry + 5), then a stop-out line crossed
later. Pinned: every open record, whatever its kind, is held to the SAME rule, so a stop-out alert crossed at 3 minutes
waits with the rule that was true at entry and both fall due together at entry + 5, while one crossed after the quiet
period is due at once, ahead of nothing; a record whose condition was seen false is due at once.
"""
from __future__ import annotations

import datetime as dt

import pytest
from ofo.adjustment.popup_quiet import popup_due

ENTRY = dt.datetime(2026, 11, 23, 9, 20, 0, tzinfo=dt.UTC)


def at(minutes: float) -> dt.datetime:
    return ENTRY + dt.timedelta(minutes=minutes)


def due(shown_min: float, now_min: float, *, seen_clear: bool = False) -> bool:
    return popup_due(entry_at=ENTRY, shown_at=at(shown_min), seen_clear=seen_clear, now=at(now_min))


@pytest.mark.parametrize(("now_min", "rule_due", "stop_due"), [(3, False, False), (4.99, False, False), (5, True, True),
                                                               (9, True, True)])
def test_a_rule_true_at_entry_and_a_stop_out_crossed_at_three_minutes_fall_due_together(now_min, rule_due, stop_due):
    assert (due(1, now_min), due(3, now_min)) == (rule_due, stop_due)


def test_a_stop_out_crossed_after_the_quiet_period_is_due_at_once_while_the_early_rule_is_already_due():
    assert (due(1, 7), due(7, 7)) == (True, True)


def test_a_condition_seen_false_is_due_at_once_inside_the_quiet_period():
    assert due(2, 2, seen_clear=True) is True and due(2, 2, seen_clear=False) is False
