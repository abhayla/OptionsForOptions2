"""Gap 8 (27 Nov live test day, Lane Q2): "Add to Paper" with 5,000 lots on one leg was accepted on the PC (14:28).

Decisions the coordinator relayed at 17:00 IST (ADR-330 (50), (51), (52), (58): not yet in this tree, so each test
that needs them is a STRICT xfail naming them): the lots limit counts the TOTAL the leg will hold, not only this order
(50); the default is 100 lots per leg (52); a paper exit above the freeze quantity is refused (51); paper differs
from real only by its tag (58). Before them the spec gave ``limits.max_lots`` (REQ-167 AC-5, default 10,000) as the one
limit and said nothing about freeze for paper orders. Today the paper-order door never calls ``check_lots`` and has no
freeze check.
Real PostgreSQL, every test rolled back. Run with ``--runxfail`` to see each red assertion.
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
LIMIT_LOTS = 100  # ADR-330 (52)
FREEZE_UNITS = 1800  # NIFTY, Zerodha bulletin of 1 Apr 2026 (ofo.execution.sequence.DEFAULT_FREEZE_UNITS cites it)
DECISION = "ADR-330 (50)/(51)/(52) is not in this tree and no branch applies it"


@pytest.fixture
async def db(app_engine):
    async with app_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


async def _stored(db, strategy_id: int) -> int:
    return int((await db.execute(text("SELECT count(*) FROM public.paper_orders WHERE strategy_id = :i"),
                                 {"i": strategy_id})).scalar_one())


async def _post(db, lots: int, *, kind: str = "open", side: str = "SELL", booked=None):
    """POST one order of ``lots`` lots to the first contract of a fresh strategy (or of ``booked``, a prior call's)."""
    if booked:
        app, stored = booked
    else:
        made = await _setup(db)
        app, stored = made[0], made[1]
    leg = {"contract_id": stored.saved.contract_ids[0], "side": side, "quantity": lots * LOT,
           "price": str(Decimal("50.00")), "kind": kind}
    before = await _stored(db, stored.id)
    async with _client(app) as c:
        reply = await c.post(f"/paper/strategies/{stored.id}/orders", json={"orders": [leg]})
    return reply, await _stored(db, stored.id) - before, (app, stored)


def _refused(reply, stored_rows: int) -> bool:
    return HTTPStatus.BAD_REQUEST <= reply.status_code < HTTPStatus.INTERNAL_SERVER_ERROR and stored_rows == 0


@pytest.mark.xfail(strict=True, reason=f"the registry default is 10,000 lots today; {DECISION}")
def test_the_default_lots_limit_per_leg_is_100():
    assert calc.max_lots(dict(defaults())) == LIMIT_LOTS


async def test_100_lots_on_one_leg_is_accepted(db):
    reply, rows, _ = await _post(db, LIMIT_LOTS)
    assert reply.status_code == HTTPStatus.CREATED, reply.text
    assert rows == 1


@pytest.mark.xfail(strict=True, reason=f"the paper door never calls check_lots; {DECISION}")
@pytest.mark.parametrize("lots", [LIMIT_LOTS + 1, 5_000])
async def test_a_leg_above_the_limit_is_refused_and_stores_nothing(db, lots):  # 5,000 = the PC case of 14:28
    reply, rows, _ = await _post(db, lots)
    assert _refused(reply, rows), (reply.status_code, rows)


@pytest.mark.xfail(strict=True, reason=f"the limit counts only this order today; {DECISION}")
async def test_the_limit_counts_the_total_the_leg_will_hold(db):
    first, rows, booked = await _post(db, 60)
    assert first.status_code == HTTPStatus.CREATED and rows == 1, first.text
    ok, rows_ok, _ = await _post(db, 40, kind="add", booked=booked)  # 60 + 40 = 100: inside
    assert ok.status_code == HTTPStatus.CREATED and rows_ok == 1, ok.text
    over, rows_over, _ = await _post(db, 1, kind="add", booked=booked)  # 101 in total: refused
    assert _refused(over, rows_over), (over.status_code, rows_over)


@pytest.mark.xfail(strict=True, reason=f"the paper door has no freeze check; {DECISION}")
async def test_a_paper_exit_above_the_freeze_quantity_is_refused(db):
    lots = FREEZE_UNITS // LOT + 3  # 30 lots = 1,950 units, above the 1,800 freeze
    opened, rows, booked = await _post(db, lots)
    assert opened.status_code == HTTPStatus.CREATED and rows == 1, opened.text  # an entry may be larger (slices)
    reply, rows_exit, _ = await _post(db, lots, kind="exit", side="BUY", booked=booked)
    assert _refused(reply, rows_exit), (reply.status_code, rows_exit)
