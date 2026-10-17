"""W-095 Execute route (REQ-073 AC-1; ADR-050 item 4; ADR-080 (3); REQ-055 AC-3) on the owner's REAL 2026-10-16 order.

Real inputs (tests/fixtures/kite_replies/, README there):
- ``basket-121848.json``: the entry basket the owner sent (NFO NIFTY26O1923650CE BUY LIMIT NRML 65, readonly, OFS1V1L0;
  Zerodha's basket total 354.25 and funds 1003 at that moment).
- ``quote-151720.json``: the real full quote of 15:07:20 (asks 3.35/56810, bids 3.30/55250, band 0.05 - 81.55). The
  recorder wrote money as strings; live Kite REST sends JSON numbers, so ``_live_quote`` turns each money string into
  the Decimal ``parse_float=Decimal`` would give (the W-091 JSON-number variant).
- ``orders-122104.json`` (OFS1V1L0 COMPLETE), ``positions-122104.json`` (+65 held), ``positions-151006.json`` (flat).
- ``tests/fixtures/kite_margins/funds-2026-10-16-122104.json`` and the real exit basket-margin reply recorded in the
  same 15:07 fetch (``final.total`` -214.5, Kite's credit for the exit).
Expected values are ADR-080 (3) by hand: BUY 65 lifts the ask side, 56,810 at 3.35 covers it -> 3.35; SELL 65 hits
the bid side, 55,250 at 3.30 covers it -> 3.30. The tags are the real ones (entry OFS1V1L0, exit OFS1V2L0).
"""
from __future__ import annotations

import copy
import datetime
import json
from decimal import Decimal as D
from pathlib import Path

import pytest
from ofo.engine import Action
from ofo.instruments import NSE_FO, Catalogue, InstrumentId
from ofo.instruments.parser import zerodha_listed
from ofo_app import execute_plan as ep
from ofo_app.kite_margin import KiteMargin
from ofo_app.kite_reads import KiteReads

ROOT = Path(__file__).resolve().parents[1]
REPLIES = ROOT / "tests" / "fixtures" / "kite_replies"
SLICE = json.loads((ROOT / "tests/fixtures/eligibility/instruments-2026-10-16-slice.json").read_text(encoding="utf-8"),
                   parse_float=D)
