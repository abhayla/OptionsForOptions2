"""GC-ICLIVE D-28 (ADR-299, owner 2026-11-13): ONE status word per strategy on every route.

Real 23 Nov case: condors 155, 156, 157, 159, 160, 161 had open practice legs; /api/strategies and /strategies/{id}
said status "draft" while /paper/strategies said state "LIVE". Here the saved iron condor of test_strategy_store gets
its four practice orders (the 23 Nov shape) and every route that names a strategy must carry the same word:
"Draft" before any order, "Running" with open legs, "Completed" once the row is closed (alembic 0049).
"""
from __future__ import annotations

from http import HTTPStatus

import pytest
from sqlalchemy import text
from test_strategy_store import _client
from test_strategy_tracking import ENTRY_PRICES, _paper_body, _setup


@pytest.fixture
async def db(app_engine):
    async with app_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


async def _get(app, path):
    async with _client(app) as c:
        reply = await c.get(path)
    assert reply.status_code == HTTPStatus.OK, reply.text
    return reply.json()


async def _words(app, sid, *, paper: bool) -> dict[str, str | None]:
    out = {"book": (await _get(app, f"/strategies/{sid}")).get("status_word"),
           "list": next(s for s in (await _get(app, "/strategies"))["strategies"] if s["id"] == sid).get("status_word")}
    if paper:
        out["paper_book"] = (await _get(app, f"/paper/strategies/{sid}")).get("status_word")
        out["paper_list"] = next(s for s in (await _get(app, "/paper/strategies"))["strategies"]
                                 if s["strategy_id"] == sid).get("status_word")
    return out


async def test_one_word_on_every_route_through_the_strategy_life(db):
    app, stored, *_ = await _setup(db)
    assert await _words(app, stored.id, paper=False) == {"book": "Draft", "list": "Draft"}
    async with _client(app) as c:
        placed = await c.post(f"/paper/strategies/{stored.id}/orders", json=_paper_body(stored, ENTRY_PRICES))
    assert placed.status_code == HTTPStatus.CREATED, placed.text
    assert placed.json().get("status_word") == "Running"
    running = {"book": "Running", "list": "Running", "paper_book": "Running", "paper_list": "Running"}
    assert await _words(app, stored.id, paper=True) == running
    await db.execute(text("UPDATE public.strategies SET status = 'closed' WHERE id = :i"), {"i": stored.id})
    assert set((await _words(app, stored.id, paper=True)).values()) == {"Completed"}
