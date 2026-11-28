"""Lane FE3 (28 Nov 2026), item 3 (FE2 review F4, F6, F8; REQ-115 AC-4, AC-6): the index-exit report is safe against two
writers, a failed restart write is retried, and the expiry is renewed by every write.

Real case: two API worker processes (the PC runs more than one) write their slot of the report in the same instant.
Before: each read the whole report, added its slot and wrote it back as one string, so the later write dropped the
other's slot; a dropped slot "not run: index not live" made the trade read WATCHED for up to 10 s (the reader keeps the
worker's answer for a trade nobody lists), and one with no report at all reads paused. Now each monitor writes its own
field of a Redis hash by one atomic command.
"""
from __future__ import annotations

import asyncio
import datetime
import json
import os

import pytest

from ofo_app import monitoring_state
from ofo_app.monitoring_state import ACTIVE, PAUSED, Entry, ExitsPublisher, Publisher
from test_monitoring_state import _fresh

NOW = datetime.datetime(2026, 11, 27, 11, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
SEC = datetime.timedelta(seconds=1)


@pytest.fixture
async def rds():
    import redis.asyncio as aioredis  # noqa: PLC0415
    client = aioredis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True)
    try:
        await client.ping()
    except Exception:  # noqa: BLE001
        pytest.skip("no Redis here")
    for k in (monitoring_state.exits_key(), monitoring_state.exit_slots_key(), monitoring_state.key()):
        await client.delete(k)
    yield client
    for k in (monitoring_state.exits_key(), monitoring_state.exit_slots_key(), monitoring_state.key()):
        await client.delete(k)
    await client.aclose()


class _Crossing:
    """The race, made certain: both monitors' FIRST ``get`` waits until both have read, and monitor ``slow`` waits a
    little before its first ``set``; so the other monitor has written and verified before ``slow`` writes."""

    def __init__(self, real, barrier, slow=False):
        self._real, self._barrier, self._slow = real, barrier, slow
        self._first_get = True
        self._first_set = True

    def __getattr__(self, name):
        return getattr(self._real, name)

    async def get(self, k):
        value = await self._real.get(k)
        if self._first_get:
            self._first_get = False
            await self._barrier()
        return value

    async def set(self, k, v, **kw):
        if self._first_set and self._slow:
            self._first_set = False
            await asyncio.sleep(0.2)
        return await self._real.set(k, v, **kw)


async def _two_monitors(rds):
    arrived = []
    release = asyncio.Event()

    async def barrier():
        arrived.append(1)
        if len(arrived) >= 2:
            release.set()
        try:
            await asyncio.wait_for(release.wait(), 1.0)
        except TimeoutError:
            pass  # the new code never reads with ``get`` here: nobody waits for the other
    a = ExitsPublisher(_Crossing(rds, barrier), "monitor-a")
    b = ExitsPublisher(_Crossing(rds, barrier, slow=True), "monitor-b")
    # monitor A: trade 1's index exit has no live index (not run); monitor B judges trade 2
    await asyncio.gather(a.publish([1], {1: monitoring_state.INDEX_NOT_LIVE}, NOW),
                         b.publish([2], {}, NOW))


async def _read(rds, ids, at):
    await rds.set(monitoring_state.key(), monitoring_state.encode([Entry(i, ACTIVE, "", "", NOW) for i in ids], at))
    return await monitoring_state.read_states(rds, ids, at, heartbeat=_fresh)


async def test_core_two_monitors_writing_in_the_same_instant_keep_both_slots(rds):
    await _two_monitors(rds)
    got = await _read(rds, [1, 2], NOW + SEC)
    print("READ", {i: (e.status, e.reason, e.why) for i, e in got.items()})
    assert (got[1].status, got[1].why) == (PAUSED, monitoring_state.INDEX_NOT_LIVE), \
        "monitor A's report was dropped: trade 1 reads as the worker says"
    assert got[2].status == ACTIVE


async def test_twenty_monitors_writing_at_once_all_keep_their_slot(rds):
    pubs = [ExitsPublisher(rds, f"m{i}") for i in range(20)]
    await asyncio.gather(*(p.publish([i], {}, NOW) for i, p in enumerate(pubs)))
    fields = await rds.hgetall(monitoring_state.exit_slots_key())
    assert sorted(fields) == sorted(f"m{i}" for i in range(20))
    for i in range(20):
        assert json.loads(fields[f"m{i}"])["watching"] == [i]