REAL_BASKET = json.loads((REPLIES / "basket-121848.json").read_text(encoding="utf-8"))
(REAL_ORDER,) = json.loads(REAL_BASKET["data"], parse_float=D)
TOKEN = "12080386"
CORE_ID = InstrumentId(NSE_FO, 47189)
AT = datetime.datetime(2026, 10, 16, 15, 7, 21, tzinfo=datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
_MONEY_KEYS = {"last_price", "average_price", "lower_circuit_limit", "upper_circuit_limit", "price", "open", "high",
               "low", "close", "low_limit_price_protection", "high_limit_price_protection"}


def _live(value: object) -> object:
    if isinstance(value, dict):
        return {k: (D(v) if k in _MONEY_KEYS and isinstance(v, str) else _live(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_live(v) for v in value]
    return value


def _live_quote() -> dict:
    return _live(json.loads((REPLIES / "quote-151720.json").read_text(encoding="utf-8"), parse_float=D))


def _listed():
    row = SLICE["list"][TOKEN]
    return zerodha_listed(
        instrument_token=int(TOKEN), exchange_token=int(TOKEN) >> 8, tradingsymbol=row["symbol"],
        name=row["group"].split()[0], expiry=datetime.date.fromisoformat(row["expiry"]), strike=D(row["strike"]),
        tick_size=D("0.05"), lot_size=int(row["lot"]), instrument_type=row["type"], segment="NFO-OPT", exchange="NFO")


def _catalogue() -> Catalogue:
    cat = Catalogue()
    cat.load([_listed()])
    return cat


def _leg(action: Action, quantity: int = 65) -> ep.LegToPrice:
    return ep.LegToPrice(CORE_ID, action, quantity, None)


# ---- the book floor: today's orders decide the next plan number and whether an earlier basket is still open --------

def _book(status: str, tag: str = "OFS1V1L0") -> list[dict]:
    rows = json.loads((REPLIES / "orders-122104.json").read_text(encoding="utf-8"), parse_float=D)
    rows = rows["data"] if isinstance(rows, dict) else rows
    return [{**rows[0], "status": status, "tag": tag}]


@pytest.mark.parametrize("status", ["OPEN", "TRIGGER PENDING", "AMO REQ RECEIVED", "SOMETHING NEW", ""])
def test_ac1_an_open_or_unknown_status_of_this_strategys_order_is_still_open(status):
    """AC-1: only COMPLETE / CANCELLED / REJECTED are terminal; any other word (unknown included) is open."""
    assert ep.book_floor(_book(status), 1) == (1, True)


@pytest.mark.parametrize("status", ["COMPLETE", "CANCELLED", "REJECTED"])
def test_ac1_a_terminal_order_gives_the_floor_and_nothing_open(status):
    assert ep.book_floor(_book(status), 1) == (1, False)


def test_ac1_the_real_book_gives_floor_1_and_another_strategys_tag_never_counts():
    """The real 12:21 book (OFS1V1L0 COMPLETE) -> floor 1; OFS12V3L0 OPEN is strategy 12, never strategy 1."""
    assert ep.book_floor(_book("COMPLETE"), 1) == (1, False)
    assert ep.book_floor(_book("OPEN", "OFS12V3L0"), 1) == (0, False)
    assert ep.book_floor(_book("OPEN", "OFS12V3L0"), 12) == (3, True)
    assert ep.book_floor(_book("OPEN", "XOFS1V1L0"), 1) == (0, False)
    with pytest.raises(ValueError):
        ep.book_floor(["not a row"], 1)


# ---- ADR-080 (3) pricing on the real depth ---------------------------------------------------------------------------

def test_ac1_real_depth_prices_buy_65_at_3_35_and_sell_65_at_3_30():
    quote = _live_quote()
    buy = ep.price_legs("1", "NIFTY", [_leg(Action.BUY)], _catalogue(), {TOKEN: quote}.get)
    sell = ep.price_legs("1", "NIFTY", [_leg(Action.SELL)], _catalogue(), {TOKEN: quote}.get)
    ((b,), (s,)) = buy.plan.legs, sell.plan.legs
    assert (b.contract, b.leg.action, b.leg.quantity, b.leg.entry_price) == (REAL_ORDER["tradingsymbol"], Action.BUY,
                                                                             65, D("3.35"))
    assert (s.leg.action, s.leg.entry_price) == (Action.SELL, D("3.30"))
    assert buy.quote_times == (datetime.datetime(2026, 10, 16, 15, 7, 20, tzinfo=AT.tzinfo),)
    assert list(buy.price_bands.values()) == [(D("0.05"), D("81.55"))]


def test_ac1_no_quote_thin_depth_and_outside_the_band_are_refused_never_priced_from_the_plan():
    cat, quote = _catalogue(), _live_quote()
    with pytest.raises(ep.LegRefused):
        ep.price_legs("1", "NIFTY", [ep.LegToPrice(CORE_ID, Action.BUY, 65, D("5.45"))], cat, {}.get)
    with pytest.raises(ep.LegRefused):  # 5 ask levels hold 264,420; 300,000 cannot fill
        ep.price_legs("1", "NIFTY", [_leg(Action.BUY, 300_000)], cat, {TOKEN: quote}.get)
    banded = copy.deepcopy(quote)
    banded["upper_circuit_limit"] = D("3.30")
    with pytest.raises(ep.LegRefused) as caught:
        ep.price_legs("1", "NIFTY", [_leg(Action.BUY)], cat, {TOKEN: banded}.get)
    assert "outside today's price band" in caught.value.message.what_happened
    no_time = {k: v for k, v in quote.items() if k != "timestamp"}
    with pytest.raises(ep.LegRefused):
        ep.price_legs("1", "NIFTY", [_leg(Action.BUY)], cat, {TOKEN: no_time}.get)


def test_ac1_broker_mismatch_on_this_strategys_contract_blocks():
    key = ("NIFTY", "CE", D("23650"), datetime.date(2026, 10, 19))
    assert ep.broker_mismatch({key: 65}, {key: 65}, [key]) is False
    assert ep.broker_mismatch({key: 130}, {key: 65}, [key]) is True
    assert ep.broker_mismatch({}, {key: 65}, [key]) is True
    assert ep.broker_mismatch({key: 65}, {}, [key]) is True


# ---- the route on the database (core proof) -------------------------------------------------------------------------

class _Replay:
    """Fake transport for both Zerodha clients, answering with recorded replies."""

    def __init__(self, *, funds: str, basket_total: str, orders: str | None, positions: str) -> None:
        self.funds, self.basket_total, self.orders, self.positions = funds, basket_total, orders, positions
        self.calls: list[tuple[str, str]] = []

    def _reply(self, name: str) -> dict:
        return json.loads((REPLIES / f"{name}.json").read_text(encoding="utf-8"), parse_float=D)

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url))
        if url.endswith("/user/margins"):
            return 200, '{"status": "success", "data": {"equity": {"enabled": true, "net": %s}}}' % self.funds  # noqa: UP031
        if "/margins/basket" in url:
            return 200, _basket_reply(self.basket_total)
        if url.endswith("/orders"):
            data = [] if self.orders is None else _rows(self._reply(self.orders))
            return 200, json.dumps({"status": "success", "data": data}, default=str)
        if url.endswith("/portfolio/positions"):
            data = self._reply(self.positions)
            data = data.get("data", data)
            return 200, json.dumps({"status": "success", "data": data}, default=str)
        raise AssertionError(url)


def _rows(reply):
    return reply["data"] if isinstance(reply, dict) and "data" in reply else reply


def _basket_reply(total: str) -> str:
    """The shape of the real 15:07 basket-margin reply (fetch.json margin_raw), with ``final.total`` set to the
    recorded figure of the basket in question (entry 354.25 from basket-121848.json; exit -214.5 as recorded)."""
    return ('{"status":"success","data":{"initial":{"total":0},"final":{"option_premium":0,"total":%s},'  # noqa: UP031
            '"orders":[{"total":0}],"charges":{"total":0}}}' % total)


@pytest.mark.usefixtures("app_engine")
async def test_core_real_order_entry_then_exit(app_engine, monkeypatch):
    """AC-1 core: ENTRY -> BUY 65 LIMIT 3.35 tagged OFS1V1L0 (plan 1 stored open); plan 1 closed filled -> EXIT ->
    SELL 65 LIMIT 3.30 tagged OFS1V2L0. Every other field equals the owner's real basket."""
    from ofo_app import execution_plan_store as plans  # noqa: PLC0415
    from ofo_app.catalogue_store import apply_update  # noqa: PLC0415
    from ofo_app.routes import execute as route  # noqa: PLC0415
    from ofo_app.strategy_store import build_definition, save_draft  # noqa: PLC0415
    from ofo.strategy import stored_form as sf  # noqa: PLC0415
    from sqlalchemy import text  # noqa: PLC0415
    from test_strategy_followups import _ConnMaker  # noqa: PLC0415
    from test_strategy_store import _app, _client, _user  # noqa: PLC0415

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("TEST_CATALOGUE_DATE", "2026-10-16")
    quote = _live_quote()

    class _Quotes:
        def leg_quote(self, token):
            return quote if token == TOKEN else None

        def underlying_price(self, underlying):
            return (D("23094.95"), datetime.datetime(2026, 10, 16, 15, 7, 17, tzinfo=AT.tzinfo))  # fetch.json spot

    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await apply_update(conn, [_listed()], as_of=datetime.datetime(2026, 10, 16, 9, 0, tzinfo=AT.tzinfo))
            cid = (await conn.execute(text("SELECT c.id FROM public.catalogue_contracts c JOIN public.broker_instruments"
                                           " b ON b.contract_id = c.id WHERE b.broker_symbol = :s AND NOT c.retired"),
                                      {"s": REAL_ORDER["tradingsymbol"]})).scalar_one()
            user = _user()
            saved = await build_definition(conn, "NIFTY", [sf.LegChoice(int(cid), Action.BUY, 65, None)],
                                           rules_ref=None, risk_limits={}, preferences={})
            strategy = await save_draft(conn, user, saved)

            def session_for(replay):
                class _S:
                    api_key = "kitekey"
                    reads = KiteReads(api_key="kitekey", access_token="tok", transport=replay)  # noqa: S106
                    margin = KiteMargin(api_key="kitekey", access_token="tok", transport=replay)  # noqa: S106
                return _S()

            app = _app(_ConnMaker(conn), user)
            app.dependency_overrides[route.get_quote_reader] = lambda: _Quotes()
            app.dependency_overrides[route.get_execute_clock] = lambda: (lambda: AT)
            entry = _Replay(funds="1003", basket_total="354.25", orders=None, positions="positions-151006")
            app.dependency_overrides[route.get_kite_session] = lambda: session_for(entry)
            async with _client(app) as ac:
                resp = await ac.post(f"/strategies/{strategy.id}/execute", json={"action": "ENTRY"})
            assert resp.status_code == 200, resp.text
            body = resp.json()
            (order,) = body["orders"]
            assert body["plan_number"] == 1 and body["tags"] == [REAL_ORDER["tag"]]
            for key in ("exchange", "tradingsymbol", "transaction_type", "order_type", "product", "quantity",
                        "readonly", "tag", "variety"):
                assert order[key] == REAL_ORDER[key], key
            assert order["price"] == "3.35"
            (open_plan,) = await plans.plans_for(conn, user, strategy.id)
            assert open_plan.plan_number == 1 and open_plan.closed_reason is None

            again = await _post(app, strategy.id, "ENTRY")  # one open plan per strategy
            assert again.status_code == 409, again.text

            await plans.close_plan(conn, user, strategy.id, 1, reason="filled")
            exit_replay = _Replay(funds="671.5", basket_total="-214.5", orders="orders-122104",
                                  positions="positions-122104")
            app.dependency_overrides[route.get_kite_session] = lambda: session_for(exit_replay)
            resp = await _post(app, strategy.id, "EXIT")
            assert resp.status_code == 200, resp.text
            (sell,) = resp.json()["orders"]
            assert (sell["transaction_type"], sell["quantity"], sell["price"], sell["tag"]) == ("SELL", 65, "3.30",
                                                                                              "OFS1V2L0")
        finally:
            await trans.rollback()


async def _post(app, strategy_id: int, action: str):
    from test_strategy_store import _client  # noqa: PLC0415

    async with _client(app) as ac:
        return await ac.post(f"/strategies/{strategy_id}/execute", json={"action": action})
