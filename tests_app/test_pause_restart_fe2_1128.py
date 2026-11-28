"""Lane FE2 (28 Nov 2026), item 4 (issue #868, REQ-165 AC-6, REQ-115 AC-4 / AC-6): the paused state is not lost on a
worker restart. Redis, the store the monitoring snapshot already uses, carries it (no migration).

Real case: a trade paused for an hour (no price for one leg since 10:00). The worker is restarted at 11:00. Until its
first check the OLD snapshot still said "active" for trades the new worker had not looked at, and "since" restarted
at 11:00. Now: the restart writes a snapshot that names no trade (every trade reads "not listed", paused, until its
first check has run) and keeps each trade's since while its status and reason stay the same.
"""
from __future__ import annotations

import datetime
import json

from ofo_app import monitoring_state
from ofo_app.monitoring_state import ACTIVE, PAUSED, Entry
from test_background_cycle import Calls, Prov, _watched, _worker, scn  # noqa: F401 - the fixture is used by name
from test_monitoring_state import SID, T0, _Client, _fresh

HOUR = datetime.timedelta(hours=1)


def _old_snapshot(client, status, reason="", since=T0):
    client.data[monitoring_state.key()] = monitoring_state.encode(
        [Entry(SID, status, reason, "", since)], since + HOUR - datetime.timedelta(seconds=5))


async def test_a_restarted_worker_leaves_no_old_active_answer_standing_before_its_first_check(scn):  # noqa: F811
    client = _Client()
    prov, now, calls = Prov(scn), [scn.clock_at], Calls()
    stamp = scn.clock_at
    client.data[monitoring_state.key()] = monitoring_state.encode(
        [Entry(SID, ACTIVE, "", "", stamp - HOUR)], stamp - datetime.timedelta(seconds=5))  # the dead worker's answer
    w = _worker(prov, _watched(scn), now, calls, want_client=client)
    before_first_check: dict = {}
    real_cycle = w.cycle

    async def spy():
        before_first_check.update(await monitoring_state.read_states(client, [SID], stamp, heartbeat=_fresh))
        await real_cycle()
        w.stop()
    w.cycle = spy
    await w.run()
    print("BEFORE FIRST CHECK", before_first_check)
    got = before_first_check[SID]
    assert (got.status, got.reason) == (PAUSED, monitoring_state.NOT_LISTED), got


async def test_the_since_of_a_trade_paused_before_the_restart_is_kept(scn):  # noqa: F811
    client = _Client()
    stamp = scn.clock_at
    client.data[monitoring_state.key()] = monitoring_state.encode(
        [Entry(SID, PAUSED, "stale", "", stamp - HOUR)], stamp - datetime.timedelta(seconds=5))
    pub = monitoring_state.Publisher(client)
    await pub.restore(stamp)
    assert await pub.publish({SID: _Status("PAUSED")}, {SID: _Reason("STALE")}, {}, stamp)
    kept = monitoring_state.decode(client.data[monitoring_state.key()], stamp)[SID]
    assert (kept.status, kept.reason, kept.since) == (PAUSED, "stale", stamp - HOUR)


async def test_a_snapshot_of_another_shape_or_a_dead_store_restores_nothing_and_never_raises(scn):  # noqa: F811
    stamp = scn.clock_at
    for raw in ("not json", '{"strategies": 5}', None):
        client = _Client()
        if raw is not None:
            client.data[monitoring_state.key()] = raw
        pub = monitoring_state.Publisher(client)
        await pub.restore(stamp)
        assert json_strategies(client) == {}
    dead = _Client(boom=True)
    await monitoring_state.Publisher(dead).restore(stamp)
    assert dead.data == {}


async def test_a_snapshot_older_than_a_day_is_not_restored(scn):  # noqa: F811
    client = _Client()
    stamp = scn.clock_at
    client.data[monitoring_state.key()] = monitoring_state.encode(
        [Entry(SID, PAUSED, "stale", "", stamp - 3 * HOUR * 24)], stamp - 2 * HOUR * 24)
    pub = monitoring_state.Publisher(client)
    await pub.restore(stamp)
    await pub.publish({SID: _Status("PAUSED")}, {SID: _Reason("STALE")}, {}, stamp)
    assert monitoring_state.decode(client.data[monitoring_state.key()], stamp)[SID].since == stamp


def json_strategies(client) -> dict:
    return json.loads(client.data[monitoring_state.key()])["strategies"]


class _Status:
    def __init__(self, name):
        self.name = name


class _Reason(_Status):
    pass


async def test_an_active_trades_since_starts_again_after_a_restart(scn):  # noqa: F811
    client = _Client()
    stamp = scn.clock_at
    client.data[monitoring_state.key()] = monitoring_state.encode(
        [Entry(SID, ACTIVE, "", "", stamp - HOUR)], stamp - datetime.timedelta(seconds=5))
    pub = monitoring_state.Publisher(client)
    await pub.restore(stamp)
    await pub.publish({SID: _Status("ACTIVE")}, {}, {}, stamp)
    assert monitoring_state.decode(client.data[monitoring_state.key()], stamp)[SID].since == stamp
