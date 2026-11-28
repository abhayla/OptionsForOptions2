"""Lane B2 item 2 (I-138, "durable key decides", ADR-016 to ADR-019): Redis is a hint, the durable claim in the order's
own transaction decides. Real case: 28 Nov, issues 855 to 877 ("durable key table undone"): a press whose first try
crashed after the commit began left a Redis record `pending`; the repeat was refused 582 for 10 minutes although the
durable table knew whether the orders were stored. Core: a pending Redis hint with no durable row lets the repeat place
once; with a durable row it replays the first result; two presses with one key store the orders once."""
# ruff: noqa: F811 - the imported fixtures are used as test arguments
from __future__ import annotations

import asyncio
import uuid
from http import HTTPStatus

import pytest
from ofo_app import request_key
from ofo_app.routes.paper import PaperOrdersIn
from test_order_request_key_durable_fd3 import BODY, USER, strategy  # noqa: F401 - fixtures
from test_order_request_key_r2_fd2 import _body, _count, _Down, _post, _prices, _use, keys  # noqa: F401 - fixtures
from test_paper_triggers_routes import _setup, db, notified  # noqa: F401 - fixtures

TWO_ORDERS = 2


async def _hint(keys, stored, body, key):
    sent = PaperOrdersIn.model_validate(body).model_dump(mode="json", exclude={"client_request_id"})
    assert await keys.claim(request_key.scoped(stored.user_ref, key), request_key.pending(stored.id, sent)) is None


async def test_core_a_pending_redis_hint_with_no_durable_row_lets_the_repeat_place_once(db, notified, keys):
    app, stored, *_ = await _setup(db)
    _use(app, keys)
    _, orders = _prices(stored)
    key = uuid.uuid4()
    body = _body(orders, key)
    await _hint(keys, stored, body, key)  # the first press crashed: Redis says pending, the table has no row
    first = await _post(app, stored, body)
    assert first.status_code == HTTPStatus.CREATED, first.text[:300]
    assert await _count(db, stored) == TWO_ORDERS
    again = await _post(app, stored, body)  # the durable row now decides: the first result, nothing more stored
    assert again.status_code == HTTPStatus.CREATED, again.text[:300]
    assert await _count(db, stored) == TWO_ORDERS


async def test_a_redis_that_is_down_no_longer_refuses_and_the_orders_store_once(db, notified):
    app, stored, *_ = await _setup(db)
    _use(app, _Down())
    _, orders = _prices(stored)
    body = _body(orders, uuid.uuid4())
    first = await _post(app, stored, body)
    assert first.status_code == HTTPStatus.CREATED, first.text[:300]
    again = await _post(app, stored, body)
    assert again.status_code == HTTPStatus.CREATED, again.text[:300]
    assert await _count(db, stored) == TWO_ORDERS


async def test_begin_still_refuses_another_strategy_and_another_body_but_not_a_pending_hint(keys):
    key = uuid.uuid4()
    await keys.claim(request_key.scoped(USER, key), request_key.pending(1, BODY))
    assert await request_key.begin(keys, USER, key, 1, BODY) is None  # same strategy, same body: a hint only
    with pytest.raises(Exception, match="request_key_other_strategy"):
        await request_key.begin(keys, USER, key, 2, BODY)
    with pytest.raises(Exception, match="request_key_different_body"):
        await request_key.begin(keys, USER, key, 1, {"orders": []})


async def test_two_presses_with_one_key_and_a_pending_hint_store_the_orders_once(
        app_engine, admin_engine, strategy, keys):
    key = uuid.uuid4()
    await keys.claim(request_key.scoped(USER, key), request_key.pending(strategy, BODY))
    assert await request_key.begin(keys, USER, key, strategy, BODY) is None  # both presses pass the hint
    async with app_engine.connect() as one, app_engine.connect() as two:
        t1, t2 = await one.begin(), await two.begin()
        await request_key.claim_in_transaction(one, USER, key, strategy, BODY, "paper")
        second = asyncio.ensure_future(request_key.claim_in_transaction(two, USER, key, strategy, BODY, "paper"))
        await asyncio.sleep(0.5)
        assert not second.done()
        await request_key.finish_in_transaction(one, USER, key, {"cancelled_stops": []})
        await t1.commit()
        with pytest.raises(request_key.Repeated):
            await second  # the second press places nothing
        await t2.rollback()
