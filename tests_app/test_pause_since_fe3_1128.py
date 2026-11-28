"""Lane FE3 (28 Nov 2026), item 4 (issue 880, worker half; REQ-049 "Monitoring paused", REQ-165 AC-6): the "since" time
of a pause survives a worker restart, however many restarts and however late the first check of that trade comes.

Real case: a trade paused (no leg price) since 10:00. The worker restarts at 11:00 and again at 11:01; the first cycle
after the first restart has not checked this trade yet (a cycle checks a limited number of trades). Before: the
snapshot of that first cycle named no trade, the kept start was forgotten, and the badge read "since 11:00" (or later)
for a pause that began at 10:00.
"""
from __future__ import annotations

import datetime

from ofo.rules.inputs import DataHealth
from ofo_app import monitoring_state
from ofo_app.monitoring_state import PAUSED, Publisher
from test_background_cycle import FIRST_ID, Calls, Prov, _watched, _worker, scn  # noqa: F401 - fixture by name
from test_monitoring_state import SID, T0, _Client, _fresh
from test_pause_restart_fe2_1128 import _Reason, _Status

HOUR = datetime.timedelta(hours=1)
MIN = datetime.timedelta(minutes=1)


def _since_in(client, at):
    return monitoring_state.decode(client.data[monitoring_state.key()], at)


async def _paused_since_ten(client):
    pub = Publisher(client)
    await pub.publish({SID: _Status("PAUSED")}, {SID: _Reason("LEG_MISSING")}, {}, T0)
    return pub


async def test_core_a_cycle_that_has_not_checked_the_trade_yet_does_not_forget_its_pause_start():
    client = _Client()
    await _paused_since_ten(client)
    restarted = Publisher(client)
    await restarted.restore(T0 + HOUR)
    await restarted.publish({}, {}, {}, T0 + HOUR + 2 * monitoring_state.REFRESH_S * datetime.timedelta(seconds=1))
    later = T0 + HOUR + 5 * MIN  # the trade is checked at last: the same reason as before
    await restarted.publish({SID: _Status("PAUSED")}, {SID: _Reason("LEG_MISSING")}, {}, later)
    got = _since_in(client, later)[SID]
    print("SINCE", got.since, "WANT", T0)
    assert (got.status, got.reason, got.since) == (PAUSED, "leg_missing", T0)


async def test_a_second_restart_before_the_trade_is_checked_still_keeps_the_start():
    client = _Client()
    await _paused_since_ten(client)
    first = Publisher(client)
    await first.restore(T0 + HOUR)
    second = Publisher(client)  # restarted again at once: the key now holds the first restart's snapshot
    await second.restore(T0 + HOUR + MIN)
    later = T0 + HOUR + 3 * MIN
    await second.publish({SID: _Status("PAUSED")}, {SID: _Reason("LEG_MISSING")}, {}, later)
    assert _since_in(client, later)[SID].since == T0


async def test_the_kept_start_is_not_a_strategy_of_the_snapshot_a_reader_sees():
    client = _Client()
    await _paused_since_ten(client)
    await Publisher(client).restore(T0 + HOUR)
    got = await monitoring_state.read_states(client, [SID], T0 + HOUR, heartbeat=_fresh)
    assert (got[SID].status, got[SID].reason) == (PAUSED, monitoring_state.NOT_LISTED)


async def test_a_trade_that_reads_watched_after_the_restart_starts_its_next_pause_afresh():
    client = _Client()
    await _paused_since_ten(client)
    restarted = Publisher(client)
    await restarted.restore(T0 + HOUR)
    await restarted.publish({SID: _Status("ACTIVE")}, {}, {}, T0 + HOUR + MIN)
    again = T0 + HOUR + 20 * MIN
    await restarted.publish({SID: _Status("PAUSED")}, {SID: _Reason("LEG_MISSING")}, {}, again)
    assert _since_in(client, again)[SID].since == again
    assert restarted._kept == {}, "an answered trade is no longer carried as a kept start"


async def test_a_different_reason_after_the_restart_is_a_new_pause():
    client = _Client()
    await _paused_since_ten(client)
    restarted = Publisher(client)
    await restarted.restore(T0 + HOUR)
    at = T0 + HOUR + MIN
    await restarted.publish({SID: _Status("PAUSED")}, {SID: _Reason("STALE")}, {}, at)
    assert _since_in(client, at)[SID].since == at


async def test_a_kept_start_nobody_answered_for_a_day_is_dropped():
    client = _Client()
    await _paused_since_ten(client)
    restarted = Publisher(client)
    await restarted.restore(T0 + HOUR)
    late = T0 + HOUR + datetime.timedelta(days=1, minutes=1)
    await restarted.publish({}, {}, {}, late)
    assert "kept" in client.data[monitoring_state.key()]
    assert monitoring_state._entries_of(client.data[monitoring_state.key()], late) == {}


async def test_the_real_worker_restarted_in_the_middle_of_a_pause_keeps_the_start(scn):  # noqa: F811
    client = _Client()
    prov, now, calls = Prov(scn), [scn.clock_at], Calls()
    prov.health = DataHealth.STALE  # the feed is stale: the trade is paused (reason ``stale``)
    first = _worker(prov, _watched(scn), now, calls, want_client=client)
    await first.cycle()
    began = monitoring_state.decode(client.data[monitoring_state.key()], now[0])[FIRST_ID]
    assert (began.status, began.reason) == (PAUSED, "stale")
    now[0] += HOUR  # the worker restarts an hour later; the feed is still stale
    second = _worker(prov, _watched(scn), now, calls, want_client=client)
    real_cycle = second.cycle

    async def one_cycle():
        await real_cycle()
        second.stop()
    second.cycle = one_cycle
    await second.run()
    got = monitoring_state.decode(client.data[monitoring_state.key()], now[0])[FIRST_ID]
    print("SINCE", got.since, "WANT", began.since)
    assert (got.status, got.reason, got.since) == (PAUSED, "stale", began.since)
