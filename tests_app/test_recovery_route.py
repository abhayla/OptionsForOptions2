"""#380-3: ``POST /strategies/{id}/recovery`` on the database, on the real 2026-10-16 replies (``execute_replay``) and
partial / blocked states derived from them. CI runs it (DB); every basket goes through the one Execute pipeline.

Expected values come from the decisions, never from running the route: a 130-unit strategy whose plan 1 filled 65
(Zerodha's real 12:21 book and +65 position) is missing 65 -> Place missing legs = BUY 65 (ADR-136 (1)); Close filled
legs = SELL the 65 Zerodha holds (ADR-136 (1), Q238); Close via a basket is offered only while blocked (ADR-137 (3)); an
open order refuses with the ADR-142 line. Blocked: plan 1 recorded 130 filled, Zerodha shows +65 -> the plain EXIT is
refused, Close via a basket sells 65 through the gate's one narrow blocked-exit rule.
"""
from __future__ import annotations

import json
from http import HTTPStatus
from decimal import Decimal as D

import pytest
from ofo_app.execute_replay import AT, REPLIES
from test_execute_route import _Quotes, _Replay, _rows_of, _session_for, _strategy_one

ORDER_OPEN_LINE = "An order for this contract is still open on Kite. Cancel or change it on Kite first."


def _book_row(**changes) -> list[dict]:
    rows = json.loads((REPLIES / "orders-122104.json").read_text(encoding="utf-8"), parse_float=D)
    rows = rows["data"] if isinstance(rows, dict) else rows
    return [{**rows[0], **changes}]


async def _post(app, sid: int, action: str):
    from test_strategy_store import _client  # noqa: PLC0415

    async with _client(app) as ac:
        return await ac.post(f"/strategies/{sid}/recovery", json={"action": action})


class _Setup:
    def __init__(self, conn, app, user, sid, route) -> None:
        self.conn, self.app, self.user, self.sid, self.route = conn, app, user, sid, route
        self.gate_calls = 0

    def kite(self, **rows) -> None:
        replay = _rows_of(_Replay(funds="1003", basket_total="354.25", orders="orders-122104",
                                  positions="positions-122104"), **rows)
        self.app.dependency_overrides[self.route.get_kite_session] = lambda: _session_for(replay)

    async def plans(self) -> list[tuple]:
        from ofo_app import execution_plan_store as plans  # noqa: PLC0415

        return [(p.plan_number, p.action, p.status) for p in await plans.plans_for(self.conn, self.user, self.sid)]


async def _partial(app_engine, conn, monkeypatch, *, filled: int) -> _Setup:
    """A 130-unit strategy, ENTRY plan 1 stored and closed with ``filled`` units; the gate is spied (it must run)."""
    from ofo_app import execution_plan_store as plans  # noqa: PLC0415
    from ofo_app.routes import execute as route  # noqa: PLC0415
    from test_strategy_followups import _ConnMaker  # noqa: PLC0415
    from test_strategy_store import _app, _user  # noqa: PLC0415

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("TEST_CATALOGUE_DATE", "2026-10-16")
    user = _user()
    sid = await _strategy_one(conn, user, app_engine.url.username, units=130)
    app = _app(_ConnMaker(conn), user)
    app.dependency_overrides[route.get_quote_reader] = _Quotes
    app.dependency_overrides[route.get_execute_clock] = lambda: (lambda: AT)
    setup = _Setup(conn, app, user, sid, route)
    entry = _Replay(funds="1003", basket_total="354.25", orders=None, positions="positions-151006")
    app.dependency_overrides[route.get_kite_session] = lambda: _session_for(entry)
    from test_strategy_store import _client  # noqa: PLC0415

    async with _client(app) as ac:
        assert (await ac.post(f"/strategies/{sid}/execute", json={"action": "ENTRY"})).status_code == HTTPStatus.OK
    await plans.close_plan(conn, user, sid, 1, reason="partial", filled={"OFS1V1L0": filled})
    real_gate = route.check_pre_execution

    def spy(*args, **kwargs):
        setup.gate_calls += 1
        return real_gate(*args, **kwargs)

    monkeypatch.setattr(route, "check_pre_execution", spy)
    return setup


