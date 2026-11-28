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
    (_ago(-3), feed_bus.FRESH), (_ago(-5), feed_bus.FRESH),  # #879: a few seconds of skew is allowed
    (_ago(-6), feed_bus.UNREADABLE), (_ago(-100), feed_bus.UNREADABLE),  # a clock 100 s ahead is not a live worker
    (_ago(-120), feed_bus.UNREADABLE), (_ago(-121), feed_bus.UNREADABLE),
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
        async def set(self, key, value, px=None, ex=None):
            if key == feed_bus.heartbeat_key():
                raise RedisConnectionError("secret-host")
            await super().set(key, value, px, ex)

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


def test_the_heartbeat_skew_is_the_snapshots_skew():
    from ofo_app import monitoring_state  # noqa: PLC0415
    assert feed_bus.HEARTBEAT_SKEW_S == monitoring_state.CLOCK_SKEW_S


def test_fd5_a_stamp_that_does_not_change_goes_stale_by_the_readers_own_clock_even_when_it_looks_young():
    """FD5 3.5 (Opus review F1, #879): a worker whose clock runs 4 s ahead and then dies stamps NOW + 4 once; the age
    rule alone calls that fresh until real time passes the stamp + 120 s. The reader notes when it last CHANGED."""
    reader = feed_bus.HeartbeatReader()
    stamp = (NOW + datetime.timedelta(seconds=4)).isoformat()
    assert reader.judge(stamp, NOW) == feed_bus.FRESH  # the first reading: nothing to compare with
    at = NOW + datetime.timedelta(seconds=120)
    assert feed_bus.judge_heartbeat(stamp, at + datetime.timedelta(seconds=1)) == feed_bus.FRESH  # the age rule alone
    assert reader.judge(stamp, at) == feed_bus.FRESH  # 120 s unchanged: still inside the window
    assert reader.judge(stamp, at + datetime.timedelta(seconds=1)) == feed_bus.STALE  # 121 s unchanged: stopped
    moved = (at + datetime.timedelta(seconds=2)).isoformat()
    assert reader.judge(moved, at + datetime.timedelta(seconds=2)) == feed_bus.FRESH  # a new stamp is live again


def test_fd5_a_changing_stamp_stays_fresh_and_the_unreadable_answers_are_not_touched():
    reader = feed_bus.HeartbeatReader()
    for n in range(0, 600, 30):
        at = NOW + datetime.timedelta(seconds=n)
        assert reader.judge(at.isoformat(), at) == feed_bus.FRESH
    assert reader.judge(None, NOW + datetime.timedelta(seconds=700)) == feed_bus.UNREADABLE
    assert reader.judge("not a time", NOW + datetime.timedelta(seconds=760)) == feed_bus.UNREADABLE


def test_fd5_the_monitoring_skew_equals_the_feed_bus_skew():
    """FD5 3.2: ``monitoring_state.CLOCK_SKEW_S`` (Lane FE3's file) and ``feed_bus.HEARTBEAT_SKEW_S`` are one number;
    FE3 makes the first the second, and until then this holds them equal."""
    from ofo_app import monitoring_state  # noqa: PLC0415
    assert monitoring_state.CLOCK_SKEW_S == feed_bus.HEARTBEAT_SKEW_S


async def test_ra_the_heartbeat_carries_a_store_side_expiry_of_the_stale_window():
    """Lane RA (FE3 "Not done", Opus F1 #879): a writer whose clock runs ahead and then dies must not read fresh: the
    key itself expires after the stale window (HEARTBEAT_STALE_S, 120 s) in the store, whatever the stamp says."""
    seen: dict = {}

    class Recorder:
        async def set(self, key, value, **kw):
            seen.update(key=key, value=value, **kw)

    at = datetime.datetime(2026, 11, 27, 11, 0, tzinfo=datetime.UTC)
    await feed_bus.write_heartbeat(Recorder(), at)
    assert seen == {"key": feed_bus.heartbeat_key(), "value": at.isoformat(), "ex": feed_bus.HEARTBEAT_STALE_S}
    assert feed_bus.HEARTBEAT_STALE_S == 120  # noqa: PLR2004 - REQ-115 AC-6
