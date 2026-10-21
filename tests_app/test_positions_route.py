"""W-111 (REQ-044 AC-3 part 1; ADR-109 (2), (5); ADR-110): the Positions read on the owner's REAL 2026-10-16 replies.

Expected values come from the recorded files and the ADRs' examples: kite_positions/positions-2026-10-16-one-ce.json
and kite_replies/positions-122104.json are NIFTY26O1923650CE net +65 at 12:21; kite_replies/positions-151006.json is the
flat row (quantity 0) at 15:10:06. kite_replies/orders-122104.json is the entry's order row (tag OFS1V1L0, BUY 65,
COMPLETE, filled 65); orders-151006.json adds the exit row (OFS1V2L0). Strategy 1 holds its own 65 (plan 1 filled 65 of
65). Hand-made, labelled derivations: the order books are RE-TAGGED through the real ``make_tag`` (each recorded
OFS<s>V<v>L<i> tag becomes make_tag(s, v, i), Q0001010 for OFS1V1L0), because plans are now stored with make_tag's
tags; the legacy case keeps the recorded OFS tags AND stores the plan with the legacy tag (both grammars attribute);
the 130 case doubles the recorded row's quantities (ADR-109:
"strategy BUY 65 CE, Zerodha 130 -> not blocked, 65 outside"); the OPEN case rewrites the recorded order row's status to
OPEN with nothing filled (ADR-110's example: "strategy 1 BUY 65 placed, Zerodha 65, Check not pressed -> ... 65 not yet
confirmed, strategy blocked; after Zerodha shows the order COMPLETE the normal comparison applies"); the second contract
NIFTY26O1923700CE is the recorded listing with its strike moved 50 points (only a catalogue entry, never a Zerodha row).

ADR-138 (2): the answer is strategy groups holding only contracts linked to a strategy, plus one "N outside lots" count;
an outside-only contract is never a row.

Answer states (B4 (d)): positions present / absent (no 'net' list) / flat / failed / empty / only outside rows / mixed
(one contract held partly by a strategy, partly outside) / unknown exchange (refused) / a never-ours row (logged);
orders present final (COMPLETE) / present not final (OPEN) / absent (the plan's tag not in the book) /
unreadable or failed / empty list: each has a test.
"""
from __future__ import annotations

import copy
import datetime
import json
from decimal import Decimal as D
from http import HTTPStatus
from pathlib import Path

import pytest
from ofo_app.routes.positions import PositionsOut, StrategyContractOut, StrategyPositionsOut

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


