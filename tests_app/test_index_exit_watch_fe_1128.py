"""Lane FE (28 Nov 2026): a crossed index exit fires, or the trade says it is not watched, when the feed's index tick
is silent. Spec basis: ADR-016 to ADR-019; REQ-115 / REQ-049 ("Monitoring paused" with its reason, never shown as
watched); ADR-330 (44), (47), (58), (65), (66).

Real case, 23 Nov 2026: the NIFTY tick stopped at 15:15:18 while trades with index exits were open. The worker read the
REST index stand-in, read FRESH and published "watched"; the paper monitor's index exits fired only on feed ticks.

Core: the monitor (API process: real database, its own feed) and the worker (its own provider, its own objects) share
NOTHING but the Redis stand-in; the worker's feed has no index tick, the REST stand-in is fresh and the level is
crossed. The monitor's feed index tick is silent.
"""
from __future__ import annotations

import dataclasses
import datetime
from decimal import Decimal

from ofo.marketdata.spot_source import SourceReading, SourceState
from ofo_app import monitoring_state, paper_monitor
from ofo_app import paper_trigger_store as triggers
from test_background_cycle import Calls, Prov, _watched, _worker, scn  # noqa: F401 - the fixture is used by name
from test_monitoring_state import _Client, _fresh
from test_paper_monitor import INDEX, Market, _monitor, _stops, _strategy, _trigger_state, db  # noqa: F401 - fixture
from test_spot_either_source import _Reader

D = Decimal
LEVEL = D("23400.00")  # the scenario's NIFTY is near 23,420
REST_VALUE = D("23420.00")  # at or above LEVEL: an "above" exit is crossed
SECOND = datetime.timedelta(seconds=1)


def _rest(scn_) -> SourceReading:
    return SourceReading(SourceState.STATED, REST_VALUE, scn_.clock_at - SECOND)


async def _exit_above(db, sid: int) -> int:  # noqa: F811 - a parameter shadows the fixture import
    return await triggers.add(db, sid, triggers.NewTrigger("conditional_exit", "above", LEVEL, underlying="NIFTY"))


async def _worker_cycle(scn_, sid: int, client, rest: SourceReading):
    """The worker as its own process: its own provider with NO index tick, the REST stand-in, one cycle."""
    prov, now, calls = Prov(scn_), [scn_.clock_at], Calls()
    prov.spot = None
    watched = [dataclasses.replace(w, strategy_id=sid) for w in _watched(scn_)]
    w = _worker(prov, watched, now, calls, want_client=client, rest_spot=_Reader(rest))
    await w.cycle()
    return w, now[0]


def _bus(monkeypatch, client) -> None:
    """The monitor's one door to the bus (the fix names it ``_bus_client``): the same stand-in the worker writes to."""
    monkeypatch.setattr(paper_monitor, "_bus_client", lambda: client, raising=False)


async def test_core_a_silent_index_tick_and_a_fresh_rest_stand_in_fires_the_crossed_exit(db, scn, monkeypatch):  # noqa: F811
    market = Market(scn.clock_at)
    stored, ids, keys = await _strategy(db)
    tid = await _exit_above(db, stored.id)
    market.tick(keys[0], "41.00")  # the legs tick; the index does NOT (23 Nov, 15:15:18)
    market.tick(keys[1], "12.50")
    client = _Client()
    _bus(monkeypatch, client)
    _w, now = await _worker_cycle(scn, stored.id, client, _rest(scn))
    seen = await monitoring_state.read_states(client, [stored.id], now, heartbeat=_fresh)
    print("WORKER STATE", seen[stored.id])
    monitor = _monitor(db, market)
    fired = await monitor.step() + await monitor.step()
    print("FIRES", fired, "STOPS", await _stops(db, stored.id), "TRIGGER", await _trigger_state(db, tid))
    assert fired == 1, "a crossed index exit must fire from the reading the worker used"
    assert await _trigger_state(db, tid) == (True, False)
    assert len(await _stops(db, stored.id)) == len(ids)


