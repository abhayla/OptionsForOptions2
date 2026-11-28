"""Lane TF item 2 (I-125): a saved plan is watched within REBUILD_SECONDS (10 s), with the worker as a SEPARATE OS
process on a real PostgreSQL database. Lane TE proved 15 s end to end; this pins the 10 s value itself and the re-read
that makes it true (``background.Worker._rebuild_loop``: sleep ``REBUILD_SECONDS``, re-list, log "N strategies
monitored").

Real case 27 Nov (#207, #209): a stop typed on a running trade was not watched until a later re-read.

Spec basis: ADR-330 (11) (no plan = nothing watched), (47); REQ-115 AC-3. The test counts polls, never reads a clock
(tests/test_no_wall_clock_asserts.py): the wait is a bounded window, and the case fails when the line does not come."""
from __future__ import annotations

import asyncio
import pathlib
import re

import _worker_chain as wc
import pytest
from ofo_app import background

pytestmark = pytest.mark.real_preferences

TEN = 10  # REBUILD_SECONDS, ADR-330 / REQ-115 AC-3: the plan sheet's promise "watched within 10 seconds"
POLL = 0.25  # seconds between two reads of the worker's log
SLACK_SECONDS = 4  # one re-list's own run time plus a loaded machine; the 15 s of Lane TE's run is far outside it
LINE = re.compile(r"background: (\d+) strategies monitored")


def counts(log: str) -> list[int]:
    return [int(n) for n in LINE.findall(log)]


async def wait_for_count(c: wc.Chain, wanted: int, polls: int) -> bool:
    for _ in range(polls):
        if counts(c.log())[-1:] == [wanted]:
            return True
        await asyncio.sleep(POLL)
    return False


@pytest.fixture
async def chain_for(monkeypatch, tmp_path: pathlib.Path, app_engine, admin_engine):
    made = []

    async def make(path_id: str) -> wc.Chain:
        app_url, admin_url = await asyncio.to_thread(wc.make_database)
        chain = wc.Chain(path_id, app_url, tmp_path)
        made.append((chain, app_url, admin_url))
        return chain
    yield make
    for chain, app_url, admin_url in made:
        await chain.close()
        await asyncio.to_thread(wc.drop_database, app_url, admin_url)


def test_the_re_read_interval_is_ten_seconds():
    assert background.REBUILD_SECONDS == TEN


async def test_a_plan_saved_while_the_worker_runs_is_watched_within_ten_seconds(chain_for, monkeypatch):
    """The trade has no plan: the worker lists 0 strategies. A plan is saved; the worker's own re-read lists 1, inside
    REBUILD_SECONDS plus the slack. The case above pins the number, so a 15 or 20 s loop fails here."""
    c = await chain_for("PATH-90")
    await c.seed(monkeypatch, plan=False)  # a strategy with no plan: nothing is watched (ADR-330 (11))
    c.start_worker()
    assert counts(c.log())[-1:] == [0], c.log()[-800:]  # the first list: nothing watched
    await c.type_plan(guards={"loss_stop_rupees": "1000"})  # what the plan sheet saves
    saved_after = len(counts(c.log()))
    assert await wait_for_count(c, 1, int((TEN + SLACK_SECONDS) / POLL)), (
        f"the saved plan was not listed within {TEN}+{SLACK_SECONDS} s; lines seen after the "
        f"save: {counts(c.log())[saved_after:]}\n{c.log()[-1200:]}")
    assert c.proc is not None and c.proc.poll() is None  # the SAME process re-read: it was never restarted