async def test_every_write_renews_the_expiry(rds):
    pub = ExitsPublisher(rds, "m1")
    await pub.publish([1], {}, NOW)
    await rds.expire(monitoring_state.exit_slots_key(), 100)  # nearly expired
    assert await pub.publish([1], {}, NOW + 11 * SEC)  # due again after REFRESH_S
    assert await rds.ttl(monitoring_state.exit_slots_key()) > monitoring_state.EXITS_KEY_TTL_S - 60


async def test_a_failed_write_is_retried_on_the_next_pass_and_not_recorded_as_written(rds):
    class Flaky:
        def __init__(self):
            self.fail = True

        def __getattr__(self, name):
            return getattr(rds, name)

        async def hset(self, *a, **k):
            if self.fail:
                self.fail = False
                raise OSError("down")
            return await rds.hset(*a, **k)
    pub = ExitsPublisher(Flaky(), "m1")
    assert await pub.publish([1], {}, NOW) is False
    assert await rds.hgetall(monitoring_state.exit_slots_key()) == {}
    assert await pub.publish([1], {}, NOW + SEC) is True  # the very next pass, not the next refresh
    assert "m1" in await rds.hgetall(monitoring_state.exit_slots_key())


async def test_a_string_key_left_by_the_old_version_is_ignored_and_never_breaks_a_write(rds):
    await rds.set(monitoring_state.exits_key(), json.dumps({"owners": {}}), ex=3600)
    pub = ExitsPublisher(rds, "m1")
    assert await pub.publish([1], {}, NOW)
    got = await _read(rds, [1], NOW + SEC)
    assert got[1].status == ACTIVE


async def test_no_report_at_all_still_reads_not_checked_yet(rds):
    got = await _read(rds, [1], NOW)
    assert (got[1].status, got[1].why) == (PAUSED, monitoring_state.EXITS_NOT_CHECKED_YET)


async def test_a_monitor_gone_for_an_hour_is_removed_by_the_next_writer_and_a_live_one_is_not(rds):
    old = {"at": (NOW - datetime.timedelta(hours=2)).isoformat(), "not_run": {}, "watching": [9]}
    live = {"at": (NOW - 5 * SEC).isoformat(), "not_run": {}, "watching": [8]}
    await rds.hset(monitoring_state.exit_slots_key(), mapping={"dead": json.dumps(old), "live": json.dumps(live)})
    assert await ExitsPublisher(rds, "m1").publish([1], {}, NOW)
    assert sorted(await rds.hgetall(monitoring_state.exit_slots_key())) == ["live", "m1"]


async def test_a_slot_that_cannot_be_read_is_skipped_not_fatal(rds):
    await rds.hset(monitoring_state.exit_slots_key(), "junk", "not json")
    assert await ExitsPublisher(rds, "m1").publish([1], {}, NOW)
    got = await _read(rds, [1], NOW + SEC)
    assert got[1].status == ACTIVE


async def test_f6_a_restart_snapshot_that_failed_is_written_again_before_the_next_cycle(rds):
    class Flaky:
        def __init__(self):
            self.fail = True

        def __getattr__(self, name):
            return getattr(rds, name)

        async def set(self, *a, **k):
            if self.fail:
                self.fail = False
                raise OSError("down")
            return await rds.set(*a, **k)
    await rds.set(monitoring_state.key(), monitoring_state.encode([Entry(7, ACTIVE, "", "", NOW)], NOW))  # old answer
    pub = Publisher(Flaky())
    assert await pub.restore(NOW + SEC) is False
    assert pub.restore_pending
    assert monitoring_state.decode(await rds.get(monitoring_state.key()), NOW + SEC)[7].status == ACTIVE  # still there
    assert await pub.retry_restore(NOW + 2 * SEC) is True
    assert not pub.restore_pending
    assert monitoring_state.decode(await rds.get(monitoring_state.key()), NOW + 2 * SEC) == {}
    assert await pub.retry_restore(NOW + 3 * SEC) is False  # nothing pending: nothing written
