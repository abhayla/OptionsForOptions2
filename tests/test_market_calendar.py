"""REQ-056 AC-12 / ADR-119: the market is open only 09:15 to 15:30 IST on an NSE trading day.

Expected values come from NSE's published F&O holiday list (fetched 2026-10-19, in ofo/market_calendar.json) and the
ADR: Tue 2026-10-20 is Dussehra (closed), Wed 2026-10-21 is a trading day, Sat/Sun are weekends."""
from __future__ import annotations

import datetime
import json

import pytest
from ofo.market_calendar import (DATA_FILE, MarketStatus, is_market_open, last_close, market_status, next_open,
                                 price_time)
from ofo.timeutil import IST


def at(day: int, hour: int, minute: int = 0, second: int = 0, month: int = 10) -> datetime.datetime:
    return datetime.datetime(2026, month, day, hour, minute, second, tzinfo=IST)


def test_ac12_dussehra_tuesday_is_closed_at_ten() -> None:
    """AC-12: Tue 2026-10-20 10:00 IST (Dussehra) is closed, status says holiday."""
    assert market_status(at(20, 10)) is MarketStatus.CLOSED_HOLIDAY
    assert is_market_open(at(20, 10)) is False


def test_ac12_wednesday_ten_is_open() -> None:
    """AC-12: Wed 2026-10-21 10:00 IST is a trading day inside the session."""
    assert is_market_open(at(21, 10)) is True


@pytest.mark.parametrize("when,expected", [
    (at(21, 9, 15, 0), True), (at(21, 9, 14, 59), False), (at(21, 15, 29, 59), True), (at(21, 15, 30, 0), False)])
def test_ac12_session_edges(when: datetime.datetime, expected: bool) -> None:
    """AC-12: 09:15:00 opens, 09:14:59 does not; 15:29:59 is open, 15:30:00 is closed."""
    assert is_market_open(when) is expected


def test_ac12_weekend_is_closed() -> None:
    """AC-12: Sat 2026-10-24 11:00 and Sun 2026-10-25 11:00 are weekend closures."""
    assert market_status(at(24, 11)) is MarketStatus.CLOSED_WEEKEND
    assert market_status(at(25, 11)) is MarketStatus.CLOSED_WEEKEND


def test_ac12_a_utc_instant_is_judged_in_ist() -> None:
    """AC-12: 04:45 UTC on Wed 21 Oct is 10:15 IST (open); 03:30 UTC is 09:00 IST (closed)."""
    utc = datetime.UTC
    assert is_market_open(datetime.datetime(2026, 10, 21, 4, 45, tzinfo=utc)) is True
    assert is_market_open(datetime.datetime(2026, 10, 21, 3, 30, tzinfo=utc)) is False


def test_ac12_year_without_data_is_closed_with_its_own_reason() -> None:
    """AC-12: 2027 has no holiday data -> NO_CALENDAR, not open (fail closed), and no next-open guess."""
    when = datetime.datetime(2027, 1, 5, 10, 0, tzinfo=IST)
    assert market_status(when) is MarketStatus.NO_CALENDAR
    assert is_market_open(when) is False
    assert next_open(when) is None


def test_ac12_next_open_after_the_holiday_and_over_the_weekend() -> None:
    """AC-12: Dussehra Tue 20 Oct -> Wed 21 Oct 09:15; Fri 23 Oct 16:00 -> Mon 26 Oct; Wed 09:00 -> same day 09:15;
    Wed 10:00 (open) -> Thu 09:15; Mon 9 Nov -> Tue 10 Nov is Balipratipada -> Wed 11 Nov."""
    assert next_open(at(20, 10)) == at(21, 9, 15)
    assert next_open(at(23, 16)) == at(26, 9, 15)
    assert next_open(at(21, 9)) == at(21, 9, 15)
    assert next_open(at(21, 10)) == at(22, 9, 15)
    assert next_open(at(9, 10, month=11)) == at(11, 9, 15, month=11)


def test_ac12_next_open_into_a_missing_year_is_unknown() -> None:
    """AC-12: Thu 31 Dec 2026 16:00 -> the next trading day is in 2027, which has no data -> None."""
    assert next_open(at(31, 16, month=12)) is None


def test_ac12_naive_time_is_refused() -> None:
    """AC-12: a naive datetime is refused (no guessing the zone)."""
    with pytest.raises(ValueError):
        market_status(datetime.datetime(2026, 10, 21, 10, 0))  # noqa: DTZ001 - the naive value is the case under test


def test_ac12_data_file_names_source_date_and_the_two_named_holidays() -> None:
    """AC-12 / step 1: the data file carries its source URL, fetch date and each holiday's name."""
    raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    assert raw["source"].startswith("https://www.nseindia.com/") and raw["fetched"] == "2026-10-19"
    named = dict(raw["holidays"]["2026"])
    assert named["2026-10-20"] == "Dussehra" and named["2026-11-10"] == "Diwali-Balipratipada"


@pytest.mark.parametrize("when,expected", [
    (at(28, 7, 46, 28), at(27, 15, 30)),  # before the open: yesterday's close
    (at(27, 15, 30), at(27, 15, 30)),  # exactly the close: that close
    (at(27, 15, 29, 59), at(26, 15, 30)),  # in hours: the latest close at or before (Mon 26th)
    (at(27, 17, 35, 6), at(27, 15, 30)),  # Kite's post-close stamp
    (at(21, 7, 46), at(19, 15, 30)),  # the day after the Tue 20 Oct Dussehra holiday
    (at(31, 11), at(30, 15, 30)),  # Saturday
    (at(1, 8, month=11), at(30, 15, 30)),  # Sunday
])
def test_last_close_is_the_mirror_of_next_open(when, expected) -> None:
    """GC-BM F-19 (ADR-200 (2)): 15:30 IST of the latest trading day whose close is at or before ``when``."""
    assert last_close(when) == expected


def test_last_close_and_price_time_without_calendar_data_are_none() -> None:
    jan = datetime.datetime(2027, 1, 4, 7, 46, tzinfo=IST)
    assert last_close(jan) is None and price_time(jan) is None
    assert price_time(at(28, 10)) == at(28, 10)  # in hours: the time itself
