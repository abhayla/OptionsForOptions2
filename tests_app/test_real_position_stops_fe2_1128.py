"""Lane FE2 (28 Nov 2026), coordinator item (b): the paper monitor never evaluates or fires a stop for a REAL position.
Spec basis: ADR-330 (64) ("stops and alerts here cover paper trades only; a real position has no stop in this app"),
ADR-330 (58) (paper and real behave the same apart from the tag), ADR-016 to ADR-019 (nothing is sent for a real trade
by a paper path).

Real case: a strategy entered "held at my broker" (ADR-292: a REAL position stored as practice orders) that carries an
old armed index exit. The index crosses the level: the monitor must not write stop orders for it. The exit is left
unfired and reported once as not applicable.
"""
from __future__ import annotations

import logging

from ofo_app import held_entry_store, paper_monitor, strategy_store
from test_paper_monitor import (  # noqa: F401 - fixture
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

CROSSED = "22800.00"  # below the exit level 22,850.00


async def test_an_old_armed_stop_on_a_real_position_is_never_fired(db, caplog):  # noqa: F811
    market = Market()
    stored, _ids, keys = await _strategy(db)
    await held_entry_store.record(db, stored.id, OPEN_AT, None)  # ADR-292: held at the broker = a real position
    tid = await _exit_below(db, stored.id)
    market.tick(keys[0], "41.00")
    market.tick(keys[1], "12.50")
    market.tick(INDEX, CROSSED)
    monitor = _monitor(db, market)
    with caplog.at_level(logging.INFO, logger=paper_monitor.log.name):
        fired = await monitor.step() + await monitor.step()
        monitor.notify()  # a reload: the report must not repeat
        market.tick(INDEX, "22790.00")
        fired += await monitor.step()
    print("FIRED", fired, "STOPS", await _stops(db, stored.id), "NOT APPLICABLE", dict(monitor.not_applicable))
    assert fired == 0
    assert await _trigger_state(db, tid) == (False, False), "left unfired, not cancelled"
    assert await _stops(db, stored.id) == [], "no stop order for a real position"
    assert monitor.not_applicable == {tid: "real"}
    told = [r for r in caplog.records if "not applicable" in r.getMessage()]
    assert len(told) == 1, "reported once"


async def test_a_paper_strategy_still_fires_and_is_not_reported_not_applicable(db):  # noqa: F811
    market = Market()
    stored, ids, keys = await _strategy(db)
    tid = await _exit_below(db, stored.id)
    market.tick(keys[0], "41.00")
    market.tick(keys[1], "12.50")
    market.tick(INDEX, "22900.00")
    monitor = _monitor(db, market)
    assert await monitor.step() == 0
    market.tick(INDEX, CROSSED)
    assert await monitor.step() == 1
    assert await _trigger_state(db, tid) == (True, False)
    assert len(await _stops(db, stored.id)) == len(ids)
    assert monitor.not_applicable == {}


async def test_a_position_whose_kind_cannot_be_read_is_not_stopped_either(db, monkeypatch):  # noqa: F811
    async def unreadable(_conn, ids):
        return dict.fromkeys(ids, "unknown")  # ADR-330 (64): a fact that could not be read: neither Exit nor Stops
    monkeypatch.setattr(strategy_store, "kinds_of", unreadable)
    market = Market()
    stored, _ids, keys = await _strategy(db)
    tid = await _exit_below(db, stored.id)
    market.tick(keys[0], "41.00")
    market.tick(keys[1], "12.50")
    market.tick(INDEX, CROSSED)
    monitor = _monitor(db, market)
    assert await monitor.step() + await monitor.step() == 0
    assert await _trigger_state(db, tid) == (False, False)
    assert monitor.not_applicable == {tid: "unknown"}
