"""The ONE read door (``ofo_app.read_door.read_quotes``), hotfix 27 Nov (finding: request market reads wait for a NEW
frame while a fresh quote is in the book).

Spec basis: REQ-133 (live / stale), ADR-330 (39) (the age rule, unchanged: ``FeedState.quote_health``), ADR-015.
The fake provider books a tick only for a token somebody holds (``KiteProvider.on_frame``), a tick arriving ``delay``
seconds (VIRTUAL time) after the subscribe; it counts subscribes, unsubscribes and the door's waits. No Kite, no real
sleep: the door's sleep and clock are one virtual clock, so a bound is counted work, never wall time.
"""
from __future__ import annotations

import asyncio
import datetime
from types import SimpleNamespace

import pytest
from ofo.marketdata.fanout import FanOut
from ofo.marketdata.feed_health import FeedState, FeedWindows
from ofo_app import read_door
from ofo_app.live_push import LiveFeed
from ofo_app.routes import leg_picker

LEGS = ["NFO:1", "NFO:2", "NFO:3", "NFO:4"]
DELAY = 0.3  # a tick arrives this long (virtual seconds) after the subscribe
SLACK = 0.02  # the poll step
POLLS_IN_A_WAIT = 9


class Clock:
    """The virtual time: the door's ``sleep`` advances it; nothing really sleeps. ``waits`` counts the door's sleeps."""

    def __init__(self) -> None:
        self.t = 0.0
        self.waits = 0

    def now(self) -> float:
        return self.t

    async def sleep(self, s: float) -> None:
        self.waits += 1
        self.t += s
        await asyncio.sleep(0)


class FakeProvider:
    def __init__(self, clock: Clock, delays: dict[str, float] | None = None) -> None:
        self.clock = clock
        self.delays = delays or {}
        self.since: dict[str, float] = {}  # held token -> the virtual time of its subscribe
        self.preloaded: set[str] = set()  # quotes already in the book (a holder elsewhere booked them)
        self.subscribed: list[str] = []
        self.unsubscribed: list[str] = []
        self.reads = 0

    def live_quote_stream(self, _cb) -> None:
        pass

    def subscribe(self, ids) -> None:
        for i in ids:
            self.subscribed.append(i)
            self.since[i] = self.clock.t

    def unsubscribe(self, ids) -> None:
        for i in ids:
            self.unsubscribed.append(i)
            self.since.pop(i, None)
            self.preloaded.discard(i)  # parked: unreadable at once

    def book(self) -> dict[str, str]:
        self.reads += 1
        quoted = {i for i, at in self.since.items() if i in self.delays and self.clock.t >= at + self.delays[i]}
        return dict.fromkeys(quoted | self.preloaded, "q")

    def status(self):
        return SimpleNamespace(connected=True)


@pytest.fixture(autouse=True)
def _fresh_leases():
    read_door._lease = None
    yield
    read_door._lease = None


def _feed(provider: FakeProvider) -> LiveFeed:
    return LiveFeed(ctx=None, fanout=FanOut(provider))  # type: ignore[arg-type]


async def _read(feed, p, clock, ids, wait_s=0.5):
    return await read_door.read_quotes(feed, ids, p.book, lambda s: all(i in s for i in ids), lambda: True,
                                       wait_s, 0.01, sleep=clock.sleep, now=clock.now)


async def test_four_held_legs_with_fresh_quotes_make_zero_waits_and_zero_subscribes():
    clock = Clock()
    p = FakeProvider(clock)
    feed = _feed(p)
    feed.fanout.subscribe(lambda q: None, LEGS)  # a page socket holds the four legs
    p.preloaded.update(LEGS)
    before = len(p.subscribed)
    p.reads = 0
    snap = await _read(feed, p, clock, LEGS)
    assert set(snap) == set(LEGS)
    assert clock.waits == 0 and clock.t == 0.0 and p.reads == 1  # one read of the book, no wait
    assert len(p.subscribed) == before  # a held token is never subscribed again


async def test_ten_concurrent_reads_the_same():
    clock = Clock()
    p = FakeProvider(clock)
    feed = _feed(p)
    feed.fanout.subscribe(lambda q: None, LEGS)
    p.preloaded.update(LEGS)
    before = len(p.subscribed)
    results = await asyncio.gather(*[_read(feed, p, clock, LEGS) for _ in range(10)])
    assert all(set(r) == set(LEGS) for r in results)
    assert clock.waits == 0 and len(p.subscribed) == before


async def test_two_of_four_missing_wait_in_parallel_bounded_by_one_deadline():
    clock = Clock()
    p = FakeProvider(clock, {"NFO:3": DELAY, "NFO:4": DELAY})
    feed = _feed(p)
    feed.fanout.subscribe(lambda q: None, LEGS[:2])
    p.preloaded.update(LEGS[:2])
    snap = await _read(feed, p, clock, LEGS, wait_s=1.0)
    assert set(snap) == set(LEGS)
    assert DELAY <= clock.t < DELAY + SLACK  # ONE parallel wait, not two in sequence (twice DELAY)
    assert p.subscribed.count("NFO:3") == 1 and p.subscribed.count("NFO:4") == 1
    clock2 = Clock()  # never quoted: the wait ends at the ONE deadline
    p2 = FakeProvider(clock2)
    snap2 = await _read(_feed(p2), p2, clock2, LEGS, wait_s=DELAY)
    assert snap2 == {} and DELAY <= clock2.t < DELAY + SLACK


async def test_a_not_held_missing_token_is_subscribed_once_and_released_after_the_lease(monkeypatch):
    monkeypatch.setattr(leg_picker, "LEASE_SECONDS", 0.05)
    clock = Clock()
    p = FakeProvider(clock, {"NFO:9": 0.02})
    feed = _feed(p)
    await _read(feed, p, clock, ["NFO:9"])
    waited = clock.waits
    snap = await _read(feed, p, clock, ["NFO:9"])  # the next request: quoted at once, no new subscribe
    assert "NFO:9" in snap and clock.waits == waited and p.subscribed == ["NFO:9"]
    await asyncio.sleep(0.2)  # the lease's own timer ends it
    assert p.unsubscribed == ["NFO:9"] and feed.fanout.subscriber_count("NFO:9") == 0


async def test_the_age_rule_is_unchanged_an_old_index_quote_still_waits():
    """``done`` reads ``FeedState.quote_health`` (ADR-330 (39)); the door adds no age rule of its own."""
    now = datetime.datetime(2026, 11, 27, 11, 0, tzinfo=datetime.UTC)
    windows = FeedWindows(stale=datetime.timedelta(seconds=60), reconnect=datetime.timedelta(seconds=120),
                          index_quote_max_age=datetime.timedelta(seconds=10))
    feed_state = FeedState(windows=windows, market_open=lambda _t: True)
    feed_state.on_connected(now)
    feed_state.on_data(now)
    index = SimpleNamespace(instrument_type=None, timestamp=now - datetime.timedelta(seconds=30))
    assert feed_state.quote_health(index, now).name == "STALE"
    clock = Clock()
    feed = _feed(FakeProvider(clock))
    snap = await read_door.read_quotes(feed, ["IDX"], lambda: index,
                                       lambda q: feed_state.quote_health(q, now).name == "AVAILABLE",
                                       lambda: True, 0.1, 0.01, sleep=clock.sleep, now=clock.now)
    assert snap is index and clock.waits >= POLLS_IN_A_WAIT  # waited to the deadline, ended stale
