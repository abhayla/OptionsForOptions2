"""REQ-113 AC-3, AC-5: the API's side of the bus (``BusSocket``) and the feed's relay, against a real Redis (CI) or the
pure-Python stand-in (a developer PC). Every Redis answer state has one behaviour, none of them "live" (ADR-015):

value present -> used | status key absent or expired -> feed down | connection refused -> stale, retried |
connection dropped mid-read -> stale, retried | empty stream -> keep waiting |
malformed / foreign-user message -> counted.

Frames come from the REAL 2026-10-08 recording. Readiness is polled, never slept.
"""
from __future__ import annotations

import asyncio
import datetime
import json
import pathlib
import sys
import time
import uuid

import pytest
import redis.asyncio as aioredis
from ofo.rules.inputs import DataHealth
from ofo_app import feed_bus

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tests"))
from marketdata._kite_fixture import all_instrument_ids, new_provider, recorded_frames

WAIT_S = 20.0
TWO_ATTEMPTS = 2
T0 = recorded_frames()[0][0]
PRICE_FRAME = next(f for _, f in recorded_frames() if len(f) > 1)


async def poll(predicate, what: str, limit: float = WAIT_S):
    deadline = time.monotonic() + limit
    while time.monotonic() < deadline:
        value = predicate()
        if asyncio.iscoroutine(value):
            value = await value
        if value:
            return value
        await asyncio.sleep(0.02)
    pytest.fail(f"timed out waiting for {what}")


class Flaky:
    """A client whose reads can be made to fail like a dropped connection."""

    def __init__(self, inner, switch: dict) -> None:
        self._inner, self._switch = inner, switch

    async def xread(self, *a, **k):
        if self._switch["drop"]:
            raise aioredis.ConnectionError("dropped mid-read")
        return await self._inner.xread(*a, **k)

    def __getattr__(self, name):
        return getattr(self._inner, name)


class World:
    """One user, a provider that wants every instrument, a BusSocket on it, and a handle on the bus."""

    def __init__(self, redis_url: str, user: str | None = None) -> None:
        self.user = user or f"u{uuid.uuid4().hex[:12]}"
        self.provider, self.clock, items = new_provider()
        self.clock.now = T0
        self.provider.subscribe(all_instrument_ids(items))
        self.switch = {"drop": False}
        self.url = redis_url
        self.socket = feed_bus.BusSocket(self.provider, user_ref=self.user, clock=self.clock,
                                         client_factory=lambda: Flaky(feed_bus.new_client(redis_url), self.switch))
        self.bus = feed_bus.new_client(redis_url)
        self.task: asyncio.Task | None = None

    async def start(self) -> None:
        self.task = asyncio.ensure_future(self.socket.run())
        await poll(lambda: self.bus.exists(feed_bus.want_key(self.user)), "the API to publish its wanted set")

    async def stop(self) -> str | None:
        self.socket.stop()
        result = None
        if self.task is not None:
            result = await asyncio.wait_for(self.task, 20)
        await self.bus.aclose()
        return result

    async def status(self, *, connected=True, ended=False, connections=1) -> None:
        body = {"u": self.user, "connected": connected, "ended": ended, "connections": connections,
                "last_frame_us": None}
        await self.bus.set(feed_bus.status_key(self.user), json.dumps(body), px=60_000)

    async def publish(self, kind: str, at: datetime.datetime, data: bytes = b"", user: str | None = None) -> None:
        await self.bus.xadd(feed_bus.ticks_key(self.user), feed_bus.encode_message(user or self.user, kind, at, data))


@pytest.fixture
async def world(redis_url):
    w = World(redis_url)
    try:
        yield w
    finally:
        if w.task is not None and not w.task.done():
            await w.stop()


async def go_live(w: World) -> None:
    await w.start()
    await w.status()
    await w.publish("connected", T0)
    await poll(lambda: w.provider.feed.connected, "the feed to be seen connected")
    await w.publish("frame", T0, PRICE_FRAME)
    await poll(lambda: w.provider.counters["frames"] >= 1, "a frame to reach the provider")


async def test_a_frame_is_stamped_with_the_feed_receive_time_so_a_late_one_is_never_live(world):
    """Attack 4: a frame published late (the feed received it T0, the API reads it 10 s on) is judged by T0."""
    w = world
    await go_live(w)
    w.clock.now = T0 + datetime.timedelta(seconds=1)
    assert w.provider.feed.health(w.clock.now) is DataHealth.AVAILABLE  # control: the same frame, read in time, is live
    w.clock.now = T0 + datetime.timedelta(seconds=10)  # the frame sat on the bus; feed time is T0
    assert w.provider.feed.health(w.clock.now) is DataHealth.STALE
    assert w.provider.feed.phase(w.clock.now) == "waiting"
    assert w.socket.last_frame_at == T0


