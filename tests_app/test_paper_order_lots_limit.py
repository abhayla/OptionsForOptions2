"""Gap 8, 27 Nov live test day (Lane Q2): "Add to Paper" with 5,000 lots on one leg was accepted on the PC (14:28).

What the spec says (searched: lots, quantity limit, freeze quantity, max lots):
 - REQ-167 AC-5 (``ofo.settings.calc.max_lots``): ONE number caps the lots of one leg, the setting
   ``limits.max_lots`` (default 10,000); "the one check every lots-accepting route passes" (``outcome.check_lots``).
 - Freeze quantity (ADR-081, ``ofo.execution.sequence``) is a REAL-order rule: a basket is sliced under NSE's freeze
   (NIFTY 1,800 units = 27 lots of 65). Nothing in the spec refuses a PAPER order for exceeding it: spec silent.
So 5,000 lots on one paper leg is WITHIN the spec's limit and its acceptance is no defect; 10,001 is above it. Whether
the paper-order door is a "lots-accepting route" of REQ-167 AC-5 is a reading: it takes units (lots x lot size) and
never calls ``check_lots`` today. The test states that reading, as a strict xfail, for the coordinator to decide.
Real PostgreSQL, every test rolled back.
"""
from __future__ import annotations

from decimal import Decimal
from http import HTTPStatus

import pytest
from ofo.settings import calc, defaults
from sqlalchemy import text
from test_strategy_store import _client
from test_strategy_tracking import _setup

LOT = 65  # NIFTY, the scenario's lot size
SPEC_MAX_LOTS = 10_000


@pytest.fixture
async def db(app_engine):
    async with app_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


def test_the_one_lots_limit_of_the_spec_is_10000_lots_per_leg():
    assert calc.max_lots(dict(defaults())) == SPEC_MAX_LOTS


async def _count(db, strategy_id: int) -> int:
    return int((await db.execute(text("SELECT count(*) FROM public.paper_orders WHERE strategy_id = :i"),
                                 {"i": strategy_id})).scalar_one())


async def _add(db, lots: int):
    app, stored, *_ = await _setup(db)
    leg = {"contract_id": stored.saved.contract_ids[0], "side": "SELL", "quantity": lots * LOT,
           "price": str(Decimal("50.00")), "kind": "open"}
    before = await _count(db, stored.id)
    async with _client(app) as c:
        reply = await c.post(f"/paper/strategies/{stored.id}/orders", json={"orders": [leg]})
    return reply, await _count(db, stored.id) - before


async def test_5000_lots_on_one_leg_is_inside_the_spec_limit_and_is_accepted(db):
    reply, stored = await _add(db, 5_000)
    assert reply.status_code == HTTPStatus.CREATED, reply.text
    assert stored == 1


@pytest.mark.xfail(strict=True, reason="paper orders never call check_lots (REQ-167 AC-5 reading); no branch fixes it: "
                                       "owner/coordinator decides whether the paper door is a lots-accepting route")
async def test_a_leg_above_the_spec_limit_is_refused_and_stores_nothing(db):
    reply, stored = await _add(db, SPEC_MAX_LOTS + 1)
    assert HTTPStatus.BAD_REQUEST <= reply.status_code < HTTPStatus.INTERNAL_SERVER_ERROR, reply.text
    assert stored == 0
