"""Lane FE2 (28 Nov 2026), items 8a and 8b (issues #878, #879; Lane Y's findings 3 and 4 of the Opus review of J2).
Spec basis: REQ-115 AC-4 and AC-6 (no heartbeat for 2 minutes: every affected strategy shows "Monitoring paused");
ADR-330 (44), (58).

#878 real case: a strategy that left the worker's list (exited, plan removed) kept its ACTIVE entry in ``Worker.status``
for as long as the worker ran, so it was published as watched. Now it is not listed, and reads paused ``not_listed``.
#879 real case: a worker clock 100 s ahead stamped the snapshot 100 s into the future; the reader judged it within
+-120 s of its own clock, so the 2-minute window became 220 s.
"""
from __future__ import annotations

import datetime

from ofo_app import monitoring_state
from ofo_app.monitoring_state import ACTIVE, PAUSED, Entry
from test_background_cycle import FIRST_ID, Calls, Prov, _watched, _worker, scn  # noqa: F401 - the module fixture
from test_monitoring_state import SID, T0, _Client, _fresh

SEC = datetime.timedelta(seconds=1)


class _Listed(list):
    unread: frozenset = frozenset()


async def test_a_strategy_that_left_the_list_is_no_longer_published_as_watched(scn):  # noqa: F811
    client = _Client()
    prov, now, calls = Prov(scn), [scn.clock_at], Calls()
    watched = _Listed(_watched(scn))
    w = _worker(prov, watched, now, calls, want_client=client)
    await w.cycle()
    assert w.status[FIRST_ID].name == "ACTIVE"
    ok = await monitoring_state.read_states(client, [FIRST_ID], now[0], heartbeat=_fresh)
    assert ok[FIRST_ID].status == ACTIVE
    watched.clear()  # the strategy exited
    await w.rebuild()
    now[0] += SEC
    await w.cycle()
    got = (await monitoring_state.read_states(client, [FIRST_ID], now[0], heartbeat=_fresh))[FIRST_ID]
    print("AFTER DROP", got, dict(w.status))
    assert FIRST_ID not in w.status and FIRST_ID not in w.paused_reason
    assert (got.status, got.reason) == (PAUSED, monitoring_state.NOT_LISTED), got


async def test_a_strategy_whose_read_failed_keeps_its_status(scn):  # noqa: F811
    prov, now, calls = Prov(scn), [scn.clock_at], Calls()
    watched = _Listed(_watched(scn))
    w = _worker(prov, watched, now, calls)
    await w.cycle()
    watched.clear()
    watched.unread = frozenset({FIRST_ID})  # a failed read is not a strategy leaving
    await w.rebuild()
    assert FIRST_ID in w.status  # its facts are kept for the next good read
    client_after = _Client()
    w2 = _worker(prov, watched, now, calls, want_client=client_after)
    w2.status.update(w.status)  # the same state, a worker that publishes
    w2.monitors = []
    now[0] += SEC
    await w2.cycle()
    got = (await monitoring_state.read_states(client_after, [FIRST_ID], now[0], heartbeat=_fresh))[FIRST_ID]
    assert (got.status, got.reason) == (PAUSED, monitoring_state.NOT_LISTED), "not monitored: never published ACTIVE"


def _snapshot_at(at, now):
    return monitoring_state.encode([Entry(SID, ACTIVE, "", "", at)], at), now


async def test_a_snapshot_stamped_in_the_future_is_not_a_fresh_snapshot():
    client = _Client()
    now = T0
    client.data[monitoring_state.key()] = monitoring_state.encode([Entry(SID, ACTIVE, "", "", now)], now + 100 * SEC)
    got = (await monitoring_state.read_states(client, [SID], now, heartbeat=_fresh))[SID]
    assert (got.status, got.reason) == (PAUSED, monitoring_state.STATE_UNREADABLE), got


async def test_a_snapshot_a_second_ahead_is_still_fresh_and_one_119_seconds_old_too():
    client = _Client()
    now = T0
    for stamp in (now + SEC, now - 119 * SEC):
        client.data[monitoring_state.key()] = monitoring_state.encode([Entry(SID, ACTIVE, "", "", now)], stamp)
        got = (await monitoring_state.read_states(client, [SID], now, heartbeat=_fresh))[SID]
        assert got.status == ACTIVE, (stamp, got)
    client.data[monitoring_state.key()] = monitoring_state.encode(
        [Entry(SID, ACTIVE, "", "", now)], now - 121 * SEC)
    got = (await monitoring_state.read_states(client, [SID], now, heartbeat=_fresh))[SID]
    assert got.reason == monitoring_state.STATE_UNREADABLE, got


async def test_a_report_stamped_in_the_future_does_not_keep_a_monitor_alive():
    now = T0
    raw = monitoring_state.json.dumps({"at": (now + 100 * SEC).isoformat(), "owners": {"a": {
        "at": (now + 100 * SEC).isoformat(), "not_run": {}, "watching": [SID]}}})
    assert monitoring_state.decode_exits(raw, now) == {SID: monitoring_state.INDEX_EXITS_NOT_RUN}


async def test_readings_noted_in_the_future_are_not_read():
    client = _Client()
    now = T0
    client.data[monitoring_state.key()] = monitoring_state.encode([], now + 100 * SEC)
    assert await monitoring_state.read_readings(client, now) is None
