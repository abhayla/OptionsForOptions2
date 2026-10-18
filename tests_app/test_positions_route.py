"""W-111 (REQ-044 AC-3 part 1; ADR-109 (2), (5)): the Positions read on the owner's REAL 2026-10-16 replies.

Expected values come from the recorded files and ADR-109's examples: kite_positions/positions-2026-10-16-one-ce.json
is NIFTY26O1923650CE net +65 at 12:21; kite_replies/positions-151006.json is the flat row (quantity 0) at 15:10:06.
Strategy 1 holds its own 65 (plan 1 filled 65 of 65, tag OFS1V1L0). The 130 case is the recorded
row with its quantities doubled by hand (ADR-109: "strategy BUY 65 CE, Zerodha 130 -> not blocked, 65
outside"). Every answer state of the read has a test: present, absent (flat), empty, failed, no session.
"""
from __future__ import annotations

import copy
import json
from decimal import Decimal as D
from http import HTTPStatus
from pathlib import Path

import pytest
from ofo_app.routes.positions import OwnLotsOut, PositionContractOut, PositionsOut

ROOT = Path(__file__).resolve().parent.parent
RECORDED = ROOT / "tests" / "fixtures" / "kite_positions" / "positions-2026-10-16-one-ce.json"
FLAT = ROOT / "tests" / "fixtures" / "kite_replies" / "positions-151006.json"
SYMBOL = "NIFTY26O1923650CE"
FORBIDDEN = ("price", "pnl", "p_and_l", "margin", "greek", "delta", "gamma", "theta", "vega", "value", "premium",
             "cost", "money", "charge", "m2m", "realised", "unrealised", "order")


def _reply(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"), parse_float=D)["data"]
    return {"day": [], **data}  # Zerodha always sends both lists; the one-row fixture keeps only 'net'


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
    """Answers GET /portfolio/positions with one reply; anything else (a write, another read) fails the test."""

    def __init__(self, data: dict | None, status: int = 200) -> None:
        self.data, self.status, self.calls = data, status, []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url))
        assert method == "GET" and body is None and url.endswith("/portfolio/positions"), (method, url)
        if self.status != HTTPStatus.OK:
            return self.status, json.dumps({"status": "error", "message": "x", "error_type": "TokenException"})
        return 200, json.dumps({"status": "success", "data": self.data}, default=str)


def _session(transport: _Transport):
    from ofo_app.kite_reads import KiteReads  # noqa: PLC0415

    kite_reads = KiteReads(api_key="kitekey", access_token="tok", transport=transport)  # noqa: S106

    class _S:
        api_key = "kitekey"
        reads = kite_reads
        margin = None  # nothing here can place an order
    return _S()


def _app_for(conn, user, transport: _Transport | None):
    import datetime  # noqa: PLC0415

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


async def _filled_plan(conn, user, sid: int) -> None:
    """Plan 1 (BUY 65 of the real contract, tag OFS1V1L0), closed filled 65 of 65."""
    from ofo.execution.basket import make_tag  # noqa: PLC0415
    from ofo_app import execution_plan_store as plans  # noqa: PLC0415
    from ofo_app.execution_plan_store import PlanOrder  # noqa: PLC0415
    from test_execute_route import CORE_ID  # noqa: PLC0415

    tag = make_tag(sid, 1, 0)
    order = PlanOrder(0, tag, f"{CORE_ID.exchange_segment}:{CORE_ID.exchange_token}", SYMBOL, "BUY", 65, D("5.45"))
    await plans.record_plan(conn, user, sid, 1, "ENTRY", (order,))
    await plans.close_plan(conn, user, sid, 1, reason="filled", filled={tag: 65})


