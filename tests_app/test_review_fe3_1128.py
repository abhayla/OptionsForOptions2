"""Lane FE3 (28 Nov 2026), the Opus review's findings F1 to F6 on the head b6cd0f0bb (each a failing test first)."""
from __future__ import annotations

import datetime

from ofo.rules.inputs import DataHealth
from ofo_app import background, held_entry_store, monitoring_state, paper_monitor, strategy_store
from test_background_cycle import DEFAULTS, FIRST_ID, Prov, _settings, _watched, _worker, scn  # noqa: F401 - fixture
from test_kinds_unread_fe3_1128 import _loaded, _raises, fail_next_read
from test_monitoring_state import _Client, _fresh
from test_paper_monitor import (  # noqa: F401
    INDEX,
    OPEN_AT,
    Market,
    _exit_below,
    _monitor,
    _stops,
    _strategy,
    _trigger_state,
    db,
)

CROSSED = "22800.00"
MOST_TRIES = 3


async def _fails_once(_w, _s, _p=None):
    raise RuntimeError("db down")


# ---- F1: a check that is owed is not forgotten when another pause reason passes over it ---------------------------
async def test_f1_a_stale_cycle_between_a_failed_check_and_a_fresh_read_does_not_clear_the_owed_check(scn):  # noqa: F811
    prov, now = Prov(scn), [scn.clock_at]
    boom = [True]

    async def recorder(wd, state, prefs=None):
        if boom[0]:
            boom[0] = False
            raise RuntimeError("db down")
    w = _worker(prov, _watched(scn), now, recorder, settings=_settings(dict(DEFAULTS)))
    await w.cycle()
    assert w.paused_reason[FIRST_ID] is background.PriceState.CHECK_FAILED
    now[0] += datetime.timedelta(seconds=1)
    prov.health = DataHealth.STALE
    await w.cycle()
    assert w.status[FIRST_ID] is background.MonitoringStatus.PAUSED
    prov.health = DataHealth.AVAILABLE
    now[0] += datetime.timedelta(seconds=1)
    ran = len(w.checks)
    await w.cycle()  # a fresh read, the check is held by the interval: nothing has passed since the failure
    assert len(w.checks) == ran
    print("AFTER", w.status[FIRST_ID], w.paused_reason.get(FIRST_ID))
    assert w.status[FIRST_ID] is background.MonitoringStatus.PAUSED
    assert w.paused_reason[FIRST_ID] is background.PriceState.CHECK_FAILED


# ---- F2: a monitor that has never loaded does not retry every poll -------------------------------------------------
async def test_f2_a_first_load_that_fails_is_tried_again_after_five_seconds_not_every_poll(db, monkeypatch):  # noqa: F811
    market = Market()
    await _strategy(db)
    calls = []

    async def counting(_conn, ids):
        calls.append(1)
        raise RuntimeError("down")
    monkeypatch.setattr(strategy_store, "kinds_of", counting)
    monitor = _monitor(db, market)
    clock = [0.0]
    monitor._monotonic = lambda: clock[0]
    for i in range(20):  # 10 s of polls, one every 0.5 s
        clock[0] = i * 0.5
        await monitor.step()
    print("RELOAD ATTEMPTS", len(calls))
    assert len(calls) <= MOST_TRIES, len(calls)  # at 0, 5 and (at most) 10 s


# ---- F3 (monitor half): a kinds read that swallowed its error answers "unknown" for every id -----------------------
async def test_f3_every_kind_unknown_after_a_known_list_is_a_failed_read_not_a_new_fact(db, monkeypatch):  # noqa: F811
    market, _stored, tid, monitor, _client, _clock = await _loaded(db, monkeypatch)

    async def swallowed(_conn, ids):  # what ``kinds_of`` does today on a database error
        return dict.fromkeys(ids, "unknown")
    fail_next_read(monkeypatch, swallowed)
    monitor.notify()
    await monitor.step()
    assert monitor.read_failures == 1 and len(monitor._exits) == 1
    market.tick(INDEX, CROSSED)
    assert await monitor.step() == 1 and await _trigger_state(db, tid) == (True, False)


