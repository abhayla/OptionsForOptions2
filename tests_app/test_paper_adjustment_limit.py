"""GC-ICGUIDE g10 (audit C9; ADR-255; REQ-109 AC-1): the plan's most adjustments is enforced when paper orders are
SAVED, not only when approaches are offered. Real PostgreSQL, every test rolled back.

Adjustment 1 and 2 are seeded at earlier times (one exit each: a partial or full exit counts, ADR-255); the third is
posted through the route. The route's clock is fixed, so it differs from the seeded times.
"""
from __future__ import annotations

import copy
import dataclasses
import datetime
from decimal import Decimal
from http import HTTPStatus

import pytest
from ofo_app import paper_limit, paper_store, playbook_store
from sqlalchemy import text
from test_strategy_store import _client
from test_strategy_tracking import _setup

D = Decimal
T0 = datetime.datetime(2026, 10, 1, 4, 0, tzinfo=datetime.UTC)
ENTRY = [("SELL", "100.00"), ("BUY", "80.00"), ("SELL", "60.00"), ("BUY", "40.00")]


@pytest.fixture
async def db(app_engine):
    async with app_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


def _new(cid: int, side: str, price: str, kind: str, at: datetime.datetime) -> paper_store.NewOrder:
    return paper_store.NewOrder(cid, side, 65, D(price), kind, at)


def _post(cid: int, side: str, price: str = "50.00") -> dict:
    return {"contract_id": cid, "side": side, "quantity": 65, "price": price, "kind": "exit"}


async def _book(db, *, max_adjustments: int | None, adjustments: int = 2):
    """A condor with its entry and ``adjustments`` one-leg exits already stored, and a plan with the given maximum."""
    app, stored, *_ = await _setup(db)
    ids = stored.saved.contract_ids
    await paper_store.place(db, stored.user_ref, stored.id, [_new(ids[i], s, p, "open", T0)
                                                             for i, (s, p) in enumerate(ENTRY)])
    for n in range(adjustments):
        side = "BUY" if ENTRY[n][0] == "SELL" else "SELL"
        await paper_store.place(db, stored.user_ref, stored.id,
                                [_new(ids[n], side, "50.00", "exit", T0 + datetime.timedelta(hours=n + 1))])
    if max_adjustments is not None:
        system = await playbook_store.active_for(db, stored.user_ref, "ic")
        body = copy.deepcopy(system.body)
        body["guards"]["max_adjustments"] = max_adjustments
        await playbook_store.accept_plan(db, stored.user_ref, stored.id, system.id, body)
    return app, stored, ids


async def _count(db, strategy_id: int) -> int:
    return int((await db.execute(text("SELECT count(*) FROM public.paper_orders WHERE strategy_id = :i"),
                                 {"i": strategy_id})).scalar_one())


async def test_a_third_adjustment_is_refused_when_the_plans_maximum_is_two(db):
    app, stored, ids = await _book(db, max_adjustments=2)
    before = await _count(db, stored.id)
    async with _client(app) as c:
        reply = await c.post(f"/paper/strategies/{stored.id}/orders", json={"orders": [_post(ids[2], "BUY")]})
    assert reply.status_code == HTTPStatus.UNPROCESSABLE_ENTITY, reply.text
    assert "at most 2 adjustments" in reply.text
    assert await _count(db, stored.id) == before


async def test_a_second_adjustment_within_the_maximum_is_accepted(db):
    app, stored, ids = await _book(db, max_adjustments=2, adjustments=1)
    async with _client(app) as c:
        reply = await c.post(f"/paper/strategies/{stored.id}/orders", json={"orders": [_post(ids[1], "SELL")]})
    assert reply.status_code == HTTPStatus.CREATED, reply.text


async def test_a_full_exit_of_the_whole_strategy_is_always_allowed(db):
    app, stored, ids = await _book(db, max_adjustments=2)
    async with _client(app) as c:
        reply = await c.post(f"/paper/strategies/{stored.id}/orders",
                             json={"orders": [_post(ids[2], "BUY"), _post(ids[3], "SELL")]})
    assert reply.status_code == HTTPStatus.CREATED, reply.text


async def test_the_entry_batch_is_not_an_adjustment(db):
    app, stored, *_ = await _setup(db)
    ids = stored.saved.contract_ids
    body = {"orders": [{"contract_id": ids[i], "side": s, "quantity": 65, "price": p, "kind": "open"}
                       for i, (s, p) in enumerate(ENTRY)]}
    system = await playbook_store.active_for(db, stored.user_ref, "ic")
    plan = copy.deepcopy(system.body)
    plan["guards"]["max_adjustments"] = 0
    await playbook_store.accept_plan(db, stored.user_ref, stored.id, system.id, plan)
    async with _client(app) as c:
        reply = await c.post(f"/paper/strategies/{stored.id}/orders", json=body)
    assert reply.status_code == HTTPStatus.CREATED, reply.text


