"""W-096 (REQ-073 AC-3): the return from Kite on the owner's REAL 2026-10-16 replies (tests/fixtures/kite_replies/).

Expected values come from the fixture files or by hand: plan 1 = OFS1V1L0 BUY 65 LIMIT 5.45 (the real basket), Kite's
12:21:04 orders show it COMPLETE 65 of 65 with one trade 4484194 of 65; plan 2 = OFS1V2L0 SELL 65 LIMIT 3.10, Kite's
15:10:06 orders show it COMPLETE 65 with trade 5966618; positions 12:21:04 = +65, 15:10:06 = the flat row (quantity 0).
P&L by hand: (3.10 - 5.10) x 65 = -130.00 = the flat row's ``unrealised`` -130 (ADR-102).
"""
from __future__ import annotations

import copy
import dataclasses
import datetime
import json
from decimal import Decimal as D
from http import HTTPStatus

import pytest
from ofo.execution.basket import make_tag
from ofo_app import execution_return as er
from ofo_app import return_book as rb
from ofo_app.execute_replay import recorded_text
from ofo_app.execution_plan_store import PlanOrder, StoredPlan

pytestmark = pytest.mark.usefixtures("order_path_on")  # W-121

SYMBOL = "NIFTY26O1923650CE"
IID = "NSE_FO:47189"  # never read by the pure part; the DB test uses the catalogue's own id
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
AT = datetime.datetime(2026, 10, 16, 12, 21, 4, tzinfo=IST)
ENTRY_PLAN, EXIT_PLAN = 1, 2  # the real tags OFS1V1L0 / OFS1V2L0 (ADR-105)
KEY = ("NIFTY", "CE", D("23650"), datetime.date(2026, 10, 19))
TODAY = AT.date()  # the session the stored plans were created in (2026-10-16, IST)


def _data(name: str) -> list:
    return json.loads(recorded_text(f"{name}.json"), parse_float=D)["data"]


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
    return rb.read_book(orders, trades, 1, frozenset(o.tag for p in plans for o in p.orders))


def test_ac3_core_real_replies_close_entry_filled_then_exit_with_pnl_once():
    """AC-3 core (pure part): 12:21:04 -> plan 1 filled 65 of 65; 15:10:06 -> plan 2 filled in full, plan 1 unchanged
    (no drift), the fills' P&L -130.00; the same replies twice -> the same answer, each trade id once."""
    book = _book(_data("orders-122104"), _data("trades-122104"), (ENTRY_OPEN,))
    assert er.classify(ENTRY_OPEN, book, TODAY) == er.PlanAnswer(er.FILLED, {"Q0001010": 65})
    assert er.pnl_or_none(book.fills) is None  # an open position has no realised P&L
    trades = _data("trades-151006")
    for replay in (trades, trades + copy.deepcopy(trades)):
        book = _book(_data("orders-151006"), replay, (ENTRY_DONE, EXIT_OPEN))
        assert er.classify(EXIT_OPEN, book, TODAY) == er.PlanAnswer(er.FILLED, {"Q0001020": 65})
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
    assert er.classify(ENTRY_OPEN, _book(orders, _data("trades-122104"), (ENTRY_OPEN,)), TODAY).state == er.WAITING


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
    empty = _book([], [], (ENTRY_OPEN,))
    assert er.classify(ENTRY_OPEN, empty, TODAY) == er.PlanAnswer(er.NOTHING_PLACED, {"Q0001010": 0})
    orders = _data("orders-122104")
    orders[0].update(status=status, filled_quantity=0)
    assert er.classify(ENTRY_OPEN, _book(orders, [], (ENTRY_OPEN,)), TODAY).state == er.NOTHING_PLACED


def test_ac3_one_of_two_orders_filled_is_partial_with_the_four_choices_in_order():
    """AC-3 / REQ-058 AC-2: leg 0 filled, leg 1 cancelled unfilled -> partial; the choices are REQ-058 AC-2's order."""
    plan = _plan(1, "ENTRY", ("BUY", "BUY"))
    second = {**_data("orders-122104")[0], "order_id": "261016170576174", "tag": "Q0001011", "status": "CANCELLED",
              "filled_quantity": 0}
    book = _book([*_data("orders-122104"), second], _data("trades-122104"), (plan,))
    assert er.classify(plan, book, TODAY) == er.PlanAnswer(er.PARTIAL, {"Q0001010": 65, "Q0001011": 0})
    assert er.PARTIAL_CHOICES == ("complete_strategy", "retry_failed_leg", "review_manually", "close_partial_strategy")


