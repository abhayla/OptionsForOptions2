"""W-111 (REQ-044 AC-3 part 1; ADR-109 (2), (5); ADR-110): the Positions read on the owner's REAL 2026-10-16 replies.

Expected values come from the recorded files and the ADRs' examples: kite_positions/positions-2026-10-16-one-ce.json
and kite_replies/positions-122104.json are NIFTY26O1923650CE net +65 at 12:21; kite_replies/positions-151006.json is the
flat row (quantity 0) at 15:10:06. kite_replies/orders-122104.json is the entry's order row (tag OFS1V1L0, BUY 65,
COMPLETE, filled 65); orders-151006.json adds the exit row (OFS1V2L0). Strategy 1 holds its own 65 (plan 1 filled 65 of
65, tag OFS1V1L0). Hand-made, labelled derivations: the 130 case doubles the recorded row's quantities (ADR-109:
"strategy BUY 65 CE, Zerodha 130 -> not blocked, 65 outside"); the OPEN case rewrites the recorded order row's status to
OPEN with nothing filled (ADR-110's example: "strategy 1 BUY 65 placed, Zerodha 65, Check not pressed -> ... 65 not yet
confirmed, strategy blocked; after Zerodha shows the order COMPLETE the normal comparison applies"); the second contract
NIFTY26O1923700CE is the recorded listing with its strike moved 50 points (only a catalogue entry, never a Zerodha row).

Answer states (B4 (d)): positions present / absent (no 'net' list) / flat / failed; orders present final (COMPLETE) /
present not final (OPEN) / absent (the plan's tag not in the book) / unreadable or failed / empty list: each has a test.
"""
from __future__ import annotations

import copy
import datetime
import json
from decimal import Decimal as D
from http import HTTPStatus
from pathlib import Path

import pytest
from ofo_app.routes.positions import OwnLotsOut, PendingPlanOut, PositionContractOut, PositionsOut

ROOT = Path(__file__).resolve().parent.parent
REPLIES = ROOT / "tests" / "fixtures" / "kite_replies"
RECORDED = ROOT / "tests" / "fixtures" / "kite_positions" / "positions-2026-10-16-one-ce.json"
POSITIONS_ENTRY = REPLIES / "positions-122104.json"
FLAT = REPLIES / "positions-151006.json"
ORDERS_ENTRY = REPLIES / "orders-122104.json"
ORDERS_EXIT = REPLIES / "orders-151006.json"
SYMBOL = "NIFTY26O1923650CE"
SECOND_SYMBOL = "NIFTY26O1923700CE"
FORBIDDEN = ("price", "pnl", "p_and_l", "margin", "greek", "delta", "gamma", "theta", "vega", "value", "premium",
             "cost", "money", "charge", "m2m", "realised", "unrealised", "order")


def _reply(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"), parse_float=D)["data"]
    return {"day": [], **data}  # Zerodha always sends both lists; the one-row fixture keeps only 'net'


def _orders(path: Path = ORDERS_ENTRY) -> list:
    return json.loads(path.read_text(encoding="utf-8"), parse_float=D)["data"]


def _orders_open() -> list:
    """The recorded entry order row with its status rewritten to OPEN and nothing filled (a hand-made derivation)."""
    rows = copy.deepcopy(_orders())
    for row in rows:
        row.update(status="OPEN", filled_quantity=0, pending_quantity=row["quantity"])
    return rows


def _doubled() -> dict:
    """The recorded +65 row with every quantity doubled (Zerodha 130): a hand-made, labelled derivation."""
    data = copy.deepcopy(_reply(RECORDED))
    for row in data["net"]:
        for key in ("quantity", "buy_quantity", "day_buy_quantity"):
            row[key] = row[key] * 2
        for key in ("value", "buy_value", "buy_m2m", "day_buy_value"):
            row[key] = row[key] * 2
    return data


class _Transport:
    """Answers GET /portfolio/positions and GET /orders with one reply each; anything else (a write, another read)
    fails the test. ``orders`` = None with ``orders_status`` != 200 is a failed orders read."""

    def __init__(self, data: dict | None, status: int = 200, orders: object = None, orders_status: int = 200) -> None:
        self.data, self.status, self.calls = data, status, []
        self.orders, self.orders_status = orders, orders_status

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url))
        assert method == "GET" and body is None, (method, url)
        if url.endswith("/portfolio/positions"):
            status, data = self.status, self.data
        else:
            assert url.endswith("/orders"), url
            status, data = self.orders_status, self.orders
        if status != HTTPStatus.OK:
            return status, json.dumps({"status": "error", "message": "x", "error_type": "TokenException"})
        return 200, json.dumps({"status": "success", "data": data}, default=str)


