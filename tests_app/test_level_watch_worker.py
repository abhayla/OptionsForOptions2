"""GC-IC1 step 4c core (A-37, ADR-242): a user's watched index level, stored per strategy, makes the REAL background
Worker open ONE adjustment record per crossing episode, through the alert gate (the one writer, ADR-237 (6)).

Scenario ADJ-02 seeded through the app's stores, intraday-pinned (1-minute candles), the Worker on a pinned clock,
records counted by SQL. The scenario settles at spot 23000 with T-01 clear; the watch is set at 23200 ("above"), so
every spot below stays outside T-01's band (it starts near 23383) and only the watch can open a record. The brief's
example (watch 23,800; 23,790 / 23,805 / 23,780 / 23,810) is the same set of offsets around this scenario's level.
"""
from __future__ import annotations

import datetime

import pytest
from ofo_app import background, strategy_level_watch_store
from sqlalchemy import text
from test_background_worker import (  # noqa: F401 - the shared fixture
    _advance,
    _last_id,
    _push_spot,
    _ready,
    app_db_url,
)

LEVEL = "23200"
ABOVE_ID = "watch.level.above"
EPISODES = 2
WAIT_S = 130  # past the next 1-minute candle close, with room


@pytest.fixture
async def cleared(app_db_url):  # noqa: F811
    """The seed reuses one strategy per scenario: a watch left behind would fire in the next test, so every test ends
    with every watch cleared."""
    yield
    async with app_db_url.connect() as conn:
        sids = (await conn.exec_driver_sql("SELECT DISTINCT strategy_id FROM public.strategy_level_watch")).all()
        for (sid,) in sids:
            for w in await strategy_level_watch_store.watches_of(conn, "owner", sid):
                await strategy_level_watch_store.clear_watch(conn, "owner", sid, w.direction)
        await conn.commit()


async def _watch_rows(engine, sid: int, since: int) -> list[tuple]:
    async with engine.connect() as conn:
        rows = (await conn.execute(text("SELECT id, outcome, timeline->0->>'label' FROM public.adjustment_suggestions "
                                        "WHERE strategy_id = :s AND rule_id = :r AND id > :i ORDER BY id"),
                                   {"s": sid, "r": ABOVE_ID, "i": since})).all()
    return [tuple(r) for r in rows]


async def _move(worker, scn, now, spot: str, seconds: int = WAIT_S) -> None:
    now[0] += datetime.timedelta(seconds=5)
    _push_spot(scn, spot, now[0])
    await _advance(worker, now, seconds)


async def test_core_a_watched_level_opens_one_record_per_crossing_episode(app_db_url, monkeypatch, cleared):  # noqa: F811
    sid, scn, now, worker = await _ready(app_db_url, monkeypatch)
    async with app_db_url.connect() as conn:
        await strategy_level_watch_store.set_watch(conn, "owner", sid, "above", LEVEL)
        await conn.commit()
    await worker.rebuild()  # the rebuild task reads the watch with the gate load (never per check)
    assert worker._gate_load[sid].watches
    base = await _last_id(app_db_url, sid)
    await _move(worker, scn, now, "23190")
    assert await _watch_rows(app_db_url, sid, base) == []  # 10 points under: nothing
    await _move(worker, scn, now, "23205")
    rows = await _watch_rows(app_db_url, sid, base)
    assert len(rows) == 1, rows  # reached at the next close: one record, with its words
    assert rows[0][1] == "open" and rows[0][2] == "Watched level reached (at or above)", rows
    for spot in ("23230", "23260", "23215"):  # further ticks above: the same episode
        await _move(worker, scn, now, spot, 70)
    assert len(await _watch_rows(app_db_url, sid, base)) == 1
    await _move(worker, scn, now, "23180")  # back below at a close: the gate re-arms (ADR-237 (1))
    await _move(worker, scn, now, "23210")
    rows = await _watch_rows(app_db_url, sid, base)
    assert len(rows) == EPISODES, rows  # a new episode: a second record
    assert worker.errors == [] and worker.status[sid] is background.MonitoringStatus.ACTIVE


async def test_a_cleared_watch_opens_nothing(
        app_db_url, monkeypatch, cleared):  # noqa: F811
    sid, scn, now, worker = await _ready(app_db_url, monkeypatch)
    async with app_db_url.connect() as conn:
        await strategy_level_watch_store.set_watch(conn, "owner", sid, "above", LEVEL)
        await strategy_level_watch_store.clear_watch(conn, "owner", sid, "above")
        await conn.commit()
    await worker.rebuild()
    assert worker._gate_load[sid].watches == ()
    base = await _last_id(app_db_url, sid)
    await _move(worker, scn, now, "23250")
    assert await _watch_rows(app_db_url, sid, base) == []
