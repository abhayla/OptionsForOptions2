"""W-096 (REQ-073 AC-3): the return from Kite on the owner's REAL 2026-10-16 replies (tests/fixtures/kite_replies/).

Expected values come from the fixture files or by hand: plan 1 = OFS1V1L0 BUY 65 LIMIT 5.45 (the real basket), Kite's
12:21:04 orders show it COMPLETE 65 of 65 with one trade 4484194 of 65; plan 2 = OFS1V2L0 SELL 65 LIMIT 3.10, Kite's
15:10:06 orders show it COMPLETE 65 with trade 5966618; positions 12:21:04 = +65, 15:10:06 = the flat row (quantity 0).
P&L by hand: (3.10 - 5.10) x 65 = -130.00 = the flat row's ``unrealised`` -130 (ADR-102).
"""
from __future__ import annotations

import copy
import datetime
import json
from decimal import Decimal as D
from http import HTTPStatus
from pathlib import Path

import pytest
from ofo.execution.basket import make_tag
from ofo_app import execution_return as er
from ofo_app.execution_plan_store import PlanOrder, StoredPlan

REPLIES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "kite_replies"
SYMBOL = "NIFTY26O1923650CE"
IID = "NSE_FO:47189"  # never read by the pure part; the DB test uses the catalogue's own id
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
AT = datetime.datetime(2026, 10, 16, 12, 21, 4, tzinfo=IST)
ENTRY_PLAN, EXIT_PLAN = 1, 2  # the real tags OFS1V1L0 / OFS1V2L0 (ADR-105)
KEY = ("NIFTY", "CE", D("23650"), datetime.date(2026, 10, 19))


def _data(name: str) -> list:
    return json.loads((REPLIES / f"{name}.json").read_text(encoding="utf-8"), parse_float=D)["data"]


def _plan(number: int, action: str, sides: tuple[str, ...], closed: tuple[tuple[int, ...], str] | None = None,
          ) -> StoredPlan:
    """An open plan, or (``closed`` = (filled per leg, reason)) a closed one; 65 units per leg."""
    filled, reason = closed if closed is not None else ((None,) * len(sides), None)
    orders = tuple(PlanOrder(i, make_tag(1, number, i), IID, SYMBOL, side, 65, D("5.45"), filled[i])
                   for i, side in enumerate(sides))
    status = "open" if closed is None else "closed"
    return StoredPlan(1, number, action, status, orders, AT, None if closed is None else AT, reason)


ENTRY_OPEN = _plan(1, "ENTRY", ("BUY",))
ENTRY_DONE = _plan(1, "ENTRY", ("BUY",), ((65,), "filled"))
EXIT_OPEN = _plan(2, "EXIT", ("SELL",))


def _book(orders: list, trades: list, plans: tuple[StoredPlan, ...]) -> er.TodaysBook:
    return er.read_book(orders, trades, 1, frozenset(o.tag for p in plans for o in p.orders))


def test_ac3_core_real_replies_close_entry_filled_then_exit_with_pnl_once():
    """AC-3 core (pure part): 12:21:04 -> plan 1 filled 65 of 65; 15:10:06 -> plan 2 filled in full, plan 1 unchanged
    (no drift), the fills' P&L -130.00; the same replies twice -> the same answer, each trade id once."""
    book = _book(_data("orders-122104"), _data("trades-122104"), (ENTRY_OPEN,))
    assert er.classify(ENTRY_OPEN, book) == er.PlanAnswer(er.FILLED, {"OFS1V1L0": 65})
    assert er.pnl_or_none(book.fills) is None  # an open position has no realised P&L
    trades = _data("trades-151006")
    for replay in (trades, trades + copy.deepcopy(trades)):
        book = _book(_data("orders-151006"), replay, (ENTRY_DONE, EXIT_OPEN))
        assert er.classify(EXIT_OPEN, book) == er.PlanAnswer(er.FILLED, {"OFS1V2L0": 65})
        assert er.drifted((ENTRY_DONE, EXIT_OPEN), book) == ()
        assert sorted(f.trade_id for f in book.fills) == ["4484194", "5966618"]
        assert er.pnl_or_none(book.fills) == D("-130.00")
        assert book.external == ()


@pytest.mark.parametrize("status", ["OPEN", "TRIGGER PENDING", "AMO REQ RECEIVED", "VALIDATION PENDING", "complete",
                                    "PUT ORDER REQ RECEIVED"])
