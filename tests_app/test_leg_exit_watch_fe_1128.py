"""Lane FE item 2 (28 Nov 2026): a leg-price exit whose leg tick is silent on the monitor's feed is judged on the
reading the worker used, or the trade reads paused. Spec basis: ADR-016 to ADR-019; REQ-115 / REQ-049 ("Monitoring
paused", never watched); ADR-330 (44), (47), (58), (66).

The leg of the monitor's feed ticks nothing; the worker (its own provider, joined only by the Redis stand-in) reads
that same contract FRESH at a price beyond the stop.
"""
from __future__ import annotations

import dataclasses
import datetime
from decimal import Decimal

from ofo_app import monitoring_state, paper_monitor
from ofo_app import paper_trigger_store as triggers
from test_background_cycle import Calls, Prov, _watched, _worker, scn  # noqa: F401 - the fixture is used by name
from test_monitoring_state import _Client, _fresh
from test_paper_monitor import INDEX, Market, _monitor, _stops, _strategy, _trigger_state, db  # noqa: F401 - fixture

D = Decimal
STOP = D("120.00")
WORKER_LEG_PRICE = D("130.00")


def _bus(monkeypatch, client) -> None:
    monkeypatch.setattr(paper_monitor, "_bus_client", lambda: client, raising=False)


async def _armed(db, scn_, worker_ran: bool):  # noqa: F811
    """A leg stop above 120 on contract 0; the monitor's feed ticks the index and contract 1 only. The worker (its own
    provider) holds both contracts under the SAME feed keys, contract 0 at 130."""
    market = Market(scn_.clock_at)
    stored, ids, keys = await _strategy(db)
    tid = await triggers.add(db, stored.id, triggers.NewTrigger("leg_stop", "above", STOP, contract_id=ids[0]))
    market.tick(INDEX, "23410.00")
    market.tick(keys[1], "12.50")  # contract 0 is silent here
    client = _Client()
    now = scn_.clock_at
    if worker_ran:
        prov = Prov(scn_)
        legs = scn_.data["position"]["legs"]
        for i, key in enumerate(keys):
            iid = prov.leg_id(legs[i]["strike"], legs[i]["type"])
            real = next(q for q in prov.real.option_chain_snapshot("NIFTY", datetime.date(2026, 11, 9))
                        if q.instrument_id == iid)
            ltp = WORKER_LEG_PRICE if i == 0 else D("12.50")
            prov.moved[iid] = dataclasses.replace(real, instrument_id=key, ltp=ltp, timestamp=now)
        calls = Calls()
        w = _worker(prov, [dataclasses.replace(x, strategy_id=stored.id) for x in _watched(scn_)], [now], calls,
                    want_client=client)
        await w.cycle()
        assert w.status[stored.id].name == "ACTIVE", w.paused_reason
    return market, stored, ids, keys, tid, client, now


async def test_core_c_a_silent_leg_tick_and_a_worker_reading_beyond_the_stop_fires_it(db, scn, monkeypatch):  # noqa: F811
    market, stored, ids, _keys, tid, client, now = await _armed(db, scn, worker_ran=True)
    _bus(monkeypatch, client)
    seen = (await monitoring_state.read_states(client, [stored.id], now, heartbeat=_fresh))[stored.id]
    print("WORKER STATE", seen.status)
    monitor = _monitor(db, market)
    fired = await monitor.step() + await monitor.step()
    print("FIRES", fired, "STOPS", await _stops(db, stored.id))
    assert fired == 1, "a crossed leg stop must fire from the reading the worker used"
    assert await _trigger_state(db, tid) == (True, False)
    assert [(s[0], s[3]) for s in await _stops(db, stored.id)] == [(ids[0], WORKER_LEG_PRICE)]


async def test_core_d_a_silent_leg_tick_and_no_worker_reading_is_not_checked_and_reads_paused(db, scn, monkeypatch):  # noqa: F811
    market, stored, _ids, _keys, tid, client, now = await _armed(db, scn, worker_ran=False)
    client.data[monitoring_state.key()] = monitoring_state.encode(
        [monitoring_state.Entry(stored.id, monitoring_state.ACTIVE, "", "", now)], now)  # the worker says: watched
    _bus(monkeypatch, client)
    monitor = _monitor(db, market)
    assert await monitor.step() + await monitor.step() == 0
    assert await _trigger_state(db, tid) == (False, False)
    got = (await monitoring_state.read_states(client, [stored.id], now, heartbeat=_fresh))[stored.id]
    print("STATE", got)
    assert got.status == monitoring_state.PAUSED and got.reason == "stale", got


async def test_a_leg_reading_the_worker_stopped_writing_is_not_a_reading(db, scn, monkeypatch):  # noqa: F811
    market, stored, _ids, keys, tid, client, now = await _armed(db, scn, worker_ran=False)
    old = monitoring_state.IndexReading(keys[0], WORKER_LEG_PRICE, now, "feed")
    noted = now - datetime.timedelta(seconds=monitoring_state.LEG_READING_MAX_AGE_S + 5)  # never re-read since
    client.data[monitoring_state.key()] = monitoring_state.encode(
        [monitoring_state.Entry(stored.id, monitoring_state.ACTIVE, "", "", now)], now,
        {f"leg:{keys[0]}": (old, noted)})
    _bus(monkeypatch, client)
    monitor = _monitor(db, market)
    assert await monitor.step() == 0
    assert await _trigger_state(db, tid) == (False, False)
    got = (await monitoring_state.read_states(client, [stored.id], now, heartbeat=_fresh))[stored.id]
    assert got.status == monitoring_state.PAUSED and got.why == monitoring_state.LEG_NOT_LIVE, got


async def test_a_leg_reading_not_beyond_the_stop_fires_nothing_and_the_trade_stays_watched(db, scn, monkeypatch):  # noqa: F811
    market, stored, _ids, keys, tid, client, now = await _armed(db, scn, worker_ran=False)
    below = monitoring_state.IndexReading(keys[0], D("119.95"), now, "feed")
    client.data[monitoring_state.key()] = monitoring_state.encode(
        [monitoring_state.Entry(stored.id, monitoring_state.ACTIVE, "", "", now)], now,
        {f"leg:{keys[0]}": (below, now)})
    _bus(monkeypatch, client)
    monitor = _monitor(db, market)
    assert await monitor.step() + await monitor.step() == 0
    assert await _trigger_state(db, tid) == (False, False)
    got = (await monitoring_state.read_states(client, [stored.id], now, heartbeat=_fresh))[stored.id]
    assert got.status == monitoring_state.ACTIVE, got