async def test_a_plan_that_cannot_be_read_refuses_the_adjustment_by_name(db, monkeypatch):
    app, stored, ids = await _book(db, max_adjustments=2)

    async def broken(*_a, **_k):
        raise RuntimeError("store down")
    monkeypatch.setattr(paper_limit, "_plan_body", broken)
    before = await _count(db, stored.id)
    async with _client(app) as c:
        reply = await c.post(f"/paper/strategies/{stored.id}/orders", json={"orders": [_post(ids[2], "BUY")]})
    assert reply.status_code == HTTPStatus.UNPROCESSABLE_ENTITY, reply.text
    assert "could not be read" in reply.text
    assert await _count(db, stored.id) == before


async def test_no_plan_uses_the_playbook_default_the_plan_sheet_prefills(db, monkeypatch):
    """No plan of its own: the type's active playbook gives the maximum (lowered to 2 here); the third is refused."""
    app, stored, ids = await _book(db, max_adjustments=None)
    system = await playbook_store.active_for(db, stored.user_ref, "ic")
    body = copy.deepcopy(system.body)
    body["guards"]["max_adjustments"] = 2

    async def default_body(*_a, **_k):
        return body
    monkeypatch.setattr(paper_limit, "_plan_body", default_body)
    async with _client(app) as c:
        reply = await c.post(f"/paper/strategies/{stored.id}/orders", json={"orders": [_post(ids[2], "BUY")]})
    assert reply.status_code == HTTPStatus.UNPROCESSABLE_ENTITY, reply.text
    assert "at most 2 adjustments" in reply.text


async def test_a_plan_with_no_maximum_does_not_limit(db, monkeypatch):
    app, stored, ids = await _book(db, max_adjustments=None)

    async def no_max(*_a, **_k):
        return {"guards": {}}
    monkeypatch.setattr(paper_limit, "_plan_body", no_max)
    async with _client(app) as c:
        reply = await c.post(f"/paper/strategies/{stored.id}/orders", json={"orders": [_post(ids[2], "BUY")]})
    assert reply.status_code == HTTPStatus.CREATED, reply.text


@pytest.fixture
def only_the_condor_is_limited(monkeypatch):
    """No plan of its own: the active playbook of the position's type gives the maximum. The system condor playbook
    keeps its maximum (2); every other type gets 99, so a wrong type read after the batch shows as an allowed save."""
    real = playbook_store.active_for

    async def active_for(conn, user_ref, strategy_type):
        found = await real(conn, user_ref, strategy_type)
        if strategy_type == "ic":
            return found
        guards = {**found.body["guards"], "max_adjustments": 99}
        return dataclasses.replace(found, body={**found.body, "guards": guards})
    monkeypatch.setattr(playbook_store, "active_for", active_for)


async def _condor(db, adjustments: int):
    """A four-leg condor with NO plan of its own that has used ``adjustments``: each takes the first leg out and puts
    it back in one batch, so the four legs stay open."""
    app, stored, *_ = await _setup(db)
    ids = stored.saved.contract_ids
    await paper_store.place(db, stored.user_ref, stored.id, [_new(ids[i], s, p, "open", T0)
                                                             for i, (s, p) in enumerate(ENTRY)])
    for n in range(adjustments):
        at = T0 + datetime.timedelta(hours=n + 1)
        await paper_store.place(db, stored.user_ref, stored.id, [_new(ids[0], "BUY", "50.00", "exit", at),
                                                                 _new(ids[0], "SELL", "50.00", "open", at)])
    return app, stored, ids


async def test_the_limit_judges_the_condor_as_it_was_before_the_batch(db, only_the_condor_is_limited):
    """The batch takes one whole spread out; judged AFTER it the position is a two-leg spread (another type's limit).
    Judged before it, the position is the condor that has used its two adjustments, so the third is refused."""
    app, stored, ids = await _condor(db, adjustments=2)
    before = await _count(db, stored.id)
    async with _client(app) as c:
        reply = await c.post(f"/paper/strategies/{stored.id}/orders",
                             json={"orders": [_post(ids[0], "BUY"), _post(ids[1], "SELL")]})
    assert reply.status_code == HTTPStatus.UNPROCESSABLE_ENTITY, reply.text
    assert "at most 2 adjustments" in reply.text
    assert await _count(db, stored.id) == before


async def test_the_tracking_exit_judges_the_condor_as_it_was_before_the_batch(db, only_the_condor_is_limited):
    app, stored, _ids = await _condor(db, adjustments=2)
    before = await _count(db, stored.id)
    async with _client(app) as c:
        reply = await c.post(f"/strategies/{stored.id}/tracking/exit", json={"legs": [0, 1]})
    assert reply.status_code == HTTPStatus.UNPROCESSABLE_ENTITY, reply.text
    assert "at most 2 adjustments" in reply.text
    assert await _count(db, stored.id) == before


async def test_the_second_adjustment_of_a_condor_is_not_counted_twice(db, only_the_condor_is_limited):
    app, stored, ids = await _condor(db, adjustments=1)
    async with _client(app) as c:
        reply = await c.post(f"/paper/strategies/{stored.id}/orders",
                             json={"orders": [_post(ids[0], "BUY"), _post(ids[1], "SELL")]})
    assert reply.status_code == HTTPStatus.CREATED, reply.text
