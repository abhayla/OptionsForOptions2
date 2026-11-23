"""D-03 part B (ADR-317 (7)): GET /paper/strategies/{id}/armed-exits, the lines the paper confirm list shows under the
orders: one per armed index exit, judged on the legs AS THEY WILL BE after the listed orders. Read only, real PostgreSQL."""
# ruff: noqa: F811 - the imported fixtures are used as test arguments
from __future__ import annotations

import json
from http import HTTPStatus

from test_paper_routes import _new
from test_paper_triggers_routes import _open, _url, db, notified  # noqa: F401 - fixtures
from test_strategy_store import _client

KEEPS_CALL = "Exit above 23,100 stays armed at its level; after this change your short call will be 22,800. Check this level."
KEEPS_PUT = "Exit below 22,000 stays armed at its level; after this change your short put will be 22,400. Check this level."


def _order(o) -> dict:
    return {"contract_id": o.contract_id, "side": o.side, "quantity": o.quantity, "price": str(o.price), "kind": o.kind}


async def _lines(app, stored, orders):
    async with _client(app) as c:
        reply = await c.get(f"/paper/strategies/{stored.id}/armed-exits", params={"orders": json.dumps([_order(o) for o in orders])})
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
    lines = await _lines(app, stored, [_new(ids[0], "BUY", 65, "30", "exit")])  # the short call closes, no put is opened
    assert lines == ["Exit above 23,100 stays armed at its level; after this change you will hold no short call. Check this level.",
                     "Exit below 22,000 stays armed at its level; after this change you will hold no short put. Check this level."]


async def test_no_line_without_an_armed_exit_or_for_a_full_exit(db, notified):
    app, stored, ids = await _open(db)
    assert await _lines(app, stored, [_new(ids[2], "SELL", 65, "82.75")]) == []  # nothing armed
    await _arm(app, stored, {"kind": "conditional_exit", "above": "23100"})
    assert await _lines(app, stored, [_new(ids[0], "BUY", 65, "30", "exit"), _new(ids[1], "SELL", 65, "10", "exit")]) == []  # every leg closes
    assert await _lines(app, stored, [_new(ids[2], "SELL", 65, "82.75")]) == [KEEPS_CALL]