async def test_core_b_a_trade_whose_exit_cannot_be_checked_is_never_shown_as_watched(db, scn, monkeypatch):  # noqa: F811
    """The monitor cannot read the worker's index reading (the store fails for it) and its own tick is silent: the
    exit is NOT evaluated and the trade reads paused, never watched."""
    market = Market(scn.clock_at)
    stored, _ids, keys = await _strategy(db)
    await _exit_above(db, stored.id)
    market.tick(keys[0], "41.00")
    market.tick(keys[1], "12.50")
    client = _Client()
    _w, now = await _worker_cycle(scn, stored.id, client, _rest(scn))
    assert (await monitoring_state.read_states(client, [stored.id], now, heartbeat=_fresh))[stored.id].status \
        == monitoring_state.ACTIVE

    class _NoIndexRead(_Client):
        async def get(self, k):
            if ":index:" in k:
                raise OSError("down")
            return await super().get(k)
    blind = _NoIndexRead()
    blind.data = client.data  # the same store; only the monitor's index read fails
    _bus(monkeypatch, blind)
    monitor = _monitor(db, market)
    assert await monitor.step() + await monitor.step() == 0
    got = (await monitoring_state.read_states(client, [stored.id], now, heartbeat=_fresh))[stored.id]
    print("STATE AFTER", got)
    assert got.status == monitoring_state.PAUSED, got


# ---- every other answer state of the one index reading ---------------------------------------------------------------

async def _armed(db, scn_, rest_value=None, rest_age=SECOND):  # noqa: F811
    """A monitor with an armed "above" exit, silent index tick, legs ticking; the worker ran with ``rest_value``."""
    market = Market(scn_.clock_at)
    stored, ids, keys = await _strategy(db)
    tid = await _exit_above(db, stored.id)
    market.tick(keys[0], "41.00")
    market.tick(keys[1], "12.50")
    client = _Client()
    now = scn_.clock_at
    if rest_value is not None:
        _w, now = await _worker_cycle(scn_, stored.id, client,
                                      SourceReading(SourceState.STATED, rest_value, scn_.clock_at - rest_age))
    return market, stored, ids, keys, tid, client, now


async def test_a_reading_below_the_level_fires_nothing_and_the_trade_stays_watched(db, scn, monkeypatch):  # noqa: F811
    market, stored, _ids, _keys, tid, client, now = await _armed(db, scn, D("23390.00"))
    _bus(monkeypatch, client)
    monitor = _monitor(db, market)
    assert await monitor.step() + await monitor.step() == 0
    assert await _trigger_state(db, tid) == (False, False)
    got = (await monitoring_state.read_states(client, [stored.id], now, heartbeat=_fresh))[stored.id]
    assert (got.status, got.reason) == (monitoring_state.ACTIVE, "")


async def test_no_reading_anywhere_nothing_is_evaluated_and_the_trade_reads_paused(db, scn, monkeypatch):  # noqa: F811
    market, stored, _ids, _keys, tid, client, now = await _armed(db, scn)  # the worker never read an index
    client.data[monitoring_state.key()] = monitoring_state.encode(
        [monitoring_state.Entry(stored.id, monitoring_state.ACTIVE, "", "", now)], now)  # the worker says: watched
    _bus(monkeypatch, client)
    monitor = _monitor(db, market)
    assert await monitor.step() + await monitor.step() == 0
    assert await _trigger_state(db, tid) == (False, False)
    got = (await monitoring_state.read_states(client, [stored.id], now, heartbeat=_fresh))[stored.id]
    assert (got.status, got.reason, got.why) == (monitoring_state.PAUSED, "stale", monitoring_state.INDEX_NOT_LIVE), got


