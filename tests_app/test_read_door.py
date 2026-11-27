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
        self.unknown: set[str] = set()  # ids the provider has no token for (the master does not list them yet)

    def live_quote_stream(self, _cb) -> None:
        pass

    def subscribe(self, ids) -> None:
        if self.unknown & set(ids):
            raise KeyError(sorted(self.unknown & set(ids)))
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


# ---- review round 1 (hotfix 27 Nov): the sentinel, unknown ids, the cap, the one sweeper ---------------------------

async def test_a_read_that_is_itself_none_is_not_the_no_token_answer():
    """Finding 1: the door's "no token" is its own value; a caller's read of None is the read."""
    clock = Clock()
    p = FakeProvider(clock)
    feed = _feed(p)
    got = await read_door.read_quotes(feed, ["NFO:1"], lambda: None, lambda _s: True, lambda: True, 0.5, 0.01,
                                      sleep=clock.sleep, now=clock.now)
    assert got is None and got is not read_door.NO_TOKEN
    p.unknown = {"NFO:7", "NFO:8"}
    out: set[str] = set()
    none_known = await read_door.read_quotes(feed, ["NFO:7", "NFO:8"], lambda: None, lambda _s: True, lambda: True,
                                             0.5, 0.01, sleep=clock.sleep, now=clock.now, unknown_out=out)
    assert none_known is read_door.NO_TOKEN and out == {"NFO:7", "NFO:8"}


async def test_an_unknown_id_is_never_leased_and_the_next_read_asks_again():
    """Finding 3: a read before the token map knows an id waits for nothing; once the map learns it the second read
    subscribes and returns the quote."""
    clock = Clock()
    p = FakeProvider(clock)
    p.unknown = {"NFO:9"}
    feed = _feed(p)
    out: set[str] = set()
    first = await read_door.read_quotes(feed, ["NFO:9"], p.book, lambda s: "NFO:9" in s, lambda: True, 0.5, 0.01,
                                        sleep=clock.sleep, now=clock.now, unknown_out=out)
    assert first is read_door.NO_TOKEN and out == {"NFO:9"} and clock.waits == 0
    assert read_door.read_lease().held_ids == frozenset()  # nothing leased for an id with no token
    p.unknown = set()  # the master refresh learns it
    p.preloaded.add("NFO:9")
    second = await _read(feed, p, clock, ["NFO:9"])
    assert "NFO:9" in second and p.subscribed == ["NFO:9"]


async def test_one_known_fresh_and_one_unknown_make_zero_waits():
    """Finding 4: an id nobody can quote is never waited for (the old door returned at once)."""
    clock = Clock()
    p = FakeProvider(clock)
    p.unknown = {"NFO:9"}
    p.preloaded.add("NFO:1")
    feed = _feed(p)
    out: set[str] = set()
    snap = await read_door.read_quotes(feed, ["NFO:1", "NFO:9"], p.book, lambda s: {"NFO:1", "NFO:9"} <= set(s),
                                       lambda: True, 3.0, 0.05, sleep=clock.sleep, now=clock.now, unknown_out=out)
    assert "NFO:1" in snap and out == {"NFO:9"} and clock.waits == 0 and clock.t == 0.0
    # with the caller's rule for the KNOWN ids only, a known id still missing is waited for, the unknown one is not
    p.delays["NFO:2"] = DELAY
    got = await read_door.read_quotes(feed, ["NFO:1", "NFO:2", "NFO:9"], p.book, lambda s: False, lambda: True, 1.0,
                                      0.05, sleep=clock.sleep, now=clock.now,
                                      done_known=lambda s, known: set(known) <= set(s))
    assert "NFO:2" in got and DELAY <= clock.t < DELAY + 0.06


async def test_two_hundred_distinct_sets_hold_a_bounded_number_of_tokens(monkeypatch):
    """Finding 5: one handle per token (a token in many sets is held once) and a cap; the oldest-renewed goes first."""
    monkeypatch.setattr(read_door, "MAX_HELD_TOKENS", 500)
    clock = Clock()
    p = FakeProvider(clock)
    feed = _feed(p)
    for n in range(200):  # 200 distinct sets of 4 tokens drawn from 700 distinct tokens
        ids = [f"T:{(n * 3 + k) % 700}" for k in range(4)]
        await read_door.read_quotes(feed, ids, p.book, lambda _s: True, lambda: True, 0.0, 0.01,
                                    sleep=clock.sleep, now=clock.now)
    held = read_door.read_lease().held_ids
    assert len(held) <= 500 and "T:600" in held and "T:0" not in held  # noqa: PLR2004 - bounded, oldest let go first
    assert all(feed.fanout.subscriber_count(t) == 1 for t in held)
    assert set(p.since) == set(held)  # the vendor holds exactly the leased tokens
    read_door.read_lease().release()
    assert p.since == {}