def _orders(path: Path = ORDERS_ENTRY, *, legacy: bool = False) -> list:
    """The recorded order book; unless ``legacy``, each row's recorded OFS<s>V<v>L<i> tag is re-tagged through the real
    ``make_tag(s, v, i)`` (a derived fixture: plans are stored with make_tag's tags since 2026-10-19)."""
    from ofo.execution.basket import make_tag, parse_tag  # noqa: PLC0415

    rows = json.loads(path.read_text(encoding="utf-8"), parse_float=D)["data"]
    if not legacy:
        for row in rows:
            parts = parse_tag(row["tag"])
            row["tag"] = make_tag(parts.strategy_id, parts.plan_version, parts.leg_index)
    return rows


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
    make_tag(sid, number, 0), or with ``legacy=True`` the pre-2026-10-19 OFS<sid>V<number>L0), closed filled 65 of 65,
    or with ``closed=False`` left OPEN (placed on Kite's page, Check not pressed: ADR-110)."""
    symbol, closed = opts.get("symbol", SYMBOL), opts.get("closed", True)
    from ofo.execution.basket import make_tag  # noqa: PLC0415
    from ofo_app import execution_plan_store as plans  # noqa: PLC0415
    from ofo_app.execution_plan_store import PlanOrder  # noqa: PLC0415
    from test_execute_route import CORE_ID  # noqa: PLC0415
    from test_execution_plan_store import trades_for  # noqa: PLC0415

    token = CORE_ID.exchange_token if symbol == SYMBOL else CORE_ID.exchange_token + 1
    if opts.get("legacy"):  # a row written before 0018: record_plan mints only make_tag's grammar, so the store's
        tag = f"OFS{sid}V{number}L0"  # own INSERT statements write it, as the old code did (the DB still accepts it)
        await conn.execute(plans._INSERT_PLAN, {"s": sid, "p": number, "a": "ENTRY"})
        await conn.execute(plans._INSERT_ORDER, {"s": sid, "p": number, "l": 0, "tag": tag, "iid": _iid(token),
                                                 "side": "BUY", "q": 65, "price": D("5.45")})
        if closed:
            await plans.close_plan(conn, user, sid, number, reason="filled", filled={tag: 65},
                                   fills=trades_for({tag: 65}))
        return
    tag = make_tag(sid, number, 0)
    await plans.record_plan(conn, user, sid, number, "ENTRY", (PlanOrder(0, tag, _iid(token), symbol, "BUY", 65,
                                                                         D("5.45")),))
    if closed:
        await plans.close_plan(conn, user, sid, number, reason="filled", filled={tag: 65},
                                   fills=trades_for({tag: 65}))


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
    the same contract), 'open_legacy' (plan 1 OPEN, stored with the legacy OFS1V1L0 tag)."""
    from test_execute_route import _strategy_one  # noqa: PLC0415
    from test_strategy_store import _user  # noqa: PLC0415

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("TEST_CATALOGUE_DATE", "2026-10-16")
    user = _user()
    sid = await _strategy_one(conn, user, app_engine.url.username)
    ids = {"first": sid}
    if plans in ("closed", "two_contracts", "two_strategies"):
        await _plan(conn, user, sid, 1)
    if plans in ("open", "open_legacy"):
        await _plan(conn, user, sid, 1, closed=False, legacy=plans == "open_legacy")
    if plans == "two_contracts":
        await _second_contract(conn)
        await _plan(conn, user, sid, 2, symbol=SECOND_SYMBOL, closed=False)
    if plans == "two_strategies":
        ids["second"] = await _second_strategy(conn, user)
        await _plan(conn, user, ids["second"], 1, closed=False)
    return user, ids


def _closed_keys(node) -> None:
    """Every object in an answer is one of the declared shapes (exact key sets), and no key names a money figure."""
    assert set(node) == set(PositionsOut.model_fields)
    for group in node["strategies"]:
        assert set(group) == set(StrategyPositionsOut.model_fields)
        for row in group["contracts"]:
            assert set(row) == set(StrategyContractOut.model_fields)


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


def _own(units: int, zerodha: int, symbol: str = SYMBOL) -> dict:
    """A strategy's own row on a contract (not pending)."""
    return {"tradingsymbol": symbol, "zerodha_units": zerodha, "units": units, "pending": False, "pending_plans": []}


def _waiting(zerodha: int, plans: list, symbol: str = SYMBOL) -> dict:
    """A pending row (ADR-110): Zerodha's units as read, no own split, the strategy's waiting plan numbers."""
    return {"tradingsymbol": symbol, "zerodha_units": zerodha, "units": None, "pending": True, "pending_plans": plans}


def _group(sid: int, contracts: list, blocked: bool) -> dict:
    return {"strategy_id": sid, "blocked": blocked, "contracts": contracts}


def _with_row(data: dict, **changes) -> dict:
    """The reply plus one more net row: a copy of its first row with ``changes`` (a hand-made, labelled derivation)."""
    data = copy.deepcopy(data)
    data["net"].append({**copy.deepcopy(data["net"][0]), **changes})
    return data


def _requantified(units: int) -> dict:
    """The recorded +65 row with its quantity set to ``units`` (a hand-made, labelled derivation)."""
    data = copy.deepcopy(_reply(RECORDED))
    for row in data["net"]:
        row.update(quantity=units, buy_quantity=units, day_buy_quantity=units)
    return data


