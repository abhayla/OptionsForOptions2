"""Guard for finding fixture-dates-expire-with-the-clock (issue #649), no database.

The scenario library carries fixed real dates; the database's lifecycle guard (0005, ADR-057) refuses to re-list a
contract whose expiry is before the DATABASE's today. ``scenario_mode.read`` (the one reader of scenario files) moves
every date by one whole-week offset so the earliest expiry is always ahead of today; the NSE holidays move with it
while a scenario is requested. These tests fail if the shift is not applied, if any loaded file still carries an
expiry in the past, or if a reader bypasses ``read``.
"""
from __future__ import annotations

import datetime
import json
import pathlib
import re

from ofo import market_calendar as mc
from ofo.timeutil import IST
from ofo_app import scenario_mode as sm

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _today() -> datetime.date:
    return datetime.datetime.now(IST).date()


def test_fixture_dates_every_loaded_file_has_its_expiries_ahead_of_today():
    """The bomb cannot go off: read through ``read``, no scenario file's earliest expiry is before today + lead."""
    floor = _today() + datetime.timedelta(days=sm.LEAD_DAYS)
    late = {f.name: min(e) for f in sm.library_files() if (e := sm.expiries(sm.read(f))) and min(e) < floor}
    assert late == {}, late


def test_fixture_dates_shift_is_applied_to_every_date_and_keeps_the_weekday():
    raw = json.loads(sm.scenario_path("ADJ-02").read_text(encoding="utf-8"))
    step = sm.date_shift()
    assert step.days % 7 == 0 and step >= datetime.timedelta(0)
    got = sm.read(sm.scenario_path("ADJ-02"))
    assert got["expiry"] == (datetime.date.fromisoformat(raw["expiry"]) + step).isoformat()
    assert got["clock"]["ist"] == sm.shifted(raw["clock"]["ist"])
    assert got["clock"]["ist"][10:] == raw["clock"]["ist"][10:]  # the time of day is untouched
    assert got["position"]["entry"]["clock"] == sm.shifted(raw["position"]["entry"]["clock"])
    stamp = raw["broker"]["quote"]["legs"][0]["timestamp"]  # Kite's "YYYY-MM-DD HH:MM:SS" form
    assert got["broker"]["quote"]["legs"][0]["timestamp"] == sm.shifted(stamp) and " " in stamp
    assert got["position"]["legs"][0]["tradingsymbol"] == raw["position"]["legs"][0]["tradingsymbol"]  # opaque id
    assert got["title"] == raw["title"]  # prose untouched
    assert sm.load("ADJ-02").clock() == datetime.datetime.fromisoformat(raw["clock"]["ist"]) + step


def test_fixture_dates_offset_rule_whole_weeks_smallest_that_clears_the_lead():
    exp = datetime.date(2026, 11, 3)
    assert sm.shift_weeks(datetime.date(2026, 10, 1), exp) == 0  # not needed yet: no shift
    assert sm.shift_weeks(datetime.date(2026, 11, 8), exp) == 2  # 11-03 -> 11-17 >= 11-15  # noqa: PLR2004
    for today in (datetime.date(2026, 11, 8), datetime.date(2027, 6, 30), datetime.date(2031, 2, 1)):
        moved = exp + datetime.timedelta(weeks=sm.shift_weeks(today, exp))
        floor = today + datetime.timedelta(days=sm.LEAD_DAYS)
        assert floor <= moved < floor + datetime.timedelta(days=7)


def test_fixture_dates_holidays_move_with_the_scenario_world_only(monkeypatch):
    def at(day: datetime.date) -> mc.MarketStatus:
        return mc.market_status(datetime.datetime.combine(day, datetime.time(12, 0), IST))

    diwali = datetime.date(2026, 11, 10)  # NSE F&O holiday (market_calendar.json)
    two = datetime.timedelta(weeks=2)
    monkeypatch.setattr(sm, "_shift", [two])
    monkeypatch.delenv("OFO_SCENARIO", raising=False)
    assert at(diwali) is mc.MarketStatus.CLOSED_HOLIDAY  # no scenario: the real calendar
    monkeypatch.setenv("OFO_SCENARIO", "ADJ-02")
    assert at(diwali + two) is mc.MarketStatus.CLOSED_HOLIDAY  # the holiday sits where the shifted fixture expects it
    assert at(datetime.date(2026, 12, 25) + two) is mc.MarketStatus.CLOSED_HOLIDAY  # into 2027: still covered


def test_fixture_dates_no_reader_bypasses_the_shifting_reader():
    """Structural: app code and scripts read scenario files only through ``scenario_mode.read``."""
    bypass = re.compile(r"(scenario_path|frame_path)\([^)]*\)\.read_text")
    hits = [f"{p.relative_to(ROOT)}:{n}" for base in ("backend/ofo_app", "scripts") for p in (ROOT / base).rglob("*.py")
            for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1) if bypass.search(line)]
    assert hits == [], hits
