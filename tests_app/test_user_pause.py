"""GC-IC1 step 4a core (A-38, REQ-170 AC-5): the user's pause makes the REAL background Worker skip the ADJUSTMENT
checks of that one strategy until the chosen time, and the pause ends by itself at that time.

Scenario ADJ-02 seeded through the app's stores, intraday-pinned (1-minute candles), the Worker on a pinned clock (the
scenario's clock), records counted by SQL. Clock: S = the settled start. The user pauses until S + 20 min. At S + 5 min
the T-01 crossing price arrives and stays: no record while the pause holds (status PAUSED, reason USER_PAUSED, the end
shown). After the end, with no action, the crossing (still true) opens exactly ONE record through the gate. The paper
stop inside the pause is proven in ``test_risk_exit_not_gated.py`` (the paper exit path never reads the pause).
"""
from __future__ import annotations

import datetime

import pytest
from ofo.timeutil import IST
from ofo_app import background, strategy_pause_store
from test_background_worker import (  # noqa: F401 - the shared fixture
    CROSS_SPOT,
    _advance,
    _last_id,
    _push_spot,
    _ready,
    _t01_rows,
    app_db_url,
)

PAUSE_MINUTES = 20
CROSS_AFTER_MINUTES = 5
OK = 200


@pytest.fixture
async def cleared(app_db_url):  # noqa: F811
    """The seed reuses one strategy per scenario on a clock that restarts: a pause left behind would pause the next
    test's settling (and the gate tests of test_background_worker.py), so every test ends with the pause cleared."""
    yield
    async with app_db_url.connect() as conn:
        sids = (await conn.exec_driver_sql("SELECT DISTINCT strategy_id FROM public.strategy_monitor_pause")).all()
        for (sid,) in sids:
            if await strategy_pause_store.pause_of(conn, "owner", sid) is not None:
                await strategy_pause_store.clear_pause(conn, "owner", sid)
        await conn.commit()


async def _pause(engine, sid: int, until: datetime.datetime, now: datetime.datetime) -> None:
    async with engine.connect() as conn:
        await strategy_pause_store.set_pause(conn, "owner", sid, until, now)
        await conn.commit()


async def test_core_a_user_pause_skips_adjustment_checks_until_its_end_then_one_record_opens(
        app_db_url, monkeypatch, cleared):  # noqa: F811
    sid, scn, now, worker = await _ready(app_db_url, monkeypatch)
    start = now[0]
    until = start + datetime.timedelta(minutes=PAUSE_MINUTES)
    await _pause(app_db_url, sid, until, start)
    await worker.rebuild()  # the rebuild task reads the pause with the gate load (never per check)
    base = await _last_id(app_db_url, sid)
    checks_before = len(worker.checks)
    await _advance(worker, now, 60)
    assert worker.status[sid] is background.MonitoringStatus.PAUSED
    assert worker.paused_reason[sid] is background.PriceState.USER_PAUSED
    assert worker.user_paused_until[sid] == until
    now[0] = start + datetime.timedelta(minutes=CROSS_AFTER_MINUTES)
    _push_spot(scn, CROSS_SPOT, now[0])  # T-01 true, and it stays true
    while now[0] + datetime.timedelta(seconds=5) < until:  # the last cycle stays inside the pause
        await _advance(worker, now, 5, step=5)
    assert now[0] < until
    assert await _t01_rows(app_db_url, sid, base) == []  # the crossing inside the pause opened nothing
    assert len(worker.checks) == checks_before  # no adjustment check ran inside the pause
    assert worker.status[sid] is background.MonitoringStatus.PAUSED
    opened_at = None
    for _ in range(200):  # no action: the pause ends by itself at its end time
        await _advance(worker, now, 1)
        if await _t01_rows(app_db_url, sid, base):
            opened_at = now[0]
            break
    assert opened_at is not None, "no record after the pause ended"
    assert until < opened_at <= until + datetime.timedelta(minutes=3), (opened_at, until)
    assert sid not in worker.user_paused_until
    assert worker.status[sid] is background.MonitoringStatus.ACTIVE
    await _advance(worker, now, 30)
    assert len(await _t01_rows(app_db_url, sid, base)) == 1 and worker.errors == []


async def test_a_cleared_pause_checks_again_at_the_next_rebuild(app_db_url, monkeypatch, cleared):  # noqa: F811
    sid, _scn, now, worker = await _ready(app_db_url, monkeypatch)
    await _pause(app_db_url, sid, now[0] + datetime.timedelta(minutes=PAUSE_MINUTES), now[0])
    await worker.rebuild()
    await _advance(worker, now, 2)
    assert worker.paused_reason[sid] is background.PriceState.USER_PAUSED
    async with app_db_url.connect() as conn:
        await strategy_pause_store.clear_pause(conn, "owner", sid)
        await conn.commit()
    await worker.rebuild()
    await _advance(worker, now, 61)
    assert worker.status[sid] is background.MonitoringStatus.ACTIVE and sid not in worker.user_paused_until


async def test_the_screen_check_shows_the_pause_with_its_end_and_evaluates_nothing(
        app_db_url, monkeypatch, cleared):  # noqa: F811
    from test_adjustment_check import _check  # noqa: PLC0415 - the check route's own harness
    sid, scn, _now, _worker = await _ready(app_db_url, monkeypatch)
    status, before = await _check("ADJ-02", sid)
    assert status == OK and before["paused"] is None and before["results"], before  # not paused: evaluated
    until = scn.clock_at + datetime.timedelta(minutes=PAUSE_MINUTES)
    await _pause(app_db_url, sid, until, scn.clock_at)
    status, body = await _check("ADJ-02", sid)
    end = f"{until.astimezone(IST):%H%M}"
    assert status == OK and body["paused"] == {
        "until": end, "text": f"Adjustment checks paused until {end[:2]}:{end[2:]}."}, body
    assert body["results"] == []  # paused: not evaluated, as the worker
