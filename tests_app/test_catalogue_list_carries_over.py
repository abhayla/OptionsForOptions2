"""Defect 2026-11-27 (PR #722): a process started before 08:30 IST had no instrument list from 08:30 until restarted.

Spec basis: REQ-053 AC-3 (the picker offers nothing from a list of an earlier session, as written) + F-56 (the list is
current from 08:30 IST; the refresh's first scheduled load is 08:35); ADR-016..019 (no load, no silence).
Class: the start-up load at 08:07 counted as the scheduler's last run, so the first reload was due at 09:07, not 08:35,
and a refused or failed run was the only thing that logged. Fix: the first in-window run of a day is due at 08:35
whatever ran earlier. The picker is NOT changed (owner question LJ-3).

The database stamps last_seen_at with its own clock, so the test keeps its own stamp (set by the fake Kite load) and
judges the list with the real ``loaded_before`` against the injected clock; the rows are the real slice.
"""

from __future__ import annotations

import datetime
import io
import logging
from datetime import timedelta, timezone

import pytest
from ofo_app import catalogue_load, catalogue_picker
from ofo_app.catalogue_refresh import FAILED, LOADED, REFUSED, RefreshScheduler
from test_catalogue_load_command import AS_OF, _csv, _set_percent

IST = timezone(timedelta(hours=5, minutes=30))
DAY = datetime.datetime(2026, 12, 1, tzinfo=IST)  # a Tuesday; SENSEX has expiries to 2026-12-31 in the slice
PUBLISH = datetime.time(8, 30)


def at(hour: int, minute: int) -> datetime.datetime:
    return DAY.replace(hour=hour, minute=minute)


class Clock:
    def __init__(self, now: datetime.datetime) -> None:
        self.at = now

    def __call__(self) -> datetime.datetime:
        return self.at


async def test_a_process_started_before_0830_reloads_at_0835_not_one_interval_later():
    clock, calls = Clock(at(8, 7)), []

    async def load() -> int:
        calls.append(clock.at)
        return 0

    sch = RefreshScheduler(load, now=clock)
    assert await sch.step() == LOADED  # start-up 08:07
    clock.at = at(8, 34)
    assert await sch.step() is None  # still before the window
    clock.at = at(8, 35)
    assert await sch.step() == LOADED, "the 08:35 run is skipped because the 08:07 start-up run counts as the last"
    assert calls == [at(8, 7), at(8, 35)]
    clock.at = at(8, 40)
    assert await sch.step() is None  # and then hourly again


async def test_the_pcs_sequence_start_0807_empty_at_0830_todays_list_after_the_0835_refresh(app_engine, monkeypatch):
    clock = Clock(at(8, 7))
    stamp: list[datetime.datetime | None] = [None]

    async def fake_current(conn, today):  # the real rule on the injected clock and the load's injected stamp
        return not catalogue_picker.loaded_before(stamp[0], clock.at, PUBLISH)

    monkeypatch.setattr(catalogue_picker, "list_is_current", fake_current)
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await _set_percent(conn, "100")

            async def fake_kite_load() -> int:  # Kite's answer: the slice; the load happens "now" on the clock
                assert await catalogue_load.run(conn, _csv(), io.StringIO(), as_of=AS_OF) == 0
                stamp[0] = clock.at
                return 0

            sch = RefreshScheduler(fake_kite_load, now=clock)
            day = DAY.date()
            assert await sch.step() == LOADED  # API start-up 08:07 (yesterday's list, as Kite has not published)
            assert await catalogue_picker.pickable_expiries(conn, "SENSEX", day)  # list_is_current: before 08:30
            clock.at = at(8, 30)
            assert await catalogue_picker.pickable_expiries(conn, "SENSEX", day) == []  # REQ-053 AC-3, as written
            assert await catalogue_picker.pickable_contracts(conn, "SENSEX", day) == []
            clock.at = at(8, 35)
            assert await sch.step() == LOADED
            assert await catalogue_picker.pickable_expiries(conn, "SENSEX", day)  # today's list again
        finally:
            await trans.rollback()


@pytest.mark.parametrize(("failure", "outcome", "word"), [("refuse", REFUSED, "refused"), ("raise", FAILED, "failed")])
async def test_a_refresh_with_no_session_says_why_in_one_line(caplog, failure, outcome, word):
    clock = Clock(at(8, 35))

    async def load() -> int:
        if failure == "raise":
            raise PermissionError("no Kite session")
        return 1

    sch = RefreshScheduler(load, now=clock)
    sch._last_started = at(8, 7)  # the start-up run
    with caplog.at_level(logging.INFO, logger="ofo_app.catalogue_refresh"):
        assert await sch.step() == outcome
    lines = [r for r in caplog.records if r.name == "ofo_app.catalogue_refresh"]
    assert len(lines) == 1 and word in lines[0].getMessage()
    assert "no Kite session" not in lines[0].getMessage()  # the type only, never the message


async def test_a_loaded_refresh_logs_one_info_line(caplog):
    async def load() -> int:
        return 0

    with caplog.at_level(logging.INFO, logger="ofo_app.catalogue_refresh"):
        assert await RefreshScheduler(load, now=Clock(at(8, 35))).attempt() == LOADED
    lines = [r for r in caplog.records if r.name == "ofo_app.catalogue_refresh"]
    assert [r.levelno for r in lines] == [logging.INFO]