async def test_one_sweeper_timer_for_many_reads_and_it_releases_the_expired_tokens(monkeypatch):
    """Finding 7: a read arms no timer of its own; ONE sweeper per door ends the leases."""
    monkeypatch.setattr(leg_picker, "LEASE_SECONDS", 0.05)
    clock = Clock()
    p = FakeProvider(clock)
    feed = _feed(p)
    loop = asyncio.get_running_loop()
    real = loop.call_later
    armed: list[float] = []
    loop.call_later = lambda delay, cb, *a: armed.append(delay) or real(delay, cb, *a)
    try:
        for n in range(30):
            await read_door.read_quotes(feed, [f"T:{n}"], p.book, lambda _s: True, lambda: True, 0.0, 0.01,
                                        sleep=clock.sleep, now=clock.now)
        assert len(armed) == 1
        await asyncio.sleep(0.3)  # the sweeper runs, finds every token expired and lets them go
    finally:
        loop.call_later = real
    assert read_door.read_lease().held_ids == frozenset() and p.since == {}


async def test_a_token_a_read_is_polling_on_is_not_evicted_by_another_reads_cap(monkeypatch):
    """Opus round 2: read A polls on X (tick due 0.3 s); read B leases 500 other ids past the cap. X is pinned by A:
    it is not unsubscribed and A gets its quote (a live market is never answered "not live")."""
    monkeypatch.setattr(read_door, "MAX_HELD_TOKENS", 500)
    clock = Clock()
    p = FakeProvider(clock, {"X": DELAY})
    feed = _feed(p)
    task_a = asyncio.ensure_future(_read(feed, p, clock, ["X"], wait_s=1.0))
    for _ in range(3):
        await asyncio.sleep(0)  # A is inside its poll loop
    assert not task_a.done() and read_door.read_lease().in_use("X") == 1
    others = [f"O:{n}" for n in range(500)]
    await read_door.read_quotes(feed, others, p.book, lambda _s: True, lambda: True, 0.0, 0.01,
                                sleep=clock.sleep, now=clock.now)
    assert "X" not in p.unsubscribed and "X" in read_door.read_lease().held_ids
    got = await task_a
    assert "X" in got and read_door.read_lease().in_use("X") == 0
    read_door.read_lease().release()


async def test_cancelling_a_read_releases_its_pin_and_the_token_can_then_be_evicted(monkeypatch):
    monkeypatch.setattr(read_door, "MAX_HELD_TOKENS", 3)
    clock = Clock()
    p = FakeProvider(clock, {"X": 100.0})  # X never ticks: A polls until cancelled
    feed = _feed(p)
    task_a = asyncio.ensure_future(_read(feed, p, clock, ["X"], wait_s=50.0))
    for _ in range(3):
        await asyncio.sleep(0)
    assert read_door.read_lease().in_use("X") == 1
    task_a.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task_a
    assert read_door.read_lease().in_use("X") == 0
    await read_door.read_quotes(feed, ["A", "B", "C"], p.book, lambda _s: True, lambda: True, 0.0, 0.01,
                                sleep=clock.sleep, now=clock.now)
    assert "X" not in read_door.read_lease().held_ids and "X" in p.unsubscribed
    read_door.read_lease().release()


async def test_expired_tokens_are_evicted_before_unexpired_ones(monkeypatch):
    monkeypatch.setattr(read_door, "MAX_HELD_TOKENS", 3)
    p = FakeProvider(Clock())
    feed = _feed(p)
    lease = read_door.ReadLease()
    lease.hold(feed, ["a"], seconds=100, now=0.0)  # oldest-renewed, not expired
    lease.hold(feed, ["b"], seconds=1, now=0.0)  # expired at t=5
    lease.hold(feed, ["c"], seconds=100, now=0.0)
    lease.hold(feed, ["d"], seconds=100, now=5.0)  # over the cap: b (expired) goes, not the older a
    assert lease.held_ids == frozenset({"a", "c", "d"})


async def test_everything_pinned_goes_over_the_cap_rather_than_evicting_a_pinned_token(monkeypatch, caplog):
    monkeypatch.setattr(read_door, "MAX_HELD_TOKENS", 2)
    p = FakeProvider(Clock())
    feed = _feed(p)
    lease = read_door.ReadLease()
    with caplog.at_level("WARNING"):
        lease.hold(feed, ["a", "b", "c"], seconds=100, now=0.0, pin=True)  # one 3-id call over a cap of 2
    assert lease.held_ids == frozenset({"a", "b", "c"}) and p.unsubscribed == []
    assert any("cap" in r.message for r in caplog.records)
    lease.unpin(["a", "b", "c"])
    lease.hold(feed, ["d"], seconds=100, now=1.0)
    assert len(lease.held_ids) == 2 and "d" in lease.held_ids  # noqa: PLR2004
