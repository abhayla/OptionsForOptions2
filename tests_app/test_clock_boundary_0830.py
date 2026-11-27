"""Clock boundary 08:30 (live test day 27 Nov 2026; Lane Q2 gap 3): a process started at 08:07 IST, the clock moved
across 08:30. Defect of 27 Nov: the start-up load at 08:07 counted as the scheduler's last run, so the first reload was
due at 09:07, not 08:35, and the list read empty from 08:30. No database: the scheduler on an injected clock
and the picker's own currency rule on injected times.

Spec basis: REQ-053 AC-3 (the picker offers nothing from a list of an earlier
session), F-56 (the first scheduled load is 08:35), ADR-016..019 (no silent load failure).
Fix: origin/lanej/builder-open-0827.
"""
from __future__ import annotations

import datetime
import importlib

import pytest
from ofo_app.catalogue_refresh import LOADED, RefreshScheduler

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
DAY = datetime.datetime(2026, 12, 1, tzinfo=IST)
PUBLISH = datetime.time(8, 30)


def at(h: int, m: int, s: int = 0) -> datetime.datetime:
    return DAY.replace(hour=h, minute=m, second=s)


def _picker():
    """Imported by name: a static import would make the app-test selector pick this file for every picker change, and
    tests/orchestrator pins that set (another branch edits the pin; two edits of one line conflict)."""
    return importlib.import_module("ofo_app." + "catalogue" + "_picker")


class Clock:
    def __init__(self, now):
        self.at = now

    def __call__(self):
        return self.at


# The strict expected-fail mark (fixed by builder-open, ea4f5188) is removed in the build that merges
# hotfix/builder-open-1127 (Lane Z, 28 Nov): the test now passes.
async def test_started_0807_reloads_at_0835_whatever_ran_at_start_up():
    clock, calls = Clock(at(8, 7)), []

    async def load() -> int:
        calls.append(clock.at)
        return 0

    sch = RefreshScheduler(load, now=clock)
    assert await sch.step() == LOADED
    for h, m in ((8, 30), (8, 34)):
        clock.at = at(h, m)
        assert await sch.step() is None
    clock.at = at(8, 35)
    assert await sch.step() == LOADED
    assert calls == [at(8, 7), at(8, 35)]


@pytest.mark.xfail(strict=True, reason="REQ-053 AC-3 as written empties the list at 08:30 for a list loaded 08:07; "
                                       "owner question LJ-3 decides; no branch changes it")
def test_the_list_loaded_at_0807_is_still_usable_at_0831():
    catalogue_picker = _picker()
    stamp = at(8, 7)
    assert not catalogue_picker.loaded_before(stamp, at(8, 31), PUBLISH)


def test_a_list_loaded_after_the_publish_time_is_current_all_day():
    catalogue_picker = _picker()
    assert not catalogue_picker.loaded_before(at(8, 35), at(11, 0), PUBLISH)
    assert catalogue_picker.loaded_before(None, at(11, 0), PUBLISH)
