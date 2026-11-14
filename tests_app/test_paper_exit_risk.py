"""GC-ICFIX Issue 10 (ADR-256, ADR-143, REQ-109 AC-4): GET /paper/strategies/{id}/exit-risk, replay market,
real PostgreSQL, every test rolled back. Strategy: the app's four condor contracts opened as the real paper fixture
(tests/fixtures/paper/before-2026-10-29.json, strategy 48 legs, as test_paper_routes). Read only: nothing is stored."""
from __future__ import annotations

import datetime
import json
from decimal import Decimal
from http import HTTPStatus

import pytest
from ofo_app import paper_store
from sqlalchemy import text
from test_paper_routes import _strategy_48
from test_strategy_store import _client
from test_strategy_tracking import IDS, _frame, _setup

D = Decimal
AT = datetime.datetime(2026, 10, 29, 5, 0, tzinfo=datetime.UTC)


@pytest.fixture
async def db(app_engine):
    async with app_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


async def _condor(db, **kw):
    """The four legs opened at the fixture's entry prices, the feed at its current prices; no leg exited."""
    app, stored, provider, _clock, last = await _setup(db, **kw)
    legs = _strategy_48()["legs"]
    ids = stored.saved.contract_ids
    await paper_store.place(db, stored.user_ref, stored.id, [
        paper_store.NewOrder(ids[i], leg["action"], leg["quantity"], D(leg["entry_price"]), "open", AT)
        for i, leg in enumerate(legs)])
    for iid, leg in zip(IDS, legs, strict=True):
        provider.on_frame(_frame(provider, iid, leg["current_price"] or "100"), last)
    return app, stored, ids, legs


def _exit_of(ids, legs, picks) -> list[dict]:
    """Exit orders (the opposite side, the whole quantity) for the legs at the positions in ``picks``."""
    return [{"contract_id": ids[i], "side": "SELL" if legs[i]["action"] == "BUY" else "BUY",
             "quantity": legs[i]["quantity"], "price": "0", "kind": "exit"} for i in picks]


async def _ask(app, strategy_id: int, orders: list[dict]):
    async with _client(app) as c:
        return await c.get(f"/paper/strategies/{strategy_id}/exit-risk", params={"orders": json.dumps(orders)})


async def _exit_rows(db, strategy_id: int) -> int:
    return (await db.execute(text("SELECT count(*) FROM public.paper_orders WHERE strategy_id = :i AND kind = 'exit'"),
                             {"i": strategy_id})).scalar_one()


def _bought_call(legs) -> int:
    return next(i for i, leg in enumerate(legs) if leg["action"] == "BUY" and leg["instrument"] == "CE")


def _sold_call(legs) -> int:
    return next(i for i, leg in enumerate(legs) if leg["action"] == "SELL" and leg["instrument"] == "CE")


async def test_closing_a_bought_leg_alone_is_yes_limited_before_unlimited_after_and_names_the_sold_leg(db):
    app, stored, ids, legs = await _condor(db)
    reply = await _ask(app, stored.id, _exit_of(ids, legs, [_bought_call(legs)]))
    assert reply.status_code == HTTPStatus.OK, reply.text
    body = reply.json()
    assert body["state"] == "yes"
    assert body["max_loss_before"] not in (None, "unlimited")
    assert body["max_loss_after"] is not None  # test-catalogue contract types differ from the fixture labels
    assert "Less protected" in body["warning_text"] and "CE" in body["warning_text"]
    assert await _exit_rows(db, stored.id) == 0  # read only


async def test_closing_everything_is_no(db):
    app, stored, ids, legs = await _condor(db)
    reply = await _ask(app, stored.id, _exit_of(ids, legs, list(range(len(legs)))))
    assert reply.status_code == HTTPStatus.OK, reply.text
    assert reply.json()["state"] == "no" and reply.json()["warning_text"] is None


async def test_closing_one_whole_spread_follows_the_more_than_double_rule(db):
    """ADR-256 amendment: the condor's call spread gone leaves the put spread, whose Max Loss is more than double."""
    app, stored, ids, legs = await _condor(db)
    reply = await _ask(app, stored.id, _exit_of(ids, legs, [_sold_call(legs), _bought_call(legs)]))
    assert reply.status_code == HTTPStatus.OK, reply.text
    assert reply.json()["state"] in ("yes", "no")
    body = reply.json()
    if body["state"] == "yes":
        assert "Less protected" not in body["warning_text"]  # no sold leg lost its cover, only the Max Loss grew


async def test_a_roll_basket_is_judged_after_all_orders(db):
    """Close the bought call and open it again in the same basket: the legs after are the legs before."""
    app, stored, ids, legs = await _condor(db)
    i = _bought_call(legs)
    reopen = {"contract_id": ids[i], "side": legs[i]["action"], "quantity": legs[i]["quantity"],
              "price": legs[i]["current_price"] or "100", "kind": "open"}
    reply = await _ask(app, stored.id, [*_exit_of(ids, legs, [i]), reopen])
    assert reply.status_code == HTTPStatus.OK, reply.text
    assert reply.json()["state"] == "no"


async def test_an_exit_larger_than_what_is_open_is_cannot_tell_never_no(db):
    app, stored, ids, legs = await _condor(db)
    orders = _exit_of(ids, legs, [_bought_call(legs)])
    orders[0]["quantity"] *= 3
    reply = await _ask(app, stored.id, orders)
    assert reply.status_code == HTTPStatus.OK, reply.text
    assert reply.json()["state"] == "cannot_tell"


async def test_malformed_orders_are_refused_never_answered_no(db):
    app, stored, _ids, _legs = await _condor(db)
    async with _client(app) as c:
        for bad in ("not json", "[{}]", "[]"):
            reply = await c.get(f"/paper/strategies/{stored.id}/exit-risk", params={"orders": bad})
            assert HTTPStatus.BAD_REQUEST <= reply.status_code < HTTPStatus.INTERNAL_SERVER_ERROR, (bad, reply.text)
            assert "state" not in reply.json()


async def test_unreadable_exit_prices_say_not_available_and_the_state_is_still_yes(db):
    app, stored, ids, legs = await _condor(db, ctx="none")
    reply = await _ask(app, stored.id, _exit_of(ids, legs, [_bought_call(legs)]))
    assert reply.status_code == HTTPStatus.OK, reply.text
    body = reply.json()
    assert body["state"] == "yes"
    assert body["max_loss_before"] is None and body["max_loss_after"] is None  # never 0
    assert "not available" in body["warning_text"]


async def test_another_users_or_a_missing_strategy_answers_not_found(db):
    app, stored, ids, legs = await _condor(db)
    other, *_ = await _setup(db)
    orders = _exit_of(ids, legs, [_bought_call(legs)])
    assert (await _ask(other, stored.id, orders)).status_code == HTTPStatus.NOT_FOUND  # never another user's book
    assert (await _ask(app, 999999999, orders)).status_code == HTTPStatus.NOT_FOUND
