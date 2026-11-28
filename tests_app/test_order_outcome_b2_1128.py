# ruff: noqa: F811 - the imported fixtures are used as test arguments
"""Lane B2 (ADR-016 to ADR-019, ADR-330 (58); migration 0063): while a strategy has an order request whose outcome is
not known, EVERY further order request for it is refused by the server, whatever its key or body; released when the
outcome is known. Real case (Lane FJ2's Opus review, 28 Nov 18:45): the request key de-duplicated only the same key and
body; a retry with another body (`prices_not_live_confirmed` changed) or another key (an add priced from the live tick)
was a new request and a second order could follow. Real PostgreSQL, rolled back."""
from __future__ import annotations

import uuid
from http import HTTPStatus

from ofo_app import order_outcome
from sqlalchemy import text
from test_order_request_key_r2_fd2 import _body, _count, _post, _prices, _use, keys  # noqa: F401 - fixtures
from test_paper_triggers_routes import _setup, db, notified  # noqa: F401 - fixtures

TWO_ORDERS = 2
UNKNOWN = "no known result yet"


async def _states(db, stored) -> list[str]:
    rows = (await db.execute(text("SELECT state FROM public.order_attempts WHERE strategy_id = :s ORDER BY id"),
                             {"s": stored.id})).all()
    return [r[0] for r in rows]


async def _crash_after_commit_began(db, notified, keys, monkeypatch):
    """The first request dies with the commit outcome unknown (the exception comes AFTER the commit began)."""
    from ofo_app.routes import paper as route  # noqa: PLC0415
    app, stored, *_ = await _setup(db)
    _use(app, keys)
    _, orders = _prices(stored)
    real = route._place_orders

    async def crash(db_, strategy_id, stored_, body, deps, stage):  # noqa: PLR0913
        stage["commit_started"] = True
        raise RuntimeError("the connection dropped during the commit")

    monkeypatch.setattr(route, "_place_orders", crash)
    first = await _post(app, stored, _body(orders, uuid.uuid4()))
    assert first.status_code == HTTPStatus.INTERNAL_SERVER_ERROR, first.text[:200]
    monkeypatch.setattr(route, "_place_orders", real)
    return app, stored, orders


async def test_core_after_an_unknown_outcome_another_body_and_another_key_are_refused(db, notified, keys, monkeypatch):
    app, stored, orders = await _crash_after_commit_began(db, notified, keys, monkeypatch)
    assert await _states(db, stored) == ["open"]
    other_key_same_body = await _post(app, stored, _body(orders, uuid.uuid4()))
    other_body = await _post(app, stored, _body(orders[:1], uuid.uuid4()))
    no_key = await _post(app, stored, _body(orders))
    for reply in (other_key_same_body, other_body, no_key):
        assert reply.status_code == HTTPStatus.CONFLICT and UNKNOWN in reply.text, reply.text[:300]
    assert await _count(db, stored) == 0  # nothing stored by any of them
    assert await _states(db, stored) == ["open"]  # the refused requests opened nothing


async def test_the_same_key_with_another_body_is_refused_too_while_the_outcome_is_unknown(db, notified, keys,
                                                                                          monkeypatch):
    from ofo_app.routes import paper as route  # noqa: PLC0415
    app, stored, *_ = await _setup(db)
    _use(app, keys)
    _, orders = _prices(stored)
    key = uuid.uuid4()
    real = route._place_orders

    async def crash(db_, strategy_id, stored_, body, deps, stage):  # noqa: PLR0913
        stage["commit_started"] = True
        raise RuntimeError("dropped")

    monkeypatch.setattr(route, "_place_orders", crash)
    assert (await _post(app, stored, _body(orders, key))).status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    monkeypatch.setattr(route, "_place_orders", real)
    changed = await _post(app, stored, _body(orders[:1], key))
    assert changed.status_code == HTTPStatus.CONFLICT and UNKNOWN in changed.text, changed.text[:300]
    assert await _count(db, stored) == 0


async def test_the_block_releases_when_the_attempt_is_old_and_nothing_was_stored(db, notified, keys, monkeypatch):
    app, stored, orders = await _crash_after_commit_began(db, notified, keys, monkeypatch)
    monkeypatch.setattr(order_outcome, "SETTLE_SECONDS", -1)  # the attempt is now "older than the window"
    placed = await _post(app, stored, _body(orders, uuid.uuid4()))
    assert placed.status_code == HTTPStatus.CREATED, placed.text[:300]
    assert await _count(db, stored) == TWO_ORDERS
    assert await _states(db, stored) == ["not_stored", "stored"]


async def test_the_block_releases_at_once_when_the_unknown_request_did_store_its_orders(db, notified, keys,
                                                                                        monkeypatch):
    from ofo_app.routes import paper as route  # noqa: PLC0415
    app, stored, *_ = await _setup(db)
    _use(app, keys)
    _, orders = _prices(stored)

    async def reply_fails(*_a, **_k):
        raise RuntimeError("the answer could not be built after the commit")

    monkeypatch.setattr(route, "_book", reply_fails)
    first = await _post(app, stored, _body(orders, uuid.uuid4()))
    assert first.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert await _count(db, stored) == TWO_ORDERS  # stored, the reply was lost
    assert await _states(db, stored) == ["open"]
    monkeypatch.undo()
    app2, _stored2, *_ = app, stored
    again = await _post(app2, stored, _body(orders[:1], uuid.uuid4()))  # the outcome is now KNOWN: stored
    assert again.status_code != HTTPStatus.CONFLICT or UNKNOWN not in again.text, again.text[:300]
    assert (await _states(db, stored))[0] == "stored"


async def test_two_tabs_the_second_is_refused_while_the_first_is_running_and_released_when_it_ends(db, notified, keys):
    app, stored, *_ = await _setup(db)
    _use(app, keys)
    _, orders = _prices(stored)
    running = await order_outcome.open_attempt(db, stored.user_ref, stored.id, "paper")  # tab one is placing
    second = await _post(app, stored, _body(orders, uuid.uuid4()))
    assert second.status_code == HTTPStatus.CONFLICT and UNKNOWN in second.text, second.text[:300]
    await order_outcome.close_attempt(db, running, None)  # tab one finished
    third = await _post(app, stored, _body(orders, uuid.uuid4()))
    assert third.status_code == HTTPStatus.CREATED, third.text[:300]


async def test_a_clean_refusal_releases_at_once_and_a_corrected_press_places(db, notified, keys):
    app, stored, *_ = await _setup(db)
    _use(app, keys)
    ids = stored.saved.contract_ids
    from test_paper_routes import _new  # noqa: PLC0415
    too_big = _body([_new(ids[0], "BUY", 650, "30", "exit")])
    assert (await _post(app, stored, too_big)).status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert await _states(db, stored) == ["not_stored"]
    _, orders = _prices(stored)
    assert (await _post(app, stored, _body(orders))).status_code == HTTPStatus.CREATED
    assert await _states(db, stored) == ["not_stored", "stored"]


async def test_a_table_that_cannot_be_used_refuses_and_stores_nothing(db, notified, keys, monkeypatch):
    app, stored, *_ = await _setup(db)
    _use(app, keys)
    _, orders = _prices(stored)
    monkeypatch.setattr(order_outcome, "_OPEN", text("INSERT INTO public.order_attempts_missing VALUES (1)"))
    reply = await _post(app, stored, _body(orders, uuid.uuid4()))
    assert reply.status_code == HTTPStatus.SERVICE_UNAVAILABLE, reply.text[:300]
    assert await _count(db, stored) == 0
