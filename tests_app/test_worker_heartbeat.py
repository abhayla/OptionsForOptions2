"""GC-ICSAFE (ADR-286, REQ-115 AC-6): the background worker's heartbeat in the feed bus store, and the pure judgement of
its age. Non-DB: a fake Redis. Every answer state (fresh, stale, missing, malformed, store raises) has its own test."""
from __future__ import annotations

import datetime
import logging

import pytest
from ofo_app import feed_bus
from redis.exceptions import ConnectionError as RedisConnectionError

from tests_app.test_background_wire_want import FakeRedis, IndexedProv, _watched, _worker, scn  # noqa: F401 - fixture

NOW = datetime.datetime(2026, 11, 10, 10, 0, tzinfo=feed_bus.IST)


def _ago(seconds: int) -> str:
    return (NOW - datetime.timedelta(seconds=seconds)).isoformat()


@pytest.mark.parametrize("raw, state", [
    (_ago(0), feed_bus.FRESH), (_ago(119), feed_bus.FRESH), (_ago(120), feed_bus.FRESH), (_ago(121), feed_bus.STALE),
    (_ago(121).encode(), feed_bus.STALE), (None, feed_bus.UNREADABLE), ("", feed_bus.UNREADABLE),
    ("not a time", feed_bus.UNREADABLE), (b"\xff\xfe", feed_bus.UNREADABLE), (12345, feed_bus.UNREADABLE),
    ("2026-11-10T09:59:00", feed_bus.UNREADABLE),  # no time zone: cannot be compared, never read as fresh
    (_ago(-120), feed_bus.FRESH), (_ago(-121), feed_bus.UNREADABLE),  # a time far AHEAD of now is not a live worker
])
def test_judge_the_age(raw, state):
    assert feed_bus.judge_heartbeat(raw, NOW) == state


class _Store:
    def __init__(self, value=None, error=None):
        self.value, self.error = value, error

    async def get(self, key):
        assert key == feed_bus.heartbeat_key()
        if self.error is not None:
            raise self.error
        return self.value


async def test_read_state_judges_what_the_store_holds():
    assert await feed_bus.read_heartbeat_state(_Store(_ago(5)), NOW) == feed_bus.FRESH
    assert await feed_bus.read_heartbeat_state(_Store(_ago(500)), NOW) == feed_bus.STALE
    assert await feed_bus.read_heartbeat_state(_Store(None), NOW) == feed_bus.UNREADABLE


async def test_a_store_that_raises_is_unreadable_never_fresh():
    assert await feed_bus.read_heartbeat_state(_Store(error=RedisConnectionError("down")), NOW) \
        == feed_bus.UNREADABLE


async def test_each_cycle_writes_the_cycle_time(scn):  # noqa: F811
    prov, now, client = IndexedProv(scn), [scn.clock_at], FakeRedis()
    prov.closed = True
    await _worker(prov, _watched(scn), now, client).cycle()
    assert client.data[feed_bus.heartbeat_key()] == scn.clock_at.isoformat()
    now[0] += datetime.timedelta(seconds=7)
    await _worker(prov, _watched(scn), now, client).cycle()
    assert client.data[feed_bus.heartbeat_key()] == now[0].isoformat()


async def test_a_failed_heartbeat_write_is_logged_by_type_and_never_stops_the_cycle(scn, caplog):  # noqa: F811
    class Down(FakeRedis):
        async def set(self, key, value, px=None):
            if key == feed_bus.heartbeat_key():
                raise RedisConnectionError("secret-host")
            await super().set(key, value, px)

    prov, now, client = IndexedProv(scn), [scn.clock_at], Down()
    prov.closed = True
    worker = _worker(prov, _watched(scn), now, client)
    caplog.set_level(logging.WARNING)
    await worker.cycle()
    assert worker._cycles == 1 and feed_bus.want_key("owner") + ":bg" in client.data  # the rest of the cycle ran
    assert "ConnectionError" in caplog.text and "secret-host" not in caplog.text


async def test_the_scenario_role_has_no_bus_client_so_it_never_writes_the_live_heartbeat(scn):  # noqa: F811
    """The scenario role is wired without ``want_client`` (``background._serve_scenario``), so a simulated clock can
    never reach the shared key the live API judges."""
    prov, now = IndexedProv(scn), [scn.clock_at]
    prov.closed = True
    worker = _worker(prov, _watched(scn), now, None)
    await worker.cycle()
    assert worker._cycles == 1
