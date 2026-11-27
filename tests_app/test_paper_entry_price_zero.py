"""Lane K item 4 (PC check T3-13, 27 Nov): Add to Paper refuses an entry price of 0 or below, naming the leg.
(Item 2, the typed price with the feed down, ADR-330 (28), is Lane N's change 5e7d34c9 with its own test file.)
Real PostgreSQL; every test rolls back."""
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


# ---- Lane K item 4 (PC check T3-13, 27 Nov): an entry price of 0 or below is refused, naming the leg ----

@pytest.mark.parametrize("price", ["0", "0.00", "-5.00"])
@pytest.mark.parametrize("kind", ["open", "add"])
async def test_a_zero_or_negative_entry_price_is_refused_naming_the_leg(db, price, kind):
    app, stored, *_ = await _setup(db)
    c = stored.saved.contract_ids
    await _store_freeze(db, c[0])
    async with _client(app) as client:
        reply = await client.post(f"/paper/strategies/{stored.id}/orders", json={"orders": [
            {"contract_id": c[0], "side": "BUY", "quantity": 65, "price": price, "kind": kind}]})
    assert reply.status_code == HTTPStatus.UNPROCESSABLE_ENTITY, reply.text[:400]
    assert "The entry price for NIFTY 13 Oct 22800 CE must be above 0." in reply.text
