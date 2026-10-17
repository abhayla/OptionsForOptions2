"""W-107 (REQ-060 AC-6, AC-4, AC-7; ADR-105): Execute refuses while the strategy's own CLOSED plan drifted at Zerodha.

Real inputs (tests/fixtures/kite_replies/): ``orders-122104.json`` (OFS1V1L0 BUY 65 COMPLETE, filled 65),
``trades-122104.json``, ``positions-122104.json`` (+65 held). The 2026-10-16 defect: the owner pressed "Check with
Zerodha" before Kite's book showed the order, plan 1 closed ``nothing_placed``, the order then filled, and a second
ENTRY was allowed (130 long). Every case runs the real route on the database inside a rolled-back transaction.

This covers the drift half of AC-6 only: Q222's "block stays until a recorded resolution" is not built here.
"""
from __future__ import annotations

import copy
import json
from contextlib import asynccontextmanager
from decimal import Decimal as D

import pytest
from ofo_app.execute_replay import AT, REPLIES, RecordedKite
from test_execute_route import (
    RATES,
    _post,
    _Quotes,
    _refused_with,
    _session_for,
    _strategy_one,
)

HTTP_OK, HTTP_CONFLICT, PLANS_AFTER_EXIT = 200, 409, 2
TAG = "OFS1V1L0"
RECONCILE_PHRASE = "do not match what we recorded"


def _real_rows() -> list[dict]:
    reply = json.loads((REPLIES / "orders-122104.json").read_text(encoding="utf-8"), parse_float=D)
    return reply["data"]


def _book(**changes: object) -> list[dict]:
    return [{**_real_rows()[0], **changes}]


def _replay(orders: list[dict], held: int = 65) -> RecordedKite:
    replay = RecordedKite(funds="1003", basket_total="354.25", orders=None, positions="positions-122104",
                          trades="trades-122104")
    replay.order_rows = orders
    positions = json.loads((REPLIES / "positions-122104.json").read_text(encoding="utf-8"), parse_float=D)
    data = copy.deepcopy(positions.get("data", positions))
    data["net"][0]["quantity"] = held
    replay.position_rows = data["net"]
    return replay


@asynccontextmanager
async def _world(app_engine, admin_engine, monkeypatch, *, close: str, filled: dict | None):
    """Strategy 1 with plan 1 (the real ENTRY BUY 65 OFS1V1L0) stored through the route, then closed as given."""
    from ofo_app import execution_plan_store as plans  # noqa: PLC0415
    from ofo_app.routes import execute as route  # noqa: PLC0415
    from test_strategy_followups import _ConnMaker  # noqa: PLC0415
    from test_strategy_store import _app, _user  # noqa: PLC0415

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("TEST_CATALOGUE_DATE", "2026-10-16")
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            user = _user()
            sid = await _strategy_one(conn, user, app_engine.url.username)
            app = _app(_ConnMaker(conn), user)
            app.dependency_overrides[route.get_quote_reader] = _Quotes
            app.dependency_overrides[route.get_execute_clock] = lambda: (lambda: AT)
            app.dependency_overrides[route.load_charge_rates] = lambda: RATES
            first = RecordedKite(funds="1003", basket_total="354.25", orders=None, positions="positions-151006")
            app.dependency_overrides[route.get_kite_session] = lambda: _session_for(first)
            assert (await _post(app, sid, "ENTRY")).status_code == HTTP_OK
            await plans.close_plan(conn, user, sid, 1, reason=close, filled=filled)

            def use(replay: RecordedKite) -> None:
                app.dependency_overrides[route.get_kite_session] = lambda: _session_for(replay)

            async def stored() -> int:
                return len(await plans.plans_for(conn, user, sid))

            yield app, sid, use, stored
        finally:
            await trans.rollback()


@pytest.mark.usefixtures("app_engine")
async def test_ac6_nothing_placed_plan_whose_order_later_filled_blocks_entry_and_exit(app_engine, admin_engine,
                                                                                      monkeypatch):
    """The real 2026-10-16 case: plan 1 closed ``nothing_placed`` (0 stored) while Zerodha's book shows OFS1V1L0
    COMPLETE 65 and 65 held there. ENTRY (which main allowed: 130 long) and EXIT are refused; nothing is stored."""
    async with _world(app_engine, admin_engine, monkeypatch, close="nothing_placed", filled=None) as (
            app, sid, use, stored):
        use(_replay(_real_rows()))
        await _refused_with(app, sid, "ENTRY", RECONCILE_PHRASE)
        resp = await _post(app, sid, "EXIT")
        assert resp.status_code == HTTP_CONFLICT, resp.text
        assert await stored() == 1  # nothing stored, no plan number consumed