def test_ac3_an_open_or_unknown_status_word_keeps_the_plan_open(status):
    """AC-3 / REQ-057 AC-2: an order still working (or a word not in the terminal allow-list) changes nothing."""
    orders = _data("orders-122104")
    orders[0]["status"] = status
    assert er.classify(ENTRY_OPEN, _book(orders, _data("trades-122104"), (ENTRY_OPEN,))).state == er.WAITING


def test_ac3_an_unreadable_status_refuses_the_whole_read():
    """AC-3: an empty or missing status word is not guessed: the read is refused (the route answers 409)."""
    from ofo_app.kite_replies import KiteReplyError  # noqa: PLC0415

    for broken in ({"status": ""}, {"status": None}):
        orders = [{**_data("orders-122104")[0], **broken}]
        with pytest.raises(KiteReplyError):
            _book(orders, [], (ENTRY_OPEN,))


@pytest.mark.parametrize("status", ["COMPLETE", "CANCELLED", "REJECTED"])
def test_ac3_basket_closed_on_kites_page_or_ended_unfilled_is_nothing_placed(status):
    """AC-3: no tag in today's book (the user closed the basket) or a terminal order with 0 filled -> nothing_placed,
    never filled."""
    assert er.classify(ENTRY_OPEN, _book([], [], (ENTRY_OPEN,))) == er.PlanAnswer(er.NOTHING_PLACED, {"OFS1V1L0": 0})
    orders = _data("orders-122104")
    orders[0].update(status=status, filled_quantity=0)
    assert er.classify(ENTRY_OPEN, _book(orders, [], (ENTRY_OPEN,))).state == er.NOTHING_PLACED


def test_ac3_one_of_two_orders_filled_is_partial_with_the_four_choices_in_order():
    """AC-3 / REQ-058 AC-2: leg 0 filled, leg 1 cancelled unfilled -> partial; the choices are REQ-058 AC-2's order."""
    plan = _plan(1, "ENTRY", ("BUY", "BUY"))
    second = {**_data("orders-122104")[0], "order_id": "261016170576174", "tag": "OFS1V1L1", "status": "CANCELLED",
              "filled_quantity": 0}
    book = _book([*_data("orders-122104"), second], _data("trades-122104"), (plan,))
    assert er.classify(plan, book) == er.PlanAnswer(er.PARTIAL, {"OFS1V1L0": 65, "OFS1V1L1": 0})
    assert er.PARTIAL_CHOICES == ("complete_strategy", "retry_failed_leg", "review_manually", "close_partial_strategy")


def test_ac3_an_order_tagged_for_a_plan_never_stored_is_external_and_another_strategys_tag_is_ignored():
    """AC-3 / ADR-050 item 4(d): OFS1V9L0 with no stored plan 9 is kept as external; OFS12V1L0 is strategy 12's."""
    real = _data("orders-122104")[0]
    orders = [{**real, "tag": "OFS1V9L0", "order_id": "9"}, {**real, "tag": "OFS12V1L0", "order_id": "12"}, real]
    book = _book(orders, _data("trades-122104"), (ENTRY_OPEN,))
    assert [r["tag"] for r in book.external] == ["OFS1V9L0"]
    assert list(book.ours) == ["OFS1V1L0"]


@pytest.mark.parametrize("change", ["short_trades", "conflicting_trade", "posted_twice", "wrong_side", "wrong_symbol"])
def test_ac3_zerodha_disagreeing_with_itself_or_the_plan_needs_reconciliation(change):
    """AC-3: filled 65 vs trades summing 60, a trade id repeated with other content, a basket posted twice (130 of 65),
    the wrong side or contract -> the plan stays open, reconciliation required (never pick one)."""
    orders, trades = _data("orders-122104"), _data("trades-122104")
    if change == "short_trades":
        trades[0]["quantity"] = 60
    elif change == "conflicting_trade":
        trades.append({**trades[0], "quantity": 5})
    elif change == "posted_twice":
        orders.append({**orders[0], "order_id": "261016170576999"})
        trades.append({**trades[0], "order_id": "261016170576999", "trade_id": "4484195"})
    elif change == "wrong_side":
        orders[0]["transaction_type"] = "SELL"
    else:
        orders[0]["tradingsymbol"] = "NIFTY26O1923700CE"
    assert er.classify(ENTRY_OPEN, _book(orders, trades, (ENTRY_OPEN,))) == er.PlanAnswer(er.RECONCILE, {})


