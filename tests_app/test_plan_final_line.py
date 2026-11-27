"""ADR-330 (57): GET /paper/strategies/{id} serves ``plan_final_text`` for a fully closed trade (and only then): what
the plan was and how the trade ended, built by the server (REAL case 27 Nov: settled trade 173 showed a Plan watch box
and "Add a leg to start one"). The book is the app's iron condor (tests_app/test_leg_stop_risk.py), 65 units a leg,
closed at 11:23 IST (05:53 UTC). Replay market, real PostgreSQL, every test rolled back."""
from __future__ import annotations

import copy
import datetime
from decimal import Decimal
from http import HTTPStatus

import pytest
from ofo_app import paper_store, playbook_store
from ofo_app.routes.outcome import get_answer_clock
from test_leg_stop_risk import SIDES, _book
from test_strategy_store import _client

D = Decimal
CLOSE_AT = datetime.datetime(2026, 11, 25, 5, 53, tzinfo=datetime.UTC)  # 11:23 IST on the day the book is read
READ_AT = datetime.datetime(2026, 11, 25, 9, 0, tzinfo=datetime.UTC)  # 14:30 IST, 25 Nov


@pytest.fixture
async def db(app_engine):
    async with app_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


async def _close_all(db, stored, ids, *, kind="exit", at=CLOSE_AT, reason=None):  # noqa: PLR0913
    await paper_store.place(db, stored.user_ref, stored.id, [
        paper_store.NewOrder(ids[i], "BUY" if SIDES[i] == "SELL" else "SELL", 65, D("10"), kind, at, reason=reason)
        for i in range(4)])


async def _plan(db, stored, stop=None, target=None):
    system = await playbook_store.active_for(db, stored.user_ref, "ic")
    body = copy.deepcopy(system.body)
    guards = body.setdefault("guards", {})
    for key, value in (("loss_stop_rupees", stop), ("profit_target_rupees", target)):
        if value is not None:
            guards[key] = value
    mine = await playbook_store.duplicate(db, stored.user_ref, system.id, f"Plan final {stored.id}")
    saved = await playbook_store.save_in_place(db, stored.user_ref, mine.id, body, mine.version)
    await playbook_store.accept_plan(db, stored.user_ref, stored.id, saved.id)


async def _get(app, strategy_id):
    app.dependency_overrides[get_answer_clock] = lambda: lambda: READ_AT
    async with _client(app) as c:
        reply = await c.get(f"/paper/strategies/{strategy_id}")
    assert reply.status_code == HTTPStatus.OK, reply.text
    return reply.json()


async def test_an_exit_with_a_plan_reads_the_owner_example(db):
    app, stored, ids = await _book(db)
    await _plan(db, stored, stop="300", target="800")
    await _close_all(db, stored, ids)
    body = await _get(app, stored.id)
    assert body["plan_final_text"] == "Plan: stop Rs 300, target Rs 800. Closed by your exit at 11:23."


async def test_an_open_book_has_no_final_line(db):
    app, stored, _ = await _book(db)
    await _plan(db, stored, stop="300", target="800")
    assert (await _get(app, stored.id))["plan_final_text"] is None


async def test_a_trade_with_no_plan_says_so(db):
    app, stored, ids = await _book(db)
    await _close_all(db, stored, ids)
    got = (await _get(app, stored.id))["plan_final_text"]
    assert got == "No plan was set for this trade. Closed by your exit at 11:23."


async def test_an_expiry_settlement_is_named_and_a_stop_is_named(db):
    app, stored, ids = await _book(db)
    await _plan(db, stored, stop="300", target="800")
    await _close_all(db, stored, ids, kind="settle", at=datetime.datetime(2026, 11, 25, 10, 0, tzinfo=datetime.UTC),
                     reason=None)
    assert (await _get(app, stored.id))["plan_final_text"].endswith("Closed by expiry settlement at 15:30.")


async def test_a_trade_closed_on_an_earlier_day_names_the_day(db):
    app, stored, ids = await _book(db)
    await _close_all(db, stored, ids, at=datetime.datetime(2026, 11, 24, 5, 53, tzinfo=datetime.UTC))
    assert (await _get(app, stored.id))["plan_final_text"].endswith("Closed by your exit on 24 Nov at 11:23.")


async def test_a_percent_plan_whose_rupees_cannot_be_worked_out_prints_no_number(db):
    """The system plan sets its levels as percents; with no stop base stored and no max profit the rupee figures are
    absent, and the line says "not available" for them (never "no stop", never an invented figure)."""
    app, stored, ids = await _book(db)
    await _plan(db, stored)
    await _close_all(db, stored, ids)
    got = (await _get(app, stored.id))["plan_final_text"]
    assert got == "Plan: stop not available, target not available. Closed by your exit at 11:23."