@pytest.mark.usefixtures("app_engine")
async def test_ac6_a_plan_closed_filled_65_that_agrees_with_the_book_is_not_refused_for_drift(app_engine,
                                                                                              admin_engine,
                                                                                              monkeypatch):
    """The same book against plan 1 closed ``filled`` 65: stored fill = book fill, positions agree -> EXIT works."""
    async with _world(app_engine, admin_engine, monkeypatch, close="filled", filled={TAG: 65}) as (
            app, sid, use, stored):
        use(_replay(_real_rows()))
        resp = await _post(app, sid, "EXIT")
        assert resp.status_code == HTTP_OK, resp.text
        assert await stored() == PLANS_AFTER_EXIT


@pytest.mark.usefixtures("app_engine")
async def test_ac6_an_order_still_working_on_a_closed_plan_is_refused(app_engine, admin_engine, monkeypatch):
    """Still-working tag on a closed plan. The order-book floor (``gate_dependencies_unsatisfied``) already refuses an
    open order before the drift check; this pins that the press stays refused and stores nothing."""
    async with _world(app_engine, admin_engine, monkeypatch, close="filled", filled={TAG: 65}) as (
            app, sid, use, stored):
        use(_replay(_book(status="OPEN", filled_quantity=0)))
        for action in ("ENTRY", "EXIT"):
            assert (await _post(app, sid, action)).status_code == HTTP_CONFLICT
        assert await stored() == 1


@pytest.mark.usefixtures("app_engine")
@pytest.mark.parametrize("status", ["COMPLETE", "CANCELLED"])
async def test_ac6_a_fill_other_than_the_stored_65_blocks(app_engine, admin_engine, monkeypatch, status):
    """Book shows 30 filled (partial, or cancelled after a part fill) against 65 stored at close -> refused. Zerodha's
    positions still say 65, so ONLY the drift guard can refuse this (positions agree with the stored plan)."""
    async with _world(app_engine, admin_engine, monkeypatch, close="filled", filled={TAG: 65}) as (
            app, sid, use, stored):
        use(_replay(_book(status=status, filled_quantity=30, pending_quantity=0)))
        await _refused_with(app, sid, "EXIT", RECONCILE_PHRASE)
        assert await stored() == 1


@pytest.mark.usefixtures("app_engine")
async def test_ac6_another_strategys_drifted_tag_does_not_block_this_strategy(app_engine, admin_engine, monkeypatch):
    """OFS2V1L0 (strategy 2) filled 30 in the book is not this strategy's drift -> EXIT of strategy 1 goes through."""
    async with _world(app_engine, admin_engine, monkeypatch, close="filled", filled={TAG: 65}) as (
            app, sid, use, _stored):
        other = {**_real_rows()[0], "tag": "OFS2V1L0", "tags": ["OFS2V1L0"], "filled_quantity": 30,
                 "order_id": "261016170576999"}
        use(_replay([*_real_rows(), other]))
        resp = await _post(app, sid, "EXIT")
        assert resp.status_code == HTTP_OK, resp.text


@pytest.mark.usefixtures("app_engine")
async def test_ac7_an_untagged_surplus_at_zerodha_blocks_nothing(app_engine, admin_engine, monkeypatch):
    """Zerodha holds 130 on the contract, the strategy 65, and an untagged order sits in the book (REQ-060 AC-7): no
    drift, nothing blocked -> EXIT goes through."""
    async with _world(app_engine, admin_engine, monkeypatch, close="filled", filled={TAG: 65}) as (
            app, sid, use, _stored):
        untagged = {**_real_rows()[0], "tag": None, "tags": [], "order_id": "261016170576888"}
        use(_replay([*_real_rows(), untagged], held=130))
        resp = await _post(app, sid, "EXIT")
        assert resp.status_code == HTTP_OK, resp.text