def test_ac3_a_closed_plan_whose_order_filled_after_the_close_has_drifted():
    """AC-3 / design review 5: plan 1 closed nothing_placed, then Kite shows its tag filled 65 -> drift (blocks)."""
    closed = _plan(1, "ENTRY", ("BUY",), ((0,), "nothing_placed"))
    book = _book(_data("orders-122104"), _data("trades-122104"), (closed,))
    assert er.drifted((closed,), book) == (1,)
    assert er.drifted((ENTRY_DONE,), book) == ()


@pytest.mark.parametrize(("held", "others", "net", "kind", "unexplained"), [
    (65, 0, 65, None, 0),  # the real 12:21:04 state
    (65, 0, 130, None, 65),  # a standalone 65 beyond the strategy: blocks no strategy (REQ-060 AC-7)
    (65, 65, 130, None, 0),  # another stored strategy explains the other 65
    (65, 65, 65, er.MISSING, -65),  # Zerodha's 65 belong to the other strategy: this one holds none of it
    (65, 0, 0, er.MISSING, -65),  # Zerodha 0 while the strategy holds 65: blocks this strategy
    (65, 0, 30, er.QUANTITY, -35),
    (65, 0, -65, er.SIDE, -130),
])
def test_ac3_reconciliation_per_strategy(held, others, net, kind, unexplained):
    """AC-3 / REQ-060 AC-7: the strategy's share = Zerodha's net minus other strategies' units; fewer or the wrong
    side blocks it, units beyond it block nothing."""
    (check,) = er.reconcile([KEY], {KEY: held}, {KEY: others}, {KEY: net})
    assert (check.kind, check.unexplained) == (kind, unexplained)


def test_ac3_an_exit_with_zerodha_still_holding_65_is_not_exited():
    """AC-3 / REQ-058 AC-5: the strategy flat by its fills but Zerodha still +65 -> not exited; flat both -> exited."""
    assert not er.exit_is_clean(er.reconcile([KEY], {KEY: 0}, {}, {KEY: 65}))
    assert not er.exit_is_clean(er.reconcile([KEY], {KEY: 65}, {}, {KEY: 65}))
    assert er.exit_is_clean(er.reconcile([KEY], {KEY: 0}, {}, {}))
    assert er.exit_is_clean(er.reconcile([KEY], {KEY: 0}, {KEY: 65}, {KEY: 65}))  # the 65 are another strategy's


# ---- the route on the database (core proof; CI) -----------------------------------------------------------------

class _Reads:
    """Fake transport answering the three reads with one recorded snapshot; anything else (a write) fails the test."""

    def __init__(self, snapshot: str, *, orders: list | None = None) -> None:
        self.snapshot, self.orders, self.calls = snapshot, orders, []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url))
        assert method == "GET" and body is None, (method, url)
        for path, name in (("/orders", "orders"), ("/trades", "trades"), ("/portfolio/positions", "positions")):
            if url.endswith(path):
                data = self.orders if name == "orders" and self.orders is not None else _data(f"{name}-{self.snapshot}")
                return 200, json.dumps({"status": "success", "data": data}, default=str)
        raise AssertionError(url)


def _session(reads: _Reads):
    from ofo_app.kite_reads import KiteReads  # noqa: PLC0415

    class _S:
        api_key = "kitekey"
        reads = KiteReads(api_key="kitekey", access_token="tok", transport=reads)  # noqa: S106
        margin = None  # the return never asks for margin; nothing here can place an order
    return _S()


async def _post(app, strategy_id: int):
    from test_strategy_store import _client  # noqa: PLC0415

    async with _client(app) as ac:
        return await ac.post(f"/strategies/{strategy_id}/execution/return")


async def _store_plan(conn, user, sid, order_shape: tuple[str, str, str]) -> int:
    """Stores the next plan through the W-094 store: (action, side, LIMIT price), 65 units of the real contract."""
    from ofo_app import execution_plan_store as plans  # noqa: PLC0415
    from test_execute_route import CORE_ID  # noqa: PLC0415

    action, side, price = order_shape
    number = await plans.next_plan_number(conn, user, sid)
    order = PlanOrder(0, make_tag(sid, number, 0), f"{CORE_ID.exchange_segment}:{CORE_ID.exchange_token}", SYMBOL,
                      side, 65, D(price))
    await plans.record_plan(conn, user, sid, number, action, (order,))
    return number


async def _audit_count(conn) -> int:
    from sqlalchemy import text  # noqa: PLC0415

    sql = text("SELECT count(*) FROM public.audit_events WHERE correlation_id LIKE 'external:1:%'")
    return int((await conn.execute(sql)).scalar_one())


