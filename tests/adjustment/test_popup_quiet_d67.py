"""D-67 (ADR-326 (5), REQ-170 cool-down): the adjustment pop-up of a rule that was already true when the trade was
entered waits 5 minutes after entry; a rule that became true later pops up at once; the record is written as before.

Real case 23 Nov 2026: condor C10 (strategy 166) gamma 2.95 % against the 2 % rule and condor C11 (167) tested delta
0.3809 against 0.35, both raised within 1 to 3 minutes of opening. Entry time unknown -> raised at once (fail open
toward telling the trader: a missed pop-up costs more than a early one).
"""
from __future__ import annotations

import datetime as dt

from ofo.adjustment.popup_quiet import FIRST_CHECK_WINDOW, QUIET_PERIOD, popup_due

ENTRY = dt.datetime(2026, 11, 23, 9, 20, 0, tzinfo=dt.UTC)
SHOWN = ENTRY + dt.timedelta(minutes=1)  # the record opened (the gate confirmed the rule)
FIRST = ENTRY + dt.timedelta(seconds=20)  # the rule memory was first written by the first check, 20 s after entry


def at(minutes: float) -> dt.datetime:
    return ENTRY + dt.timedelta(minutes=minutes)


def test_the_quiet_period_is_five_minutes_like_the_alert_cool_down():
    assert dt.timedelta(minutes=5) == QUIET_PERIOD


def test_c10_gamma_true_at_entry_is_quiet_at_one_and_three_minutes_and_due_at_five():
    kw = {"entry_at": ENTRY, "shown_at": SHOWN, "seen_clear": False, "first_check_at": FIRST}
    assert popup_due(now=at(1), **kw) is False
    assert popup_due(now=at(3), **kw) is False
    assert popup_due(now=at(4.99), **kw) is False
    assert popup_due(now=at(5), **kw) is True
    assert popup_due(now=at(30), **kw) is True


def test_c11_tested_delta_true_at_entry_is_quiet_then_due():
    kw = {"entry_at": ENTRY, "shown_at": at(3), "seen_clear": False, "first_check_at": FIRST}
    assert popup_due(now=at(3), **kw) is False
    assert popup_due(now=at(5), **kw) is True


def test_a_rule_that_was_false_at_a_check_after_entry_pops_up_at_once():
    assert popup_due(entry_at=ENTRY, shown_at=at(2), seen_clear=True, first_check_at=FIRST, now=at(2)) is True


def test_a_rule_that_became_true_after_the_quiet_period_pops_up_at_once():
    assert popup_due(entry_at=ENTRY, shown_at=at(7), seen_clear=False, first_check_at=FIRST, now=at(7)) is True


def test_entry_time_unknown_fails_open():
    assert popup_due(entry_at=None, shown_at=SHOWN, seen_clear=False, first_check_at=FIRST, now=at(1)) is True


def test_rule_memory_unknown_fails_open():
    assert popup_due(entry_at=ENTRY, shown_at=SHOWN, seen_clear=None, first_check_at=FIRST, now=at(1)) is True


def test_an_entry_after_the_record_or_a_clock_without_zone_fails_open():
    # an entry later than the record: another clock (scenario)
    assert popup_due(entry_at=at(10), shown_at=SHOWN, seen_clear=False, first_check_at=FIRST, now=at(1)) is True
    naive = ENTRY.replace(tzinfo=None)
    assert popup_due(entry_at=naive, shown_at=SHOWN, seen_clear=False, first_check_at=FIRST, now=at(1)) is True


def test_the_first_check_window_is_the_worker_join_time_of_a_new_strategy():
    assert dt.timedelta(seconds=60) == FIRST_CHECK_WINDOW  # monitor set re-read every 30 s, AC-3: joins within 60 s


def test_first_check_at_entry_finds_false_then_true_at_two_minutes_pops_up_at_once():
    assert popup_due(entry_at=ENTRY, shown_at=at(2), seen_clear=True, first_check_at=FIRST, now=at(2)) is True


def test_no_check_until_two_minutes_and_true_then_pops_up_at_once_entry_state_unknown():
    # the first evaluation came 2 minutes after entry: the rule may have turned true after entry, so tell the trader
    late = at(2)
    assert popup_due(entry_at=ENTRY, shown_at=at(2.5), seen_clear=False, first_check_at=late, now=at(3)) is True


def test_first_check_time_unknown_fails_open():
    assert popup_due(entry_at=ENTRY, shown_at=SHOWN, seen_clear=False, first_check_at=None, now=at(1)) is True


def test_a_scenario_dated_case_on_one_clock_is_quiet_then_due():
    entry = dt.datetime(2026, 11, 3, 9, 20, tzinfo=dt.UTC)  # the scenario's own day, not today
    kw = {"entry_at": entry, "shown_at": entry + dt.timedelta(minutes=1), "seen_clear": False,
          "first_check_at": entry + dt.timedelta(seconds=10)}
    assert popup_due(now=entry + dt.timedelta(minutes=2), **kw) is False
    assert popup_due(now=entry + dt.timedelta(minutes=5), **kw) is True