async def test_redis_dropped_mid_read_reads_stale_then_recovers_only_on_a_fresh_frame(world):
    """Attack 5 / state "connection dropped mid-read": quotes read stale, not live, until a fresh frame."""
    w = world
    await go_live(w)
    w.clock.now = T0 + datetime.timedelta(seconds=1)
    assert w.provider.feed.health(w.clock.now) is DataHealth.AVAILABLE
    w.switch["drop"] = True
    await poll(lambda: w.socket.counters["redis_lost"] >= 1, "the API to notice the lost connection")
    assert w.provider.feed.connected is False
    assert w.provider.feed.health(w.clock.now) is DataHealth.STALE
    w.switch["drop"] = False
    await poll(lambda: w.provider.feed.connected, "the feed to be seen connected again (status key)")
    assert w.provider.feed.health(w.clock.now) is DataHealth.STALE, "connected again but no fresh frame yet"
    fresh = w.clock.now
    await w.publish("frame", fresh, PRICE_FRAME)
    await poll(lambda: w.provider.feed.health(fresh) is DataHealth.AVAILABLE, "a fresh frame to make the data live")


async def test_connection_refused_reads_not_live_and_is_retried(redis_url):
    """State "connection refused": nothing is live, and the socket keeps retrying until stopped."""
    provider, clock, items = new_provider()
    clock.now = T0
    provider.subscribe(all_instrument_ids(items))
    socket = feed_bus.BusSocket(provider, user_ref="refused1", clock=clock, redis_url="redis://127.0.0.1:1/0")
    task = asyncio.ensure_future(socket.run())
    await poll(lambda: socket.counters["redis_lost"] >= TWO_ATTEMPTS, "two refused attempts")
    assert provider.feed.health(T0) is not DataHealth.AVAILABLE
    socket.stop()
    assert await asyncio.wait_for(task, 20) == feed_bus.STOPPED


async def test_an_empty_stream_keeps_waiting_and_shows_nothing_live(world):
    """State "empty stream": no entries, no error, no frames, not live."""
    w = world
    await w.start()
    await w.status()
    await poll(lambda: w.provider.feed.connected, "the status key to mark the feed connected")
    await asyncio.sleep(0.5)  # two read cycles of an empty stream: the absence of an event is what is asserted
    assert w.provider.counters["frames"] == 0
    assert not [k for k in w.socket.counters if k.startswith("bus_")]
    assert w.provider.feed.health(T0) is DataHealth.STALE  # connected, but no data frame yet


@pytest.mark.parametrize("fields", [
    {"u": "USER", "k": "frame", "t": "not-a-number", "d": b"\x00\x01"},
    {"u": "USER", "k": "frame", "t": "1", "d": b""},
    {"u": "USER", "k": "frame", "t": "1"},
    {"u": "USER", "k": "unknown-kind", "t": "1"},
    {"u": "USER", "k": "dropped", "t": "1", "extra": "x"},
    {"k": "frame", "t": "1", "d": b"\x00\x01"},
])
async def test_a_malformed_message_is_counted_and_never_reaches_the_provider(world, fields):
    """State "malformed message": allow-list decode; nothing reaches the provider."""
    w = world
    await w.start()
    await w.bus.xadd(feed_bus.ticks_key(w.user), {k: (w.user if v == "USER" else v) for k, v in fields.items()})
    await poll(lambda: w.socket.counters["bus_malformed"] >= 1, "the malformed message to be counted")
    assert w.provider.counters["frames"] == 0


async def test_another_users_message_in_this_users_stream_is_refused(world):
    """AC-5: a message carrying another user's ref is never given to this user's provider."""
    w = world
    await w.start()
    await w.publish("frame", T0, PRICE_FRAME, user="someone-else")
    await poll(lambda: w.socket.counters["bus_foreign_user"] >= 1, "the foreign message to be counted")
    assert w.provider.counters["frames"] == 0


async def test_user_a_frames_never_reach_user_b_consumer(redis_url):
    """AC-5: two users on one bus: a frame on A's stream moves A's provider and not B's."""
    a, b = World(redis_url), World(redis_url)
    try:
        await asyncio.gather(a.start(), b.start())
        await a.status()
        await b.status()
        await a.publish("connected", T0)
        await a.publish("frame", T0, PRICE_FRAME)
        await poll(lambda: a.provider.counters["frames"] >= 1, "A's frame")
        await asyncio.sleep(0.5)
        assert b.provider.counters["frames"] == 0
        assert b.provider.feed.connected is True  # B's own status says connected; A's events did not touch it
    finally:
        await asyncio.gather(a.stop(), b.stop())