def test_ac3_an_order_tagged_for_a_plan_never_stored_is_external_and_another_strategys_tag_is_ignored():
    """AC-3 / ADR-050 item 4(d): OFS1V9L0 with no stored plan 9 is kept as external; OFS12V1L0 is strategy 12's."""
    real = _data("orders-122104")[0]
    orders = [{**real, "tag": "Q0001090", "order_id": "9"}, {**real, "tag": "Q000C010", "order_id": "12"}, real]
    book = _book(orders, _data("trades-122104"), (ENTRY_OPEN,))
    assert [r["tag"] for r in book.external] == ["Q0001090"]
    assert list(book.ours) == ["Q0001010"]


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
    assert er.classify(ENTRY_OPEN, _book(orders, trades, (ENTRY_OPEN,)), TODAY) == er.PlanAnswer(er.RECONCILE, {})


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
    assert not er.exit_is_clean(er.reconcile([KEY], {KEY: 0}, {}, {}, frozenset({KEY})))  # another's plan unsettled


def test_ac3_a_plan_from_an_earlier_session_is_never_closed_from_todays_book():
    """Review MAJOR 2: plan 1 created 2026-10-16, returned 2026-10-17 with an empty book (Kite's book holds only
    today's orders) -> stays open, reconciliation required, reason named; a stamp with no zone counts as earlier."""
    empty = _book([], [], (ENTRY_OPEN,))
    next_day = TODAY + datetime.timedelta(days=1)
    assert er.classify(ENTRY_OPEN, empty, next_day) == er.PlanAnswer(er.RECONCILE, {}, er.EARLIER_SESSION)
    real = _book(_data("orders-122104"), _data("trades-122104"), (ENTRY_OPEN,))
    assert er.classify(ENTRY_OPEN, real, next_day).state == er.RECONCILE  # even a full book never closes it
    naive = dataclasses.replace(ENTRY_OPEN, created_at=AT.replace(tzinfo=None))
    assert er.classify(naive, empty, TODAY) == er.PlanAnswer(er.RECONCILE, {}, er.EARLIER_SESSION)
    late = dataclasses.replace(ENTRY_OPEN, created_at=datetime.datetime(2026, 10, 16, 23, 59, tzinfo=IST))
    assert er.classify(late, empty, TODAY).state == er.NOTHING_PLACED  # same IST day: unchanged
    utc_prev = dataclasses.replace(ENTRY_OPEN, created_at=datetime.datetime(2026, 10, 15, 19, 0, tzinfo=datetime.UTC))
    assert er.classify(utc_prev, empty, TODAY).state == er.NOTHING_PLACED  # 00:30 IST on the 16th: today


def _other_plan(status: str, filled: int | None) -> StoredPlan:
    """Strategy 2's plan 1: BUY 65 of the same contract (tag OFS2V1L0)."""
    order = PlanOrder(0, make_tag(2, 1, 0), IID, SYMBOL, "BUY", 65, D("5.45"), filled)
    return StoredPlan(2, 1, "ENTRY", status, (order,), AT, None if status == "open" else AT,
                      None if status == "open" else "filled")


def _other_book(filled: int, plans: tuple[StoredPlan, ...]) -> er.TodaysBook:
    """Strategy 2's own rows of today's book: the real 12:21:04 order and trade, re-tagged to OFS2V1L0."""
    orders = [{**_data("orders-122104")[0], "tag": "Q0002010", "filled_quantity": filled}]
    trades = [{**_data("trades-122104")[0], "quantity": filled}] if filled else []
    return rb.read_book(orders, trades, 2, frozenset(o.tag for p in plans for o in p.orders))