async def test_f5_b_a_kind_that_cannot_be_read_at_the_fire_leaves_the_exit_armed(db, monkeypatch):  # noqa: F811
    market, _stored, tid, monitor, _client, _clock = await _loaded(db, monkeypatch)
    monkeypatch.setattr(strategy_store, "kinds_of", _raises)  # the list is kept, but the kind cannot be confirmed now
    market.tick(INDEX, CROSSED)
    assert await monitor.step() == 0
    assert await _trigger_state(db, tid) == (False, False), "fail closed (ADR-330 (64)): armed, not fired"


# ---- F4: the report names a real position's old stop in every branch ----------------------------------------------
async def test_f4_a_real_stop_reads_book_not_read_like_paper_when_the_book_is_unreadable(db, monkeypatch):  # noqa: F811
    market = Market()
    stored, _ids, keys = await _strategy(db)
    await held_entry_store.record(db, stored.id, OPEN_AT, None)  # a real position (ADR-292)
    await _exit_below(db, stored.id)
    market.tick(keys[0], "41.00")
    market.tick(keys[1], "12.50")
    market.tick(INDEX, "22900.00")
    client = _Client()
    monkeypatch.setattr(paper_monitor, "_bus_client", lambda: client)
    monitor = _monitor(db, market)
    clock = [0.0]
    monitor._monotonic = lambda: clock[0]
    await monitor.step()  # loaded: the real position's stop is judged like a paper one's (Lane R1, ADR-330 (73))
    monkeypatch.setattr(strategy_store, "kinds_of", _raises)
    monitor.notify()
    await monitor.step()
    clock[0] = paper_monitor.BOOK_UNREAD_MAX_S + 5
    monitor.notify()
    await monitor.step()
    assert monitor.book_unread_too_long()
    now = market.at
    client.data[monitoring_state.key()] = monitoring_state.encode(
        [monitoring_state.Entry(stored.id, monitoring_state.ACTIVE, "", "", now)], now)
    got = (await monitoring_state.read_states(client, [stored.id], now, heartbeat=_fresh))[stored.id]
    print("READ", got)
    assert (got.status, got.why) == (monitoring_state.PAUSED, monitoring_state.BOOK_NOT_READ), got


# ---- F5: the kind is read again inside the fire --------------------------------------------------------------------
async def test_f5_a_strategy_real_after_the_list_loaded_is_stopped_as_a_record(db, monkeypatch):  # noqa: F811
    market, stored, tid, monitor, _client, _clock = await _loaded(db, monkeypatch)
    await held_entry_store.record(db, stored.id, OPEN_AT, None)  # now a real position; the monitor was not told
    market.tick(INDEX, CROSSED)
    # Lane R1 (ADR-330 (73)): the fire reads the kind again; real -> an alert and ONE record, never a paper stop order
    assert await monitor.step() == 1
    assert await _trigger_state(db, tid) == (True, False), "fired once, as a record (no paper order)"
    assert await _stops(db, stored.id) == []


# ---- F6: a restore that could not READ the old snapshot is tried again -----------------------------------------------
async def test_f6_a_restart_whose_read_failed_reads_and_writes_again(db):  # noqa: F811
    at = datetime.datetime(2026, 11, 27, 11, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
    client = _Client()
    client.data[monitoring_state.key()] = monitoring_state.encode(
        [monitoring_state.Entry(7, monitoring_state.PAUSED, "stale", "", at - datetime.timedelta(hours=1))], at)

    class Flaky:
        fail = True

        async def get(self, k):
            if Flaky.fail:
                Flaky.fail = False
                raise OSError("down")
            return await client.get(k)

        async def set(self, k, v, **kw):
            return await client.set(k, v, **kw)
    pub = monitoring_state.Publisher(Flaky())
    assert await pub.restore(at) is False and pub.restore_pending
    assert await pub.retry_restore(at + datetime.timedelta(seconds=1)) is True
    body = client.data[monitoring_state.key()]
    assert monitoring_state.decode(body, at + datetime.timedelta(seconds=1)) == {}
    assert '"kept": {"7"' in body, "the pause start of trade 7 was read on the retry and is kept"
