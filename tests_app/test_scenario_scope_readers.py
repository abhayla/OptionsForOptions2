"""IC e2e Stage A fix round 1 (Tier A MAJOR): every background reader that lists strategies across the book goes
through ONE isolation helper (``scenario_mode.scope_clause`` / ``in_scope``): the live paper stop monitor's armed
triggers and paper settlement's due contracts. Live mode never returns a scenario strategy's row; scenario mode never
returns a live one. Real PostgreSQL; every test rolls back."""
from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from ofo.timeutil import IST
from ofo_app import paper_settlement, paper_store, paper_trigger_store
from ofo_app import strategy_store as store
from sqlalchemy import text
from test_strategy_store import _user, _with_draft

FAR_FUTURE = datetime.datetime(2030, 1, 2, 16, 0, tzinfo=IST)  # every fixture contract has expired and is due


async def _three(conn, user: str) -> dict[str, int]:
    """A live, an own-scenario (PATH-01) and an other-scenario (ADJ-02) strategy, each with one open paper leg and
    one armed conditional exit."""
    ids, live = await _with_draft(conn, user)
    own = await store.save_draft(conn, user, live.saved, "own scenario", scenario_id="PATH-01")
    other = await store.save_draft(conn, user, live.saved, "other scenario", scenario_id="ADJ-02")
    cid = next(iter(ids.values()))
    lot = (await conn.execute(text("SELECT lot_size FROM public.broker_instruments "  # lot lives per broker (0004)
                                   "WHERE contract_id = :c AND broker = 'zerodha'"), {"c": cid})).scalar_one()
    at = datetime.datetime(2026, 10, 1, 10, 0, tzinfo=IST)
    out = {"live": live.id, "own": own.id, "other": other.id}
    for sid in out.values():
        await paper_store.place(conn, user, sid, [paper_store.NewOrder(cid, "BUY", int(lot), Decimal("10.00"),
                                                                       "open", at)])
        await paper_trigger_store.add(conn, sid, paper_trigger_store.NewTrigger(
            "conditional_exit", "above", Decimal("30000"), underlying="NIFTY"))
    return out


@pytest.fixture
async def db(app_engine):
    async with app_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


@pytest.mark.parametrize(("mode", "kept"), [(None, "live"), ("PATH-01", "own")])
async def test_the_stop_monitor_arms_only_its_own_mode(db, monkeypatch, mode, kept):
    user = _user()
    ids = await _three(db, user)
    if mode is None:
        monkeypatch.delenv("OFO_SCENARIO", raising=False)
    else:
        monkeypatch.setenv("OFO_SCENARIO", mode)
    mine = {a.trigger.strategy_id for a in await paper_trigger_store.armed(db) if a.user_ref == user}
    assert mine == {ids[kept]}, (mine, ids)


@pytest.mark.parametrize(("mode", "kept"), [(None, "live"), ("PATH-01", "own")])
async def test_settlement_settles_only_its_own_mode(db, monkeypatch, mode, kept):
    user = _user()
    ids = await _three(db, user)
    if mode is None:
        monkeypatch.delenv("OFO_SCENARIO", raising=False)
    else:
        monkeypatch.setenv("OFO_SCENARIO", mode)
    mine = {d.strategy_id for d in await paper_settlement.due_contracts(db, FAR_FUTURE) if d.user_ref == user}
    assert mine == {ids[kept]}, (mine, ids)