@pytest.mark.usefixtures("app_engine")
async def test_ac3_core_recorded_reply_shows_the_strategys_own_65_and_nothing_outside(app_engine, admin_engine,
                                                                                      monkeypatch):
    """AC-3 core: the recorded +65 reply and the recorded order book (COMPLETE 65), strategy 1 holding its own 65 ->
    one strategy group with its own 65, nothing outside, not blocked; only the two GETs were made."""
    resp, transport, _ = await _run((app_engine, admin_engine), monkeypatch, _reply(RECORDED))
    assert resp.status_code == HTTPStatus.OK, resp.text
    body = resp.json()
    _closed_keys(body)
    assert body["strategies"] == [_group(1, [_own(65, 65)], False)]
    assert (body["has_outside"], body["outside_lots"]) == (False, 0)
    assert body["blocked"] is False and body["blocked_strategy_ids"] == []
    assert [(m, u.rsplit("/", 1)[-1]) for m, u in transport.calls] == [("GET", "positions"), ("GET", "orders")]


@pytest.mark.usefixtures("app_engine")
async def test_adr110_core_open_plan_with_the_order_open_at_zerodha_is_pending(app_engine, admin_engine, monkeypatch):
    """AC-3 / ADR-110 core: plan 1 OPEN, the recorded 12:21 positions (+65) and the (re-tagged) recorded order row
    rewritten to OPEN -> strategy 1's row is pending: Zerodha's 65 as read, plan 1 waiting, units null (never 0),
    strategy 1 blocked, nothing counted outside."""
    resp, _, _ = await _run((app_engine, admin_engine), monkeypatch, _reply(POSITIONS_ENTRY), plans="open",
                            orders=_orders_open())
    assert resp.status_code == HTTPStatus.OK, resp.text
    body = resp.json()
    _closed_keys(body)
    assert body["strategies"] == [_group(1, [_waiting(65, [1])], True)]
    assert (body["has_outside"], body["outside_lots"]) == (False, 0)
    assert body["blocked"] is True and body["blocked_strategy_ids"] == [1]


@pytest.mark.usefixtures("app_engine")
@pytest.mark.parametrize("grammar", ["make_tag", "legacy"])
async def test_adr110_open_plan_with_the_real_complete_row_takes_the_normal_comparison(app_engine, admin_engine,
                                                                                       monkeypatch, grammar):
    """ADR-110: "after Zerodha shows the order COMPLETE the normal comparison applies even if Check is never pressed":
    plan 1 still OPEN, the COMPLETE row (filled 65) -> own 65, not pending, not blocked. Both tag grammars attribute:
    a plan stored with make_tag's Q0001010 against the re-tagged book, and a plan stored with the legacy OFS1V1L0
    against the recorded book exactly as Zerodha sent it (review finding 1)."""
    legacy = grammar == "legacy"
    resp, _, _ = await _run((app_engine, admin_engine), monkeypatch, _reply(POSITIONS_ENTRY),
                            plans="open_legacy" if legacy else "open", orders=_orders(legacy=legacy))
    assert resp.status_code == HTTPStatus.OK, resp.text
    body = resp.json()
    assert body["strategies"] == [_group(1, [_own(65, 65)], False)]
    assert body["blocked"] is False and body["blocked_strategy_ids"] == []


@pytest.mark.usefixtures("app_engine")
async def test_adr110_empty_order_book_keeps_a_closed_plans_stored_fill(app_engine, admin_engine, monkeypatch):
    """Orders answer state EMPTY LIST: a successful read of no orders today (Kite's book holds today's orders only);
    plan 1 closed filled 65 keeps its stored fill -> own 65, not pending, not blocked."""
    resp, _, _ = await _run((app_engine, admin_engine), monkeypatch, _reply(POSITIONS_ENTRY), orders=[])
    assert resp.status_code == HTTPStatus.OK, resp.text
    assert resp.json()["strategies"] == [_group(1, [_own(65, 65)], False)]


