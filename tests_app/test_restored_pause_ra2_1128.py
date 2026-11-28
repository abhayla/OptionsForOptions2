"""Lane RA2 item 3, F8 (Lane FE3 review; ADR-330 (64), REQ-165 AC-6): a pause start restored at the worker's start
is kept only for a strategy the worker still lists. Real case: ids 100 and 999 were paused (since 10:00) when the
worker stopped; trade 999 was deleted while it was down. After the first successful read of the strategy list
(ids {100}) only 100 keeps its start. A FAILED strategy-list read names nobody and never drops a kept start."""
from __future__ import annotations

import datetime

import pytest
from ofo_app import monitoring_state
from ofo_app.monitoring_state import Publisher
from test_background_cycle import scn  # noqa: F401 - fixture by name
from test_monitoring_state import _Client

AT = datetime.datetime(2026, 11, 28, 11, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
SINCE = AT - datetime.timedelta(hours=1)


def _old_snapshot() -> str:
    entries = [monitoring_state.Entry(i, monitoring_state.PAUSED, "price_stale", "", SINCE) for i in (1, 2)]
    return monitoring_state.encode(entries, AT - datetime.timedelta(seconds=30))


async def _restored() -> Publisher:
    client = _Client()
    client.data[monitoring_state.key()] = _old_snapshot()
    pub = Publisher(client)
    assert await pub.restore(AT) is True
    assert sorted(pub._kept) == [1, 2]
    return pub


async def test_a_deleted_trades_kept_start_is_dropped_after_the_list_was_read():
    pub = await _restored()
    assert pub.forget_unlisted({1}) == [2]
    assert sorted(pub._kept) == [1] and sorted(pub._previous) == [1]


async def test_the_worker_drops_it_after_a_good_list_read_and_never_after_a_failed_one(scn):  # noqa: F811
    from test_background_cycle import Calls, Prov, _watched, _worker  # noqa: PLC0415 - the cycle tests' own harness

    now = [scn.clock_at]
    client = _Client()
    entries = [monitoring_state.Entry(i, monitoring_state.PAUSED, "price_stale", "", SINCE) for i in (100, 999)]
    stamp = scn.clock_at - datetime.timedelta(seconds=30)
    client.data[monitoring_state.key()] = monitoring_state.encode(entries, stamp)
    worker = _worker(Prov(scn), _watched(scn), now, Calls(), want_client=client)
    assert await worker._monitoring.restore(scn.clock_at) is True
    assert sorted(worker._monitoring._kept) == [100, 999]

    async def failing():
        raise RuntimeError("the strategy list could not be read")
    good = worker._lister
    worker._lister = failing
    with pytest.raises(RuntimeError):
        await worker.rebuild()
    assert sorted(worker._monitoring._kept) == [100, 999], "a failed read names nobody: nothing is dropped"
    worker._lister = good
    await worker.rebuild()
    assert sorted(worker._monitoring._kept) == [100], "trade 999 was deleted while the worker was down"
