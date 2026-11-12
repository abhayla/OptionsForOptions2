"""GC-TRACK1 k08 (ADR-283 (1), ADR-292 (3); findings entry-facts-skipped-when-the-api-holds-no-index-quote,
rule-entry-baseline-taken-at-first-check): a saved paper basket always stores its rule starting point, even when the
API process holds no quote for the index (bus mode, no page open); otherwise the save is refused by name.

Core proof (DB, fresh database): the index quote appears only after the route SUBSCRIBES it on the fan-out (the way the
live feed behaves); before the fix: 201 and 0 rows in strategy_basket_facts, after: 201 and one row with the spot.
Answer states of the index read at save: held already / first quote within the wait / never quoted / feed not
connected / quote not a positive price / no feed at all.
"""
from __future__ import annotations

import dataclasses
from decimal import Decimal as D
from http import HTTPStatus
from types import SimpleNamespace

import pytest
from ofo_app import adjustment_readers
from ofo_app.routes.paper import get_live_feed
from sqlalchemy import text
from test_strategy_store import _client
from test_strategy_tracking import _paper_body, _setup

INDEX_ID = "NSE:9999"
_FACTS = text("SELECT spot FROM public.strategy_basket_facts WHERE strategy_id = :i")
_ORDERS = text("SELECT count(*) FROM public.paper_orders WHERE strategy_id = :i")


@pytest.fixture
async def db(app_engine):
    async with app_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


class _Fanout:
    """The shared fan-out: the index quote appears only once somebody subscribes it."""

    def __init__(self, on_subscribe):
        self.on_subscribe = on_subscribe
        self.held: list[list[str]] = []
        self.released = 0

    def subscribe(self, _listener, ids, **_kw):
        self.held.append(list(ids))
        self.on_subscribe(list(ids))
        return len(self.held)

    def unsubscribe(self, _handle):
        self.released += 1


def _unheld_index(provider, *, quote_after_subscribe, spot=None):
    """The provider answers no index quote until the index id is subscribed (then ``spot``, or a bad one)."""
    seen = provider.underlying_quote("NIFTY")
    state = {"held": False}
    quote = seen if spot is None else dataclasses.replace(seen, ltp=spot)
    provider.index_id = lambda _u: INDEX_ID
    provider.underlying_quote = lambda _u: quote if state["held"] else None

    def on_subscribe(ids):
        if INDEX_ID in ids and quote_after_subscribe:
            state["held"] = True
    return SimpleNamespace(fanout=_Fanout(on_subscribe), ctx=None), quote


async def _save(app, stored):
    async with _client(app) as c:
        return await c.post(f"/paper/strategies/{stored.id}/orders", json=_paper_body(stored))


async def _stored(db, sid):
    return (await db.execute(_ORDERS, {"i": sid})).scalar_one(), (await db.execute(_FACTS, {"i": sid})).all()


async def test_nobody_holds_the_index_the_save_holds_it_and_stores_the_spot(db, monkeypatch):
    app, stored, provider, *_ = await _setup(db)
    feed, quote = _unheld_index(provider, quote_after_subscribe=True)
    app.dependency_overrides[get_live_feed] = lambda: feed
    monkeypatch.setattr(adjustment_readers, "LEG_POLL_S", 0.01)
    reply = await _save(app, stored)
    assert reply.status_code == HTTPStatus.CREATED, reply.text
    orders, rows = await _stored(db, stored.id)
    assert orders == 4  # noqa: PLR2004
    assert [r.spot for r in rows] == [quote.ltp]
    assert [INDEX_ID] in feed.fanout.held
    assert feed.fanout.released == len(feed.fanout.held)  # every hold released


async def test_index_never_quoted_within_the_wait_refuses_and_stores_nothing(db, monkeypatch):
    app, stored, provider, *_ = await _setup(db)
    feed, _ = _unheld_index(provider, quote_after_subscribe=False)
    app.dependency_overrides[get_live_feed] = lambda: feed
    monkeypatch.setattr(adjustment_readers, "LEG_WAIT_S", 0.1)
    monkeypatch.setattr(adjustment_readers, "LEG_POLL_S", 0.01)
    reply = await _save(app, stored)
    assert reply.status_code == HTTPStatus.CONFLICT, reply.text
    assert "live index price is not available" in reply.text
    assert await _stored(db, stored.id) == (0, [])


async def test_no_feed_and_no_index_quote_refuses_and_stores_nothing(db):
    app, stored, provider, *_ = await _setup(db)
    _unheld_index(provider, quote_after_subscribe=True)  # feed stays None: nothing can hold it
    reply = await _save(app, stored)
    assert reply.status_code == HTTPStatus.CONFLICT, reply.text
    assert await _stored(db, stored.id) == (0, [])


@pytest.mark.parametrize("bad", [D("0")])  # a negative price cannot even be built as a quote
async def test_a_non_positive_index_price_refuses_and_stores_nothing(db, monkeypatch, bad):
    app, stored, provider, *_ = await _setup(db)
    feed, _ = _unheld_index(provider, quote_after_subscribe=True, spot=bad)
    app.dependency_overrides[get_live_feed] = lambda: feed
    monkeypatch.setattr(adjustment_readers, "LEG_WAIT_S", 0.1)
    monkeypatch.setattr(adjustment_readers, "LEG_POLL_S", 0.01)
    reply = await _save(app, stored)
    assert reply.status_code == HTTPStatus.CONFLICT, reply.text
    assert await _stored(db, stored.id) == (0, [])


async def test_a_disconnected_provider_refuses_and_stores_nothing(db):
    app, stored, provider, *_ = await _setup(db)
    feed, _ = _unheld_index(provider, quote_after_subscribe=True)
    provider.status = lambda: SimpleNamespace(connected=False, session_ended=False)
    app.dependency_overrides[get_live_feed] = lambda: feed
    reply = await _save(app, stored)
    assert reply.status_code in (HTTPStatus.CONFLICT, HTTPStatus.UNPROCESSABLE_ENTITY), reply.text
    assert await _stored(db, stored.id) == (0, [])
