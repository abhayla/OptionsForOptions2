# ruff: noqa: F811, PLR2004
"""Lane B1b item 6 (FE4 F7; RA2's design): ONE market-open clock for the worker and the monitor.

Real case (RESULTS-lane-fe4 F7 / RESULTS-lane-ra2 "Not done"): the worker (``background.feed_state`` /
``market_closed_for``) and the monitor (``may_act.market_open(feed.ctx, now)``) each asked the calendar with their OWN
clock, so around the bell one said open and the other closed: a trade read "watched" while the monitor did not act (or
the reverse). Now the worker's snapshot carries its market answer at its own instant (``market_open``, ``at``) and the
monitor acts only when its own clock AND that answer (under two minutes old) say open; a missing, old, unreadable or
field-less snapshot leaves the monitor on its own clock. Fixture: Thursday 29 Oct 2026 10:00 IST, a trading day
(tests_app/test_paper_monitor.py), a below-22,850 exit crossed by a 22,849.95 tick."""
from __future__ import annotations

import datetime
from typing import Any

import pytest
from ofo_app import monitoring_state, paper_monitor
from test_paper_monitor import INDEX, OPEN_AT, Market, _exit_below, _monitor, _stops, _strategy, db  # noqa: F401

SNAP = monitoring_state.key()


class _Bus:
    """The one get/set the monitor and the reader use (a bare double: no hashes)."""

    def __init__(self, raw: Any = None) -> None:
        self.raw = raw

    async def get(self, key: str) -> Any:
        return self.raw if key == SNAP else None

    async def set(self, key: str, value: Any, ex: int | None = None) -> None:
        self.raw = value


def _snapshot(market_open: bool | None, at: datetime.datetime = OPEN_AT) -> str:
    return monitoring_state.encode([], at, market_open=market_open)


async def _crossing(db, monkeypatch, raw) -> int:
    market = Market()
    stored, _ids, keys = await _strategy(db)
    await _exit_below(db, stored.id)
    monkeypatch.setattr(paper_monitor, "_bus_client", lambda: _Bus(raw))
    monitor = _monitor(db, market)
    assert await monitor.step() == 0
    market.tick(keys[0], "41.00")
    market.tick(keys[1], "12.50")
    market.tick(INDEX, "22849.95")
    await monitor.step()
    return len(await _stops(db, stored.id))


async def test_core_the_worker_says_closed_so_the_monitor_does_not_fire_though_its_own_clock_says_open(
        db, monkeypatch):
    assert await _crossing(db, monkeypatch, _snapshot(False)) == 0


async def test_the_worker_says_open_and_the_monitor_fires(db, monkeypatch):
    assert await _crossing(db, monkeypatch, _snapshot(True)) == 2


@pytest.mark.parametrize("raw", [None, "not json", '{"at": "x"}', _snapshot(None)])
async def test_no_usable_answer_leaves_the_monitor_on_its_own_clock(db, monkeypatch, raw):
    assert await _crossing(db, monkeypatch, raw) == 2


async def test_an_old_closed_answer_is_not_used(db, monkeypatch):
    old = OPEN_AT - datetime.timedelta(seconds=monitoring_state.MARKET_CLOCK_MAX_AGE_S + 5)
    assert await _crossing(db, monkeypatch, _snapshot(False, old)) == 2


async def test_the_reader_of_the_answer_judges_from_the_snapshots_instant():
    bus = _Bus(_snapshot(True))
    just_after = OPEN_AT + datetime.timedelta(seconds=30)
    assert await monitoring_state.read_market_open(bus, just_after) is True
    assert await monitoring_state.read_market_open(bus, OPEN_AT - datetime.timedelta(seconds=60)) is None  # ahead
    assert await monitoring_state.read_market_open(None, OPEN_AT) is None
    assert await monitoring_state.read_market_open(_Bus(_snapshot(None)), OPEN_AT) is None


async def test_the_publisher_writes_the_market_answer_and_a_flip_is_written_at_once():
    bus = _Bus()
    publisher = monitoring_state.Publisher(bus)
    assert await publisher.publish({}, {}, {}, OPEN_AT, None, True)
    assert await monitoring_state.read_market_open(bus, OPEN_AT) is True
    soon = OPEN_AT + datetime.timedelta(seconds=1)
    assert not await publisher.publish({}, {}, {}, soon, None, True)  # unchanged: not rewritten before it is due
    assert await publisher.publish({}, {}, {}, soon, None, False)  # the bell: written at once
    assert await monitoring_state.read_market_open(bus, soon) is False