def _session(transport: _Transport):
    from ofo_app.kite_reads import KiteReads  # noqa: PLC0415

    kite_reads = KiteReads(api_key="kitekey", access_token="tok", transport=transport)  # noqa: S106

    class _S:
        api_key = "kitekey"
        reads = kite_reads
        margin = None  # nothing here can place an order
    return _S()


def _app_for(conn, user, transport: _Transport | None):
    from ofo_app.routes import execute as route  # noqa: PLC0415
    from test_strategy_followups import _ConnMaker  # noqa: PLC0415
    from test_strategy_store import _app  # noqa: PLC0415

    at = datetime.datetime(2026, 10, 16, 12, 21, 4, tzinfo=datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
    app = _app(_ConnMaker(conn), user)
    app.dependency_overrides[route.get_execute_clock] = lambda: (lambda: at)
    app.dependency_overrides[route.get_kite_session] = lambda: None if transport is None else _session(transport)
    return app


async def _get(app, url: str = "/positions"):
    from test_strategy_store import _client  # noqa: PLC0415

    async with _client(app) as ac:
        return await ac.get(url)


def _iid(token: int) -> str:
    from test_execute_route import CORE_ID  # noqa: PLC0415

    return f"{CORE_ID.exchange_segment}:{token}"


async def _plan(conn, user, sid: int, number: int, **opts) -> None:
    """Plan ``number`` of strategy ``sid``: BUY 65 of ``opts['symbol']`` (default the real contract; tag
    OFS<sid>V<number>L0), closed filled 65 of 65, or with ``closed=False`` left OPEN (placed on Kite's page, Check not
    pressed: ADR-110)."""
    symbol, closed = opts.get("symbol", SYMBOL), opts.get("closed", True)
    from ofo.execution.basket import make_tag  # noqa: PLC0415
    from ofo_app import execution_plan_store as plans  # noqa: PLC0415
    from ofo_app.execution_plan_store import PlanOrder  # noqa: PLC0415
    from test_execute_route import CORE_ID  # noqa: PLC0415

    token = CORE_ID.exchange_token if symbol == SYMBOL else CORE_ID.exchange_token + 1
    tag = make_tag(sid, number, 0)
    await plans.record_plan(conn, user, sid, number, "ENTRY", (PlanOrder(0, tag, _iid(token), symbol, "BUY", 65,
                                                                         D("5.45")),))
    if closed:
        await plans.close_plan(conn, user, sid, number, reason="filled", filled={tag: 65})


async def _second_contract(conn) -> None:
    """NIFTY26O1923700CE in the catalogue: the recorded listing with strike +50 and the next token (derived)."""
    from ofo.instruments.parser import zerodha_listed  # noqa: PLC0415
    from ofo_app.catalogue_store import apply_update  # noqa: PLC0415
    from ofo_app.execute_replay import AT, listed_contract  # noqa: PLC0415

    real = listed_contract()
    terms, ref = real.contract, real.broker_refs[0]
    token = int(ref.broker_token) + 256  # exchange_token + 1
    second = zerodha_listed(
        instrument_token=token, exchange_token=token >> 8, tradingsymbol=SECOND_SYMBOL, name=terms.name,
        expiry=terms.expiry, strike=terms.strike + 50, tick_size=terms.tick_size, lot_size=terms.lot_size,
        instrument_type=terms.instrument_type, segment=ref.broker_segment, exchange="NFO")
    await apply_update(conn, [real, second], as_of=datetime.datetime(2026, 10, 16, 9, 1, tzinfo=AT.tzinfo))


async def _second_strategy(conn, user: str) -> int:
    """A second strategy of the same user, BUY 65 of the real contract (its id is the store's)."""
    from ofo.engine import Action  # noqa: PLC0415
    from ofo.strategy import stored_form as sf  # noqa: PLC0415
    from ofo_app.strategy_store import build_definition, save_draft  # noqa: PLC0415
    from sqlalchemy import text  # noqa: PLC0415

    cid = (await conn.execute(text("SELECT c.id FROM public.catalogue_contracts c JOIN public.broker_instruments b "
                                   "ON b.contract_id = c.id WHERE b.broker_symbol = :s AND NOT c.retired"),
                              {"s": SYMBOL})).scalar_one()
    saved = await build_definition(conn, "NIFTY", [sf.LegChoice(int(cid), Action.BUY, 65, None)],
                                   rules_ref=None, risk_limits={}, preferences={})
    return (await save_draft(conn, user, saved)).id


async def _world(conn, app_engine, monkeypatch, plans: str) -> tuple[str, dict]:
    """plans: 'closed' (plan 1 filled 65), 'none', 'open' (plan 1 OPEN), 'two_contracts' (plan 1 closed 65 + plan 2
    OPEN on the second contract), 'two_strategies' (strategy 1 plan 1 closed 65 + a second strategy's plan 1 OPEN on
    the same contract)."""
    from test_execute_route import _strategy_one  # noqa: PLC0415
    from test_strategy_store import _user  # noqa: PLC0415

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("TEST_CATALOGUE_DATE", "2026-10-16")
    user = _user()
    sid = await _strategy_one(conn, user, app_engine.url.username)
    ids = {"first": sid}
    if plans in ("closed", "two_contracts", "two_strategies"):
        await _plan(conn, user, sid, 1)
    if plans == "open":
        await _plan(conn, user, sid, 1, closed=False)
    if plans == "two_contracts":
        await _second_contract(conn)
        await _plan(conn, user, sid, 2, symbol=SECOND_SYMBOL, closed=False)
    if plans == "two_strategies":
        ids["second"] = await _second_strategy(conn, user)
        await _plan(conn, user, ids["second"], 1, closed=False)
    return user, ids


def _closed_keys(node) -> None:
    """Every object in an answer is one of the declared shapes (exact key sets), and no key names a money figure."""
    shapes = {"top": set(PositionsOut.model_fields), "contract": set(PositionContractOut.model_fields),
              "own": set(OwnLotsOut.model_fields), "plan": set(PendingPlanOut.model_fields)}
    assert set(node) == shapes["top"]
    for row in node["contracts"]:
        assert set(row) == shapes["contract"]
        for own in row["own"]:
            assert set(own) == shapes["own"]
        for plan in row["pending_plans"]:
            assert set(plan) == shapes["plan"]


async def _run(engines, monkeypatch, data, *, url="/positions", **opts):
    """opts: plans (default 'closed'), status (Kite's positions status, default 200), session (default True),
    orders (the orders reply data, default the recorded 12:21 book), orders_status (default 200)."""
    plans, status, session = opts.get("plans", "closed"), opts.get("status", 200), opts.get("session", True)
    orders, orders_status = opts.get("orders", _orders()), opts.get("orders_status", 200)
    app_engine, admin_engine = engines
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            user, ids = await _world(conn, app_engine, monkeypatch, plans)
            transport = _Transport(data, status, orders, orders_status)
            resp = await _get(_app_for(conn, user, transport if session else None), url)
            return resp, transport, ids
        finally:
            await trans.rollback()


def _normal(zerodha: int, own: list, outside: int, blocked: bool, symbol: str = SYMBOL) -> dict:
    return {"tradingsymbol": symbol, "zerodha_units": zerodha, "own": own,
            "own_units": sum(o["units"] for o in own), "outside_units": outside, "pending": False,
            "pending_plans": [], "blocked": blocked}


@pytest.mark.usefixtures("app_engine")
async def test_ac3_core_recorded_reply_shows_the_strategys_own_65_and_nothing_outside(app_engine, admin_engine,
                                                                                      monkeypatch):
    """AC-3 core: the recorded +65 reply and the recorded order book (COMPLETE 65), strategy 1 holding its own 65 ->
    one contract, own 65 for strategy 1, 0 outside, not blocked; only the two GETs were made."""
    resp, transport, _ = await _run((app_engine, admin_engine), monkeypatch, _reply(RECORDED))
    assert resp.status_code == HTTPStatus.OK, resp.text
    body = resp.json()
    _closed_keys(body)
    assert body["contracts"] == [{"tradingsymbol": SYMBOL, "zerodha_units": 65, "outside_units": 0, "blocked": False,
                                  "own_units": 65, "own": [{"strategy_id": 1, "units": 65, "blocked": False}],
                                  "pending": False, "pending_plans": []}]
    assert body["blocked"] is False and body["blocked_strategy_ids"] == []
    assert [(m, u.rsplit("/", 1)[-1]) for m, u in transport.calls] == [("GET", "positions"), ("GET", "orders")]


@pytest.mark.usefixtures("app_engine")
async def test_adr110_core_open_plan_with_the_order_open_at_zerodha_is_pending(app_engine, admin_engine, monkeypatch):
    """AC-3 / ADR-110 core: plan 1 OPEN, the recorded 12:21 positions (+65) and the recorded order row rewritten to
    OPEN -> the contract is pending: Zerodha's 65 as read, plan (1, 1) waiting, no own lots, own/outside null (never
    0), strategy 1 blocked."""
    resp, _, _ = await _run((app_engine, admin_engine), monkeypatch, _reply(POSITIONS_ENTRY), plans="open",
                            orders=_orders_open())
    assert resp.status_code == HTTPStatus.OK, resp.text
    body = resp.json()
    _closed_keys(body)
    assert body["contracts"] == [{"tradingsymbol": SYMBOL, "zerodha_units": 65, "own": [], "own_units": None,
                                  "outside_units": None, "pending": True,
                                  "pending_plans": [{"strategy_id": 1, "plan_number": 1}], "blocked": True}]
    assert body["blocked"] is True and body["blocked_strategy_ids"] == [1]


@pytest.mark.usefixtures("app_engine")
async def test_adr110_open_plan_with_the_real_complete_row_takes_the_normal_comparison(app_engine, admin_engine,
                                                                                       monkeypatch):
    """ADR-110: "after Zerodha shows the order COMPLETE the normal comparison applies even if Check is never pressed":
    plan 1 still OPEN, the REAL COMPLETE row (filled 65) -> own 65, outside 0, not pending, not blocked."""
    resp, _, _ = await _run((app_engine, admin_engine), monkeypatch, _reply(POSITIONS_ENTRY), plans="open")
    assert resp.status_code == HTTPStatus.OK, resp.text
    body = resp.json()
    assert body["contracts"] == [_normal(65, [{"strategy_id": 1, "units": 65, "blocked": False}], 0, False)]
    assert body["blocked"] is False and body["blocked_strategy_ids"] == []


@pytest.mark.usefixtures("app_engine")
async def test_adr110_empty_order_book_keeps_a_closed_plans_stored_fill(app_engine, admin_engine, monkeypatch):
    """Orders answer state EMPTY LIST: a successful read of no orders today (Kite's book holds today's orders only);
    plan 1 closed filled 65 keeps its stored fill -> own 65, not pending, not blocked."""
    resp, _, _ = await _run((app_engine, admin_engine), monkeypatch, _reply(POSITIONS_ENTRY), orders=[])
    assert resp.status_code == HTTPStatus.OK, resp.text
    assert resp.json()["contracts"] == [_normal(65, [{"strategy_id": 1, "units": 65, "blocked": False}], 0, False)]


@pytest.mark.usefixtures("app_engine")
async def test_adr110_empty_order_book_with_an_open_plan_is_pending(app_engine, admin_engine, monkeypatch):
    """Orders answer state EMPTY LIST with an open plan: its order is not in the book -> pending, blocked (never
    counted as filled, never as outside)."""
    resp, _, _ = await _run((app_engine, admin_engine), monkeypatch, _reply(POSITIONS_ENTRY), plans="open", orders=[])
    assert resp.status_code == HTTPStatus.OK, resp.text
    (row,) = resp.json()["contracts"]
    assert (row["pending"], row["own"], row["own_units"], row["outside_units"]) == (True, [], None, None)
    assert resp.json()["blocked_strategy_ids"] == [1]


@pytest.mark.usefixtures("app_engine")
@pytest.mark.parametrize("failure", ["http_error", "not_a_list", "bad_row", "text_row", "null_row", "number_row"])
async def test_adr110_a_failed_or_unreadable_orders_read_is_refused_never_an_empty_book(app_engine, admin_engine,
                                                                                        monkeypatch, failure):
    """Orders answer state UNREADABLE / FAILED: a Kite error status, a reply that is not a list, or a row Zerodha's
    adapter refuses -> 409 gate_broker_unconfirmed (as for positions), never an answer built on an empty book."""
    from ofo.errors import render  # noqa: PLC0415

    bad_row = [{**_orders()[0], "filled_quantity": 66}]  # filled more than its 65: impossible
    cases = {"http_error": (None, 403), "not_a_list": ({"orders": []}, 200), "bad_row": (bad_row, 200),
             "text_row": (["x"], 200), "null_row": ([None], 200), "number_row": ([5], 200)}
    orders, status = cases[failure]
    resp, _, _ = await _run((app_engine, admin_engine), monkeypatch, _reply(POSITIONS_ENTRY), plans="open",
                            orders=orders, orders_status=status)
    assert resp.status_code == HTTPStatus.CONFLICT, resp.text
    assert "contracts" not in resp.json()
    assert render("gate_broker_unconfirmed").what_happened in resp.text


@pytest.mark.usefixtures("app_engine")
async def test_adr110_two_strategies_on_one_contract_one_pending_blocks_both(app_engine, admin_engine, monkeypatch):
    """ADR-110 + Q224: strategy 1 holds its own 65 (closed, COMPLETE in the book); a second strategy's plan 1 is OPEN on
    the same contract and its tag is not in the book (orders answer state ABSENT) -> the contract is pending for the
    second strategy's plan, no split, and BOTH strategies are blocked."""
    resp, _, ids = await _run((app_engine, admin_engine), monkeypatch, _reply(POSITIONS_ENTRY), plans="two_strategies")
    assert resp.status_code == HTTPStatus.OK, resp.text
    body = resp.json()
    _closed_keys(body)
    assert body["contracts"] == [{"tradingsymbol": SYMBOL, "zerodha_units": 65, "own": [], "own_units": None,
                                  "outside_units": None, "pending": True,
                                  "pending_plans": [{"strategy_id": ids["second"], "plan_number": 1}],
                                  "blocked": True}]
    assert body["blocked_strategy_ids"] == sorted([1, ids["second"]])
    # What the page reads (review round 1 MINOR 4): the EXACT key sets of the answer and of a pending row, as literals.
    # frontend/e2e/positions.spec.ts and frontend/tests/positions-page.test.js mock exactly these keys.
    assert set(body) == {"read_at", "contracts", "blocked", "blocked_strategy_ids"}
    assert set(body["contracts"][0]) == {"tradingsymbol", "zerodha_units", "own", "own_units", "outside_units",
                                         "pending", "pending_plans", "blocked"}
    assert set(body["contracts"][0]["pending_plans"][0]) == {"strategy_id", "plan_number"}


@pytest.mark.usefixtures("app_engine")
async def test_adr110_a_pending_strategys_other_contract_shows_its_normal_row_but_blocked(app_engine, admin_engine,
                                                                                          monkeypatch):
    """ADR-110 "The strategy is blocked until the plan closes": strategy 1 holds 65 of the real contract (agreeing
    with Zerodha) and has plan 2 OPEN on a second contract (tag OFS1V2L0 absent from the 12:21 book) -> the real
    contract's row is normal (own 65, outside 0) but blocked; the second contract is pending with Zerodha 0."""
    resp, _, _ = await _run((app_engine, admin_engine), monkeypatch, _reply(POSITIONS_ENTRY), plans="two_contracts")
    assert resp.status_code == HTTPStatus.OK, resp.text
    body = resp.json()
    _closed_keys(body)
    rows = {row["tradingsymbol"]: row for row in body["contracts"]}
    assert rows[SYMBOL] == _normal(65, [{"strategy_id": 1, "units": 65, "blocked": True}], 0, True)
    assert rows[SECOND_SYMBOL] == {"tradingsymbol": SECOND_SYMBOL, "zerodha_units": 0, "own": [], "own_units": None,
                                   "outside_units": None, "pending": True,
                                   "pending_plans": [{"strategy_id": 1, "plan_number": 2}], "blocked": True}
    assert body["blocked"] is True and body["blocked_strategy_ids"] == [1]


@pytest.mark.usefixtures("app_engine")
async def test_ac3_zerodha_130_against_own_65_shows_65_outside_no_block(app_engine, admin_engine, monkeypatch):
    """AC-3 / ADR-109 (2): Zerodha 130, strategy 65 -> own 65, outside 65, strategy not blocked."""
    resp, _, _ = await _run((app_engine, admin_engine), monkeypatch, _doubled())
    assert resp.status_code == HTTPStatus.OK, resp.text
    (row,) = resp.json()["contracts"]
    assert (row["zerodha_units"], row["outside_units"], row["blocked"], row["pending"]) == (130, 65, False, False)
    assert row["own"] == [{"strategy_id": 1, "units": 65, "blocked": False}]
    assert resp.json()["blocked"] is False


@pytest.mark.usefixtures("app_engine")
async def test_ac3_zerodha_flat_against_own_65_is_blocked_and_shown(app_engine, admin_engine, monkeypatch):
    """AC-3 / ADR-109 (5): the real flat 15:10:06 book (and its real order book) while the strategy holds 65 -> the
    contract is listed with Zerodha 0, own 65 and blocked (not an empty list)."""
    resp, _, _ = await _run((app_engine, admin_engine), monkeypatch, _reply(FLAT), orders=_orders(ORDERS_EXIT))
    assert resp.status_code == HTTPStatus.OK, resp.text
    body = resp.json()
    assert body["contracts"] == [_normal(0, [{"strategy_id": 1, "units": 65, "blocked": True}], 0, True)]
    assert body["blocked"] is True and body["blocked_strategy_ids"] == [1]


@pytest.mark.usefixtures("app_engine")
async def test_ac3_a_position_in_no_strategy_is_all_outside(app_engine, admin_engine, monkeypatch):
    """AC-3 / ADR-109 (2): the strategy stored no plan; Zerodha +65 -> 65 outside, no own lots, nothing blocked."""
    resp, _, _ = await _run((app_engine, admin_engine), monkeypatch, _reply(RECORDED), plans="none")
    assert resp.status_code == HTTPStatus.OK, resp.text
    assert resp.json()["contracts"] == [_normal(65, [], 65, False)]


@pytest.mark.usefixtures("app_engine")
async def test_ac3_empty_book_and_no_lots_is_an_empty_list_with_a_read_time(app_engine, admin_engine, monkeypatch):
    """AC-3 (answer state EMPTY): a read that succeeded with no net row and no held lots -> 200 with no contracts."""
    data = {"net": [], "day": []}
    resp, _, _ = await _run((app_engine, admin_engine), monkeypatch, data, plans="none", orders=[])
    assert resp.status_code == HTTPStatus.OK, resp.text
    body = resp.json()
    assert body["contracts"] == [] and body["blocked"] is False and body["read_at"]


@pytest.mark.usefixtures("app_engine")
async def test_ac3_no_session_is_the_catalogue_message_not_an_empty_list(app_engine, admin_engine, monkeypatch):
    """AC-3 (answer state NO SESSION): 409 with the catalogue's gate_broker_not_connected text; no contracts key."""
    from ofo.errors import render  # noqa: PLC0415

    resp, transport, _ = await _run((app_engine, admin_engine), monkeypatch, _reply(RECORDED), session=False)
    assert resp.status_code == HTTPStatus.CONFLICT, resp.text
    assert "contracts" not in resp.json()
    assert render("gate_broker_not_connected").what_happened in resp.text
    assert transport.calls == []


@pytest.mark.usefixtures("app_engine")
@pytest.mark.parametrize("failure", ["http_error", "unreadable_reply"])
async def test_ac3_a_failed_or_unreadable_read_is_the_catalogue_message(app_engine, admin_engine, monkeypatch, failure):
    """AC-3 (answer states FAILED, ABSENT): a Kite error status, or a reply with no 'net' list -> 409
    gate_broker_unconfirmed, never 'no positions'."""
    from ofo.errors import render  # noqa: PLC0415

    kwargs = {"status": 403} if failure == "http_error" else {}
    data = None if failure == "http_error" else {"day": []}
    resp, _, _ = await _run((app_engine, admin_engine), monkeypatch, data, **kwargs)
    assert resp.status_code == HTTPStatus.CONFLICT, resp.text
    assert "contracts" not in resp.json()
    assert render("gate_broker_unconfirmed").what_happened in resp.text


@pytest.mark.usefixtures("app_engine")
async def test_ac3_client_supplied_units_are_ignored(app_engine, admin_engine, monkeypatch):
    """AC-3 attack 1 / ADR-110 attack 3: held units, outside lots, strategy ids, pending or blocked in the query change
    nothing (the route takes none)."""
    base, _, _ = await _run((app_engine, admin_engine), monkeypatch, _reply(POSITIONS_ENTRY), plans="open",
                            orders=_orders_open())
    forged, _, _ = await _run((app_engine, admin_engine), monkeypatch, _reply(POSITIONS_ENTRY), plans="open",
                              orders=_orders_open(),
                              url="/positions?held_units=999&outside_units=65&strategy_id=1&blocked=false&pending=false")
    assert forged.status_code == HTTPStatus.OK
    assert {k: v for k, v in forged.json().items() if k != "read_at"} == {
        k: v for k, v in base.json().items() if k != "read_at"}
    assert forged.json()["contracts"][0]["pending"] is True


def test_ac3_answer_key_set_is_closed_and_names_no_money_figure():
    """AC-3 attack 4: the declared answer keys are exactly these, and none names a price, P&L, margin or Greek; a
    key added to a model fails here."""
    assert set(PositionsOut.model_fields) == {"read_at", "contracts", "blocked", "blocked_strategy_ids"}
    assert set(PositionContractOut.model_fields) == {"tradingsymbol", "zerodha_units", "own", "own_units",
                                                     "outside_units", "pending", "pending_plans", "blocked"}
    assert set(OwnLotsOut.model_fields) == {"strategy_id", "units", "blocked"}
    assert set(PendingPlanOut.model_fields) == {"strategy_id", "plan_number"}
    for model in (PositionsOut, PositionContractOut, OwnLotsOut, PendingPlanOut):
        for name, field in model.model_fields.items():
            assert not any(word in name for word in FORBIDDEN), name
            assert field.annotation is not D, name


def test_ac3_extra_key_in_an_answer_is_refused():
    """AC-3 attack 4 (mutation): an answer carrying a pnl key does not validate (ApiModel is closed)."""
    row = {"strategy_id": 1, "units": 65, "blocked": False, "pnl": "1.00"}
    with pytest.raises(ValueError):
        OwnLotsOut.model_validate(row)