@pytest.mark.parametrize(("status", "stored", "at_kite", "unsettled"), [
    ("open", None, 65, True),  # B's open plan filled at Zerodha, not returned: its 65 are unknown here
    ("closed", 0, 65, True),  # B's closed plan drifted (stored 0, Kite 65)
    ("closed", 65, 65, False),  # B closed and settled: counts by its stored fills
])
def test_ac3_another_strategys_open_or_drifted_plan_makes_the_contract_undecidable(status, stored, at_kite, unsettled):
    """Review MAJOR 1 (worked case): A holds 65 by its plans, B has a plan BUY 65 on the same contract, Zerodha net
    65. Before: B counted 0 -> A "no mismatch". After: open or drifted B -> reconciliation required, reason named."""
    other = (_other_plan(status, stored),)
    keys = frozenset(KEY for _ in er.unsettled_orders(other, _other_book(at_kite, other)))
    assert bool(keys) is unsettled
    others = {KEY: 65} if status == "closed" else {}
    (check,) = er.reconcile([KEY], {KEY: 65}, others, {KEY: 65}, keys)
    assert (check.undecidable, check.blocks) == ((er.OTHER_UNSETTLED, True) if unsettled else (None, True))
    if not unsettled:
        assert check.kind == er.MISSING  # settled B explains Zerodha's 65: A's share is 0 (decided normally)


# ---- the route on the database (core proof; CI) -----------------------------------------------------------------

class _Reads:
    """Fake transport answering the three reads with one recorded snapshot; anything else (a write) fails the test."""

    def __init__(self, snapshot: str, *, orders: list | None = None, trades: list | None = None) -> None:
        self.snapshot, self.calls = snapshot, []
        self.replaced = {"orders": orders, "trades": trades}

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url))
        assert method == "GET" and body is None, (method, url)
        for path, name in (("/orders", "orders"), ("/trades", "trades"), ("/portfolio/positions", "positions")):
            if url.endswith(path):
                data = self.replaced.get(name)
                data = _data(f"{name}-{self.snapshot}") if data is None else data
                return 200, json.dumps({"status": "success", "data": data}, default=str)
        raise AssertionError(url)


def _session(transport: _Reads):
    from ofo_app.kite_reads import KiteReads  # noqa: PLC0415

    # Built outside the class body: a class body that assigns ``reads`` cannot see the function's own ``reads``.
    kite_reads = KiteReads(api_key="kitekey", access_token="tok", transport=transport)  # noqa: S106

    class _S:
        api_key = "kitekey"
        reads = kite_reads
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


#: W-017's declared keys (work/W-017.md, the allow-list module's docstring): one Kite ORDER record / one TRADE record.
W017_ORDER_KEYS = ("order_id", "exchange_order_id", "parent_order_id", "status", "order_timestamp",
                   "exchange_timestamp", "exchange", "tradingsymbol", "instrument_token", "order_type",
                   "transaction_type", "product", "quantity", "disclosed_quantity", "price", "trigger_price",
                   "average_price", "filled_quantity", "pending_quantity", "cancelled_quantity", "tag")
W017_TRADE_KEYS = ("trade_id", "order_id", "exchange_order_id", "instrument_token", "tradingsymbol", "exchange",
                   "transaction_type", "product", "quantity", "average_price", "order_timestamp", "fill_timestamp",
                   "exchange_timestamp")


def _kept(row: dict, keys: tuple[str, ...]) -> dict:
    """The recorded row restricted to the W-017 keys it carries (what the allow-list keeps)."""
    return {k: row[k] for k in keys if k in row}


def _expected_reply_events(snapshot: str, order_id: str) -> list[tuple[str, str, dict]]:
    """The two events one real order's return writes: its ORDER record, then its TRADE record (one each)."""
    (order,) = [r for r in _data(f"orders-{snapshot}") if r["order_id"] == order_id]
    (trade,) = [r for r in _data(f"trades-{snapshot}") if r["order_id"] == order_id]
    return [("broker_response_recorded", f"order:{order_id}:COMPLETE:65", _kept(order, W017_ORDER_KEYS)),
            ("execution_recorded", f"trade:{order_id}:{trade['trade_id']}", _kept(trade, W017_TRADE_KEYS))]


async def _created_date(conn) -> datetime.date:
    """The India date the database stamps a new plan with (``created_at`` is the real clock, not the pin)."""
    from ofo_app.sql_time import IST_SQL_ZONE  # noqa: PLC0415
    from sqlalchemy import text  # noqa: PLC0415

    return (await conn.execute(text(f"SELECT (clock_timestamp() {IST_SQL_ZONE})::date"))).scalar_one()


def _app_for(conn, user, reads: _Reads, today: datetime.date | None = None):
    """``today`` = the return's session date; default: the date the database stamps new plans with (same session)."""
    from ofo_app import eligibility_from_zerodha as elig  # noqa: PLC0415
    from ofo_app.routes import execute as route  # noqa: PLC0415
    from test_strategy_followups import _ConnMaker  # noqa: PLC0415
    from test_strategy_store import _app  # noqa: PLC0415

    async def _today(db) -> datetime.date:
        return today if today is not None else await _created_date(db)

    app = _app(_ConnMaker(conn), user)
    app.dependency_overrides[route.get_execute_clock] = lambda: (lambda: AT)
    app.dependency_overrides[route.get_kite_session] = lambda: _session(reads)
    app.dependency_overrides[elig.get_eligibility_today] = lambda: _today
    return app


