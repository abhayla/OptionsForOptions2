"""GC-ICLIVE D-66 (owner decision): the Completed page shows the time the trade CLOSED (the last closing fill or settlement
record), not the last builder save. Real case 24 Nov 2026: C1 showed 11:06:39 (last save) against a real stop-out at 13:24:07.

The server sends `closed_at` on every list row: the placed_at of the last exit / stop / settle order of a Completed strategy;
absent (null) for a strategy that is not Completed. Real PostgreSQL, rolled back.
"""
from __future__ import annotations

import datetime
from decimal import Decimal as D
from http import HTTPStatus

from ofo_app import paper_store
from test_strategy_store import _client
from test_strategy_tracking import ANSWERED, ENTRY_PRICES, _paper_body, _setup, db  # noqa: F401 - db is the fixture


async def _row(app, sid):
    async with _client(app) as c:
        reply = await c.get("/strategies")
    assert reply.status_code == HTTPStatus.OK, reply.text
    return next(s for s in reply.json()["strategies"] if s["id"] == sid)


def _exits(stored, indexes, at, kind="exit"):
    legs, ids = stored.saved.definition.legs, stored.saved.contract_ids
    return [paper_store.NewOrder(ids[i], "BUY" if legs[i].action.value == "SELL" else "SELL", legs[i].quantity,
                                 D("1.00"), kind, at) for i in indexes]


async def _open(app, stored):
    async with _client(app) as c:
        placed = await c.post(f"/paper/strategies/{stored.id}/orders", json=_paper_body(stored, ENTRY_PRICES))
    assert placed.status_code == HTTPStatus.CREATED, placed.text


async def test_core_completed_row_carries_the_time_of_the_last_closing_fill_not_the_last_save(db):  # noqa: F811
    app, stored, *_ = await _setup(db)
    await _open(app, stored)
    first_exit = ANSWERED + datetime.timedelta(hours=2)
    last_exit = ANSWERED + datetime.timedelta(hours=3, minutes=24, seconds=7)
    await paper_store.place(db, stored.user_ref, stored.id, _exits(stored, [0, 1], first_exit))
    await paper_store.place(db, stored.user_ref, stored.id, _exits(stored, [2, 3], last_exit, "stop"))
    row = await _row(app, stored.id)
    assert row["status_word"] == "Completed"
    assert datetime.datetime.fromisoformat(row["closed_at"]) == last_exit
    assert datetime.datetime.fromisoformat(row["closed_at"]) != datetime.datetime.fromisoformat(row["updated_at"])


async def test_settlement_record_is_the_close_time(db):  # noqa: F811
    app, stored, *_ = await _setup(db)
    await _open(app, stored)
    settled = ANSWERED + datetime.timedelta(hours=11, minutes=45)  # 15:45 IST on the case's day
    await paper_store.place(db, stored.user_ref, stored.id, _exits(stored, [0, 1, 2, 3], settled, "settle"))
    assert datetime.datetime.fromisoformat((await _row(app, stored.id))["closed_at"]) == settled


async def test_a_strategy_that_is_not_completed_has_no_close_time(db):  # noqa: F811
    app, stored, *_ = await _setup(db)
    assert (await _row(app, stored.id)).get("closed_at") is None  # a draft
    await _open(app, stored)
    await paper_store.place(db, stored.user_ref, stored.id, _exits(stored, [0], ANSWERED + datetime.timedelta(hours=1)))
    row = await _row(app, stored.id)  # one leg exited, three open: Running, nothing closed yet
    assert row["status_word"] == "Running" and row.get("closed_at") is None
