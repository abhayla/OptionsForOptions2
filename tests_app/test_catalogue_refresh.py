"""W-133 (REQ-053 AC-3, finding daily-load-misses-intraday-additions / F-33): the scheduled catalogue refresh.

Spec basis (quoted): REQ-053 AC-3 "Before a leg is added, the builder checks what Zerodha data allows"; F-33 "a
once-a-day catalogue load misses strikes listed after it ran". The scheduler runs ``catalogue_load.load_once``
unchanged, so the guards of ``apply_update`` apply; these tests use the real-instrument slice
(tests/fixtures/instruments) and a fake clock.
Scheduler tests need no database; the list tests run on real PostgreSQL inside a transaction that is rolled back.
"""

from __future__ import annotations

import asyncio
import datetime
import functools
import io
import logging
import threading
from datetime import timedelta, timezone
from decimal import Decimal

import pytest
from ofo_app import catalogue_load, catalogue_picker, catalogue_refresh, main
from ofo_app.catalogue_refresh import BUSY, FAILED, LOADED, REFUSED, TIMED_OUT, RefreshScheduler
from sqlalchemy import text
from test_catalogue_load_command import AS_OF, TABLE, _count, _csv, _lines_where, _settings

IST = timezone(timedelta(hours=5, minutes=30))
MONDAY = datetime.datetime(2026, 10, 19, 9, 0, tzinfo=IST)
SATURDAY = datetime.datetime(2026, 10, 17, 3, 0, tzinfo=IST)  # the Saturday before MONDAY


class Clock:
    def __init__(self, at: datetime.datetime) -> None:
        self.at = at

    def __call__(self) -> datetime.datetime:
        return self.at


TWO_RUNS, THREE_RUNS, FIVE_TICKS = 2, 3, 5

#: The shared test catalogue may already hold a real list (#497), and loading the slice onto it delists most of it,
#: which the 10% guard rightly refuses. A FIRST load in these tests lifts the guard (the work rolls back); every later
#: load, and every refusal asserted, runs under the real 10%.
_ONTO_ANY_CATALOGUE = _settings("100")


FAIL_FAST_SECONDS = 10


def fail_fast(test):
    """A scheduler test that hangs fails after ``FAIL_FAST_SECONDS`` with a TimeoutError, not at the CI job's limit."""
    @functools.wraps(test)
    async def wrapper(*args, **kwargs):
        async with asyncio.timeout(FAIL_FAST_SECONDS):
            return await test(*args, **kwargs)
    return wrapper


def _scheduler(load, clock: Clock, **kwargs) -> RefreshScheduler:
    return RefreshScheduler(load, now=clock, **kwargs)


# ---- the timetable -----------------------------------------------------------------------------------------------

@pytest.mark.parametrize(("at", "expected"), [
    (datetime.datetime(2026, 10, 19, 8, 34, tzinfo=IST), False),
    (datetime.datetime(2026, 10, 19, 8, 35, tzinfo=IST), True),
    (datetime.datetime(2026, 10, 19, 15, 45, tzinfo=IST), True),
    (datetime.datetime(2026, 10, 19, 15, 46, tzinfo=IST), False),
    (datetime.datetime(2026, 10, 24, 10, 0, tzinfo=IST), False),  # Saturday
    (datetime.datetime(2026, 10, 25, 10, 0, tzinfo=IST), False),  # Sunday
    (datetime.datetime(2026, 10, 19, 3, 10, tzinfo=datetime.UTC), True),  # 08:40 IST, given in UTC
])
def test_the_window_is_weekdays_0835_to_1545_ist(at, expected):
    assert catalogue_refresh.in_window(at) is expected


@pytest.mark.parametrize(("env", "expected"), [
    ({}, False), ({"CATALOGUE_REFRESH": "1"}, True), ({"LIVE_MARKET": "1"}, True),
    ({"LIVE_MARKET": "1", "CATALOGUE_REFRESH": "0"}, False), ({"CATALOGUE_REFRESH": "off"}, False),
    ({"CATALOGUE_REFRESH": "true"}, True),
])
def test_the_refresh_is_off_unless_asked_and_on_by_default_with_live_market(env, expected):
    assert catalogue_refresh.refresh_requested(env) is expected


