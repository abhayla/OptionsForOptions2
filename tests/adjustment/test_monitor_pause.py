"""A-38 (GC-IC1 step 4a): the pause end is today, after now, by the close; in force only before its end."""
from __future__ import annotations

import datetime

import pytest
from ofo.adjustment import monitor_pause as mp
from ofo.timeutil import IST

DAY = datetime.date(2026, 11, 3)


def at(h: int, m: int, s: int = 0, day: datetime.date = DAY) -> datetime.datetime:
    return datetime.datetime.combine(day, datetime.time(h, m, s), IST)


def test_an_end_later_today_by_the_close_is_accepted():
    assert mp.check_until(at(10, 30), at(10, 10)) == at(10, 30)
    assert mp.check_until(at(15, 30), at(15, 20)) == at(15, 30)  # the close itself


@pytest.mark.parametrize(("until", "now", "reason"), [
    (at(15, 40), at(15, 20), mp.Refusal.AFTER_CLOSE),  # attack 3: set at 15:20 for 15:40
    (at(15, 30, 1), at(15, 20), mp.Refusal.AFTER_CLOSE),
    (at(10, 10), at(10, 10), mp.Refusal.IN_PAST),
    (at(10, 0), at(10, 10), mp.Refusal.IN_PAST),
    (at(10, 30, day=datetime.date(2026, 11, 4)), at(10, 10), mp.Refusal.NOT_TODAY),
    (datetime.datetime(2026, 11, 3, 10, 30), at(10, 10), mp.Refusal.NO_ZONE),  # noqa: DTZ001 - the naive case
])
def test_a_refused_end_names_its_reason(until, now, reason):
    with pytest.raises(mp.PauseRefused) as refused:
        mp.check_until(until, now)
    assert refused.value.reason is reason


@pytest.mark.parametrize(("until", "now", "held"), [
    (None, at(10, 10), False),  # none / cleared
    (at(10, 30), at(10, 10), True),
    (at(10, 30), at(10, 29, 59), True),
    (at(10, 30), at(10, 30), False),  # ends by itself at its end (attack 2)
    (at(10, 30), at(10, 31), False),  # expired
    (at(10, 30), at(10, 10, day=datetime.date(2026, 11, 4)), False),  # compared by instant, never by date only
])
def test_in_force_compares_the_end_with_the_given_time(until, now, held):
    assert mp.in_force(until, now) is held