@pytest.mark.usefixtures("app_engine")
async def test_place_missing_legs_buys_only_the_missing_65(app_engine, admin_engine, monkeypatch):
    """ADR-136 (1): plan 1 filled 65 of 130 -> one basket BUY 65 tagged OFS1V2L0 (plan 2, ENTRY), the gate ran."""
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            s = await _partial(app_engine, conn, monkeypatch, filled=65)
            s.kite()
            resp = await _post(s.app, s.sid, "place_missing_legs")
            assert resp.status_code == HTTPStatus.OK, resp.text
            body = resp.json()
            assert (body["refusal"], body["line"]) == (None, None)
            (order,) = body["execute"]["orders"]
            assert (order["transaction_type"], order["quantity"], order["tag"]) == ("BUY", 65, "OFS1V2L0")
            assert s.gate_calls == 1
            assert await s.plans() == [(1, "ENTRY", "closed"), (2, "ENTRY", "open")]
        finally:
            await trans.rollback()


@pytest.mark.usefixtures("app_engine")
async def test_close_filled_legs_sells_the_65_zerodha_holds(app_engine, admin_engine, monkeypatch):
    """ADR-136 (1) / Q238: Zerodha +65 long, nothing short -> one basket SELL 65 (plan 2, EXIT), the gate ran."""
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            s = await _partial(app_engine, conn, monkeypatch, filled=65)
            s.kite()
            resp = await _post(s.app, s.sid, "close_filled_legs")
            assert resp.status_code == HTTPStatus.OK, resp.text
            (order,) = resp.json()["execute"]["orders"]
            assert (order["transaction_type"], order["quantity"], order["tag"]) == ("SELL", 65, "OFS1V2L0")
            assert s.gate_calls == 1
            assert await s.plans() == [(1, "ENTRY", "closed"), (2, "EXIT", "open")]
        finally:
            await trans.rollback()


@pytest.mark.usefixtures("app_engine")
async def test_refusals_store_nothing_and_carry_the_adr142_line(app_engine, admin_engine, monkeypatch):
    """ADR-142 (1): an open order of the strategy -> ``order_open`` with its exact line; Close via a basket on a
    strategy that is not blocked -> ``not_blocked`` (ADR-137 (3)); a browser-supplied quantity is refused (422)."""
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            s = await _partial(app_engine, conn, monkeypatch, filled=65)
            for action in ("place_missing_legs", "close_filled_legs"):
                s.kite(orders=_book_row(status="OPEN"))
                body = (await _post(s.app, s.sid, action)).json()
                assert (body["refusal"], body["line"], body["execute"]) == ("order_open", ORDER_OPEN_LINE, None)
            s.kite()
            body = (await _post(s.app, s.sid, "close_via_basket")).json()
            assert (body["refusal"], body["execute"]) == ("not_blocked", None)
            from test_strategy_store import _client  # noqa: PLC0415

            async with _client(s.app) as ac:
                forged = await ac.post(f"/strategies/{s.sid}/recovery",
                                       json={"action": "close_filled_legs", "quantity": 130})
            assert forged.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
            assert await s.plans() == [(1, "ENTRY", "closed")]
        finally:
            await trans.rollback()


@pytest.mark.usefixtures("app_engine")
async def test_close_via_basket_on_a_blocked_strategy_passes_only_the_narrow_rule(app_engine, admin_engine,
                                                                                 monkeypatch):
    """ADR-137 (3): plan 1 recorded 130 filled (Zerodha's book agrees), Zerodha's position shows +65 -> blocked. The
    plain EXIT is refused as a mismatch; Place missing legs is refused ``reconciliation_blocked``; Close via a basket
    sells the 65 Zerodha holds (plan 2, EXIT) through the gate."""
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            s = await _partial(app_engine, conn, monkeypatch, filled=130)
            book = _book_row(quantity=130, filled_quantity=130, status="COMPLETE")
            s.kite(orders=book)
            from test_strategy_store import _client  # noqa: PLC0415

            async with _client(s.app) as ac:
                plain = await ac.post(f"/strategies/{s.sid}/execute", json={"action": "EXIT"})
            assert plain.status_code == HTTPStatus.CONFLICT, plain.text
            assert "do not match what we recorded" in plain.text
            s.kite(orders=book)
            body = (await _post(s.app, s.sid, "place_missing_legs")).json()
            assert body["refusal"] == "reconciliation_blocked"
            s.kite(orders=book)
            resp = await _post(s.app, s.sid, "close_via_basket")
            assert resp.status_code == HTTPStatus.OK, resp.text
            (order,) = resp.json()["execute"]["orders"]
            assert (order["transaction_type"], order["quantity"], order["tag"]) == ("SELL", 65, "OFS1V2L0")
            assert await s.plans() == [(1, "ENTRY", "closed"), (2, "EXIT", "open")]
        finally:
            await trans.rollback()