def _app_for(conn, user, reads: _Reads):
    from ofo_app.routes import execute as route  # noqa: PLC0415
    from test_strategy_followups import _ConnMaker  # noqa: PLC0415
    from test_strategy_store import _app  # noqa: PLC0415

    app = _app(_ConnMaker(conn), user)
    app.dependency_overrides[route.get_execute_clock] = lambda: (lambda: AT)
    app.dependency_overrides[route.get_kite_session] = lambda: _session(reads)
    return app


@pytest.mark.usefixtures("app_engine")
async def test_core_real_order_return_entry_then_exit(app_engine, admin_engine, monkeypatch):
    """AC-3 core: plan 1 open + 12:21:04 replies -> filled 65 of 65, platform 65 = Zerodha 65, 0 mismatches; plan 2
    open + 15:10:06 replies -> exited, position 0, Zerodha flat, strategy exited, P&L -130.00; a replay changes
    nothing; only GET reads were made."""
    from ofo_app import execution_plan_store as plans  # noqa: PLC0415
    from test_execute_route import _strategy_one  # noqa: PLC0415
    from test_strategy_store import _user  # noqa: PLC0415

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("TEST_CATALOGUE_DATE", "2026-10-16")
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            user = _user()
            sid = await _strategy_one(conn, user, app_engine.url.username)
            assert await _store_plan(conn, user, sid, ("ENTRY", "BUY", "5.45")) == ENTRY_PLAN
            entry = _Reads("122104")
            resp = await _post(_app_for(conn, user, entry), sid)
            assert resp.status_code == HTTPStatus.OK, resp.text
            body = resp.json()
            assert body["plans"] == [{"plan_number": 1, "action": "ENTRY", "state": "filled", "choices": []}]
            assert body["contracts"] == [{"tradingsymbol": SYMBOL, "platform_units": 65, "zerodha_units": 65,
                                          "other_strategies_units": 0, "unexplained_units": 0, "mismatch": None}]
            assert (body["mismatches"], body["blocked"], body["strategy_state"], body["realised_pnl"]) == (
                0, False, "holding", None)
            (stored,) = await plans.plans_for(conn, user, sid)
            assert (stored.close_reason, stored.orders[0].filled_quantity) == ("filled", 65)

            assert await _store_plan(conn, user, sid, ("EXIT", "SELL", "3.10")) == EXIT_PLAN
            exit_reads = _Reads("151006")
            app = _app_for(conn, user, exit_reads)
            first = (await _post(app, sid)).json()
            assert [p["state"] for p in first["plans"]] == ["filled", "exited"]
            assert first["contracts"][0] == {"tradingsymbol": SYMBOL, "platform_units": 0, "zerodha_units": 0,
                                                  "other_strategies_units": 0, "unexplained_units": 0,
                                                  "mismatch": None}
            assert (first["mismatches"], first["blocked"], first["strategy_state"], first["realised_pnl"]) == (
                0, False, "exited", "-130.00")
            before = await plans.plans_for(conn, user, sid)
            again = (await _post(app, sid)).json()
            assert {k: v for k, v in again.items() if k != "read_at"} == {
                k: v for k, v in first.items() if k != "read_at"}
            assert await plans.plans_for(conn, user, sid) == before
            assert {m for m, _ in entry.calls + exit_reads.calls} == {"GET"}
        finally:
            await trans.rollback()


@pytest.mark.usefixtures("app_engine")
async def test_ac3_external_order_recorded_once_and_closed_basket_is_nothing_placed(app_engine, admin_engine,
                                                                                    monkeypatch):
    """AC-3 / ADR-050 4(d): the book shows only OFS1V9L0 (no plan 9): plan 1 closes nothing_placed (its tag never
    reached Kite), the external order is listed and written to the audit log once across two returns."""
    from test_execute_route import _strategy_one  # noqa: PLC0415
    from test_strategy_store import _user  # noqa: PLC0415

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("TEST_CATALOGUE_DATE", "2026-10-16")
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            user = _user()
            sid = await _strategy_one(conn, user, app_engine.url.username)
            await _store_plan(conn, user, sid, ("ENTRY", "BUY", "5.45"))
            orders = [{**_data("orders-122104")[0], "tag": "OFS1V9L0"}]
            app = _app_for(conn, user, _Reads("122104", orders=orders))
            before = await _audit_count(conn)
            body = (await _post(app, sid)).json()
            assert body["plans"][0]["state"] == "nothing_placed"
            assert [(o["tag"], o["filled_quantity"]) for o in body["external_orders"]] == [("OFS1V9L0", 65)]
            await _post(app, sid)
            assert await _audit_count(conn) == before + 1
        finally:
            await trans.rollback()
