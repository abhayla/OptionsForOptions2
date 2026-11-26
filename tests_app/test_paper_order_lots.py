"""ADR-330 (23), issue #747: every order row of the paper book carries its lots, computed by the server
(units / the contract's lot size); the browser does no division. Real paper routes, real PostgreSQL, rolled back."""
from __future__ import annotations

import pytest
from ofo_app import paper_store
from test_paper_routes import _contract_lot, _new, _seed_fixture
from test_strategy_store import _client
from test_strategy_tracking import _setup


@pytest.fixture
async def db(app_engine):
    async with app_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


NIFTY_LOT = 65


async def test_core_a_65_unit_nifty_order_row_has_lots_1_in_both_book_replies(db):
    app, stored, *_ = await _setup(db)
    contract = stored.saved.contract_ids[0]
    assert await _contract_lot(db, contract) == NIFTY_LOT
    await paper_store.place(db, stored.user_ref, stored.id, [_new(contract, "BUY", 65, "100.00")])
    async with _client(app) as c:
        rows = (await c.get(f"/paper/strategies/{stored.id}")).json()["orders"]
    assert [(o["quantity"], o["lots"]) for o in rows] == [(65, 1)]
    assert isinstance(rows[0]["lots"], int)


async def test_every_row_of_the_real_fixture_book_carries_units_over_lot_size(db):
    app, stored, *_ = await _seed_fixture(db)
    async with _client(app) as c:
        rows = (await c.get(f"/paper/strategies/{stored.id}")).json()["orders"]
    assert rows
    for o in rows:
        assert o["lots"] == o["quantity"] // NIFTY_LOT and o["quantity"] % NIFTY_LOT == 0


async def test_units_that_are_not_whole_lots_give_lots_none_never_a_rounded_number(db):
    app, stored, *_ = await _setup(db)
    contract = stored.saved.contract_ids[0]
    await paper_store.place(db, stored.user_ref, stored.id, [_new(contract, "BUY", 100, "100.00")])
    async with _client(app) as c:
        rows = (await c.get(f"/paper/strategies/{stored.id}")).json()["orders"]
    assert [(o["quantity"], o["lots"]) for o in rows] == [(100, None)]
