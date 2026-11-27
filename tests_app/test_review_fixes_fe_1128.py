"""Lane FE: the Opus review's findings (28 Nov 2026), each a failing test first. Spec basis as the lane's other tests.

F1 a tick queued on the old fan-out handle is not lost at a reload; F2 a crossed exit that cannot run reads paused;
F3 the worker's tick key is read with the prices, before any await; minors: a reading of another instrument, an absurd
value, an own reading from the future.
"""
from __future__ import annotations

import dataclasses
import datetime
from decimal import Decimal

from ofo_app import monitoring_state, paper_monitor
from test_background_cycle import Calls, Prov, _watched, _worker, scn  # noqa: F401 - the fixture is used by name
from test_index_exit_watch_fe_1128 import _armed, _bus, _exit_above, _rest, _worker_cycle
from test_monitoring_state import _Client, _fresh
from test_paper_monitor import INDEX, Market, _monitor, _stops, _strategy, _trigger_state, db  # noqa: F401 - fixture

D = Decimal


async def test_f1_a_tick_queued_before_a_reload_is_judged_not_lost(db, scn, monkeypatch):  # noqa: F811
    market, _stored, _ids, _keys, tid, client, _now = await _armed(db, scn)
    _bus(monkeypatch, client)
    monitor = _monitor(db, market)
    assert await monitor.step() == 0  # loaded and subscribed
    market.tick(INDEX, "23420.00")  # queued on the current handle ...
    monitor.notify()  # ... and a reload swaps the handle before the next drain
    assert await monitor.step() + await monitor.step() == 1
    assert await _trigger_state(db, tid) == (True, False)


async def test_f2_a_crossed_exit_that_cannot_run_reads_paused_never_watched(db, scn, monkeypatch):  # noqa: F811
    """The worker's reading is across the level, but this monitor has no live leg price: the exit stays armed (no order)
    and the trade says so."""
    market = Market(scn.clock_at)
    stored, _ids, _keys = await _strategy(db)  # no leg ticks on this feed
    tid = await _exit_above(db, stored.id)
    client = _Client()
    _w, now = await _worker_cycle(scn, stored.id, client, _rest(scn))
    _bus(monkeypatch, client)
    monitor = _monitor(db, market)
    assert await monitor.step() + await monitor.step() == 0
    assert await _trigger_state(db, tid) == (False, False) and await _stops(db, stored.id) == []
    got = (await monitoring_state.read_states(client, [stored.id], now, heartbeat=_fresh))[stored.id]
    assert got.status == monitoring_state.PAUSED and got.why == monitoring_state.EXIT_NOT_PRICED, got


async def test_f3_the_workers_tick_key_is_read_with_the_prices_before_the_publish_awaits(scn):  # noqa: F811
    """A tick that lands while the worker writes its reading must not be recorded as already seen."""
    prov, now, calls = Prov(scn), [scn.clock_at], Calls()
    moved = []

    class _Moving(_Client):
        async def set(self, k, v, **kw):
            if ":index:" in k and not moved:
                moved.append(1)
                prov.move_spot(prov.spot.ltp + D("5"), scn.clock_at)  # a tick during the write
            await super().set(k, v, **kw)
    w = _worker(prov, _watched(scn), now, calls, want_client=_Moving())
    await w.cycle()
    sid = next(iter(w.status))
    assert moved and w._tick[sid] != w._tick_key(prov, _watched(scn)[0], now[0]), "the later tick must be new"


def test_minor_a_reading_of_another_instrument_is_refused():
    at = datetime.datetime(2026, 11, 6, 11, 40, tzinfo=datetime.UTC)
    raw = monitoring_state.encode_reading(monitoring_state.IndexReading("BANKNIFTY", D("1.00"), at, "rest"), at)
    assert monitoring_state.decode_reading(raw, at, datetime.timedelta(seconds=60), expect="NIFTY") is None
    assert monitoring_state.decode_reading(raw, at, datetime.timedelta(seconds=60), expect="BANKNIFTY") is not None


def test_minor_an_absurd_value_is_refused():
    at = datetime.datetime(2026, 11, 6, 11, 40, tzinfo=datetime.UTC)
    raw = monitoring_state.encode_reading(monitoring_state.IndexReading("NIFTY", D("1E+30"), at, "rest"), at)
    assert monitoring_state.decode_reading(raw, at, datetime.timedelta(seconds=60), expect="NIFTY") is None


async def test_minor_an_own_reading_from_the_future_is_not_a_reading(db, scn, monkeypatch):  # noqa: F811
    market, _stored, _ids, _keys, _tid, client, now = await _armed(db, scn, D("23420.00"))
    market.tick(INDEX, "23390.00")
    market.provider.quotes[INDEX] = dataclasses.replace(
        market.provider.quotes[INDEX], timestamp=now + datetime.timedelta(seconds=30))
    _bus(monkeypatch, client)
    monitor = _monitor(db, market)
    assert await monitor.step() + await monitor.step() == 1  # the worker's reading judges it, not the future quote
    assert paper_monitor.OWN_FEED
