"""I-55 (test plan 28 Nov 2026): the side-closed question is NOT raised for a trade with no plan.

The worker raises it only for the strategies its lister returns, and the lister returns only a strategy with its own
plan (ADR-330 (11)). Real case: the ADJ-02 iron condor seeded WITHOUT a plan: not listed, so no side_closed alert is
raised for it by the worker's re-list, whatever its legs; the same trade WITH a plan is listed (the control).
Spec basis: ADR-330 (2) (b) side_closed, (11) only a strategy's own plan is watched.
"""
from __future__ import annotations

import datetime

from _scenario_catalogue import load_library
from ofo.timeutil import IST
from ofo_app import actionable_alerts as aa
from ofo_app import background, playbook_store
from sqlalchemy import text
from test_background_worker import (  # noqa: F401 - the fixture is used by name
    _SEED_RUN,
    app_db_url,
    scenario_mode,
    seed_mod,
)

AT = datetime.datetime(2026, 11, 28, 11, 0, tzinfo=IST)


async def _seed(engine, monkeypatch, *, plan: bool) -> tuple[int, object]:
    monkeypatch.setenv("OFO_SCENARIO", "ADJ-02")
    scn = scenario_mode.load("ADJ-02")
    await load_library(engine)
    run = next(_SEED_RUN)
    monkeypatch.setattr(seed_mod, "strategy_name", lambda sid: f"{seed_mod.NAME_PREFIX}{sid} n{run}")
    sid = await seed_mod.seed("ADJ-02")
    if plan:
        async with engine.begin() as conn:
            system = await playbook_store.active_for(conn, "owner", "ic")
            await playbook_store.accept_plan(conn, "owner", sid, system.id)
    return sid, scn


async def _side_closed_rows(engine, sid: int) -> int:
    async with engine.connect() as conn:
        return (await conn.execute(text(
            "SELECT count(*) FROM public.adjustment_suggestions WHERE strategy_id = :s AND kind = 'side_closed'"),
            {"s": sid})).scalar_one()


async def test_a_trade_with_no_plan_is_not_listed_and_gets_no_side_closed_alert(app_db_url, monkeypatch):  # noqa: F811
    sid, scn = await _seed(app_db_url, monkeypatch, plan=False)
    listed = await background.owner_lister(scn.provider)
    assert sid not in [w.strategy_id for w in listed]  # no plan: the worker does not watch it
    before = await _side_closed_rows(app_db_url, sid)
    worker_like = background.DbGateStore()
    for w in listed:  # what the worker's re-list does for every listed strategy: none of them is this one
        assert w.strategy_id != sid
        await worker_like.raise_side_closed(w, AT)
    assert await _side_closed_rows(app_db_url, sid) == before == 0
    async with app_db_url.connect() as conn:
        assert [a for a in await aa.unanswered(conn, "owner") if a.strategy_id == sid] == []


async def test_the_same_trade_with_its_plan_is_listed_the_control(app_db_url, monkeypatch):  # noqa: F811
    sid, scn = await _seed(app_db_url, monkeypatch, plan=True)
    assert sid in [w.strategy_id for w in await background.owner_lister(scn.provider)]