async def _world(conn, app_engine, monkeypatch, *, with_plan: bool = True):
    from test_execute_route import _strategy_one  # noqa: PLC0415
    from test_strategy_store import _user  # noqa: PLC0415

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("TEST_CATALOGUE_DATE", "2026-10-16")
    user = _user()
    sid = await _strategy_one(conn, user, app_engine.url.username)
    if with_plan:
        await _filled_plan(conn, user, sid)
    return user, sid


def _closed_keys(node) -> None:
    """Every object in an answer is one of the declared shapes (exact key sets), and no key names a money figure."""
    shapes = {"top": set(PositionsOut.model_fields), "contract": set(PositionContractOut.model_fields),
              "own": set(OwnLotsOut.model_fields)}
    assert set(node) == shapes["top"]
    for row in node["contracts"]:
        assert set(row) == shapes["contract"]
        for own in row["own"]:
            assert set(own) == shapes["own"]


async def _run(engines, monkeypatch, data, *, url="/positions", **opts):
    """opts: with_plan (default True), status (Kite's answer status, default 200), session (default True)."""
    with_plan, status, session = opts.get("with_plan", True), opts.get("status", 200), opts.get("session", True)
    app_engine, admin_engine = engines
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            user, _ = await _world(conn, app_engine, monkeypatch, with_plan=with_plan)
            transport = _Transport(data, status)
            resp = await _get(_app_for(conn, user, transport if session else None), url)
            return resp, transport
        finally:
            await trans.rollback()


@pytest.mark.usefixtures("app_engine")
async def test_ac3_core_recorded_reply_shows_the_strategys_own_65_and_nothing_outside(app_engine, admin_engine,
                                                                                      monkeypatch):
    """AC-3 core: the recorded +65 reply, strategy 1 holding its own 65 -> one contract, own 65 for strategy 1, 0
    outside, not blocked; only a GET was made."""
    resp, transport = await _run((app_engine, admin_engine), monkeypatch, _reply(RECORDED))
    assert resp.status_code == HTTPStatus.OK, resp.text
    body = resp.json()
    _closed_keys(body)
    assert body["contracts"] == [{"tradingsymbol": SYMBOL, "zerodha_units": 65, "outside_units": 0, "blocked": False,
                                  "own_units": 65, "own": [{"strategy_id": 1, "units": 65, "blocked": False}]}]
    assert body["blocked"] is False
    assert transport.calls == [("GET", transport.calls[0][1])]


@pytest.mark.usefixtures("app_engine")
async def test_ac3_zerodha_130_against_own_65_shows_65_outside_no_block(app_engine, admin_engine, monkeypatch):
    """AC-3 / ADR-109 (2): Zerodha 130, strategy 65 -> own 65, outside 65, strategy not blocked."""
    resp, _ = await _run((app_engine, admin_engine), monkeypatch, _doubled())
    assert resp.status_code == HTTPStatus.OK, resp.text
    (row,) = resp.json()["contracts"]
    assert (row["zerodha_units"], row["outside_units"], row["blocked"]) == (130, 65, False)
    assert row["own"] == [{"strategy_id": 1, "units": 65, "blocked": False}]
    assert resp.json()["blocked"] is False


@pytest.mark.usefixtures("app_engine")
async def test_ac3_zerodha_flat_against_own_65_is_blocked_and_shown(app_engine, admin_engine, monkeypatch):
    """AC-3 / ADR-109 (5): the real flat 15:10:06 book while the strategy holds 65 -> the contract is listed with
    Zerodha 0, own 65 and blocked (not an empty list)."""
    resp, _ = await _run((app_engine, admin_engine), monkeypatch, _reply(FLAT))
    assert resp.status_code == HTTPStatus.OK, resp.text
    body = resp.json()
    assert body["contracts"] == [{"tradingsymbol": SYMBOL, "zerodha_units": 0, "outside_units": 0, "blocked": True,
                                  "own_units": 65, "own": [{"strategy_id": 1, "units": 65, "blocked": True}]}]
    assert body["blocked"] is True


