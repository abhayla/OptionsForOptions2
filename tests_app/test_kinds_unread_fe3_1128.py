"""Lane FE3 (28 Nov 2026), item 2 (ADR-330 (64), REQ-115 AC-4, ADR-016 to ADR-019): a read of the book that fails (the
position kinds, after Lane FD4 makes ``strategy_store.kinds_of`` raise) never empties the paper monitor's watch.

Real case: a paper trade with an armed index exit at 22,850.00; the database answers one reload with an error (a lock
timeout, a restart). Before: the monitor was told "unknown" for every trade and dropped every exit for up to 60 s while
the index fell through the level. Now the last known list stays, the failure is counted and tried again after 5 s;
only a failure that lasts longer than 120 s makes the trades read "not watched: could not read the book" (and no exit
is judged then: a kind that cannot be read is never stopped here).
"""
from __future__ import annotations

from ofo_app import monitoring_state, paper_monitor, strategy_store
from test_monitoring_state import _Client, _fresh
from test_paper_monitor import INDEX, Market, _exit_below, _monitor, _stops, _strategy, _trigger_state, db  # noqa: F401

CROSSED = "22800.00"  # below the exit level 22,850.00


async def _raises(_conn, _ids):
    raise RuntimeError("the database could not answer")


async def _loaded(db, monkeypatch):  # noqa: F811
    market = Market()
    stored, _ids, keys = await _strategy(db)
    tid = await _exit_below(db, stored.id)
    market.tick(keys[0], "41.00")
    market.tick(keys[1], "12.50")
    market.tick(INDEX, "22900.00")
    client = _Client()
    monkeypatch.setattr(paper_monitor, "_bus_client", lambda: client)
    monitor = _monitor(db, market)
    clock = [0.0]
    monitor._monotonic = lambda: clock[0]
    assert await monitor.step() == 0
    assert len(monitor._exits) == 1
    return market, stored, tid, monitor, client, clock


async def test_core_a_failed_kinds_read_keeps_the_last_watch_and_the_exit_still_fires(db, monkeypatch):  # noqa: F811
    market, stored, tid, monitor, _client, clock = await _loaded(db, monkeypatch)
    real = strategy_store.kinds_of
    monkeypatch.setattr(strategy_store, "kinds_of", _raises)
    monitor.notify()
    clock[0] = 10.0
    assert await monitor.step() == 0  # the reload fails here; the index is still above the level
    assert monitor.read_failures == 1, "the read failure is reported"
    assert len(monitor._exits) == 1, "the watch list was not emptied"
    market.tick(INDEX, CROSSED)
    fired = await monitor.step()
    print("FIRED", fired, "FAILURES", monitor.read_failures)
    assert fired == 1 and await _trigger_state(db, tid) == (True, False), "the kept exit still fires"
    assert len(await _stops(db, stored.id)) == 2
    monkeypatch.setattr(strategy_store, "kinds_of", real)


async def test_a_failure_inside_the_allowed_age_reads_watched_not_unread(db, monkeypatch):  # noqa: F811
    _market, stored, _tid, monitor, client, clock = await _loaded(db, monkeypatch)
    monkeypatch.setattr(strategy_store, "kinds_of", _raises)
    monitor.notify()
    clock[0] = paper_monitor.BOOK_UNREAD_MAX_S - 1
    await monitor.step()
    assert not monitor.book_unread_too_long()
    now = _market.at
    client.data[monitoring_state.key()] = monitoring_state.encode(
        [monitoring_state.Entry(stored.id, monitoring_state.ACTIVE, "", "", now)], now)  # the worker says: watched
    got = (await monitoring_state.read_states(client, [stored.id], now, heartbeat=_fresh))[stored.id]
    assert got.status == monitoring_state.ACTIVE, got


async def test_a_failure_longer_than_the_allowed_age_reports_the_book_unread_and_judges_nothing(db, monkeypatch):  # noqa: F811
    market, stored, tid, monitor, client, clock = await _loaded(db, monkeypatch)
    monkeypatch.setattr(strategy_store, "kinds_of", _raises)
    monitor.notify()
    await monitor.step()  # first failed reload at t=0
    clock[0] = paper_monitor.BOOK_UNREAD_MAX_S + 5
    monitor.notify()
    market.tick(INDEX, CROSSED)
    fired = await monitor.step()
    assert monitor.book_unread_too_long()
    assert fired == 0 and await _trigger_state(db, tid) == (False, False), "nothing is judged on an unconfirmed list"
    assert len(monitor._exits) == 1, "the list is still kept for the recovery"
    now = market.at
    client.data[monitoring_state.key()] = monitoring_state.encode(
        [monitoring_state.Entry(stored.id, monitoring_state.ACTIVE, "", "", now)], now)  # the worker says: watched
    got = (await monitoring_state.read_states(client, [stored.id], now, heartbeat=_fresh))[stored.id]
    print("READ", got)
    assert (got.status, got.why) == (monitoring_state.PAUSED, monitoring_state.BOOK_NOT_READ), got


async def test_a_read_that_works_again_clears_the_failure_and_judges_again(db, monkeypatch):  # noqa: F811
    market, _stored, tid, monitor, _client, clock = await _loaded(db, monkeypatch)
    real = strategy_store.kinds_of
    monkeypatch.setattr(strategy_store, "kinds_of", _raises)
    monitor.notify()
    await monitor.step()
    assert monitor.book_unread_since is not None
    monkeypatch.setattr(strategy_store, "kinds_of", real)
    clock[0] = paper_monitor.READ_RETRY_SECONDS + 1  # the retry is due long before the 60 s reload period
    market.tick(INDEX, CROSSED)
    assert await monitor.step() == 1
    assert monitor.book_unread_since is None and not monitor.book_unread_too_long()
    assert await _trigger_state(db, tid) == (True, False)


async def test_the_retry_is_due_after_five_seconds_not_sixty(db, monkeypatch):  # noqa: F811
    _market, _stored, _tid, monitor, _client, clock = await _loaded(db, monkeypatch)
    calls = []

    async def counting(_conn, ids):
        calls.append(1)
        raise RuntimeError("down")
    monkeypatch.setattr(strategy_store, "kinds_of", counting)
    monitor.notify()
    await monitor.step()
    clock[0] = 3.0
    await monitor.step()
    assert len(calls) == 1
    clock[0] = 6.0
    await monitor.step()
    assert len(calls) == 2