@pytest.mark.usefixtures("app_engine")
async def test_adr110_empty_order_book_with_an_open_plan_is_pending(app_engine, admin_engine, monkeypatch):
    """Orders answer state EMPTY LIST with an open plan: its order is not in the book -> pending, blocked (never
    counted as filled, never as outside)."""
    resp, _, _ = await _run((app_engine, admin_engine), monkeypatch, _reply(POSITIONS_ENTRY), plans="open", orders=[])
    assert resp.status_code == HTTPStatus.OK, resp.text
    body = resp.json()
    assert body["strategies"] == [_group(1, [_waiting(65, [1])], True)]
    assert body["has_outside"] is False and body["blocked_strategy_ids"] == [1]


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
    assert "strategies" not in resp.json()
    assert render("gate_broker_unconfirmed").what_happened in resp.text


@pytest.mark.usefixtures("app_engine")
async def test_adr110_two_strategies_on_one_contract_one_pending_blocks_both(app_engine, admin_engine, monkeypatch):
    """ADR-110 + Q224: strategy 1 holds its own 65 (closed, COMPLETE in the book); a second strategy's plan 1 is OPEN on
    the same contract and its tag is not in the book (orders answer state ABSENT) -> the contract is pending for the
    second strategy's plan, no split, and BOTH strategies are blocked (strategy 1 keeps its group for the badge)."""
    resp, _, ids = await _run((app_engine, admin_engine), monkeypatch, _reply(POSITIONS_ENTRY), plans="two_strategies")
    assert resp.status_code == HTTPStatus.OK, resp.text
    body = resp.json()
    _closed_keys(body)
    assert body["strategies"] == [_group(1, [], True), _group(ids["second"], [_waiting(65, [1])], True)]
    assert body["blocked_strategy_ids"] == sorted([1, ids["second"]])
    # What the page reads: the EXACT key sets as literals. frontend/e2e/positions.spec.ts and
    # frontend/tests/positions-page.test.js mock exactly these keys.
    assert set(body) == {"read_at", "strategies", "has_outside", "outside_lots", "blocked", "blocked_strategy_ids"}
    assert set(body["strategies"][1]) == {"strategy_id", "blocked", "contracts"}
    assert set(body["strategies"][1]["contracts"][0]) == {"tradingsymbol", "zerodha_units", "units", "pending",
                                                          "pending_plans"}


@pytest.mark.usefixtures("app_engine")
async def test_adr110_a_pending_strategys_other_contract_shows_its_normal_row_but_blocked(app_engine, admin_engine,
                                                                                          monkeypatch):
    """ADR-110 "The strategy is blocked until the plan closes": strategy 1 holds 65 of the real contract (agreeing
    with Zerodha) and has plan 2 OPEN on a second contract (its tag absent from the 12:21 book) -> one blocked group:
    the real contract's row is normal (own 65), the second contract is pending with Zerodha 0."""
    resp, _, _ = await _run((app_engine, admin_engine), monkeypatch, _reply(POSITIONS_ENTRY), plans="two_contracts")
    assert resp.status_code == HTTPStatus.OK, resp.text
    body = resp.json()
    _closed_keys(body)
    assert body["strategies"] == [_group(1, [_own(65, 65), _waiting(0, [2], SECOND_SYMBOL)], True)]
    assert body["blocked"] is True and body["blocked_strategy_ids"] == [1]


@pytest.mark.usefixtures("app_engine")
async def test_ac3_mixed_zerodha_130_against_own_65_is_own_65_and_one_outside_lot(app_engine, admin_engine,
                                                                                    monkeypatch):
    """Answer state MIXED (attack 2) / ADR-109 (2): Zerodha 130 on one contract, strategy 65 -> the strategy's row
    shows its own 65 (Zerodha 130 as read), the other 65 units are 1 outside lot (lot 65), nothing blocked."""
    resp, _, _ = await _run((app_engine, admin_engine), monkeypatch, _doubled())
    assert resp.status_code == HTTPStatus.OK, resp.text
    body = resp.json()
    assert body["strategies"] == [_group(1, [_own(65, 130)], False)]
    assert (body["has_outside"], body["outside_lots"], body["blocked"]) == (True, 1, False)


