"""Defect 2026-11-27 (PR #722): a process started before 08:30 IST lost its instrument list at 08:30.

Spec basis: REQ-053 AC-3 + F-56 (the list is current from 08:30 IST; the refresh's first scheduled load is 08:35);
ADR-016..019 (no silent substitution: yesterday's list in use is SAID, in the log and on the expiries reply).
Class: the start-up load at 08:07 stamped the list before the 08:30 publish time, the scheduler counted it as the last
run (next due 09:07), and every picker read answered [] meanwhile. Fix: the first in-window run of a day is due at
08:35 whatever ran earlier; the picker keeps offering the previous list until today's has loaded, and says so.
"""

from __future__ import annotations

import datetime
import io
import logging
from datetime import timedelta, timezone

import pytest
from ofo_app import catalogue_load, catalogue_picker
from ofo_app.catalogue_refresh import LOADED, RefreshScheduler
from test_catalogue_load_command import AS_OF, _csv, _set_percent

IST = timezone(timedelta(hours=5, minutes=30))
STARTED = datetime.datetime(2026, 10, 19, 8, 7, tzinfo=IST)  # Monday: the API's start-up load
# last_seen_at is the DATABASE clock (cannot be backdated by the app role), so the judging day moves instead: a day
# before the real load is a session whose list is loaded (current); a day after it (Tue 2026-12-01 12:00, SENSEX has
# expiries to 2026-12-31) is a session whose list is not loaded yet.
LOAD_DAY, NEXT_DAY = datetime.date(2026, 9, 28), datetime.date(2026, 12, 1)


class Clock:
    def __init__(self, at: datetime.datetime) -> None:
        self.at = at

    def __call__(self) -> datetime.datetime:
        return self.at


async def test_a_process_started_before_0830_reloads_at_0835_not_one_interval_later():
    clock, calls = Clock(STARTED), []

    async def load() -> int:
        calls.append(clock.at)
        return 0

    sch = RefreshScheduler(load, now=clock)
    assert await sch.step() == LOADED  # start-up 08:07
    clock.at = STARTED.replace(hour=8, minute=34)
    assert await sch.step() is None  # still before the window
    clock.at = STARTED.replace(hour=8, minute=35)
    assert await sch.step() == LOADED, "the 08:35 run is skipped because the 08:07 start-up run counts as the last"
    assert len(calls) == len([STARTED, STARTED])
    clock.at = STARTED.replace(hour=8, minute=40)
    assert await sch.step() is None  # and then hourly again


async def test_a_load_that_ends_unloaded_is_logged_with_its_reason(caplog):
    clock = Clock(STARTED.replace(hour=8, minute=35))

    async def refuse() -> int:
        return 1

    with caplog.at_level(logging.INFO, logger="ofo_app.catalogue_refresh"):
        assert await RefreshScheduler(refuse, now=clock).attempt() == "refused"
    assert any("refused" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("today_loaded", [True, False])
async def test_the_picker_keeps_yesterdays_list_until_todays_has_loaded(app_engine, caplog, today_loaded):
    """today_loaded: the session's list is loaded (current) or not yet (the 08:30 passed, the refresh has not run or
    could not run, e.g. no Kite session): the rows offered are the same; the second case is said in the log."""
    day = LOAD_DAY if today_loaded else NEXT_DAY
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await _set_percent(conn, "100")
            assert await catalogue_load.run(conn, _csv(), io.StringIO(), as_of=AS_OF) == 0
            with caplog.at_level(logging.WARNING, logger="ofo_app.catalogue_picker"):
                expiries = await catalogue_picker.pickable_expiries(conn, "SENSEX", day)
                contracts = await catalogue_picker.pickable_contracts(conn, "SENSEX", day, expiries[-1])
            assert expiries and contracts and all(e >= day for e in expiries)
            status = await catalogue_picker.list_status(conn, day)
            assert status.current is today_loaded and status.list_day is not None
            # ADR-330 (61): the ONE line is said while yesterday's list is in use, and only then
            assert (status.notice is None) is today_loaded
            if not today_loaded:
                assert str(status.notice) == (f"Contract list of {status.list_day.day:02d} {status.list_day:%b}. "
                                              "Today's list loads at about 08:35.")
            said = [r for r in caplog.records if "not loaded" in r.getMessage()]
            assert bool(said) is (not today_loaded), "yesterday's list in use must be said once in the log"
            with caplog.at_level(logging.WARNING, logger="ofo_app.catalogue_picker"):
                await catalogue_picker.pickable_expiries(conn, "SENSEX", day)
            assert len([r for r in caplog.records if "not loaded" in r.getMessage()]) == len(said)  # once, not per read
        finally:
            await trans.rollback()


async def test_with_no_list_loaded_at_all_nothing_is_offered(app_engine):
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            assert await catalogue_picker.pickable_expiries(conn, "NIFTY", LOAD_DAY) == []
            assert (await catalogue_picker.list_status(conn, LOAD_DAY)).list_day is None
        finally:
            await trans.rollback()