async def test_a_worker_reading_older_than_the_index_age_is_not_a_reading(db, scn, monkeypatch):  # noqa: F811
    market, stored, _ids, _keys, tid, client, now = await _armed(db, scn)
    old = monitoring_state.IndexReading("NIFTY", REST_VALUE, now - datetime.timedelta(minutes=11), "rest")
    await monitoring_state.publish_index(client, old, now)  # published just now, but the quote is 11 min old
    client.data[monitoring_state.key()] = monitoring_state.encode(
        [monitoring_state.Entry(stored.id, monitoring_state.ACTIVE, "", "", now)], now)
    _bus(monkeypatch, client)
    monitor = _monitor(db, market)
    assert await monitor.step() == 0
    assert await _trigger_state(db, tid) == (False, False)
    got = (await monitoring_state.read_states(client, [stored.id], now, heartbeat=_fresh))[stored.id]
    assert got.status == monitoring_state.PAUSED and got.why == monitoring_state.INDEX_NOT_LIVE, got


async def test_a_live_own_index_tick_still_fires_with_no_worker_reading(db, scn, monkeypatch):  # noqa: F811
    market, _stored, _ids, _keys, tid, client, _now = await _armed(db, scn)
    _bus(monkeypatch, client)
    monitor = _monitor(db, market)
    assert await monitor.step() == 0
    market.tick(INDEX, "23410.00")
    assert await monitor.step() == 1
    assert await _trigger_state(db, tid) == (True, False)


async def test_a_newer_own_tick_wins_over_an_older_worker_reading(db, scn, monkeypatch):  # noqa: F811
    """The worker's reading says crossed, this feed's newer index tick says not: the newer one is the reading."""
    market, stored, _ids, _keys, tid, client, now = await _armed(db, scn, REST_VALUE, datetime.timedelta(seconds=3))
    market.tick(INDEX, "23390.00")  # timestamped at the clock: newer than the REST reading 3 s before it
    _bus(monkeypatch, client)
    monitor = _monitor(db, market)
    assert await monitor.step() + await monitor.step() == 0
    assert await _trigger_state(db, tid) == (False, False)
    got = (await monitoring_state.read_states(client, [stored.id], now, heartbeat=_fresh))[stored.id]
    assert got.status == monitoring_state.ACTIVE, got


async def test_a_monitor_that_stopped_reporting_pauses_every_trade_it_listed(db, scn, monkeypatch):  # noqa: F811
    market, stored, _ids, _keys, _tid, client, now = await _armed(db, scn, REST_VALUE)
    _bus(monkeypatch, client)
    market.tick(INDEX, "23390.00")
    monitor = _monitor(db, market)
    await monitor.step()
    ok = (await monitoring_state.read_states(client, [stored.id], now, heartbeat=_fresh))[stored.id]
    assert ok.status == monitoring_state.ACTIVE, ok
    later = now + datetime.timedelta(seconds=monitoring_state.SNAPSHOT_STALE_S - 1)  # the worker is still fresh
    client.data[monitoring_state.key()] = monitoring_state.encode(
        [monitoring_state.Entry(stored.id, monitoring_state.ACTIVE, "", "", later)], later)
    got = (await monitoring_state.read_states(client, [stored.id], later + datetime.timedelta(seconds=2),
                                              heartbeat=_fresh))[stored.id]
    assert (got.status, got.why) == (monitoring_state.PAUSED, monitoring_state.INDEX_EXITS_NOT_RUN), got


async def test_an_unreadable_report_never_clears_a_trade(db, scn, monkeypatch):  # noqa: F811
    _market, stored, _ids, _keys, _tid, client, now = await _armed(db, scn, REST_VALUE)
    client.data[monitoring_state.exits_key()] = "not json"
    got = (await monitoring_state.read_states(client, [stored.id], now, heartbeat=_fresh))[stored.id]
    assert (got.status, got.reason) == (monitoring_state.PAUSED, monitoring_state.STATE_UNREADABLE), got


async def test_a_closed_market_judges_nothing_and_reports_nothing_listed(db, scn, monkeypatch):  # noqa: F811
    market, _stored, _ids, _keys, tid, client, _now = await _armed(db, scn, REST_VALUE)
    market.at = scn.clock_at + datetime.timedelta(hours=6)  # 17:40 IST: after the close
    _bus(monkeypatch, client)
    monitor = _monitor(db, market)
    assert await monitor.step() == 0
    assert await _trigger_state(db, tid) == (False, False)
    assert '"not_run": {}' in client.data[monitoring_state.exits_key()]
