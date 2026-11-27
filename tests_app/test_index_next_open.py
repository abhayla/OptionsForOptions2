"""ADR-330 (60) / ADR-119: the one market-state answer the frontend reads (``indices_answer``, REST ``/market/indices``
and its push) names the next session open, from the app's calendar (``ofo.market_calendar.next_open``), so the Exit
dialog's "Exits can be placed from 09:15 on <next trading day>" needs no calendar of its own.

Answer states: closed after hours (Fri 27 Nov 2026 16:00 -> Mon 30 Nov 09:15); weekend; the eve of a holiday (Mon 23 Nov
16:00, Tue 24 Nov is Prakash Gurpurb -> Wed 25 Nov 09:15); the calendar's last covered day (31 Dec 2026 16:00: the next
open is in a year the calendar lacks -> null); past the calendar (2031 -> null); market open -> null (nothing to wait
for)."""
from __future__ import annotations

import datetime

import pytest
from ofo.marketdata.kite_provider import IST
from ofo_app.index_push import indices_answer


def _at(day: int, month: int, hour: int, year: int = 2026) -> datetime.datetime:
    return datetime.datetime(year, month, day, hour, 0, tzinfo=IST)


def _next_open(now: datetime.datetime):
    return indices_answer(None, live=False, now=lambda: now)


@pytest.mark.parametrize(("now", "expected"), [
    (_at(27, 11, 16), datetime.datetime(2026, 11, 30, 9, 15, tzinfo=IST)),  # Friday after the close -> Monday
    (_at(28, 11, 11), datetime.datetime(2026, 11, 30, 9, 15, tzinfo=IST)),  # Saturday
    (_at(23, 11, 16), datetime.datetime(2026, 11, 25, 9, 15, tzinfo=IST)),  # eve of the 24 Nov holiday
    (_at(30, 11, 7), datetime.datetime(2026, 11, 30, 9, 15, tzinfo=IST)),  # before the open the same day
    (_at(31, 12, 16), None),  # the calendar's last covered day: the next open is in 2027, a year it has no data for
    (_at(5, 3, 10, 2031), None),  # past the calendar
    (_at(30, 11, 10), None),  # market open: nothing to wait for
])
def test_next_open_at_comes_from_the_calendar_while_closed_and_is_null_when_it_cannot_say(now, expected):
    out = _next_open(now)
    assert out.next_open_at == expected
    assert out.market_closed is (now != _at(30, 11, 10))