@fail_fast
async def test_it_loads_at_start_up_on_any_day_then_only_inside_the_window_one_interval_apart():
    clock, calls = Clock(SATURDAY), []

    async def load() -> int:
        calls.append(clock.at)
        return 0

    sch = _scheduler(load, clock)
    assert await sch.step() == LOADED and len(calls) == 1  # start-up: Saturday 03:00, still loads
    clock.at = SATURDAY + timedelta(hours=2)
    assert await sch.step() is None  # outside the window and a non-trading day
    clock.at = MONDAY - timedelta(minutes=26)  # 08:34 Monday
    assert await sch.step() is None
    clock.at = MONDAY - timedelta(minutes=25)  # 08:35 Monday: in the window, > 60 min since the last start
    assert await sch.step() == LOADED and len(calls) == TWO_RUNS
    clock.at += timedelta(minutes=59)
    assert await sch.step() is None
    clock.at += timedelta(minutes=1)
    assert await sch.step() == LOADED and len(calls) == THREE_RUNS
    clock.at = MONDAY.replace(hour=16)  # after 15:45
    assert await sch.step() is None


@fail_fast
async def test_two_runs_never_overlap():
    started, release, calls = asyncio.Event(), asyncio.Event(), []

    async def load() -> int:
        calls.append(1)
        started.set()
        await release.wait()
        return 0

    sch = _scheduler(load, Clock(MONDAY))
    first = asyncio.create_task(sch.attempt())
    await started.wait()
    assert await sch.attempt() == BUSY and len(calls) == 1
    release.set()
    assert await first == LOADED


@fail_fast
async def test_a_failing_run_logs_its_code_only_and_retries_on_schedule(caplog):
    clock, calls = Clock(MONDAY), []

    async def load() -> int:
        calls.append(1)
        raise ConnectionError("https://api.kite.trade/instruments?secret=abc")

    sch = _scheduler(load, clock)
    with caplog.at_level(logging.ERROR):
        assert await sch.step() == FAILED
    assert "ConnectionError" in caplog.text and "secret" not in caplog.text and "kite.trade" not in caplog.text
    clock.at += timedelta(minutes=30)
    assert await sch.step() is None  # not a retry loop
    clock.at += timedelta(minutes=30)
    assert await sch.step() == FAILED and len(calls) == TWO_RUNS  # on schedule


@fail_fast
async def test_a_refused_list_is_reported_as_refused():
    async def load() -> int:
        return 1

    assert await _scheduler(load, Clock(MONDAY)).attempt() == REFUSED


@fail_fast
async def test_a_hung_load_times_out_and_never_blocks_other_work():
    """Standing item (a): the higher-priority work (a stand-in for the live feed and a request) keeps running."""
    ticks = []

    async def hung() -> int:
        await asyncio.Event().wait()
        return 0

    async def other_work() -> None:
        for _ in range(FIVE_TICKS):
            ticks.append(1)
            await asyncio.sleep(0.005)

    sch = _scheduler(hung, Clock(MONDAY), timeout=0.05)
    outcome, _ = await asyncio.gather(sch.attempt(), other_work())
    assert outcome == TIMED_OUT and len(ticks) == FIVE_TICKS
    assert await sch.attempt() == TIMED_OUT  # the lock was released: the next run is not stuck BUSY


@fail_fast
async def test_a_hung_download_carries_a_socket_timeout_so_its_thread_ends_and_the_run_times_out(monkeypatch):
    """The fetch passes a socket timeout to the door; a fetch past it ends with the timeout code, no thread is left."""
    import threading  # noqa: PLC0415 - local to this one test
    from ofo.instruments import downloader  # noqa: PLC0415

    seen: dict = {}
    release, ended = threading.Event(), threading.Event()

    def hung_open(url, *, timeout=None, **_kw):
        seen["timeout"] = timeout
        try:
            release.wait(5)  # stands in for a socket that never answers, until its timeout would fire
            raise TimeoutError
        finally:
            ended.set()

    monkeypatch.setattr(downloader, "open_url", hung_open)

    async def load() -> int:
        return await catalogue_load.load_once(_settings("10"), io.StringIO())

    sch = _scheduler(load, Clock(MONDAY), timeout=0.2)
    assert await sch.attempt() == TIMED_OUT
    assert seen["timeout"] is not None and 0 < seen["timeout"] <= catalogue_refresh.RUN_TIMEOUT_SECONDS
    assert not ended.is_set()  # the run gave up while the fetch was still going
    release.set()  # the socket timeout fires: the fetch ends, its thread returns to the pool
    assert await asyncio.to_thread(ended.wait, 5)


