"""W-067 round 2, AC-5 (REQ-051): a recorder write returns to the feed thread in milliseconds whatever the database does.

Spec basis (quoted): REQ-051 AC-5 "Historical data and simulation never block live strategy creation, Option Chain,
execution or monitoring". The review probe (round 1) held the history advisory lock from another session: the feed
thread blocked for 15.06 s per write (the command timeout), because the store waited on the database from the caller.

Real input: the recorded 2026-10-08 15:06-15:12 frames through the W-059 provider and fan-out into the W-062 recorder
and the PostgreSQL store. The owner session holds the lock (advisory key, or ACCESS EXCLUSIVE on the bar table) while
the replay runs; the feed must finish while the lock is held (liveness, not a stopwatch).
"""
from __future__ import annotations

import asyncio
import contextlib
import datetime
import sys
import threading
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests" / "history"))

from _history_fixture import DAY, replay_window  # noqa: F401  (tests/history is on the path via test_history_pg_store)
from test_history_pg_store import _url, committed_day  # noqa: F401

from ofo.history.recorder import Recorder
from ofo.history.store import InMemoryHistoryStore
from ofo_app.history_store import _LOCK_KEY, PostgresHistoryStore

W = "1506-1512"
LIVENESS_S = 60  # a generous liveness bound for a feed that must not wait at all (the old defect: 15.06 s per write)


@contextlib.contextmanager
def owner_holds(sql: str):
    """The owner role runs ``sql`` in an open transaction on its own thread and keeps it open until the block ends."""
    ready, release = threading.Event(), threading.Event()
    failure: list[BaseException] = []

    def run():
        async def hold():
            engine = create_async_engine(_url("TEST_ADMIN_DATABASE_URL"), poolclass=NullPool)
            try:
                async with engine.connect() as conn:
                    trans = await conn.begin()
                    await conn.execute(text(sql))
                    ready.set()
                    await asyncio.get_running_loop().run_in_executor(None, release.wait)
                    await trans.rollback()
            finally:
                await engine.dispose()

        try:
            asyncio.run(hold())
        except BaseException as exc:  # noqa: BLE001
            failure.append(exc)
            ready.set()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    assert ready.wait(30) and not failure, failure
    try:
        yield
    finally:
        release.set()
        thread.join(30)


def replay(store) -> Recorder:
    """Replay the window; the fan-out calls into the recorder on the calling (feed) thread, then the window is flushed."""
    holder: dict = {}

    def wire(fan, ids):
        fan.subscribe(lambda q: None, ids)  # the feed already carries the ids
        rec = holder["rec"] = Recorder(store)
        fan.subscribe(rec.on_quote, ids)

    _, _, last = replay_window(W, wire)
    holder["rec"].flush(last + datetime.timedelta(minutes=1))
    return holder["rec"]


FEED_THREAD = "test-feed"


class ThreadRecordingStore:
    """Delegates to the real store and records which thread made each call: the structural proof that the feed thread
    never touches the database (the same check the domain test makes with `store.threads`)."""

    def __init__(self, store) -> None:
        self._store, self.threads = store, set()

    def __getattr__(self, name):
        attr = getattr(self._store, name)
        if not callable(attr):
            return attr

        def call(*args, **kwargs):
            self.threads.add(threading.current_thread().name)
            return attr(*args, **kwargs)
        return call


def replay_finishes_while_the_database_is_locked(store) -> tuple[bool, Recorder | None]:
    """Runs the feed on its own thread and joins with a generous liveness limit. The lock is released only after this
    returns, so a feed that waited on the database would never finish: a liveness check, not a timing threshold
    (finding wall-clock-assertion-flakes-under-load)."""
    out: dict = {}

    def run():
        try:
            out["rec"] = replay(store)
        except BaseException as exc:  # noqa: BLE001
            out["error"] = exc

    feeder = threading.Thread(target=run, daemon=True, name=FEED_THREAD)
    feeder.start()
    feeder.join(LIVENESS_S)
    assert "error" not in out, out.get("error")
    return not feeder.is_alive(), out.get("rec")


def expected_bars():
    mem = InMemoryHistoryStore()
    rec = replay(mem)
    assert rec.drain(30)
    return mem.bars_for_day(DAY), mem.gaps(DAY)


@pytest.mark.parametrize("hold_sql", [f"SELECT pg_advisory_xact_lock({_LOCK_KEY})",
                                      "LOCK TABLE public.history_minute_bars IN ACCESS EXCLUSIVE MODE"],
                         ids=["advisory-lock", "table-lock"])
def test_a_locked_database_never_blocks_the_feed_thread_and_nothing_is_lost_when_it_frees(committed_day, hold_sql):
    want_bars, want_gaps = expected_bars()
    assert len(want_bars) > 25 and want_gaps
    pg = PostgresHistoryStore(_url("TEST_DATABASE_URL"))
    watched = ThreadRecordingStore(pg)
    rec = None
    try:
        with owner_holds(hold_sql):
            finished, rec = replay_finishes_while_the_database_is_locked(watched)
            assert finished, "the feed thread waited on a locked database"
            assert FEED_THREAD not in watched.threads, "the feed thread called the database"
            assert rec.counters["errors"] == 0  # the lock is held only for the replay: the writer simply waits
        assert rec.drain(60), "the writer did not finish once the lock was released"
        assert pg.bars_for_day(DAY) == want_bars  # the same bars the in-memory store holds: nothing was lost
        assert pg.gaps(DAY) == want_gaps
        assert rec.counters["bars_lost"] == 0 and rec.counters["bars_written"] > 25
    finally:
        if rec is not None:
            rec.close()
        pg.close()