@pytest.mark.usefixtures("app_engine")
async def test_ac3_outside_units_not_a_whole_lot_are_shown_without_a_number(app_engine, admin_engine, monkeypatch):
    """Zerodha 95 against own 65: 30 outside units are not a whole lot of 65 -> has_outside, outside_lots null (never a
    rounded guess); the strategy's row is unchanged and nothing is blocked by it."""
    resp, _, _ = await _run((app_engine, admin_engine), monkeypatch, _requantified(95))
    assert resp.status_code == HTTPStatus.OK, resp.text
    body = resp.json()
    assert body["strategies"] == [_group(1, [_own(65, 95)], False)]
    assert (body["has_outside"], body["outside_lots"], body["blocked"]) == (True, None, False)


@pytest.mark.usefixtures("app_engine")
async def test_ac3_zerodha_flat_against_own_65_is_blocked_and_shown(app_engine, admin_engine, monkeypatch):
    """AC-3 / ADR-109 (5): the real flat 15:10:06 book (and its re-tagged order book) while the strategy holds 65 ->
    the strategy's row shows own 65 with Zerodha 0, and the group is blocked (the mismatch badge), not an empty list."""
    resp, _, _ = await _run((app_engine, admin_engine), monkeypatch, _reply(FLAT), orders=_orders(ORDERS_EXIT))
    assert resp.status_code == HTTPStatus.OK, resp.text
    body = resp.json()
    assert body["strategies"] == [_group(1, [_own(65, 0)], True)]
    assert body["blocked"] is True and body["blocked_strategy_ids"] == [1]


@pytest.mark.usefixtures("app_engine")
async def test_ac3_only_outside_positions_are_zero_rows_and_a_count(app_engine, admin_engine, monkeypatch):
    """Answer state ONLY OUTSIDE (attack 1) / ADR-138 (2): the strategy stored no plan; Zerodha +65 -> no strategy
    group, no contract row, "1 outside lot" (65 units, lot 65), nothing blocked."""
    resp, _, _ = await _run((app_engine, admin_engine), monkeypatch, _reply(RECORDED), plans="none")
    assert resp.status_code == HTTPStatus.OK, resp.text
    body = resp.json()
    _closed_keys(body)
    assert body["strategies"] == []
    assert (body["has_outside"], body["outside_lots"], body["blocked"]) == (True, 1, False)
    assert SYMBOL not in resp.text  # the outside contract is never named: no copy of Kite's list


@pytest.mark.usefixtures("app_engine")
async def test_ac3_empty_book_and_no_lots_is_an_empty_list_with_a_read_time(app_engine, admin_engine, monkeypatch):
    """AC-3 (answer state EMPTY): a read that succeeded with no net row and no held lots -> 200, no groups, nothing
    outside."""
    data = {"net": [], "day": []}
    resp, _, _ = await _run((app_engine, admin_engine), monkeypatch, data, plans="none", orders=[])
    assert resp.status_code == HTTPStatus.OK, resp.text
    body = resp.json()
    assert body["strategies"] == [] and body["blocked"] is False and body["read_at"]
    assert (body["has_outside"], body["outside_lots"]) == (False, 0)


@pytest.mark.usefixtures("app_engine")
async def test_ac3_unknown_exchange_is_refused_never_skipped(app_engine, admin_engine, monkeypatch):
    """Answer state UNKNOWN EXCHANGE (attack 3): a non-flat row on an exchange code Kite's adapter does not know ->
    409 gate_broker_unconfirmed, never read as "not ours"."""
    from ofo.errors import render  # noqa: PLC0415

    resp, _, _ = await _run((app_engine, admin_engine), monkeypatch, _with_row(_reply(RECORDED), exchange="NSEFO"))
    assert resp.status_code == HTTPStatus.CONFLICT, resp.text
    assert "strategies" not in resp.json()
    assert render("gate_broker_unconfirmed").what_happened in resp.text