async def test_an_expired_or_malformed_status_key_means_the_feed_is_down(world):
    """State "key expired" / "malformed value" on the status key: the feed reads down, never live."""
    w = world
    await go_live(w)
    await w.bus.delete(feed_bus.status_key(w.user))
    await poll(lambda: w.provider.feed.connected is False, "the missing status key to mark the feed down")
    assert w.socket.counters["status_missing"] >= 1
    await w.bus.set(feed_bus.status_key(w.user), "garbage", px=60_000)
    await poll(lambda: w.socket.counters["bus_malformed"] >= 1, "the malformed status key to be counted")
    assert w.provider.feed.connected is False


async def test_a_session_ended_event_ends_the_socket_and_the_feed_reads_ended(world):
    """The feed's 'ended' event: the socket returns the same word KiteSocket does and the provider reads ended."""
    w = world
    await go_live(w)
    await w.publish("ended", T0)
    assert await asyncio.wait_for(w.task, 20) == feed_bus.SESSION_ENDED
    assert w.provider.feed.session_ended is True
    assert w.provider.feed.health(T0) is DataHealth.UNAVAILABLE
    await w.bus.aclose()


async def test_the_want_key_expiring_makes_the_feed_unsubscribe_and_a_restarted_api_rebuilds_it(redis_url):
    """Attack 6: the wanted snapshot has an expiry; when it lapses the feed wants nothing, and a restarted API
    writes the full set again from its own screens."""
    user = f"w{uuid.uuid4().hex[:12]}"
    bus = feed_bus.new_client(redis_url)
    relay = feed_bus.FeedRelay(user, lambda: T0)
    await bus.set(feed_bus.want_key(user), feed_bus.encode_want(user, [11, 22, 33]), px=300)
    await relay.refresh_want(bus)
    assert relay.drain_subscription_changes() == ([11, 22, 33], [])
    await poll(lambda: _gone(bus, feed_bus.want_key(user)), "the wanted snapshot to expire")
    await relay.refresh_want(bus)
    assert relay.drain_subscription_changes() == ([], [11, 22, 33])
    w = World(redis_url, user)  # the API restarts: its provider wants its screens' instruments again
    try:
        await w.start()
        await relay.refresh_want(bus)
        assert relay.subscribed_tokens() == w.provider.subscribed_tokens() != []
    finally:
        await w.stop()
        await bus.aclose()


async def _gone(bus, key) -> bool:
    return not await bus.exists(key)


@pytest.mark.parametrize("raw", [b"not json", b"[1,2]", json.dumps({"u": "x", "tokens": "1"}).encode(),
                                 json.dumps({"u": "x", "tokens": [1, "2"]}).encode(),
                                 json.dumps({"u": "other", "tokens": [1]}).encode(),
                                 json.dumps({"u": "x", "tokens": [1], "more": 1}).encode(),
                                 json.dumps({"u": "x", "tokens": [True]}).encode()])
def test_a_malformed_or_foreign_want_snapshot_means_nothing_is_wanted(raw):
    """Fail closed: a snapshot the feed cannot account for subscribes nothing."""
    relay = feed_bus.FeedRelay("x", lambda: T0)
    relay.apply_want(feed_bus.encode_want("x", [5]).encode())
    assert relay.subscribed_tokens() == [5]
    relay.apply_want(raw)
    assert relay.subscribed_tokens() == []
    assert relay.counters["bus_malformed"] == 1


def test_a_user_ref_that_could_address_another_key_is_refused():
    for bad in ("", "a:b", "a b", "a" * 65, "x*"):
        with pytest.raises(ValueError, match="user ref"):
            feed_bus.ticks_key(bad)


async def test_the_relay_publishes_frames_in_order_with_the_feed_receive_time(redis_url):
    """The feed side: frames and events leave in the order they came, each with the time the feed received it."""
    user = f"r{uuid.uuid4().hex[:12]}"
    bus = feed_bus.new_client(redis_url)
    relay = feed_bus.FeedRelay(user, lambda: T0)
    relay.on_connected(T0)
    for i in range(3):
        relay.on_frame(PRICE_FRAME, T0 + datetime.timedelta(seconds=i))
    relay.on_disconnected(T0 + datetime.timedelta(seconds=9))
    await relay.flush(bus)
    entries = await bus.xrange(feed_bus.ticks_key(user))
    decoded = [feed_bus.decode_message(user, fields)[0] for _id, fields in entries]
    assert [m.kind for m in decoded] == ["connected", "frame", "frame", "frame", "dropped"]
    assert [m.at for m in decoded][1:4] == [T0 + datetime.timedelta(seconds=i) for i in range(3)]
    assert all(m.data == PRICE_FRAME for m in decoded if m.kind == "frame")
    await bus.aclose()
