"""Lane H item 3: how much of the event loop does the paper monitor take? One armed index exit;
the monitor's step (a poll every 0.5 s) with 3 non-crossing quotes, and its 60 s reload. Skipped unless OFO_PERF=1.
    OFO_PERF=1 python -m pytest -c pytest-app.ini tests_app/perf_monitor_share.py -q -s"""
from __future__ import annotations

import os
import time

import pytest
from test_paper_monitor import INDEX, Market, _exit_below, _monitor, _strategy, db  # noqa: F401

pytestmark = pytest.mark.skipif(os.environ.get("OFO_PERF") != "1", reason="measurement harness: set OFO_PERF=1")


async def test_monitor_share(db):  # noqa: F811
    market = Market()
    stored, _ids, keys = await _strategy(db)
    await _exit_below(db, stored.id)
    monitor = _monitor(db, market)
    assert await monitor.step() == 0
    t0 = time.perf_counter()
    for i in range(500):
        market.tick(INDEX, f"{23000 + i % 50}.00")  # never below the 22850 level
        for k in keys:
            market.tick(k, f"{40 + i % 5}.00")
        assert await monitor.step() == 0
    step_ms = (time.perf_counter() - t0) * 1000 / 500
    t0 = time.perf_counter()
    for _ in range(50):
        monitor.notify()
        await monitor.step()
    reload_ms = (time.perf_counter() - t0) * 1000 / 50
    print(f"\nPAPER MONITOR: step with 3 quotes {step_ms:.3f} ms (2 steps/s = {step_ms * 2 / 10:.3f}% of the loop); "
          f"reload {reload_ms:.2f} ms (once a minute = {reload_ms / 600:.4f}% of the loop)")
