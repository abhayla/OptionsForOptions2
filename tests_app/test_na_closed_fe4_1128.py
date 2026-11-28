"""Lane FE4 (28 Nov 2026), review finding N3: "not applicable: real position" for an old armed paper stop was reported
only while the market was open. The owner's PC tests on weekends: with the market closed the same trade read paused in
one branch (open) and watched in the other (closed). Spec basis: ADR-330 (64) (a real position has no stop here),
REQ-115 AC-4 (a trade whose exits are not judged never reads watched), ADR-016 to ADR-019 (fail closed).
"""
from __future__ import annotations

import datetime

from ofo_app import held_entry_store, monitoring_state, paper_monitor
from test_monitoring_state import _Client
from test_paper_monitor import (  # noqa: F401
    AFTER_CLOSE,
    INDEX,
    OPEN_AT,
    Market,
    _exit_below,
    _monitor,
    _strategy,
    db,
)
from test_r6_r7_fe3_1128 import _worker_says_watched

SATURDAY = datetime.datetime(2026, 11, 28, 5, 0, tzinfo=datetime.UTC)  # 10:30 IST, a weekend


async def _read(db, monkeypatch, at, *, real):  # noqa: F811
    market = Market(at)
    stored, _ids, keys = await _strategy(db)
    if real:
        await held_entry_store.record(db, stored.id, OPEN_AT, None)  # ADR-292: held at the broker = a real position
    await _exit_below(db, stored.id)
    market.tick(keys[0], "41.00")
    market.tick(keys[1], "12.50")
    market.tick(INDEX, "22800.00")
    client = _Client()
    monkeypatch.setattr(paper_monitor, "_bus_client", lambda: client)
    monitor = _monitor(db, market)
    await monitor.step()
    return await _worker_says_watched(client, stored.id, at)


async def test_n3_a_real_positions_old_stop_reads_not_applicable_after_the_close(db, monkeypatch):  # noqa: F811
    got = await _read(db, monkeypatch, AFTER_CLOSE, real=True)
    print("AFTER CLOSE", got)
    assert (got.status, got.why) == (monitoring_state.PAUSED, monitoring_state.EXIT_NOT_APPLICABLE), got


async def test_n3_a_real_positions_old_stop_reads_not_applicable_on_a_weekend(db, monkeypatch):  # noqa: F811
    got = await _read(db, monkeypatch, SATURDAY, real=True)
    assert (got.status, got.why) == (monitoring_state.PAUSED, monitoring_state.EXIT_NOT_APPLICABLE), got


async def test_n3_a_paper_trade_is_not_called_not_applicable_when_closed(db, monkeypatch):  # noqa: F811
    got = await _read(db, monkeypatch, AFTER_CLOSE, real=False)
    assert got.why != monitoring_state.EXIT_NOT_APPLICABLE, got


async def test_n3_open_market_still_reads_not_applicable(db, monkeypatch):  # noqa: F811
    got = await _read(db, monkeypatch, OPEN_AT, real=True)
    assert (got.status, got.why) == (monitoring_state.PAUSED, monitoring_state.EXIT_NOT_APPLICABLE), got
