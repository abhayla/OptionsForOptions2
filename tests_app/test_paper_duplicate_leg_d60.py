"""D-60 round 2 (ADR-319 (3), REQ-059 gate decision, REQ-030 AC-11): Add to Paper with a kept duplicate is refused with the
gate's own sentence (gate_duplicate_leg); a buy and a sell of one contract are two legs and are NOT a duplicate here.
Real PostgreSQL; every test rolls back."""
from __future__ import annotations

from http import HTTPStatus

import pytest
from test_strategy_store import _client
from test_strategy_tracking import _setup

UNPROCESSABLE = HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.fixture
async def db(app_engine):
    async with app_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


def _order(contract: int, side: str) -> dict:
    return {"contract_id": contract, "side": side, "quantity": 65, "price": "10.00", "kind": "open"}


async def test_two_open_orders_on_one_contract_and_side_are_refused_with_the_gate_sentence(db):
    app, stored, *_ = await _setup(db)
    c = stored.saved.contract_ids
    async with _client(app) as client:
        reply = await client.post(f"/paper/strategies/{stored.id}/orders", json={"orders": [_order(c[0], "BUY"), _order(c[0], "BUY")]})
    assert reply.status_code == UNPROCESSABLE, reply.text
    assert "is the same contract as leg 1. The legs have not been combined" in reply.text


async def test_a_buy_and_a_sell_of_one_contract_are_not_a_duplicate(db):
    app, stored, *_ = await _setup(db)
    c = stored.saved.contract_ids
    async with _client(app) as client:
        reply = await client.post(f"/paper/strategies/{stored.id}/orders", json={"orders": [_order(c[0], "BUY"), _order(c[0], "SELL")]})
    assert "same contract as leg" not in reply.text
