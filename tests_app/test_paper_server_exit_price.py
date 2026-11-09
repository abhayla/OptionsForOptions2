"""GC-ICGUIDE g21 (audit C10; REQ-109 AC-4/AC-5; ADR-008): a paper EXIT is priced by the server from the live market it
reads, never from the browser. Entry prices stay typed (REQ-109 AC-1). Real PostgreSQL, rolled back."""
from __future__ import annotations

import datetime
from decimal import Decimal
from http import HTTPStatus

import pytest
from ofo.marketdata.kite_provider import IST
from ofo_app import paper_store
from ofo_app.routes.outcome import MarketContext, get_answer_clock, get_market_context
from sqlalchemy import text
from test_strategy_store import _client
from test_strategy_tracking import IDS, _frame, _setup

D = Decimal
AT = datetime.datetime(2026, 10, 1, 4, 0, tzinfo=datetime.UTC)


@pytest.fixture
async def db(app_engine):
    async with app_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


async def _open_leg(db, **kw):
    app, stored, provider, _clock, last = await _setup(db, **kw)
    cid = stored.saved.contract_ids[0]
    entry = paper_store.NewOrder(cid, "SELL", 65, D("100.00"), "open", AT)
    await paper_store.place(db, stored.user_ref, stored.id, [entry])
    return app, stored, provider, last, cid


async def _exit_rows(db, strategy_id: int):
    return (await db.execute(text("SELECT price FROM public.paper_orders WHERE strategy_id = :i AND kind = 'exit'"),
                             {"i": strategy_id})).scalars().all()


def _exit(cid: int, price: str) -> dict:
    return {"orders": [{"contract_id": cid, "side": "BUY", "quantity": 65, "price": price, "kind": "exit"}]}


async def test_a_browser_sent_exit_price_is_ignored_and_the_servers_live_price_is_stored(db):
    app, stored, provider, last, cid = await _open_leg(db)
    provider.on_frame(_frame(provider, IDS[0], "55.00"), last)
    async with _client(app) as c:
        reply = await c.post(f"/paper/strategies/{stored.id}/orders", json=_exit(cid, "99.00"))
    assert reply.status_code == HTTPStatus.CREATED, reply.text
    assert [D(p) for p in await _exit_rows(db, stored.id)] == [D("55.00")]


async def test_after_hours_an_exit_is_refused_never_filled_at_the_last_close(db):
    """ADR-212 (restored): closed market (18:00 IST, ADR-119 calendar) -> no paper fill at a closing price."""
    app, stored, provider, last, cid = await _open_leg(db)
    provider.on_frame(_frame(provider, IDS[0], "55.00"), last)
    after = datetime.datetime(2026, 10, 8, 18, 0, tzinfo=IST)
    app.dependency_overrides[get_market_context] = lambda: MarketContext(provider, lambda: after, D("0.065"))
    app.dependency_overrides[get_answer_clock] = lambda: lambda: after
    async with _client(app) as c:
        reply = await c.post(f"/paper/strategies/{stored.id}/orders", json=_exit(cid, "99.00"))
    assert reply.status_code == HTTPStatus.CONFLICT, reply.text
    assert await _exit_rows(db, stored.id) == []


async def test_an_exit_with_no_market_at_all_is_refused_by_name_and_nothing_is_written(db):
    app, stored, _provider, _last, cid = await _open_leg(db, ctx="none")
    async with _client(app) as c:
        reply = await c.post(f"/paper/strategies/{stored.id}/orders", json=_exit(cid, "99.00"))
    assert reply.status_code == HTTPStatus.CONFLICT, reply.text
    assert await _exit_rows(db, stored.id) == []


async def test_an_entry_keeps_its_typed_price(db):
    app, stored, *_ = await _setup(db)
    cid = stored.saved.contract_ids[0]
    body = {"orders": [{"contract_id": cid, "side": "SELL", "quantity": 65, "price": "101.15", "kind": "open"}]}
    async with _client(app) as c:
        reply = await c.post(f"/paper/strategies/{stored.id}/orders", json=body)
    assert reply.status_code == HTTPStatus.CREATED, reply.text
    assert reply.json()["orders"][0]["price"] == "101.15"