@fail_fast
async def test_the_parse_of_a_full_list_runs_off_the_event_loop(monkeypatch):
    """Standing item (a), attack 2: a blocking parse leaves the loop free to serve requests. The parse blocks until the
    requests have been served; if the parse ran ON the loop they could never run and the wait would time out (no
    wall-clock threshold: the order of events is the proof)."""
    served = threading.Event()
    parse_saw_served = []

    def slow_parse(_stream):
        parse_saw_served.append(served.wait(5))
        raise ValueError("stop after the parse")

    monkeypatch.setattr(catalogue_load, "parse_rows_naming_the_row", slow_parse)
    ticks = []

    async def request_served_meanwhile() -> None:
        for _ in range(FIVE_TICKS):
            ticks.append(len(ticks))
            await asyncio.sleep(0)
        served.set()

    code, _ = await asyncio.gather(catalogue_load.run(None, "x", _settings("10"), io.StringIO()),
                                   request_served_meanwhile())
    assert code == 1  # the parse's refusal, nothing written
    assert len(ticks) == FIVE_TICKS and parse_saw_served == [True]  # served while the parse was still blocking


@fail_fast
async def test_shutdown_stops_the_task_and_the_run_in_flight():
    started, cancelled = asyncio.Event(), []

    async def load() -> int:
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.append(1)
            raise
        return 0

    task = asyncio.create_task(_scheduler(load, Clock(MONDAY)).run_forever())
    await started.wait()
    await catalogue_refresh.stop(task)
    assert task.done() and cancelled == [1]
    await catalogue_refresh.stop(None)  # nothing started: nothing to stop


@fail_fast
async def test_the_lifespan_starts_the_task_only_when_asked_and_stops_it_on_shutdown(monkeypatch):
    events = []

    async def noop() -> None:
        return None

    monkeypatch.setattr(main, "verify_pool_budget", noop)
    monkeypatch.setattr(main, "close_db", noop)
    monkeypatch.setattr(catalogue_refresh, "start", lambda: events.append("start") or "task")

    async def stop(task) -> None:
        events.append(("stop", task))

    monkeypatch.setattr(catalogue_refresh, "stop", stop)
    monkeypatch.delenv("LIVE_MARKET", raising=False)
    monkeypatch.delenv("CATALOGUE_REFRESH", raising=False)
    async with main._lifespan(object()):
        pass
    assert events == [("stop", None)]
    events.clear()
    monkeypatch.setenv("CATALOGUE_REFRESH", "1")
    async with main._lifespan(object()):
        pass
    assert events == ["start", ("stop", "task")]


# ---- the lists (real PostgreSQL) ----------------------------------------------------------------------------------

def _held_back(csv_text: str) -> tuple[str, list[str]]:
    """The slice without three real NIFTY 2026-10-06 calls, and those three lines."""
    held = _lines_where(csv_text, name="NIFTY", expiry="2026-10-06", type="CE")[:3]
    kept = [line for line in csv_text.splitlines(True) if line.rstrip("\r\n") not in held]
    return "".join(kept), held


async def test_a_list_loaded_twice_in_a_day_offers_the_additions_with_no_duplicates(app_engine):
    """Attack 2 (F-33): the second load of the same day lists three strikes the first did not."""
    first, held = _held_back(_csv())
    strikes = {Decimal(line.split(",")[6]) for line in held}
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            out = io.StringIO()
            assert await catalogue_load.run(conn, first, _ONTO_ANY_CATALOGUE, out, as_of=AS_OF) == 0
            before = await _count(conn)
            today = datetime.date(2026, 9, 28)
            offered = {c.strike for c in await catalogue_picker.pickable_contracts(
                conn, "NIFTY", today, datetime.date(2026, 10, 6)) if c.instrument_type == "CE"}
            assert not strikes & offered  # held back: not offered yet

            out = io.StringIO()
            assert await catalogue_load.run(conn, _csv(), _settings("10"), out, as_of=AS_OF + timedelta(hours=2)) == 0
            assert "added=3 " in out.getvalue(), out.getvalue()
            assert await _count(conn) == before + 3
            offered = {c.strike for c in await catalogue_picker.pickable_contracts(
                conn, "NIFTY", today, datetime.date(2026, 10, 6)) if c.instrument_type == "CE"}
            assert strikes <= offered  # the held-back contracts are offered after the second load
            duplicates = (await conn.execute(text(
                f"SELECT count(*) FROM (SELECT exchange_segment, exchange_token FROM {TABLE} "  # noqa: S608 constant table name
                f"GROUP BY 1, 2 HAVING count(*) > 1) d"))).scalar_one()
            assert duplicates == 0
        finally:
            await trans.rollback()


