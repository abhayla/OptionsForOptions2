"""D-02 (REQ-159 AC-6 "buy legs first in the order sequence"; REQ-058 Q238 "buy back the shorts first, then sell the
longs"): every batch of paper orders against an open position (the strategy already has orders) is recorded BUY exits,
BUY adds, SELL exits, SELL adds (stable inside each group), so a short option is never left without its protection
between two fills. An entry batch (empty book) is recorded exactly as sent, so the legs keep the order the trader built.

Core proof: ``paper_store.place`` (the one writer) given the real case of strategy 155 on 23 Nov, a roll sent as
"1. SELL the hedge, 2. BUY the short", records the BUY first; then one test per caller (route, stop-out, settlement,
tracking exit). The Orderbook reads ORDER BY id (paper_store._SELECT, _SELECT_USER), so the recorded sequence is the
id order. Real PostgreSQL; every test rolls back.
"""
from __future__ import annotations

import datetime
from decimal import Decimal
from http import HTTPStatus

import pytest
import test_paper_monitor as pm
import test_paper_settlement as ps_t
from ofo.tracking.orderbook import net_positions
from ofo_app import paper_settlement as ps
from ofo_app import paper_store, tracked_contracts
from test_strategy_store import _client, _user, _with_draft
from test_strategy_tracking import _open_book, _setup

D = Decimal
AT = datetime.datetime(2026, 11, 23, 5, 0, tzinfo=datetime.UTC)
CREATED, OK = HTTPStatus.CREATED, HTTPStatus.OK


@pytest.fixture
async def db(app_engine):
    async with app_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


def _new(contract: int, side: str, qty: int, price: str, kind: str = "open") -> paper_store.NewOrder:
    return paper_store.NewOrder(contract, side, qty, D(price), kind, AT)


async def _book(db, sid: int) -> list[tuple[int, str, str]]:
    """The recorded sequence as the Orderbook reads it (load: ORDER BY id): (contract, side, kind)."""
    return [(o.order.contract_id, o.order.side, o.order.kind) for o in await paper_store.load(db, sid)]


async def _held(db) -> tuple[str, int, list[int]]:
    """A condor-shaped book: c[0] long (the hedge), c[1] short, c[2] long, c[3] short, all opened, ids ascending."""
    user = _user()
    _, stored = await _with_draft(db, user)
    c = sorted(stored.saved.contract_ids)
    await paper_store.place(db, user, stored.id, [_new(c[0], "BUY", 65, "10.00"), _new(c[1], "SELL", 65, "20.00"),
                                                  _new(c[2], "BUY", 65, "5.00"), _new(c[3], "SELL", 65, "8.00")])
    return user, stored.id, c


async def test_core_place_records_the_roll_buy_first_strategy_155(db):
    user, sid, c = await _held(db)
    # 23 Nov strategy 155: "1. SELL 25300 PE (the hedge), 2. BUY 25400 PE (the short)": the short was naked after fill 1
    await paper_store.place(db, user, sid, [_new(c[0], "SELL", 65, "11.00", "exit"),
                                            _new(c[1], "BUY", 65, "19.00", "exit")])
    assert (await _book(db, sid))[4:] == [(c[1], "BUY", "exit"), (c[0], "SELL", "exit")]


async def test_place_orders_the_four_groups_and_keeps_order_inside_each(db):
    user, sid, c = await _held(db)
    batch = [_new(c[0], "SELL", 65, "11.00", "exit"), _new(c[1], "SELL", 30, "21.00", "open"),
             _new(c[3], "BUY", 65, "7.00", "exit"), _new(c[2], "BUY", 10, "6.00", "open"),
             _new(c[1], "BUY", 65, "19.00", "exit"), _new(c[0], "BUY", 5, "12.00", "open")]
    await paper_store.place(db, user, sid, batch)
    assert (await _book(db, sid))[4:] == [
        (c[3], "BUY", "exit"), (c[1], "BUY", "exit"), (c[2], "BUY", "open"), (c[0], "BUY", "open"),
        (c[0], "SELL", "exit"), (c[1], "SELL", "open")]