@pytest.mark.usefixtures("app_engine")
async def test_core_real_order_return_entry_then_exit(app_engine, admin_engine, monkeypatch):
    """AC-3 core: plan 1 open + 12:21:04 replies -> filled 65 of 65, platform 65 = Zerodha 65, 0 mismatches; plan 2
    open + 15:10:06 replies -> exited, position 0, Zerodha flat, strategy exited, P&L -130.00; a replay changes
    nothing; only GET reads were made. W-103: each order read back by tag -> one ``broker_response_recorded``, each
    trade -> one ``execution_recorded`` (W-017 keys), never twice across returns; the chain verifies."""
    from ofo_app import execution_plan_store as plans  # noqa: PLC0415
    from ofo_app.audit_store import load_log  # noqa: PLC0415
    from test_execute_route import _strategy_one, audit_head, audit_since  # noqa: PLC0415
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
            head = await audit_head(conn)
            resp = await _post(_app_for(conn, user, entry), sid)
            assert resp.status_code == HTTPStatus.OK, resp.text
            # W-103: the order read back by tag and its one trade, each recorded once (real 12:21:04 replies)
            entry_events = await audit_since(conn, head)
            assert entry_events == _expected_reply_events("122104", "261016170576173")
            assert entry_events[1][2]["trade_id"] == "4484194" and entry_events[0][2]["filled_quantity"] == 65
            assert "placed_by" not in entry_events[0][2] and "account_id" not in entry_events[0][2]
            body = resp.json()
            assert body["plans"] == [{"plan_number": 1, "action": "ENTRY", "state": "filled", "choices": [],
                                     "reason": None}]
            assert body["contracts"] == [{"tradingsymbol": SYMBOL, "platform_units": 65, "zerodha_units": 65,
                                          "other_strategies_units": 0, "unexplained_units": 0, "mismatch": None,
                                          "reconciliation_reason": None}]
            assert (body["mismatches"], body["blocked"], body["strategy_state"], body["realised_pnl"]) == (
                0, False, "holding", None)
            (stored,) = await plans.plans_for(conn, user, sid)
            assert (stored.close_reason, stored.orders[0].filled_quantity) == ("filled", 65)

            assert await _store_plan(conn, user, sid, ("EXIT", "SELL", "3.10")) == EXIT_PLAN
            exit_reads = _Reads("151006")
            app = _app_for(conn, user, exit_reads)
            head = await audit_head(conn)
            first = (await _post(app, sid)).json()
            # the 15:10:06 book repeats the entry order and trade: only the exit's order and trade are new
            assert await audit_since(conn, head) == _expected_reply_events("151006", "261016170858845")
            assert [p["state"] for p in first["plans"]] == ["filled", "exited"]
            assert first["contracts"][0] == {"tradingsymbol": SYMBOL, "platform_units": 0, "zerodha_units": 0,
                                                  "other_strategies_units": 0, "unexplained_units": 0,
                                                  "mismatch": None, "reconciliation_reason": None}
            assert (first["mismatches"], first["blocked"], first["strategy_state"], first["realised_pnl"]) == (
                0, False, "exited", "-130.00")
            before = await plans.plans_for(conn, user, sid)
            head = await audit_head(conn)
            again = (await _post(app, sid)).json()
            assert await audit_since(conn, head) == []  # a replayed return writes no audit event
            _, anchor = await load_log(conn)  # the hash chain verifies with the four events in it
            assert anchor.count == head
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
    from test_execute_route import _strategy_one, audit_head, audit_since  # noqa: PLC0415
    from test_strategy_store import _user  # noqa: PLC0415

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("TEST_CATALOGUE_DATE", "2026-10-16")
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            user = _user()
            sid = await _strategy_one(conn, user, app_engine.url.username)
            await _store_plan(conn, user, sid, ("ENTRY", "BUY", "5.45"))
            orders = [{**_data("orders-122104")[0], "tag": "Q0001090"}]
            app = _app_for(conn, user, _Reads("122104", orders=orders))
            before = await _audit_count(conn)
            head = await audit_head(conn)
            body = (await _post(app, sid)).json()
            assert body["plans"][0]["state"] == "nothing_placed"
            assert [(o["tag"], o["filled_quantity"]) for o in body["external_orders"]] == [("Q0001090", 65)]
            await _post(app, sid)
            assert await _audit_count(conn) == before + 1
            # W-103: the external order is not one of the plan's orders, so neither it nor its trade is recorded as ours
            assert [(t, c) for t, c, _ in await audit_since(conn, head)] == [
                ("broker_response_recorded", "external:1:261016170576173:COMPLETE:65")]
        finally:
            await trans.rollback()