async def test_a_term_changed_on_the_second_load_is_one_revision_not_a_duplicate(app_engine):
    csv_text = _csv()
    victim = _lines_where(csv_text, name="NIFTY", expiry="2026-10-06", type="PE")[0]
    fields = victim.split(",")
    fields[8] = str(int(fields[8]) + 5)  # lot_size
    changed = csv_text.replace(victim, ",".join(fields), 1)
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            assert await catalogue_load.run(conn, csv_text, _ONTO_ANY_CATALOGUE, io.StringIO(), as_of=AS_OF) == 0
            before = await _count(conn)
            out = io.StringIO()
            assert await catalogue_load.run(conn, changed, _settings("10"), out, as_of=AS_OF + timedelta(hours=2)) == 0
            assert "added=0 " in out.getvalue() and "revised=1 " in out.getvalue(), out.getvalue()
            assert await _count(conn) == before
        finally:
            await trans.rollback()


async def test_a_truncated_list_from_the_scheduler_path_is_refused_and_the_previous_list_kept(app_engine, caplog):
    """Attack 5 / standing item (d): more than 10% of an index missing -> refused, nothing written, list kept."""
    nifty = _lines_where(_csv(), name="NIFTY")
    drop = set(nifty[: len(nifty) // 5 + 1])  # ~20% of NIFTY
    truncated = "".join(line for line in _csv().splitlines(True) if line.rstrip("\r\n") not in drop)
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            assert await catalogue_load.run(conn, _csv(), _ONTO_ANY_CATALOGUE, io.StringIO(), as_of=AS_OF) == 0
            snapshot = tuple((await conn.execute(text(
                f"SELECT count(*), count(*) FILTER (WHERE currently_listed), count(*) FILTER (WHERE delisted) "  # noqa: S608 constant table name
                f"FROM {TABLE}"))).one())

            async def load() -> int:
                return await catalogue_load.run(conn, truncated, _settings("10"), io.StringIO(), as_of=AS_OF)

            with caplog.at_level(logging.ERROR):
                assert await _scheduler(load, Clock(MONDAY)).attempt() == REFUSED
            assert "refused" in caplog.text and "NIFTY" not in caplog.text  # a code, never the rows
            after = tuple((await conn.execute(text(
                f"SELECT count(*), count(*) FILTER (WHERE currently_listed), count(*) FILTER (WHERE delisted) "  # noqa: S608 constant table name
                f"FROM {TABLE}"))).one())
            assert after == snapshot
        finally:
            await trans.rollback()


async def test_an_empty_list_is_refused_and_writes_nothing(app_engine):
    header = _csv().splitlines()[0] + "\n"
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            assert await catalogue_load.run(conn, _csv(), _ONTO_ANY_CATALOGUE, io.StringIO(), as_of=AS_OF) == 0
            before = await _count(conn)
            out = io.StringIO()
            assert await catalogue_load.run(conn, header, _settings("10"), out, as_of=AS_OF) == 1, out.getvalue()
            assert await _count(conn) == before
            listed = (await conn.execute(text(
                f"SELECT count(*) FROM {TABLE} WHERE currently_listed"))).scalar_one()  # noqa: S608 constant table name
            assert listed == before
        finally:
            await trans.rollback()


async def test_an_old_list_loaded_today_offers_no_expired_contract(app_engine):
    """Standing item (d), 'a list for the wrong date': the 2026-09-28 slice loaded now has only expired contracts, so
    the picker offers nothing for today's date (expiry on or after today is required)."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            assert await catalogue_load.run(conn, _csv(), _ONTO_ANY_CATALOGUE, io.StringIO(), as_of=AS_OF) == 0
            today = await catalogue_picker.database_today(conn)
            future = list(await catalogue_picker.pickable_expiries(conn, "NIFTY", today))
            assert all(e >= today for e in future)
            assert await catalogue_picker.pickable_expiries(conn, "NIFTY", datetime.date(2099, 1, 1)) == []
        finally:
            await trans.rollback()
