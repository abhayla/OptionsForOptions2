"""Lane FE3 (28 Nov 2026), item 1 (REQ-115 AC-4 / AC-6, ADR-016 to ADR-019): a failed check stays failed.

Real case: the write of a check fails (the database is down for a second). ``Worker._write_one`` pauses the trade
(``CHECK_FAILED``). The next cycle has a fresh price but its check is held (the style's interval has not passed): before
this lane that fresh read set the trade ACTIVE again, so a trade whose last check FAILED read "watched" without a
check having run. Now only a check that has run and passed clears it.

Core: the real worker on the real monitoring store (Redis), read back the way the API process reads it.
"""
from __future__ import annotations

import datetime
import os
import uuid

import pytest

from ofo_app import background, monitoring_state
from test_background_cycle import DEFAULTS, FIRST_ID, Calls, Prov, _settings, _watched, _worker, scn  # noqa: F401
from test_monitoring_state import _fresh


@pytest.fixture
async def redis_client():
    import redis.asyncio as aioredis  # noqa: PLC0415
    client = aioredis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True)
    try:
        await client.ping()
    except Exception:  # noqa: BLE001
        pytest.skip("no Redis here")
    yield client
    await client.delete(monitoring_state.key())
    await client.aclose()


async def _state(client, now):
    await monitoring_state.ExitsPublisher(client, "m-" + uuid.uuid4().hex[:6]).publish([], {}, now)  # a live monitor
    return (await monitoring_state.read_states(client, [FIRST_ID], now, heartbeat=_fresh))[FIRST_ID]


def _worker_on(redis_client, prov, now, recorder, scn):  # noqa: F811
    w = _worker(prov, _watched(scn), now, recorder, want_client=redis_client, settings=_settings(dict(DEFAULTS)))

    async def no_wants(*_a, **_k):  # the test provider has no token table; the want write is not what is tested here
        return None
    w._write_wants = no_wants
    return w


def _failing_once(calls):
    boom = [True]

    async def recorder(wd, state, prefs=None):
        if boom[0]:
            boom[0] = False
            raise RuntimeError("db down")
        await calls(wd, state, prefs)
    return recorder


async def test_core_a_failed_check_is_not_undone_by_a_cycle_that_skips_the_check(scn, redis_client):  # noqa: F811
    prov, now, calls = Prov(scn), [scn.clock_at], Calls()
    w = _worker_on(redis_client, prov, now, _failing_once(calls), scn)
    await w.cycle()  # the check ran; its write raised
    assert w.paused_reason[FIRST_ID] is background.PriceState.CHECK_FAILED
    ran = len(w.checks)
    now[0] += datetime.timedelta(seconds=1)  # a fresh read, the check is held by the style's interval
    await w.cycle()
    assert len(w.checks) == ran, "the check must have been skipped in this cycle"
    got = await _state(redis_client, now[0])
    print("READ BACK", got, w.status[FIRST_ID], w.paused_reason.get(FIRST_ID))
    assert w.status[FIRST_ID] is background.MonitoringStatus.PAUSED
    assert w.paused_reason[FIRST_ID] is background.PriceState.CHECK_FAILED
    assert got.status == monitoring_state.PAUSED, got


async def test_a_check_that_ran_and_passed_clears_the_failure(scn, redis_client):  # noqa: F811
    prov, now, calls = Prov(scn), [scn.clock_at], Calls()
    w = _worker_on(redis_client, prov, now, _failing_once(calls), scn)
    await w.cycle()
    now[0] += datetime.timedelta(seconds=1)
    await w.cycle()  # held
    assert w.status[FIRST_ID] is background.MonitoringStatus.PAUSED
    for _ in range(40):  # past every style's interval; the price moves so the signature is new
        now[0] += datetime.timedelta(seconds=30)
        prov.move_spot(prov.spot.ltp + 1, now[0])
        await w.cycle()
        if w.status[FIRST_ID] is background.MonitoringStatus.ACTIVE:
            break
    assert w.status[FIRST_ID] is background.MonitoringStatus.ACTIVE
    assert FIRST_ID not in w.paused_reason
    assert len(calls.writes) >= 1  # the check that cleared it wrote its result
    got = await _state(redis_client, now[0])
    assert got.status == monitoring_state.ACTIVE, got


async def test_a_second_failed_write_pauses_again(scn, redis_client):  # noqa: F811
    prov, now, calls = Prov(scn), [scn.clock_at], Calls()

    async def always_fails(_w, _s, _p=None):
        raise RuntimeError("db down")
    w = _worker_on(redis_client, prov, now, always_fails, scn)
    for _ in range(4):
        now[0] += datetime.timedelta(seconds=60)
        prov.move_spot(prov.spot.ltp + 1, now[0])
        await w.cycle()
        assert w.paused_reason[FIRST_ID] is background.PriceState.CHECK_FAILED
        assert w.status[FIRST_ID] is background.MonitoringStatus.PAUSED
