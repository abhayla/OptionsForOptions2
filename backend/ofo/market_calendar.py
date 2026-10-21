"""Is the NSE derivatives market open? (ADR-119, REQ-056 AC-12): 09:15 to 15:30 IST on a trading day.

Adapted from abhayla/algochanakya@bf9faf7 backend/app/utils/market_hours.py (legacy-reuse row M2). Changes: the caller
passes the time (no wall clock in the domain); the holidays are dated data (``market_calendar.json``, NSE's own F&O
list with its source and fetch date; the legacy file's hard-coded list was wrong for 2026: it had no 20 Oct Dussehra);
a year with no data is its own answer (``NO_CALENDAR``), never "open".

Standard library only. The session times are ``ofo.timeutil.SESSION_OPEN`` / ``SESSION_CLOSE``.
"""
from __future__ import annotations

import datetime
import json
from enum import Enum, unique
from functools import lru_cache
from pathlib import Path
from typing import Final

from ofo.timeutil import IST, SESSION_CLOSE, SESSION_OPEN

DATA_FILE: Final = Path(__file__).with_name("market_calendar.json")
#: How far ``next_open`` looks ahead before giving up (longer than any real run of closed days).
_LOOKAHEAD_DAYS: Final = 14
_SATURDAY: Final = 5
_YEAR_DIGITS: Final = 4
_ROW_LEN: Final = 2  # [date, name]

Holidays = dict[int, frozenset[datetime.date]]


@unique
class MarketStatus(Enum):
    OPEN = "OPEN"
    CLOSED_HOURS = "CLOSED_HOURS"
    CLOSED_WEEKEND = "CLOSED_WEEKEND"
    CLOSED_HOLIDAY = "CLOSED_HOLIDAY"
    NO_CALENDAR = "NO_CALENDAR"  # no holiday data for that year: unknown, treated as closed


class CalendarError(ValueError):
    """The data file is missing, unreadable or malformed. Callers treat it as "no calendar" (fail closed)."""


_TOP_KEYS: Final = frozenset({"source", "fetched", "segment", "note", "holidays"})


def _parse_year(key: object, rows: object) -> tuple[int, frozenset[datetime.date]]:
    if not isinstance(key, str) or not key.isdigit() or len(key) != _YEAR_DIGITS:
        raise CalendarError(f"year key {key!r} is not a four-digit year")
    year = int(key)
    if not isinstance(rows, list) or not rows:
        raise CalendarError(f"year {year} has no holiday rows")
    days: set[datetime.date] = set()
    for row in rows:
        if not isinstance(row, list) or len(row) != _ROW_LEN or not all(isinstance(x, str) and x for x in row):
            raise CalendarError(f"year {year}: row {row!r} is not [date, name]")
        day = datetime.date.fromisoformat(row[0])
        if day.year != year:
            raise CalendarError(f"year {year}: {day} is outside its year")
        if day in days:
            raise CalendarError(f"year {year}: {day} is listed twice")
        days.add(day)
    return year, frozenset(days)


@lru_cache(maxsize=1)
def _load() -> Holidays:
    """Validated holiday data; ANY problem raises ``CalendarError`` (never a bare KeyError/JSON error)."""
    try:
        raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or not raw.keys() <= _TOP_KEYS or not isinstance(raw.get("holidays"), dict):
            raise CalendarError("calendar file has unknown keys or no holidays object")
        if not raw["holidays"]:
            raise CalendarError("calendar file lists no years")
        return dict(_parse_year(k, v) for k, v in raw["holidays"].items())
    except CalendarError:
        raise
    except (OSError, ValueError, TypeError) as exc:  # unreadable file, bad JSON, bad date
        raise CalendarError(str(exc)) from exc


def _table(holidays: Holidays | None) -> Holidays:
    """``holidays`` for tests; production reads the file. A bad file is an EMPTY table: every year answers
    NO_CALENDAR (the gate's "unconfirmed" block), never an exception."""
    if holidays is not None:
        return holidays
    try:
        return _load()
    except CalendarError:
        return {}


def _day_status(day: datetime.date, holidays: Holidays) -> MarketStatus | None:
    """The day-level closure (None = a trading day), or NO_CALENDAR when the year has no data."""
    if day.year not in holidays:
        return MarketStatus.NO_CALENDAR
    if day.weekday() >= _SATURDAY:
        return MarketStatus.CLOSED_WEEKEND
    if day in holidays[day.year]:
        return MarketStatus.CLOSED_HOLIDAY
    return None


def _local(now: datetime.datetime) -> datetime.datetime:
    if not isinstance(now, datetime.datetime) or now.utcoffset() is None:
        raise ValueError(f"now must be a timezone-aware datetime, got {now!r}")
    return now.astimezone(IST)


def market_status(now: datetime.datetime, holidays: Holidays | None = None) -> MarketStatus:
    """The status at ``now`` (timezone-aware, any zone). ``holidays`` is for tests; production reads the data file."""
    local = _local(now)
    closed = _day_status(local.date(), _table(holidays))
    if closed is not None:
        return closed
    return MarketStatus.OPEN if SESSION_OPEN <= local.time() < SESSION_CLOSE else MarketStatus.CLOSED_HOURS


def is_market_open(now: datetime.datetime, holidays: Holidays | None = None) -> bool:
    return market_status(now, holidays) is MarketStatus.OPEN


def next_open(now: datetime.datetime, holidays: Holidays | None = None) -> datetime.datetime | None:
    """The next 09:15 IST after ``now`` on a trading day; None when the search reaches a year with no data (the answer
    would be a guess)."""
    local = _local(now)
    table = _table(holidays)
    for offset in range(_LOOKAHEAD_DAYS + 1):
        day = local.date() + datetime.timedelta(days=offset)
        status = _day_status(day, table)
        if status is MarketStatus.NO_CALENDAR:
            return None
        opens = datetime.datetime.combine(day, SESSION_OPEN, IST)
        if status is None and opens > local:
            return opens
    return None


__all__ = ["DATA_FILE", "CalendarError", "MarketStatus", "is_market_open", "market_status", "next_open"]
