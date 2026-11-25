"""GC-ICLIVE D-42 (ADR-299): My Strategies shows the CURRENT legs and the same word as the paper page.

Real case (23 Nov 2026): condors C6 / C1 rows still read "NIFTY 25300 PE and 3 more" (a leg closed after the save), and a
strategy whose every leg was exited was missing from the Completed list. The /strategies list now reads the legs from the
paper book (the source the Positions page reads: the open positions) and the word from the same function as the paper
list, so the list and the Positions page agree.

Real PostgreSQL, every test rolled back (the fixture of test_strategy_tracking).
"""
from __future__ import annotations

import datetime
from decimal import Decimal as D
from http import HTTPStatus

from ofo_app import paper_store
from test_strategy_store import _client
from test_strategy_tracking import ANSWERED, ENTRY_PRICES, _paper_body, _setup, db  # noqa: F401 - db is the fixture


async def _get_ok(app, path):
    async with _client(app) as c:
        reply = await c.get(path)
    assert reply.status_code == HTTPStatus.OK, reply.text
    return reply.json()


async def _row(app, sid):
    return next(s for s in (await _get_ok(app, "/strategies"))["strategies"] if s["id"] == sid)


async def _positions(app, sid):
    return (await _get_ok(app, f"/paper/strategies/{sid}"))["positions"]


def _terms(position):
    return {"instrument": position["instrument"], "strike": str(position["strike"]), "expiry": str(position["expiry"])}


def _row_terms(row):
    leg = row["first_leg"]
    return {"instrument": leg["instrument"], "strike": str(leg["strike"]), "expiry": str(leg["expiry"])}


async def _exit_leg(c, stored, index):
    leg = stored.saved.definition.legs[index]
    side = "BUY" if leg.action.value == "SELL" else "SELL"
    done = await c.post(f"/paper/strategies/{stored.id}/orders", json={"orders": [
        {"contract_id": stored.saved.contract_ids[index], "kind": "exit", "price": "1.00", "quantity": leg.quantity,
         "side": side}]})
    assert done.status_code == HTTPStatus.CREATED, done.text


async def test_core_a_closed_leg_leaves_the_list_row_and_the_first_leg_is_an_open_one(db):  # noqa: F811
    app, stored, *_ = await _setup(db)
    async with _client(app) as c:
        placed = await c.post(f"/paper/strategies/{stored.id}/orders", json=_paper_body(stored, ENTRY_PRICES))
        assert placed.status_code == HTTPStatus.CREATED, placed.text
    before = await _row(app, stored.id)
    assert before["leg_count"] == 4
    first_open = next(p for p in await _positions(app, stored.id) if p["net_quantity"] != 0)
    assert _row_terms(before) == _terms(first_open)
    # exit the leg the row names as first: the list must now name another leg and count three
    index = next(i for i, cid in enumerate(stored.saved.contract_ids) if cid == first_open["contract_id"])
    async with _client(app) as c:
        await _exit_leg(c, stored, index)
    after = await _row(app, stored.id)
    assert after["leg_count"] == 3
    still_open = [p for p in await _positions(app, stored.id) if p["net_quantity"] != 0]
    assert len(still_open) == 3
    assert _row_terms(after) == _terms(still_open[0])
    assert _row_terms(after) != _row_terms(before)  # the closed leg is not named any more
    assert after["status_word"] == "Running"


async def test_a_strategy_with_no_order_keeps_the_saved_legs(db):  # noqa: F811
    app, stored, *_ = await _setup(db)
    row = await _row(app, stored.id)
    first = stored.saved.definition.legs[0]
    assert row["leg_count"] == len(stored.saved.definition.legs)
    assert row["first_leg"]["instrument"] == first.instrument.value
    assert row["status_word"] == "Draft"


async def test_every_leg_exited_lists_the_strategy_completed_with_its_traded_legs(db):  # noqa: F811
    app, stored, *_ = await _setup(db)
    async with _client(app) as c:
        placed = await c.post(f"/paper/strategies/{stored.id}/orders", json=_paper_body(stored, ENTRY_PRICES))
        assert placed.status_code == HTTPStatus.CREATED, placed.text
        for index in range(len(stored.saved.contract_ids)):
            await _exit_leg(c, stored, index)
    row = await _row(app, stored.id)  # the closed strategy is in the list
    assert row["status"] == "closed"
    assert row["status_word"] == "Completed"
    assert row["leg_count"] == 4  # nothing is open: the legs it traded, not "0 legs"


async def test_the_list_word_is_the_paper_list_word_after_every_leg_is_exited(db):  # noqa: F811
    """Every leg exited (the paper list says Completed): the My Strategies list says the same word, so the Completed
    page shows it. (Placing the last exit marks the row closed too: alembic 0049.)"""
    app, stored, *_ = await _setup(db)
    async with _client(app) as c:
        placed = await c.post(f"/paper/strategies/{stored.id}/orders", json=_paper_body(stored, ENTRY_PRICES))
        assert placed.status_code == HTTPStatus.CREATED, placed.text
    later = ANSWERED + datetime.timedelta(minutes=5)
    exits = [paper_store.NewOrder(cid, "BUY" if leg.action.value == "SELL" else "SELL", leg.quantity, D("1.00"),
                                  "exit", later)
             for cid, leg in zip(stored.saved.contract_ids, stored.saved.definition.legs, strict=True)]
    await paper_store.place(db, stored.user_ref, stored.id, exits)
    paper = next(s for s in (await _get_ok(app, "/paper/strategies"))["strategies"] if s["strategy_id"] == stored.id)
    assert paper["status_word"] == "Completed"
    assert (await _row(app, stored.id))["status_word"] == paper["status_word"]
