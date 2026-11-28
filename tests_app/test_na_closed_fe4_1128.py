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


# Lane R1 (ADR-330 (73)) rewrites N3: a REAL position's stop is judged like a paper one's, so at every hour (open, after
# the close, a weekend) the real trade reads exactly what the same paper trade reads, never "not applicable".
import pytest  # noqa: E402


@pytest.mark.parametrize("at", [AFTER_CLOSE, SATURDAY, OPEN_AT], ids=["after_close", "weekend", "open"])
async def test_n3_a_real_position_reads_what_the_same_paper_trade_reads_never_not_applicable(db, monkeypatch, at):  # noqa: F811
    real = await _read(db, monkeypatch, at, real=True)
    paper = await _read(db, monkeypatch, at, real=False)
    print("REAL", real, "PAPER", paper)
    assert real.why != monitoring_state.EXIT_NOT_APPLICABLE, real
    assert (real.status, real.why) == (paper.status, paper.why), (real, paper)
