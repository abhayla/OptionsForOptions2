"""D-03 part B (ADR-317 (7)): GET /paper/strategies/{id}/armed-exits, the lines the paper confirm list shows under the
orders: one per armed index exit, judged on the legs AS THEY WILL BE after the listed orders. Read only, real
PostgreSQL."""
# ruff: noqa: F811 - the imported fixtures are used as test arguments
from __future__ import annotations

import json
from decimal import Decimal as D
from http import HTTPStatus

from ofo_app import paper_trigger_store
from test_paper_routes import _new
from test_paper_triggers_routes import _open, _setup, _url, db, notified  # noqa: F401 - fixtures
from test_strategy_store import _client

KEEPS_CALL = ("Exit above 23,100 stays armed at its level; after this change your short call will be 22,800. "
              "Check this level.")
KEEPS_PUT = ("Exit below 22,000 stays armed at its level; after this change your short put will be 22,400. "
             "Check this level.")


def _order(o) -> dict:
    return {"contract_id": o.contract_id, "side": o.side, "quantity": o.quantity, "price": str(o.price), "kind": o.kind}


async def _lines(app, stored, orders):
    async with _client(app) as c:
        reply = await c.get(f"/paper/strategies/{stored.id}/armed-exits",
                            params={"orders": json.dumps([_order(o) for o in orders])})
    assert reply.status_code == HTTPStatus.OK, reply.text
    return reply.json()["lines"]


async def _arm(app, stored, body):
    async with _client(app) as c:
        assert (await c.post(_url(stored), json=body)).status_code == HTTPStatus.CREATED


async def test_each_armed_exit_is_named_against_the_short_strikes_after_the_listed_orders(db, notified):
    app, stored, ids = await _open(db)  # short call 22800, long call 23000
    await _arm(app, stored, {"kind": "conditional_exit", "above": "23100", "below": "22000"})
    lines = await _lines(app, stored, [_new(ids[2], "SELL", 65, "82.75"), _new(ids[3], "BUY", 65, "35.80")])
    assert lines == [KEEPS_CALL, KEEPS_PUT]


async def test_no_short_left_on_a_side_after_the_orders_says_so(db, notified):
    app, stored, ids = await _open(db)
    await _arm(app, stored, {"kind": "conditional_exit", "above": "23100", "below": "22000"})
    # the short call closes, no put is opened
    lines = await _lines(app, stored, [_new(ids[0], "BUY", 65, "30", "exit")])
    assert lines == [
        "Exit above 23,100 stays armed at its level; after this change you will hold no short call. Check this level.",
        "Exit below 22,000 stays armed at its level; after this change you will hold no short put. Check this level."]


async def test_no_line_without_an_armed_exit_or_for_a_full_exit(db, notified):
    app, stored, ids = await _open(db)
    assert await _lines(app, stored, [_new(ids[2], "SELL", 65, "82.75")]) == []  # nothing armed
    await _arm(app, stored, {"kind": "conditional_exit", "above": "23100"})
    # every leg closes
    both_close = [_new(ids[0], "BUY", 65, "30", "exit"), _new(ids[1], "SELL", 65, "10", "exit")]
    assert await _lines(app, stored, both_close) == []
    assert await _lines(app, stored, [_new(ids[2], "SELL", 65, "82.75")]) == [KEEPS_CALL]


async def test_another_users_or_a_missing_strategy_is_refused_by_armed_exits(db, notified):
    app, stored, ids = await _open(db)
    other, *_ = await _setup(db)
    params = {"orders": json.dumps([_order(_new(ids[2], "SELL", 65, "82.75"))])}
    async with _client(other) as c:
        reply = await c.get(f"/paper/strategies/{stored.id}/armed-exits", params=params)
    assert reply.status_code == HTTPStatus.NOT_FOUND and "lines" not in reply.json()
    async with _client(app) as c:
        missing = await c.get("/paper/strategies/999999999/armed-exits", params=params)
        assert missing.status_code == HTTPStatus.NOT_FOUND


# --- #774: a leg stop goes with its closed contract, said before Confirm and done at Confirm ---------------------

async def _stop(app, stored, contract, direction="above", level="120.00"):
    async with _client(app) as c:
        reply = await c.post(_url(stored), json={"kind": "leg_stop", "contract_id": contract, "direction": direction,
                                                 "level": level})
    assert reply.status_code == HTTPStatus.CREATED, reply.text


async def _armed_stops(db, stored):
    return [(r.trigger.contract_id, r.trigger.level, r.cancelled_at is None)
            for r in await paper_trigger_store.list_for(db, stored.id) if r.trigger.kind == "leg_stop"]


def _post_body(orders) -> dict:
    return {"orders": [_order(o) for o in orders]}


async def test_a_move_lists_the_leg_stop_it_removes_and_the_route_removes_exactly_that(db, notified):
    app, stored, ids = await _open(db)  # short 22800 CE (ids[0]), long 23000 CE (ids[1])
    await _stop(app, stored, ids[0])
    await _stop(app, stored, ids[1], "below", "5.00")
    move = [_new(ids[0], "BUY", 65, "30", "exit"), _new(ids[2], "SELL", 65, "82.75")]  # exit A, add A'
    lines = await _lines(app, stored, move)
    assert len(lines) == 1 and lines[0].startswith("The stop on ") and lines[0].endswith(
        " will be removed; set a new one after the move."), lines
    async with _client(app) as c:
        assert (await c.post(f"/paper/strategies/{stored.id}/orders", json=_post_body(move))).status_code == \
            HTTPStatus.CREATED
    # the preview named exactly what the route did: the stop on A is cancelled, the stop on the untouched leg stays
    assert await _armed_stops(db, stored) == [(ids[0], D("120.00"), False), (ids[1], D("5.00"), True)]


async def test_a_refused_order_set_changes_no_stop(db, notified):
    app, stored, ids = await _open(db)
    await _stop(app, stored, ids[0])
    too_big = [_new(ids[0], "BUY", 650, "30", "exit"), _new(ids[2], "SELL", 65, "82.75")]
    async with _client(app) as c:
        reply = await c.post(f"/paper/strategies/{stored.id}/orders", json=_post_body(too_big))
    assert reply.status_code == HTTPStatus.UNPROCESSABLE_ENTITY, reply.text
    assert await _armed_stops(db, stored) == [(ids[0], D("120.00"), True)]


async def test_a_partial_exit_keeps_the_stop_and_a_full_exit_of_every_leg_lists_none(db, notified):
    app, stored, ids = await _open(db)
    await _stop(app, stored, ids[0])
    assert await _lines(app, stored, [_new(ids[0], "BUY", 30, "30", "exit")]) == []  # part of the leg stays open
    both_close = [_new(ids[0], "BUY", 65, "30", "exit"), _new(ids[1], "SELL", 65, "10", "exit")]
    assert await _lines(app, stored, both_close) == []  # flat: the existing rule cancels every trigger (ADR-317)