async def test_a_single_side_batch_and_a_one_order_batch_keep_their_order(db):
    user, sid, c = await _held(db)
    await paper_store.place(db, user, sid, [_new(c[3], "BUY", 65, "7.00", "exit"),
                                            _new(c[1], "BUY", 65, "19.00", "exit")])
    await paper_store.place(db, user, sid, [_new(c[2], "SELL", 65, "5.50", "exit")])
    assert (await _book(db, sid))[4:] == [(c[3], "BUY", "exit"), (c[1], "BUY", "exit"), (c[2], "SELL", "exit")]


async def test_the_reordered_batch_shares_one_placed_at_and_the_figures_do_not_depend_on_the_order(db):
    user, sid, c = await _held(db)
    batch = [_new(c[0], "SELL", 65, "11.00", "exit"), _new(c[1], "BUY", 65, "19.00", "exit")]
    stored = await paper_store.place(db, user, sid, batch)
    assert len({o.order.placed_at for o in stored[4:]}) == 1  # ADR-255 count and D-03 marks read batches by placed_at
    booked = {p.instrument_id: p.booked for p in net_positions([o.order.as_paper() for o in stored], {}).positions}
    assert booked[str(c[0])] + booked[str(c[1])] == D("130.00")  # (11 - 10) x 65 + (20 - 19) x 65, any sequence
    rows = await paper_store.load_all(db, user)
    assert [o.id for o in rows[0].orders] == sorted(o.id for o in rows[0].orders)  # the Orderbook reads id order


async def test_the_route_records_a_posted_roll_buy_first(db):
    app, stored, *_ = await _setup(db)
    async with _client(app) as client:
        await _open_book(client, stored)  # SELL 22800 CE, BUY 23000 CE, SELL 22400 PE, BUY 22200 PE
        c = stored.saved.contract_ids
        body = {"orders": [{"contract_id": c[1], "side": "SELL", "quantity": 65, "price": "13.00", "kind": "exit"},
                           {"contract_id": c[0], "side": "BUY", "quantity": 65, "price": "39.00", "kind": "exit"}]}
        reply = await client.post(f"/paper/strategies/{stored.id}/orders", json=body)
    assert reply.status_code == CREATED, reply.text
    assert (await _book(db, stored.id))[4:] == [(c[0], "BUY", "exit"), (c[1], "SELL", "exit")]


async def test_the_tracking_exit_of_all_four_condor_legs_records_both_buy_backs_first(db):
    app, stored, *_ = await _setup(db)
    async with _client(app) as client:
        await _open_book(client, stored)
        reply = await client.post(f"/strategies/{stored.id}/tracking/exit", json={"legs": [0, 1, 2, 3]})
    assert reply.status_code == OK, reply.text
    c = stored.saved.contract_ids
    assert (await _book(db, stored.id))[4:] == [(c[0], "BUY", "exit"), (c[2], "BUY", "exit"),
                                                (c[1], "SELL", "exit"), (c[3], "SELL", "exit")]


async def test_a_stop_out_of_a_four_leg_condor_records_both_buy_backs_before_both_sales(db):
    market = pm.Market()
    user = _user()
    _, stored = await _with_draft(db, user)
    ids = sorted(stored.saved.contract_ids)
    # held SELL ids[0], BUY ids[1], SELL ids[2], BUY ids[3]: the stop fires in contract-id order, BUY SELL BUY SELL
    await paper_store.place(db, user, stored.id, [
        _new(ids[0], "SELL", 65, "10.00"), _new(ids[1], "BUY", 65, "5.00"),
        _new(ids[2], "SELL", 65, "8.00"), _new(ids[3], "BUY", 65, "4.00")])
    keys = [c.feed_key for c in await tracked_contracts.resolve(db, ids)]
    await pm._exit_below(db, stored.id)
    monitor = pm._monitor(db, market)
    assert await monitor.step() == 0
    for k in keys:
        market.tick(k, "9.00")
    market.tick(pm.INDEX, "22849.95")
    assert await monitor.step() == 1
    stops = [(o[0], o[1]) for o in await pm._stops(db, stored.id)]
    assert stops == [(ids[0], "BUY"), (ids[2], "BUY"), (ids[1], "SELL"), (ids[3], "SELL")]