@pytest.mark.usefixtures("app_engine")
async def test_ac3_a_position_in_no_strategy_is_all_outside(app_engine, admin_engine, monkeypatch):
    """AC-3 / ADR-109 (2): the strategy stored no plan; Zerodha +65 -> 65 outside, no own lots, nothing blocked."""
    resp, _ = await _run((app_engine, admin_engine), monkeypatch, _reply(RECORDED), with_plan=False)
    assert resp.status_code == HTTPStatus.OK, resp.text
    assert resp.json()["contracts"] == [{"tradingsymbol": SYMBOL, "zerodha_units": 65, "outside_units": 65,
                                         "blocked": False, "own": [], "own_units": 0}]


@pytest.mark.usefixtures("app_engine")
async def test_ac3_empty_book_and_no_lots_is_an_empty_list_with_a_read_time(app_engine, admin_engine, monkeypatch):
    """AC-3 (answer state EMPTY): a read that succeeded with no net row and no held lots -> 200 with no contracts."""
    data = {"net": [], "day": []}
    resp, _ = await _run((app_engine, admin_engine), monkeypatch, data, with_plan=False)
    assert resp.status_code == HTTPStatus.OK, resp.text
    body = resp.json()
    assert body["contracts"] == [] and body["blocked"] is False and body["read_at"]


@pytest.mark.usefixtures("app_engine")
async def test_ac3_no_session_is_the_catalogue_message_not_an_empty_list(app_engine, admin_engine, monkeypatch):
    """AC-3 (answer state NO SESSION): 409 with the catalogue's gate_broker_not_connected text; no contracts key."""
    from ofo.errors import render  # noqa: PLC0415

    resp, transport = await _run((app_engine, admin_engine), monkeypatch, _reply(RECORDED), session=False)
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
    resp, _ = await _run((app_engine, admin_engine), monkeypatch, data, **kwargs)
    assert resp.status_code == HTTPStatus.CONFLICT, resp.text
    assert "contracts" not in resp.json()
    assert render("gate_broker_unconfirmed").what_happened in resp.text


@pytest.mark.usefixtures("app_engine")
async def test_ac3_client_supplied_units_are_ignored(app_engine, admin_engine, monkeypatch):
    """AC-3 attack 1: held units / outside lots / strategy ids in the query change nothing (the route takes none)."""
    base, _ = await _run((app_engine, admin_engine), monkeypatch, _reply(RECORDED))
    forged, _ = await _run((app_engine, admin_engine), monkeypatch, _reply(RECORDED),
                           url="/positions?held_units=999&outside_units=65&strategy_id=1&blocked=true")
    assert forged.status_code == HTTPStatus.OK
    assert {k: v for k, v in forged.json().items() if k != "read_at"} == {
        k: v for k, v in base.json().items() if k != "read_at"}


def test_ac3_answer_key_set_is_closed_and_names_no_money_figure():
    """AC-3 attack 4: the declared answer keys are exactly these, and none names a price, P&L, margin or Greek; a
    key added to a model fails here."""
    assert set(PositionsOut.model_fields) == {"read_at", "contracts", "blocked"}
    assert set(PositionContractOut.model_fields) == {"tradingsymbol", "zerodha_units", "own", "own_units",
                                                     "outside_units", "blocked"}
    assert set(OwnLotsOut.model_fields) == {"strategy_id", "units", "blocked"}
    for model in (PositionsOut, PositionContractOut, OwnLotsOut):
        for name, field in model.model_fields.items():
            assert not any(word in name for word in FORBIDDEN), name
            assert field.annotation is not D, name


def test_ac3_extra_key_in_an_answer_is_refused():
    """AC-3 attack 4 (mutation): an answer carrying a pnl key does not validate (ApiModel is closed)."""
    row = {"strategy_id": 1, "units": 65, "blocked": False, "pnl": "1.00"}
    with pytest.raises(ValueError):
        OwnLotsOut.model_validate(row)
