"""Item 15 (owner PC 27 Nov, T2-10): Add to Paper took 5000 lots on one leg. ADR-081 / ADR-092: a leg at or above the
contract's stored exchange freeze limit is blocked, never split; REQ-167 AC-5: no leg above the limits.max_lots
setting. ONE check in ``place_paper_orders`` (the door Add to Paper, Add Selected, Increase quantity and Change
expiry all post to). Real PostgreSQL; every test rolls back."""
from __future__ import annotations

import datetime
from http import HTTPStatus

import pytest
from ofo_app.strategy_refused import StrategyRefused
from sqlalchemy import text
from ofo_app import settings_store
from test_strategy_store import _client
from test_strategy_tracking import _setup

pytestmark = pytest.mark.real_freeze
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


async def _store_freeze(db, contract_id: int, limit: int = FREEZE, days_ahead: int = 0) -> None:
    await db.execute(text(
        "INSERT INTO public.exchange_freeze_limits (exchange_segment, exchange_token, file_date, freeze_limit, "
        "file_name) SELECT exchange_segment, exchange_token, CURRENT_DATE + CAST(:d AS integer), :limit, 'NSE_FO_contract.csv.gz' "
        "FROM public.catalogue_contracts WHERE id = :id"), {"limit": limit, "id": contract_id, "d": days_ahead})


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
    await _store_freeze(db, c[0])
    await _store_freeze(db, c[1])
    reply = await _post(app, stored, [_order(c[0], 1), _order(c[1], 55)])
    assert reply.status_code == UNPROCESSABLE, reply.text
    assert "NIFTY 13 Oct 23000 CE asks for 55 lots; the most one order can hold is 54 lots." in reply.text


async def test_54_lots_is_accepted_and_55_is_refused(db):
    app, stored, *_ = await _setup(db)
    c = stored.saved.contract_ids
    await _store_freeze(db, c[0])
    assert (await _post(app, stored, [_order(c[0], 54)])).status_code == HTTPStatus.CREATED
    refused = await _post(app, stored, [_order(c[0], 55)])
    assert refused.status_code == UNPROCESSABLE and "NIFTY 13 Oct 22800 CE asks for 55 lots" in refused.text


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


async def test_an_exit_within_the_limit_succeeds_and_the_book_shows_it_closed(db):
    app, stored, *_ = await _setup(db)
    c = stored.saved.contract_ids
    await _store_freeze(db, c[0])
    assert (await _post(app, stored, [_order(c[0], 50)])).status_code == HTTPStatus.CREATED
    reply = await _post(app, stored, [_order(c[0], 50, kind="exit", side="SELL")])
    assert reply.status_code == HTTPStatus.CREATED, reply.text
    book = reply.json()
    assert [(o["kind"], o["lots"]) for o in book["orders"]] == [("open", 50), ("exit", 50)]
    assert [row["contract_id"] for row in book["closed"]] == [c[0]]
    assert [p["net_quantity"] for p in book["positions"]] == [0]


# ---- Lane K, ADR-330 (50)-(52): the total a leg will hold after the order, default 100 lots, exits over freeze ----
BIG_FREEZE = 500 * LOT  # a freeze limit that does not bind: the lots limit is what is under test


async def test_core_60_held_plus_50_more_on_the_same_leg_is_refused_at_100(db):
    """Core (50): 60 lots held + 50 lots more on the same leg = 110, refused at the default limit of 100 (52)."""
    app, stored, *_ = await _setup(db)
    c = stored.saved.contract_ids
    await _store_freeze(db, c[0], BIG_FREEZE)
    assert (await _post(app, stored, [_order(c[0], 60)])).status_code == HTTPStatus.CREATED
    reply = await _post(app, stored, [_order(c[0], 50, kind="add")])
    assert reply.status_code == UNPROCESSABLE, reply.text
    assert ("NIFTY 13 Oct 22800 CE would hold 110 lots after this order; a leg can hold at most 100 lots "
            "(60 held, 50 added).") in reply.text
    assert (await db.execute(text("SELECT count(*) FROM public.paper_orders WHERE strategy_id = :i"),
                             {"i": stored.id})).scalar_one() == 1


async def test_100_total_is_accepted_and_one_more_lot_is_refused(db):
    app, stored, *_ = await _setup(db)
    c = stored.saved.contract_ids
    await _store_freeze(db, c[0], BIG_FREEZE)
    assert (await _post(app, stored, [_order(c[0], 60)])).status_code == HTTPStatus.CREATED
    assert (await _post(app, stored, [_order(c[0], 40, kind="add")])).status_code == HTTPStatus.CREATED
    refused = await _post(app, stored, [_order(c[0], 1, kind="add")])
    assert refused.status_code == UNPROCESSABLE and "would hold 101 lots" in refused.text


async def test_another_leg_does_not_count_toward_this_leg(db):
    app, stored, *_ = await _setup(db)
    c = stored.saved.contract_ids
    await _store_freeze(db, c[0], BIG_FREEZE)
    await _store_freeze(db, c[1], BIG_FREEZE)
    assert (await _post(app, stored, [_order(c[0], 90)])).status_code == HTTPStatus.CREATED
    assert (await _post(app, stored, [_order(c[1], 90)])).status_code == HTTPStatus.CREATED


