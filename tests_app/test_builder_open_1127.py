"""ADR-330 (61) (owner, 27 Nov evening): from the publish time until today's contract list has loaded, the builder keeps
working on YESTERDAY's list and says so in one line; contracts that expired yesterday are left out; every leg is checked
again against today's list before any order. Lane J2's two review findings of the refresh: the opening of the refresh
window comes from the setting ``facts.contract_list_publish_time`` (publish time + 5 minutes), and a run that did not
load is tried again in minutes, not after an hour.

Spec basis: ADR-330 (61); REQ-053 AC-3; ADR-016 to ADR-019 (no silent substitution, no silent load failure).
No database: the scheduler on an injected clock and the pure list notice.
"""
from __future__ import annotations

import datetime
import logging

from ofo_app import catalogue_picker, catalogue_refresh
from ofo_app.catalogue_refresh import FAILED, LOADED, REFUSED, TIMED_OUT, RefreshScheduler
from ofo_app.routes import execute as execute_route

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
DAY = datetime.datetime(2026, 12, 1, tzinfo=IST)  # a Tuesday
HEALTH = execute_route.DataHealth
PUBLISH = catalogue_refresh.default_publish_time()  # the registry default (08:30), never retyped


def at(h: int, m: int, s: int = 0) -> datetime.datetime:
    return DAY.replace(hour=h, minute=m, second=s)


class Clock:
    def __init__(self, now: datetime.datetime) -> None:
        self.at = now

    def __call__(self) -> datetime.datetime:
        return self.at


def _loader(clock: Clock, codes: list):
    """A load that answers the next code (an int, or an exception to raise) and records when it ran."""
    calls: list[datetime.datetime] = []

    async def load() -> int:
        calls.append(clock.at)
        code = codes.pop(0) if len(codes) > 1 else codes[0]
        if isinstance(code, BaseException):
            raise code
        return code
    load.calls = calls  # type: ignore[attr-defined]
    return load


# ---- finding 1: the window opens at the SETTING + 5 minutes ----------------------------------------------------------

def test_the_window_opens_five_minutes_after_the_publish_time_of_the_registry():
    assert datetime.time(8, 30) == PUBLISH and catalogue_refresh.window_open(PUBLISH) == datetime.time(8, 35)
    assert catalogue_refresh.window_open(datetime.time(9, 0)) == datetime.time(9, 5)
    assert catalogue_refresh.window_open(datetime.time(23, 58)) == datetime.time(0, 3)  # wraps, never raises


async def test_a_changed_publish_time_moves_the_first_reload_with_it():
    clock = Clock(at(8, 7))
    load = _loader(clock, [0])
    published = [datetime.time(9, 0)]

    async def publish_time() -> datetime.time:
        return published[0]
    sch = RefreshScheduler(load, now=clock, publish_time=publish_time)
    assert await sch.step() == LOADED  # start-up, any hour
    clock.at = at(8, 35)
    assert await sch.step() is None  # 08:35 is no longer the opening
    clock.at = at(9, 4)
    assert await sch.step() is None
    clock.at = at(9, 5)
    assert await sch.step() == LOADED
    assert load.calls == [at(8, 7), at(9, 5)]


async def test_a_publish_time_that_cannot_be_read_keeps_the_last_one_and_is_logged(caplog):
    clock = Clock(at(8, 7))
    load = _loader(clock, [0])
    broken: list[bool] = [False]

    async def publish_time() -> datetime.time:
        if broken[0]:
            raise OSError("down")
        return datetime.time(9, 0)
    sch = RefreshScheduler(load, now=clock, publish_time=publish_time)
    await sch.step()
    broken[0] = True
    clock.at = at(8, 40)
    with caplog.at_level(logging.ERROR, logger="ofo_app.catalogue_refresh"):
        assert await sch.step() is None  # still 09:00 + 5, never the default 08:35 on a guess
    assert any("publish time could not be read: OSError" in r.getMessage() for r in caplog.records)


# ---- finding 2: a run that did not load is tried again in minutes ----------------------------------------------------

async def test_a_load_that_fails_at_0835_is_tried_again_within_minutes_and_the_old_list_stays(caplog):
    clock = Clock(at(8, 7))
    load = _loader(clock, [0, OSError("no Kite"), 0])
    sch = RefreshScheduler(load, now=clock)
    assert await sch.step() == LOADED
    clock.at = at(8, 35)
    with caplog.at_level(logging.ERROR, logger="ofo_app.catalogue_refresh"):
        assert await sch.step() == FAILED
    assert any("the previous list stays in use" in r.getMessage() for r in caplog.records)
    clock.at = at(8, 37)
    assert await sch.step() is None  # not before the retry interval
    clock.at = at(8, 38)
    assert await sch.step() == LOADED
    assert load.calls == [at(8, 7), at(8, 35), at(8, 38)]
    clock.at = at(9, 37)
    assert await sch.step() is None  # a run that loaded waits its hour (from 08:38)
    clock.at = at(9, 38)
    assert await sch.step() == LOADED


async def test_a_refused_and_a_timed_out_run_are_retried_in_minutes_too():
    for code, outcome in ((1, REFUSED), (TimeoutError(), TIMED_OUT)):
        clock = Clock(at(8, 35))
        load = _loader(clock, [code, 0])
        sch = RefreshScheduler(load, now=clock, timeout=0.5)
        assert await sch.step() == outcome
        clock.at = at(8, 38)
        assert await sch.step() == LOADED, outcome


async def test_a_run_that_keeps_failing_does_not_loop_faster_than_the_retry_interval():
    clock = Clock(at(10, 0))
    load = _loader(clock, [OSError("x")])
    sch = RefreshScheduler(load, now=clock)
    await sch.step()  # start-up
    for minute in (1, 2):
        clock.at = at(10, minute)
        assert await sch.step() is None
    assert len(load.calls) == 1


# ---- the line said while yesterday's list is in use ----------------------------------------------------------------

def test_the_notice_is_one_line_with_the_list_date_and_the_expected_time():
    day = datetime.date(2026, 11, 26)
    assert catalogue_picker.list_notice(day, False, PUBLISH) == (
        "Contract list of 26 Nov. Today's list loads at about 08:35.")
    assert catalogue_picker.list_notice(day, True, PUBLISH) is None  # today's list in use: no line
    assert catalogue_picker.list_notice(None, False, PUBLISH) is None  # no list at all: nothing to say it of
    assert catalogue_picker.list_notice(day, False, datetime.time(9, 0)) == (
        "Contract list of 26 Nov. Today's list loads at about 09:05.")  # from the setting, never retyped


# ---- every leg is checked again against today's list before any order ----------------------------------------------

def test_the_pre_order_data_check_calls_yesterdays_list_stale_until_todays_has_loaded():
    loaded_0807 = at(8, 7)
    assert execute_route._list_health(loaded_0807, at(8, 31), PUBLISH) is HEALTH.STALE  # blocks the order
    assert execute_route._list_health(at(8, 36), at(8, 40), PUBLISH) is HEALTH.HEALTHY  # today's list in use
    assert execute_route._list_health(None, at(8, 31), PUBLISH) is HEALTH.UNAVAILABLE
