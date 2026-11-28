# ruff: noqa: F811, ASYNC110, PLR2004
"""Lane B1b (coordinator, PC check W-34, build 829ff65f, real link ~134 ms per query): after a worker RESTART the
"watched" badges took about 2.5 minutes to come back (restart 21:54:52, back 21:57:23); the cloud saw 3 s, the plan
says 30 s.

MEASURED here (the worker is a separate OS process on real PostgreSQL, scenario PATH-96, one trade, a test-only delay
of 130 ms before every statement: ``OFO_TEST_QUERY_DELAY_MS`` with APP_ENV=test): the strategy list is read in 5.5 s
with 39 statements (about 34 per trade, 4.6 s per trade on that link) and the first cycle ends 0.2 s later (1
statement). Nine trades therefore cost about 40 s of list reads before the first report, more with the heavier
statements and the REST and regime reads of a live market. The worker now says both numbers in its log at every
start (``start-up:`` lines).

Fixed here: the heartbeat was written only at the start of the first cycle, AFTER the whole list read, so a read longer
than the readers' two minutes read "no worker has reported" on a worker that is up. It is now written at the start and
every START_BEAT_S while the list is read. The statements per trade are pinned below so they cannot grow unseen."""
from __future__ import annotations

import asyncio
import datetime
import re
import time

from test_plan_stop_worker_chain import chain_for  # noqa: F401 - fixture by name

LIST = re.compile(r"the strategy list was read in ([\d.]+) s \((\d+) statements\)")
FIRST = re.compile(r"the first cycle ended ([\d.]+) s after the start \((\d+) statements\)")
STATEMENTS_FOR_ONE_TRADE = 45  # measured 39 (28 Nov); a rise is a slower restart for every trade on a slow link


async def test_the_start_up_cost_of_one_trade_with_a_130_ms_link_is_measured_and_bounded(chain_for, monkeypatch):
    c = await chain_for("PATH-96")
    await c.seed(monkeypatch, plan=False, pin="weekly")
    await c.type_plan(guards={"loss_stop_rupees": "80"}, t06_stages=["50", "5", "40"], keep=None)
    monkeypatch.setenv("OFO_TEST_QUERY_DELAY_MS", "130")
    c.start_worker()
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline and not FIRST.search(c.log()):
        await asyncio.sleep(1)
    log = c.log()
    listed, first = LIST.search(log), FIRST.search(log)
    assert listed and first, log[-1500:]
    assert int(listed.group(2)) <= STATEMENTS_FOR_ONE_TRADE, listed.group(0)
    assert float(first.group(1)) < 30.0, first.group(0)  # the plan's 30 s for one trade on this link


async def test_a_slow_first_list_read_never_lets_the_heartbeat_age_out(monkeypatch):
    """The heartbeat is written at the START and every START_BEAT_S while the list is read, not only after it."""
    from ofo_app import background, feed_bus  # noqa: PLC0415
    from test_background_cycle import _prefs, _settings  # noqa: PLC0415
    from test_monitoring_state import _Client  # noqa: PLC0415

    monkeypatch.setattr(background, "START_BEAT_S", 0.05)
    client, release = _Client(), asyncio.Event()

    async def slow_list():
        await release.wait()  # the list read takes "minutes"
        return []
    worker = background.Worker(provider_for=lambda _o: None, lister=slow_list, want_client=client, settings=_settings(),
                               preferences=_prefs, clock=lambda: datetime.datetime.now(datetime.UTC))
    run = asyncio.create_task(worker.run())
    await asyncio.wait_for(_until(lambda: client.sets >= 4), 5)  # the restart snapshot, then at least three beats
    assert feed_bus.heartbeat_key() in client.data, "no heartbeat while the list was being read"
    release.set()
    worker.stop()
    await asyncio.wait_for(run, 5)


async def _until(done) -> None:
    while not done():
        await asyncio.sleep(0.02)
