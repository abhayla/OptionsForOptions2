"""Lane K item 2 (triage C10; ADR-330 (28); REQ-109 AC-1): with the live feed down, Add to Paper still records an entry
at the price the user TYPED (a price he typed is his own; the browser adds the "Prices are not live" confirm line).
Real case 26 Nov 14:46: the banner "Live market data disconnected" showed. Real PostgreSQL; every test rolls back."""
from __future__ import annotations

from http import HTTPStatus

import pytest
from test_strategy_store import _client
from test_strategy_tracking import _setup

pytestmark = pytest.mark.real_freeze


@pytest.fixture
async def db(app_engine):
    async with app_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


async def _store_freeze(db, contract_id: int) -> None:
    from sqlalchemy import text  # noqa: PLC0415
    await db.execute(text(
        "INSERT INTO public.exchange_freeze_limits (exchange_segment, exchange_token, file_date, freeze_limit, "
        "file_name) SELECT exchange_segment, exchange_token, CURRENT_DATE, 100000, 'NSE_FO_contract.csv.gz' "
        "FROM public.catalogue_contracts WHERE id = :id"), {"id": contract_id})


async def _post(app, stored, c, price="10.00"):
    async with _client(app) as client:
        return await client.post(f"/paper/strategies/{stored.id}/orders", json={"orders": [
            {"contract_id": c, "side": "BUY", "quantity": 65, "price": price, "kind": "open"}]})


def _feed_down(app):
    """The provider reports "not connected" but still holds its last captured quote (the real case 26 Nov 14:46)."""
    import dataclasses  # noqa: PLC0415

    from ofo_app.routes.outcome import get_market_context  # noqa: PLC0415
    provider = app.dependency_overrides[get_market_context]().provider
    was = provider.status()
    provider.status = lambda: dataclasses.replace(was, connected=False)


async def test_core_a_typed_entry_price_is_recorded_with_the_feed_down(db):
    """Core: the feed is down (provider not connected, last captured index quote still held) and a typed 10.00 ->
    201, the order stored at 10.00, the basket's starting point the last captured index price (ADR-330 (28))."""
    app, stored, *_ = await _setup(db)
    c = stored.saved.contract_ids
    await _store_freeze(db, c[0])
    _feed_down(app)
    reply = await _post(app, stored, c[0])
    assert reply.status_code == HTTPStatus.CREATED, reply.text[:600]
    assert reply.json()["orders"][0]["price"] == "10.00"


async def test_with_no_captured_index_price_at_all_the_basket_is_still_refused_by_name(db):
    """No context at all (nothing was ever captured): the starting point cannot be invented (ADR-283 (1))."""
    app, stored, *_ = await _setup(db, ctx=None)
    c = stored.saved.contract_ids
    await _store_freeze(db, c[0])
    reply = await _post(app, stored, c[0])
    assert reply.status_code == HTTPStatus.CONFLICT and "The live index price is not available" in reply.text
