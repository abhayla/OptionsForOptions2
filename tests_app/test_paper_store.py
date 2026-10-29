"""GC-TP step 1a (REQ-109 AC-4; ADR-207): the paper order book store, as the limited application role.

Real PostgreSQL; every test rolls back (one outer transaction). The strategy and catalogue come from the shared
test_strategy_store helpers (the 2026-10-13 NIFTY iron condor contracts).
"""
from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from ofo.tracking.orderbook import net_positions
from ofo_app import paper_store
from ofo_app import strategy_store as store
from test_strategy_store import _ids, _user, _with_draft

AT = datetime.datetime(2026, 10, 29, 5, 0, tzinfo=datetime.UTC)
D = Decimal


@pytest.fixture
async def db(app_engine):
    async with app_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


async def _strategy(db, user: str) -> tuple[int, list[int]]:
    ids, stored = await _with_draft(db, user)
    return stored.id, sorted(ids.values())


def _new(contract: int, side: str, qty: int, price: str, kind: str = "open") -> paper_store.NewOrder:
    return paper_store.NewOrder(contract, side, qty, D(price), kind, AT)


async def test_place_then_load_returns_the_orders_in_placement_order(db):
    user = _user()
    sid, c = await _strategy(db, user)
    book = await paper_store.place(db, user, sid, [_new(c[1], "SELL", 65, "82.75"), _new(c[0], "BUY", 65, "35.80")])
    await paper_store.place(db, user, sid, [_new(c[1], "BUY", 30, "70.00", "exit")])
    loaded = await paper_store.load(db, sid)
    assert [(o.order.contract_id, o.order.side, o.order.quantity, o.order.price, o.order.kind) for o in loaded] == [
        (c[1], "SELL", 65, D("82.75"), "open"), (c[0], "BUY", 65, D("35.80"), "open"),
        (c[1], "BUY", 30, D("70.00"), "exit")]
    assert loaded[:2] == book
    view = net_positions([o.order.as_paper() for o in loaded], {})
    assert [(p.instrument_id, p.net_quantity, p.booked) for p in view.positions] == [
        (str(c[1]), -35, D("382.50")), (str(c[0]), 65, D(0))]  # (82.75 - 70.00) x 30


async def test_another_users_strategy_is_not_found_and_nothing_is_stored(db):
    sid, c = await _strategy(db, _user())
    with pytest.raises(store.StrategyStoreError) as err:
        await paper_store.place(db, _user(), sid, [_new(c[0], "BUY", 65, "1.00")])
    assert err.value.code == store.NOT_FOUND
    assert await paper_store.load(db, sid) == ()


@pytest.mark.parametrize(("side", "qty"), [("SELL", 66), ("BUY", 10)], ids=["larger-than-open", "wrong-side"])
async def test_an_exit_larger_than_the_open_quantity_is_refused_and_nothing_is_stored(db, side, qty):
    user = _user()
    sid, c = await _strategy(db, user)
    await paper_store.place(db, user, sid, [_new(c[0], "BUY", 65, "10.00")])
    with pytest.raises(store.StrategyStoreError) as err:
        await paper_store.place(db, user, sid, [_new(c[0], side, qty, "11.00", "exit")])
    assert err.value.code == paper_store.EXIT_EXCEEDS_OPEN
    assert len(await paper_store.load(db, sid)) == 1


async def test_an_exit_counts_earlier_orders_of_the_same_call(db):
    user = _user()
    sid, c = await _strategy(db, user)
    await paper_store.place(db, user, sid, [_new(c[0], "BUY", 65, "10.00"), _new(c[0], "SELL", 65, "11.00", "exit")])
    with pytest.raises(store.StrategyStoreError) as err:
        await paper_store.place(db, user, sid, [_new(c[0], "SELL", 1, "11.00", "exit")])  # flat now
    assert err.value.code == paper_store.EXIT_EXCEEDS_OPEN


async def test_an_exit_on_a_contract_never_opened_is_refused(db):
    user = _user()
    sid, c = await _strategy(db, user)
    with pytest.raises(store.StrategyStoreError):
        await paper_store.place(db, user, sid, [_new(c[0], "SELL", 1, "1.00", "stop")])


async def test_a_price_finer_than_a_paisa_is_refused_before_any_write(db):
    user = _user()
    sid, c = await _strategy(db, user)
    with pytest.raises(ValueError, match="finer than a paisa"):
        await paper_store.place(db, user, sid, [_new(c[0], "BUY", 1, "1.005")])
    assert await paper_store.load(db, sid) == ()


class _Counting:
    def __init__(self, conn) -> None:
        self.conn, self.calls = conn, 0

    async def execute(self, *args, **kwargs):
        self.calls += 1
        return await self.conn.execute(*args, **kwargs)


@pytest.mark.parametrize("strategies", [1, 3])
async def test_load_all_is_one_query_whatever_the_count_and_only_the_users_own(db, strategies):
    user = _user()
    made = []
    for _ in range(strategies):
        sid, c = await _strategy(db, user)
        await paper_store.place(db, user, sid, [_new(c[0], "BUY", 65, "10.00")])
        made.append(sid)
    other, oc = await _strategy(db, (stranger := _user()))
    await paper_store.place(db, stranger, other, [_new(oc[0], "BUY", 65, "10.00")])
    counting = _Counting(db)
    books = await paper_store.load_all(counting, user)
    assert counting.calls == 1
    assert [b.strategy_id for b in books] == made
    assert all(len(b.orders) == 1 for b in books)
    assert len(await _ids(db)) >= 1
