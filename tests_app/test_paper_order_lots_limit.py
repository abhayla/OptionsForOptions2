"""Item 15 (owner PC 27 Nov, T2-10): Add to Paper took 5000 lots on one leg. ADR-081 / ADR-092: a leg at or above the
contract's stored exchange freeze limit is blocked, never split; REQ-167 AC-5: no leg above the limits.max_lots
setting. ONE check in ``place_paper_orders`` (the door Add to Paper, Add Selected, Increase quantity and Change
expiry all post to). Real PostgreSQL; every test rolls back."""
from __future__ import annotations

from http import HTTPStatus

import pytest
from sqlalchemy import text
from test_strategy_store import _client
from test_strategy_tracking import _setup

UNPROCESSABLE = HTTPStatus.UNPROCESSABLE_ENTITY
LOT = 65
FREEZE = 3511  # F-36: MaxTradQty; the largest order is 3,510 units = 54 lots


@pytest.fixture
async def db(app_engine):
    async with app_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


async def _store_freeze(db, contract_id: int, limit: int = FREEZE) -> None:
    await db.execute(text(
        "INSERT INTO public.exchange_freeze_limits (exchange_segment, exchange_token, file_date, freeze_limit, "
        "file_name) SELECT exchange_segment, exchange_token, CURRENT_DATE, :limit, 'NSE_FO_contract.csv.gz' "
        "FROM public.catalogue_contracts WHERE id = :id"), {"limit": limit, "id": contract_id})


def _order(contract: int, lots: int, kind: str = "open", side: str = "BUY") -> dict:
    return {"contract_id": contract, "side": side, "quantity": lots * LOT, "price": "10.00", "kind": kind}


async def _post(app, stored, orders):
    async with _client(app) as client:
        return await client.post(f"/paper/strategies/{stored.id}/orders", json={"orders": orders})


async def test_core_5000_lots_over_a_stored_freeze_limit_is_refused_with_the_server_sentence(db):
    app, stored, *_ = await _setup(db)
    c = stored.saved.contract_ids
    await _store_freeze(db, c[0])
    reply = await _post(app, stored, [_order(c[0], 5000)])
    assert reply.status_code == UNPROCESSABLE, reply.text
    assert "NIFTY 13 Oct 22800 CE asks for 5000 lots; the most one order can hold is 54 lots." in reply.text
    assert (await db.execute(text("SELECT count(*) FROM public.paper_orders WHERE strategy_id = :i"),
                             {"i": stored.id})).scalar_one() == 0


async def test_the_refusal_names_the_contract_not_a_basket_position(db):
    app, stored, *_ = await _setup(db)
    c = stored.saved.contract_ids
    await _store_freeze(db, c[1])
    reply = await _post(app, stored, [_order(c[0], 1), _order(c[1], 55)])
    assert reply.status_code == UNPROCESSABLE, reply.text
    assert "NIFTY 13 Oct 23000 CE asks for 55 lots; the most one order can hold is 54 lots." in reply.text


async def test_54_lots_is_accepted_and_55_is_refused(db):
    app, stored, *_ = await _setup(db)
    c = stored.saved.contract_ids
    await _store_freeze(db, c[0])
    assert (await _post(app, stored, [_order(c[0], 54)])).status_code == HTTPStatus.CREATED
    refused = await _post(app, stored, [_order(c[0], 55, side="SELL")])
    assert refused.status_code == UNPROCESSABLE and "NIFTY 13 Oct 22800 CE asks for 55 lots" in refused.text


async def test_no_stored_freeze_limit_is_not_a_block_but_the_lots_setting_still_is(db):
    """ADR-081: no stored limit warns and does not block; limits.max_lots (default 10000) still holds."""
    app, stored, *_ = await _setup(db)
    c = stored.saved.contract_ids
    assert (await _post(app, stored, [_order(c[0], 100)])).status_code == HTTPStatus.CREATED
    reply = await _post(app, stored, [_order(c[1], 10001)])
    assert reply.status_code == UNPROCESSABLE, reply.text
    assert "A leg can hold at most 10000 lots; this leg has 10001." in reply.text


async def test_an_exit_is_never_blocked_by_the_limit(db):
    app, stored, *_ = await _setup(db)
    c = stored.saved.contract_ids
    await _store_freeze(db, c[0])
    reply = await _post(app, stored, [_order(c[0], 5000, kind="exit", side="SELL")])
    assert "most one order can hold" not in reply.text


async def test_an_add_order_increase_quantity_or_change_expiry_is_refused_over_the_limit(db):
    app, stored, *_ = await _setup(db)
    c = stored.saved.contract_ids
    await _store_freeze(db, c[0])
    reply = await _post(app, stored, [_order(c[0], 55, kind="add")])
    assert reply.status_code == UNPROCESSABLE, reply.text
    assert "NIFTY 13 Oct 22800 CE asks for 55 lots; the most one order can hold is 54 lots." in reply.text


async def test_a_limit_that_is_whole_lots_refuses_the_limit_itself_and_accepts_one_lot_below(db):
    """Units must be BELOW the limit (F-36): freeze 3510 = 54 lots x 65, so 54 lots is refused and 53 is placed."""
    app, stored, *_ = await _setup(db)
    c = stored.saved.contract_ids
    await _store_freeze(db, c[0], 54 * LOT)
    refused = await _post(app, stored, [_order(c[0], 54)])
    assert refused.status_code == UNPROCESSABLE, refused.text
    assert "asks for 54 lots; the most one order can hold is 53 lots." in refused.text
    assert (await _post(app, stored, [_order(c[0], 53)])).status_code == HTTPStatus.CREATED


async def test_a_limit_below_one_lot_says_so_instead_of_zero_lots(db):
    app, stored, *_ = await _setup(db)
    c = stored.saved.contract_ids
    await _store_freeze(db, c[0], 50)
    reply = await _post(app, stored, [_order(c[0], 1)])
    assert reply.status_code == UNPROCESSABLE, reply.text
    assert ("The exchange limit for NIFTY 13 Oct 22800 CE is smaller than one lot (50 units, lot 65), "
            "so it cannot be ordered.") in reply.text
    assert "0 lots" not in reply.text


async def test_an_exit_of_a_held_leg_over_the_limit_succeeds_and_the_book_shows_it_closed(db):
    app, stored, *_ = await _setup(db)
    c = stored.saved.contract_ids
    assert (await _post(app, stored, [_order(c[0], 100)])).status_code == HTTPStatus.CREATED  # no limit stored yet
    await _store_freeze(db, c[0])  # the held 100 lots is now over the 54-lot limit
    reply = await _post(app, stored, [_order(c[0], 100, kind="exit", side="SELL")])
    assert reply.status_code == HTTPStatus.CREATED, reply.text
    book = reply.json()
    assert [(o["kind"], o["lots"]) for o in book["orders"]] == [("open", 100), ("exit", 100)]
    assert [row["contract_id"] for row in book["closed"]] == [c[0]]
    assert [p["net_quantity"] for p in book["positions"]] == [0]
