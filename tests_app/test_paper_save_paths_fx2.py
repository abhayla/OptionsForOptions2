"""GC-ICGUIDE g32 fx2 (ADR-212, ADR-255, ADR-008): both paper save paths pass ONE check (market hours, then the store,
then the plan's adjustment limit), an exit is priced only by its own contract's feed key, a closed strategy takes no
new position, and the Completed figures read right. Real PostgreSQL, rolled back."""
from __future__ import annotations

import datetime
from decimal import Decimal
from http import HTTPStatus

import pytest
from ofo.marketdata.kite_provider import IST
from ofo_app import paper_store
from ofo_app.routes.outcome import MarketContext, get_answer_clock, get_market_context, load_charge_rates
from sqlalchemy import text
from test_paper_adjustment_limit import T0, _book, _new, _post
from test_paper_routes import RATES
from test_paper_server_exit_price import _exit, _exit_rows, _open_leg
from test_strategy_store import _client
from test_strategy_tracking import _DELIST, _REUSE, IDS, _frame

D = Decimal


@pytest.fixture
async def db(app_engine):
    async with app_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


async def _count(db, strategy_id: int) -> int:
    return int((await db.execute(text("SELECT count(*) FROM public.paper_orders WHERE strategy_id = :i"),
                                 {"i": strategy_id})).scalar_one())


def _after_hours(app, provider):
    after = datetime.datetime(2026, 10, 8, 18, 0, tzinfo=IST)
    app.dependency_overrides[get_market_context] = lambda: MarketContext(provider, lambda: after, D("0.065"))
    app.dependency_overrides[get_answer_clock] = lambda: lambda: after


# 1. priced only by the contract's own feed key
async def test_item1_an_exit_on_a_contract_whose_token_now_quotes_another_contract_is_refused(db):
    app, stored, provider, last, cid = await _open_leg(db)
    await db.execute(text(_DELIST), {"id": cid})
    await db.execute(text(_REUSE))
    provider.on_frame(_frame(provider, IDS[0], "55.00"), last)  # that token's quote now belongs to another contract
    async with _client(app) as c:
        reply = await c.post(f"/paper/strategies/{stored.id}/orders", json=_exit(cid, "99.00"))
    assert reply.status_code == HTTPStatus.CONFLICT, reply.text
    assert "no longer a live contract" in reply.text
    assert await _exit_rows(db, stored.id) == []


# 2. the adjustment limit on the tracking exit
async def test_item2_a_partial_tracking_exit_beyond_the_plans_maximum_is_refused(db):
    app, stored, _ids = await _book(db, max_adjustments=2)
    before = await _count(db, stored.id)
    async with _client(app) as c:
        reply = await c.post(f"/strategies/{stored.id}/tracking/exit", json={"legs": [2]})
    assert reply.status_code == HTTPStatus.UNPROCESSABLE_ENTITY, reply.text
    assert "at most 2 adjustments" in reply.text
    assert await _count(db, stored.id) == before


async def test_item2_a_tracking_exit_of_every_open_leg_stays_allowed(db):
    app, stored, _ids = await _book(db, max_adjustments=2)
    async with _client(app) as c:
        reply = await c.post(f"/strategies/{stored.id}/tracking/exit", json={"legs": [2, 3]})
    assert reply.status_code == HTTPStatus.OK, reply.text


# 3. no fill outside market hours, in both routes
async def test_item3_after_hours_an_exit_is_refused_and_nothing_is_written(db):
    app, stored, provider, last, cid = await _open_leg(db)
    provider.on_frame(_frame(provider, IDS[0], "55.00"), last)
    _after_hours(app, provider)
    async with _client(app) as c:
        reply = await c.post(f"/paper/strategies/{stored.id}/orders", json=_exit(cid, "99.00"))
    assert reply.status_code == HTTPStatus.CONFLICT, reply.text
    assert "market is closed" in reply.text
    assert await _exit_rows(db, stored.id) == []


async def test_item3_after_hours_an_entry_is_refused(db):
    app, stored, provider, _last, cid = await _open_leg(db)
    _after_hours(app, provider)
    body = {"orders": [{"contract_id": cid, "side": "SELL", "quantity": 65, "price": "50.00", "kind": "open"}]}
    async with _client(app) as c:
        reply = await c.post(f"/paper/strategies/{stored.id}/orders", json=body)
    assert reply.status_code == HTTPStatus.CONFLICT, reply.text
    assert "market is closed" in reply.text


async def test_item3_after_hours_the_tracking_exit_is_refused(db):
    app, stored, provider, last, _cid = await _open_leg(db)
    provider.on_frame(_frame(provider, IDS[0], "55.00"), last)
    _after_hours(app, provider)
    async with _client(app) as c:
        reply = await c.post(f"/strategies/{stored.id}/tracking/exit", json={"legs": [0]})
    assert reply.status_code == HTTPStatus.CONFLICT, reply.text
    assert "market is closed" in reply.text
    assert await _exit_rows(db, stored.id) == []


# 4. a closed strategy takes no new position
async def test_item4_a_new_open_on_a_closed_strategy_is_refused_by_name(db):
    app, stored, _provider, _last, cid = await _open_leg(db)
    await paper_store.place(db, stored.user_ref, stored.id,
                            [paper_store.NewOrder(cid, "BUY", 65, D("55.00"), "exit", T0)])
    before = await _count(db, stored.id)
    body = {"orders": [{"contract_id": cid, "side": "SELL", "quantity": 65, "price": "50.00", "kind": "open"}]}
    async with _client(app) as c:
        reply = await c.post(f"/paper/strategies/{stored.id}/orders", json=body)
    assert reply.status_code == HTTPStatus.CONFLICT, reply.text
    assert "strategy is closed" in reply.text
    assert await _count(db, stored.id) == before


# 5. a full exit never waits on the history read
async def test_item5_a_full_exit_is_allowed_when_the_history_cannot_be_read(db, monkeypatch):
    from ofo_app import adjustment_readers  # noqa: PLC0415
    app, stored, ids = await _book(db, max_adjustments=2)
    monkeypatch.setattr(adjustment_readers, "history_count", lambda *_a, **_k: None)
    async with _client(app) as c:
        reply = await c.post(f"/paper/strategies/{stored.id}/orders",
                             json={"orders": [_post(ids[2], "BUY"), _post(ids[3], "SELL")]})
    assert reply.status_code == HTTPStatus.CREATED, reply.text


# 6. Completed figures
async def test_item6_the_closing_exit_is_not_an_adjustment_and_a_cost_reads_as_a_cost(db):
    app, stored, ids = await _book(db, max_adjustments=None)
    await paper_store.place(db, stored.user_ref, stored.id, [
        _new(ids[2], "BUY", "50.00", "exit", T0 + datetime.timedelta(hours=5)),
        _new(ids[3], "SELL", "50.00", "exit", T0 + datetime.timedelta(hours=5))])
    app.dependency_overrides[load_charge_rates] = lambda: RATES
    async with _client(app) as c:
        rows = (await c.get("/strategies")).json()["strategies"]
    row = next(r for r in rows if r["id"] == stored.id)
    assert row["status"] == "closed"
    assert row["adjustments_made"] == 2  # noqa: PLR2004 - the two one-leg exits; entry and closing exit do not count
    assert D(row["adjustment_cost"]) > 0
    assert row["adjustment_cost_text"] == "\u221254.91"