@pytest.mark.usefixtures("app_engine")
async def test_ac3_a_never_ours_row_is_logged_and_not_counted(app_engine, admin_engine, monkeypatch, caplog):
    """Review MINOR 3: a stock row (NSE INFY) is never ours -> one INFO line names it (as the Execute and return routes
    log), it is neither a row nor an outside lot."""
    import logging  # noqa: PLC0415

    caplog.set_level(logging.INFO)
    data = _with_row(_reply(RECORDED), exchange="NSE", tradingsymbol="INFY", product="CNC", instrument_token=408065)
    resp, _, _ = await _run((app_engine, admin_engine), monkeypatch, data)
    assert resp.status_code == HTTPStatus.OK, resp.text
    body = resp.json()
    assert body["strategies"] == [_group(1, [_own(65, 65)], False)]
    assert (body["has_outside"], body["outside_lots"]) == (False, 0)
    lines = [r.getMessage() for r in caplog.records if "ignored" in r.getMessage()]
    assert lines == ["positions read: positions read ignored 1 non-platform rows: NSE:INFY"]


@pytest.mark.usefixtures("app_engine")
async def test_ac3_no_session_is_the_catalogue_message_not_an_empty_list(app_engine, admin_engine, monkeypatch):
    """AC-3 (answer state NO SESSION): 409 with the catalogue's gate_broker_not_connected text; no strategies key."""
    from ofo.errors import render  # noqa: PLC0415

    resp, transport, _ = await _run((app_engine, admin_engine), monkeypatch, _reply(RECORDED), session=False)
    assert resp.status_code == HTTPStatus.CONFLICT, resp.text
    assert "strategies" not in resp.json()
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
    assert "strategies" not in resp.json()
    assert render("gate_broker_unconfirmed").what_happened in resp.text


@pytest.mark.usefixtures("app_engine")
async def test_ac3_client_supplied_units_are_ignored(app_engine, admin_engine, monkeypatch):
    """AC-3 attack 1 / ADR-110 attack 3: held units, outside lots, strategy ids, pending or blocked in the query change
    nothing (the route takes none)."""
    base, _, _ = await _run((app_engine, admin_engine), monkeypatch, _reply(POSITIONS_ENTRY), plans="open",
                            orders=_orders_open())
    forged, _, _ = await _run((app_engine, admin_engine), monkeypatch, _reply(POSITIONS_ENTRY), plans="open",
                              orders=_orders_open(),
                              url="/positions?held_units=999&outside_lots=65&strategy_id=1&blocked=false&pending=false")
    assert forged.status_code == HTTPStatus.OK
    assert {k: v for k, v in forged.json().items() if k != "read_at"} == {
        k: v for k, v in base.json().items() if k != "read_at"}
    assert forged.json()["strategies"][0]["contracts"][0]["pending"] is True


def test_ac3_answer_key_set_is_closed_and_names_no_money_figure():
    """AC-3 attack 4: the declared answer keys are exactly these, and none names a price, P&L, margin or Greek; a
    key added to a model fails here."""
    assert set(PositionsOut.model_fields) == {"read_at", "strategies", "has_outside", "outside_lots", "blocked",
                                              "blocked_strategy_ids"}
    assert set(StrategyPositionsOut.model_fields) == {"strategy_id", "blocked", "contracts"}
    assert set(StrategyContractOut.model_fields) == {"tradingsymbol", "zerodha_units", "units", "pending",
                                                     "pending_plans"}
    for model in (PositionsOut, StrategyPositionsOut, StrategyContractOut):
        for name, field in model.model_fields.items():
            assert not any(word in name for word in FORBIDDEN), name
            assert field.annotation is not D, name


def test_ac3_extra_key_in_an_answer_is_refused():
    """AC-3 attack 4 (mutation): an answer carrying a pnl key does not validate (ApiModel is closed)."""
    row = {"tradingsymbol": SYMBOL, "zerodha_units": 65, "units": 65, "pending": False, "pending_plans": [],
           "pnl": "1.00"}
    with pytest.raises(ValueError):
        StrategyContractOut.model_validate(row)