async def _strategy_b(conn, user: str) -> int:
    """A second strategy of the same user on the same real contract (saved through the store, as the app role)."""
    from ofo.engine import Action  # noqa: PLC0415
    from ofo.strategy import stored_form as sf  # noqa: PLC0415
    from ofo_app.strategy_store import build_definition, save_draft  # noqa: PLC0415
    from sqlalchemy import text  # noqa: PLC0415
    from test_execute_route import CORE_ID  # noqa: PLC0415

    cid = (await conn.execute(text("SELECT id FROM public.catalogue_contracts WHERE exchange_segment = :g AND "
                                   "exchange_token = :t AND NOT retired"),
                              {"g": CORE_ID.exchange_segment, "t": CORE_ID.exchange_token})).scalar_one()
    saved = await build_definition(conn, "NIFTY", [sf.LegChoice(int(cid), Action.BUY, 65, None)],
                                   rules_ref=None, risk_limits={}, preferences={})
    return (await save_draft(conn, user, saved)).id


@pytest.mark.usefixtures("app_engine")
async def test_ac3_core_another_strategys_open_plan_filled_at_kite_makes_the_contract_undecidable(
        app_engine, admin_engine, monkeypatch):
    """Review MAJOR 1 core: A (strategy 1) holds 65 by its stored plan; B has an OPEN plan BUY 65 on the same contract,
    filled at Zerodha (the real 12:21:04 row and trade re-tagged to B) but not returned; Zerodha net 65. Before: B
    counted 0 -> A "no mismatch". After: A's contract is undecidable -> reconciliation required, blocked."""
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
            assert (await _post(_app_for(conn, user, _Reads("122104")), sid)).json()["plans"][0]["state"] == "filled"
            other = await _strategy_b(conn, user)
            await _store_plan(conn, user, other, ("ENTRY", "BUY", "5.45"))
            real_order, real_trade = _data("orders-122104")[0], _data("trades-122104")[0]
            b_id = "261016170576175"
            b_order = {**real_order, "tag": make_tag(other, 1, 0), "order_id": b_id}
            reads = _Reads("122104", orders=[real_order, b_order],
                           trades=[real_trade, {**real_trade, "order_id": b_id, "trade_id": "4484195"}])
            body = (await _post(_app_for(conn, user, reads), sid)).json()
            assert body["contracts"] == [{"tradingsymbol": SYMBOL, "platform_units": 65, "zerodha_units": 65,
                                          "other_strategies_units": 0, "unexplained_units": 0, "mismatch": None,
                                          "reconciliation_reason": "another_strategy_plan_unsettled"}]
            assert (body["mismatches"], body["blocked"]) == (1, True)
        finally:
            await trans.rollback()


@pytest.mark.usefixtures("app_engine")
async def test_ac3_core_a_plan_from_yesterday_is_never_closed_from_an_empty_book(app_engine, admin_engine,
                                                                                 monkeypatch):
    """Review MAJOR 2 core: plan 1 created in one session, returned the next day with an empty book (no tag in today's
    orders) and Zerodha still +65 -> the plan is NOT closed nothing_placed: open, reconciliation required, reason."""
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
            await _store_plan(conn, user, sid, ("ENTRY", "BUY", "5.45"))
            next_day = await _created_date(conn) + datetime.timedelta(days=1)
            body = (await _post(_app_for(conn, user, _Reads("122104", orders=[]), next_day), sid)).json()
            assert body["plans"] == [{"plan_number": 1, "action": "ENTRY", "state": "reconciliation_required",
                                      "choices": [], "reason": "plan_from_earlier_session"}]
            assert body["blocked"] is True
            (stored,) = await plans.plans_for(conn, user, sid)
            assert (stored.status, stored.close_reason) == ("open", None)
        finally:
            await trans.rollback()