async def test_settlement_records_the_buy_back_before_the_sale(db):
    ids = await ps_t._catalogue(db)
    sid = await ps_t._real(db, ids, 61)  # long PE 73000 (settles with a SELL), short PE 72600 (settles with a BUY)
    await ps.settle_expired(db, ps_t.AFTER, ps_t._close_of())
    settles = [o.order for o in await paper_store.load(db, sid) if o.order.kind == "settle"]
    assert [o.side for o in settles] == ["BUY", "SELL"]


async def test_an_entry_batch_is_recorded_exactly_as_sent(db):
    user = _user()
    _, stored = await _with_draft(db, user)
    c = sorted(stored.saved.contract_ids)
    sent = [(c[1], "SELL", "open"), (c[0], "BUY", "open"), (c[3], "SELL", "open"), (c[2], "BUY", "open")]
    await paper_store.place(db, user, stored.id, [_new(cid, side, 65, "10.00", kind) for cid, side, kind in sent])
    assert await _book(db, stored.id) == sent  # SELL first stays first: the book was empty, nothing to protect


async def test_leg_order_of_a_new_strategy_equals_the_order_the_legs_were_sent(db):
    user = _user()
    _, stored = await _with_draft(db, user)
    c = sorted(stored.saved.contract_ids)
    sent = [c[2], c[0], c[3], c[1]]
    await paper_store.place(db, user, stored.id, [_new(cid, "SELL" if i % 2 == 0 else "BUY", 65, "10.00")
                                                  for i, cid in enumerate(sent)])
    first_seen = list(dict.fromkeys(o.order.contract_id for o in await paper_store.load(db, stored.id)))
    assert first_seen == sent  # contract_legs numbers legs by each contract's first order


BOOK_ROWS = 4  # orders on the book after the refused batch


async def test_an_exit_that_needs_an_add_of_the_same_batch_is_refused_and_nothing_is_stored(db):
    user, sid, c = await _held(db)  # c[1] is held short 65
    # "SELL c[1] 65 more, then BUY c[1] 130 back": buys first puts the 130 buy-back ahead of its own add -> refused
    # whole
    with pytest.raises(Exception, match=r"exit_exceeds_open|EXIT_EXCEEDS_OPEN|exit of BUY"):
        await paper_store.place(db, user, sid,
                                [_new(c[1], "SELL", 65, "9.00", "open"), _new(c[1], "BUY", 130, "8.00", "exit")])
    assert len(await _book(db, sid)) == BOOK_ROWS


async def test_place_checked_records_a_mixed_batch_buys_first(db, monkeypatch):
    """D-02 review: the batch goes through the one write both user routes use, against an open position."""
    from ofo_app import paper_limit  # noqa: PLC0415

    async def no_max(*_a, **_k):
        return {"guards": {}}

    async def reader(*_a, **_k):
        return None
    monkeypatch.setattr(paper_limit, "_plan_body", no_max)
    user, sid, c = await _held(db)
    await paper_limit.place_checked(
        db, user, sid, [_new(c[0], "SELL", 65, "11.00", "exit"), _new(c[1], "BUY", 65, "19.00", "exit")],
        entry=None, ctx=None, at=AT, reader=reader, rates=None)
    assert (await _book(db, sid))[4:] == [(c[1], "BUY", "exit"), (c[0], "SELL", "exit")]
