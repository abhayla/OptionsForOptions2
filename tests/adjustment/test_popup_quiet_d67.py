"""D-67 (ADR-326 (5), REQ-170 cool-down): the adjustment pop-up of a rule that was already true when the trade was
entered waits 5 minutes after entry; a rule that became true later pops up at once; the record is written as before.

Real case 23 Nov 2026: condor C10 (strategy 166) gamma 2.95 % against the 2 % rule and condor C11 (167) tested delta
0.3809 against 0.35, both raised within 1 to 3 minutes of opening. Entry time unknown -> raised at once (fail open
toward telling the trader: a missed pop-up costs more than a early one).
"""
from __future__ import annotations

import datetime as dt

from ofo.adjustment.popup_quiet import QUIET_PERIOD, popup_due

ENTRY = dt.datetime(2026, 11, 23, 9, 20, 0, tzinfo=dt.UTC)
SHOWN = ENTRY + dt.timedelta(minutes=1)  # the first check after entry found the rule true and wrote the record


def at(minutes: float) -> dt.datetime:
    return ENTRY + dt.timedelta(minutes=minutes)


def test_the_quiet_period_is_five_minutes_like_the_alert_cool_down():
    assert dt.timedelta(minutes=5) == QUIET_PERIOD


def test_c10_gamma_true_at_entry_is_quiet_at_one_and_three_minutes_and_due_at_five():
    kw = {"entry_at": ENTRY, "shown_at": SHOWN, "seen_clear": False}
    assert popup_due(now=at(1), **kw) is False
    assert popup_due(now=at(3), **kw) is False
    assert popup_due(now=at(4.99), **kw) is False
    assert popup_due(now=at(5), **kw) is True
    assert popup_due(now=at(30), **kw) is True


def test_c11_tested_delta_true_at_entry_is_quiet_then_due():
    kw = {"entry_at": ENTRY, "shown_at": at(3), "seen_clear": False}
    assert popup_due(now=at(3), **kw) is False
    assert popup_due(now=at(5), **kw) is True


def test_a_rule_that_was_false_at_a_check_after_entry_pops_up_at_once():
    assert popup_due(entry_at=ENTRY, shown_at=at(2), seen_clear=True, now=at(2)) is True


def test_a_rule_that_became_true_after_the_quiet_period_pops_up_at_once():
    assert popup_due(entry_at=ENTRY, shown_at=at(7), seen_clear=False, now=at(7)) is True


def test_entry_time_unknown_fails_open():
    assert popup_due(entry_at=None, shown_at=SHOWN, seen_clear=False, now=at(1)) is True


def test_rule_memory_unknown_fails_open():
    assert popup_due(entry_at=ENTRY, shown_at=SHOWN, seen_clear=None, now=at(1)) is True


def test_an_entry_after_the_record_or_a_clock_without_zone_fails_open():
    assert popup_due(entry_at=at(10), shown_at=SHOWN, seen_clear=False, now=at(1)) is True  # other clock (scenario)
    naive = ENTRY.replace(tzinfo=None)
    assert popup_due(entry_at=naive, shown_at=SHOWN, seen_clear=False, now=at(1)) is True
