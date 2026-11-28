"""Lane FD2 item 1 (review finding F3, server half; ADR-330 (48)): the order reply names every leg stop the request
cancelled, read from the transaction that cancelled them. Real PostgreSQL; every test rolls back."""
# ruff: noqa: F811 - the imported fixtures are used as test arguments
from __future__ import annotations

from decimal import Decimal as D
from http import HTTPStatus

from test_paper_armed_exits import _order, _stop
from test_paper_routes import _new
from test_paper_triggers_routes import _open, db, notified  # noqa: F401 - fixtures
from test_strategy_store import _client


def _body(orders) -> dict:
    return {"orders": [_order(o) for o in orders]}


async def _post(app, stored, orders):
    async with _client(app) as c:
        return await c.post(f"/paper/strategies/{stored.id}/orders", json=_body(orders))


async def test_a_move_names_the_stop_it_cancelled_in_the_201_reply(db, notified):
    app, stored, ids = await _open(db)  # short 22800 CE (ids[0]), long 23000 CE (ids[1])
    await _stop(app, stored, ids[0])
    await _stop(app, stored, ids[1], "below", "5.00")
    reply = await _post(app, stored, [_new(ids[0], "BUY", 65, "30", "exit"), _new(ids[2], "SELL", 65, "82.75")])
    assert reply.status_code == HTTPStatus.CREATED, reply.text
    assert reply.json()["cancelled_stops"] == [
        {"leg": "NIFTY 13 Oct 22800 CE", "contract": ids[0], "level": "120.00"}], reply.json()["cancelled_stops"]


async def test_an_order_that_cancels_nothing_answers_an_empty_list(db, notified):
    app, stored, ids = await _open(db)
    await _stop(app, stored, ids[1], "below", "5.00")
    reply = await _post(app, stored, [_new(ids[2], "SELL", 65, "82.75")])
    assert reply.status_code == HTTPStatus.CREATED, reply.text
    assert reply.json()["cancelled_stops"] == []


async def test_the_get_of_a_book_has_no_cancelled_stops_to_report(db, notified):
    app, stored, _ids = await _open(db)
    async with _client(app) as c:
        reply = await c.get(f"/paper/strategies/{stored.id}")
    assert reply.json()["cancelled_stops"] == []


# --- F4 (review minor): an old orphan leg stop must not revive when its contract is opened again ----------------

async def test_an_orphan_leg_stop_on_a_flat_contract_does_not_revive_when_the_contract_is_opened_again(db, notified):
    from ofo_app import paper_trigger_store as triggers  # noqa: PLC0415
    app, stored, ids = await _open(db)  # short 22800 CE (ids[0]), long 23000 CE (ids[1]); ids[2] is flat
    # an orphan: an armed leg stop on a contract nothing holds (as old data had them)
    await triggers.add(db, stored.id, triggers.NewTrigger("leg_stop", "above", D("120.00"), contract_id=ids[2]))
    reply = await _post(app, stored, [_new(ids[2], "SELL", 65, "82.75")])  # the contract is opened again
    assert reply.status_code == HTTPStatus.CREATED, reply.text
    rows = [r for r in await triggers.list_for(db, stored.id) if r.trigger.contract_id == ids[2]]
    assert [(r.trigger.level, r.cancelled_at is not None) for r in rows] == [(D("120.00"), True)], rows
    assert reply.json()["cancelled_stops"] == []  # an old orphan is not "a stop this move removed"