async def test_a_101_lot_order_on_an_empty_leg_is_refused_at_the_default_of_100(db):
    app, stored, *_ = await _setup(db)
    c = stored.saved.contract_ids
    await _store_freeze(db, c[0], BIG_FREEZE)
    reply = await _post(app, stored, [_order(c[0], 101)])
    assert reply.status_code == UNPROCESSABLE, reply.text
    assert ("NIFTY 13 Oct 22800 CE would hold 101 lots after this order; a leg can hold at most 100 lots "
            "(0 held, 101 added).") in reply.text


async def test_a_cut_back_of_a_leg_held_over_a_lowered_limit_is_not_refused_and_growing_it_is(db):
    """A leg already held above the limit (the limit was lowered after) may be cut back, never grown. The door's own
    function, called directly with a held book of 150 lots and the default of 100."""
    from decimal import Decimal  # noqa: PLC0415

    from ofo.settings import defaults  # noqa: PLC0415
    from ofo_app import paper_limit, paper_store  # noqa: PLC0415
    from ofo_app.paper_book import StoredOrder  # noqa: PLC0415
    app, stored, *_ = await _setup(db)
    c = stored.saved.contract_ids
    await _store_freeze(db, c[0], BIG_FREEZE)
    at = datetime.datetime.now(datetime.UTC)

    def new(side, lots, kind):
        return paper_store.NewOrder(c[0], side, lots * LOT, Decimal("10.00"), kind, at)
    held = [StoredOrder(1, stored.id, new("BUY", 150, "open"), at)]
    await paper_limit.check_order_size(db, held, [new("SELL", 10, "add")], defaults())  # 140 < 150: passes
    with pytest.raises(StrategyRefused) as grown:
        await paper_limit.check_order_size(db, held, [new("BUY", 1, "add")], defaults())
    assert "would hold 151 lots after this order; a leg can hold at most 100 lots (150 held, 1 added)." in str(
        grown.value.message.what_happened)


async def test_an_exit_above_the_freeze_quantity_is_refused_like_an_open_order(db):
    """(51): ADR-092 stands, paper the same as real: an exit of 100 lots over a 54-lot limit is refused."""
    app, stored, *_ = await _setup(db)
    c = stored.saved.contract_ids
    await _store_freeze(db, c[0], BIG_FREEZE, days_ahead=-1)
    assert (await _post(app, stored, [_order(c[0], 90)])).status_code == HTTPStatus.CREATED
    await _store_freeze(db, c[0], FREEZE)  # the newest file now shows 54 lots
    reply = await _post(app, stored, [_order(c[0], 90, kind="exit", side="SELL")])
    assert reply.status_code == UNPROCESSABLE, reply.text
    assert "NIFTY 13 Oct 22800 CE asks for 90 lots; the most one order can hold is 54 lots." in reply.text


async def test_a_contract_with_no_stored_freeze_quantity_is_refused_by_name(db):
    """Owner 27 Nov: no stored freeze quantity fails closed (ADR-081's 'review warns' is reported, not guessed)."""
    app, stored, *_ = await _setup(db)
    c = stored.saved.contract_ids
    reply = await _post(app, stored, [_order(c[0], 1)])
    assert reply.status_code == UNPROCESSABLE, reply.text
    assert "The exchange freeze quantity for NIFTY 13 Oct 22800 CE is not known" in reply.text


# ---- Lane Q2's cases (branch test/live-day-gaps-1127, gap 8), rewritten to ADR-330 (50)-(52): one file, one truth ----

def test_the_one_lots_limit_is_100_lots_per_leg_by_default():
    """(52): Q2's test pinned 10,000; the owner's default is 100."""
    from ofo.settings import calc, defaults  # noqa: PLC0415
    assert calc.max_lots(dict(defaults())) == 100


async def test_5000_lots_sold_on_one_leg_is_refused_and_nothing_is_stored(db):
    """Q2's gap 8 (real case 27 Nov 14:28, a SELL of 5,000 lots accepted): refused now, the sentence names the leg."""
    app, stored, *_ = await _setup(db)
    c = stored.saved.contract_ids
    await _store_freeze(db, c[0], 10_000 * LOT)
    reply = await _post(app, stored, [_order(c[0], 5000, side="SELL")])
    assert reply.status_code == UNPROCESSABLE, reply.text
    assert "would hold 5000 lots after this order; a leg can hold at most 100 lots (0 held, 5000 added)." in reply.text
    assert (await db.execute(text("SELECT count(*) FROM public.paper_orders WHERE strategy_id = :i"),
                             {"i": stored.id})).scalar_one() == 0


async def test_100_lots_sold_is_accepted_and_one_more_sold_is_refused(db):
    app, stored, *_ = await _setup(db)
    c = stored.saved.contract_ids
    await _store_freeze(db, c[0], BIG_FREEZE)
    assert (await _post(app, stored, [_order(c[0], 100, side="SELL")])).status_code == HTTPStatus.CREATED
    refused = await _post(app, stored, [_order(c[0], 1, kind="add", side="SELL")])
    assert refused.status_code == UNPROCESSABLE and "would hold 101 lots" in refused.text
