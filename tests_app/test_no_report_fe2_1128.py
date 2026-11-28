"""Lane FE2 (28 Nov 2026), coordinator item (a): with no index-exit report at all, a trade the worker calls watched
reads NOT watched. Spec basis: REQ-115, REQ-049 ("Monitoring paused"), ADR-016 to ADR-019 (an unresolved state blocks;
it is never assumed good).

Real case: Lane FE decided "no monitor ever wrote = the worker's answer stands". That fails open: the API process (the
only place an index exit is judged) may be down or never have started, and the trade read watched with nobody judging
its exit. Now the reason is ``stale`` with the why ``exits_not_checked_yet``.
"""
from __future__ import annotations

import datetime

from ofo_app import monitoring_state
from ofo_app.monitoring_state import ACTIVE, PAUSED, Entry
from test_monitoring_state import SID, T0, _Client, _fresh

SEC = datetime.timedelta(seconds=1)


async def test_no_report_at_all_is_not_watched():
    client = _Client()
    client.data[monitoring_state.key()] = monitoring_state.encode([Entry(SID, ACTIVE, "", "", T0)], T0)
    got = (await monitoring_state.read_states(client, [SID], T0, heartbeat=_fresh))[SID]
    assert (got.status, got.reason, got.why) == (PAUSED, "stale", monitoring_state.EXITS_NOT_CHECKED_YET), got


async def test_a_report_older_than_the_allowed_age_is_not_watched():
    client = _Client()
    client.data[monitoring_state.key()] = monitoring_state.encode([Entry(SID, ACTIVE, "", "", T0)], T0)
    pub = monitoring_state.ExitsPublisher(client, "a")
    await pub.publish([SID], {}, T0 - 200 * SEC)
    got = (await monitoring_state.read_states(client, [SID], T0, heartbeat=_fresh))[SID]
    assert (got.status, got.why) == (PAUSED, monitoring_state.INDEX_EXITS_NOT_RUN), got


async def test_a_fresh_report_that_does_not_list_the_trade_leaves_it_watched():
    """The trade has no armed index exit: nothing to judge, so the worker's answer stands (the control)."""
    client = _Client()
    client.data[monitoring_state.key()] = monitoring_state.encode([Entry(SID, ACTIVE, "", "", T0)], T0)
    await monitoring_state.ExitsPublisher(client, "a").publish([SID + 1], {}, T0)
    got = (await monitoring_state.read_states(client, [SID], T0, heartbeat=_fresh))[SID]
    assert got.status == ACTIVE, got


async def test_a_trade_the_worker_already_calls_paused_keeps_its_own_reason():
    client = _Client()
    client.data[monitoring_state.key()] = monitoring_state.encode([Entry(SID, PAUSED, "stale", "rest_stale", T0)], T0)
    got = (await monitoring_state.read_states(client, [SID], T0, heartbeat=_fresh))[SID]
    assert (got.status, got.why) == (PAUSED, "rest_stale"), got
