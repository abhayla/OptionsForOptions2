"""W-095 Execute route (REQ-073 AC-1; ADR-050 item 4; ADR-080 (3); REQ-055 AC-3; REQ-060 AC-7) on the owner's REAL
2026-10-16 order.

Real inputs (tests/fixtures/kite_replies/, README there):
- ``basket-121848.json``: the entry basket the owner sent (NFO NIFTY26O1923650CE BUY LIMIT NRML 65, readonly, OFS1V1L0;
  Zerodha's basket total 354.25 and funds 1003 at that moment).
- ``quote-151720.json``: the real full quote of 15:07:20 (asks 3.35/56810, bids 3.30/55250, band 0.05 - 81.55). The
  recorder wrote money as strings; live Kite REST sends JSON numbers, so ``_live_quote`` turns each money string into
  the Decimal ``parse_float=Decimal`` would give (the W-091 JSON-number variant).
- ``orders-122104.json`` (OFS1V1L0 COMPLETE), ``positions-122104.json`` (+65 held), ``positions-151006.json`` (flat).
Expected values are ADR-080 (3) by hand: BUY 65 lifts the ask side, 56,810 at 3.35 covers it -> 3.35; SELL 65 hits
the bid side, 55,250 at 3.30 covers it -> 3.30. The tags are the real ones (entry OFS1V1L0, exit OFS1V2L0): strategy
id 1 is inserted with that explicit id (owner role, inside the rolled-back transaction; the route then runs as the
limited application role via ``SET LOCAL ROLE``).
"""
from __future__ import annotations

import copy
import datetime
import json
from decimal import Decimal as D
from pathlib import Path

import pytest
from ofo.engine import Action, Instrument
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
KEY = ("NIFTY", Instrument.CE, D("23650"), datetime.date(2026, 10, 19))
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


def _quotes(quote: object):
    return lambda iid, token: ep.quote_from_kite(quote) if token == TOKEN else None


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
    buy = ep.price_legs("1", "NIFTY", [_leg(Action.BUY)], _catalogue(), _quotes(quote))
    sell = ep.price_legs("1", "NIFTY", [_leg(Action.SELL)], _catalogue(), _quotes(quote))
    ((b,), (s,)) = buy.plan.legs, sell.plan.legs
    assert (b.contract, b.leg.action, b.leg.quantity, b.leg.entry_price) == (REAL_ORDER["tradingsymbol"], Action.BUY,
                                                                             65, D("3.35"))
    assert (s.leg.action, s.leg.entry_price) == (Action.SELL, D("3.30"))
    assert buy.quote_times == (datetime.datetime(2026, 10, 16, 15, 7, 20, tzinfo=AT.tzinfo),)
    assert list(buy.price_bands.values()) == [(D("0.05"), D("81.55"))]


def test_ac1_no_quote_thin_depth_and_outside_the_band_are_refused_never_priced_from_the_plan():
    cat, quote = _catalogue(), _live_quote()
    with pytest.raises(ep.LegRefused):
        ep.price_legs("1", "NIFTY", [ep.LegToPrice(CORE_ID, Action.BUY, 65, D("5.45"))], cat, lambda i, t: None)
    with pytest.raises(ep.LegRefused):  # 5 ask levels hold 264,420; 300,000 cannot fill
        ep.price_legs("1", "NIFTY", [_leg(Action.BUY, 300_000)], cat, _quotes(quote))
    banded = copy.deepcopy(quote)
    banded["upper_circuit_limit"] = D("3.30")
    with pytest.raises(ep.LegRefused) as caught:
        ep.price_legs("1", "NIFTY", [_leg(Action.BUY)], cat, _quotes(banded))
    assert "outside today's price band" in caught.value.message.what_happened
    no_time = {k: v for k, v in quote.items() if k != "timestamp"}
    with pytest.raises(ep.LegRefused):
        ep.price_legs("1", "NIFTY", [_leg(Action.BUY)], cat, _quotes(no_time))


def test_ac1_a_depth_source_without_a_band_prices_the_leg_and_leaves_the_band_to_the_gate():
    """The live feed (W-097) carries depth only: the leg is priced from depth, no band is invented (the gate blocks an
    entry leg as band-unknown, ``safety._price_failures``)."""
    live = ep.quote_from_kite(_live_quote())
    depth_only = ep.LegQuote(live.depth, live.at, live.last_price, None)
    priced = ep.price_legs("1", "NIFTY", [_leg(Action.BUY)], _catalogue(), lambda i, t: depth_only)
    assert priced.plan.legs[0].leg.entry_price == D("3.35") and dict(priced.price_bands) == {}
    no_base = ep.LegQuote(live.depth, live.at, None, None)
    with pytest.raises(ep.LegRefused):  # no planned entry and no last price: refused, never a guessed base
        ep.price_legs("1", "NIFTY", [_leg(Action.BUY)], _catalogue(), lambda i, t: no_base)


# ---- REQ-060 AC-7: who a broker difference blocks -------------------------------------------------------------------

def test_ac7_units_beyond_the_strategy_block_nothing():
    """A position in no strategy (Zerodha 130, the strategy 65 BUY) is offered the grouping choice, blocks nothing."""
    assert ep.strategy_blocked({KEY: 65}, {KEY: 65}) is False
    assert ep.strategy_blocked({KEY: 130}, {KEY: 65}) is False
    assert ep.strategy_blocked({KEY: -130}, {KEY: -65}) is False
    assert ep.strategy_blocked({KEY: 65}, {}) is False  # nothing held by the strategy: an entry is never blocked


def test_ac7_a_shortfall_blocks_the_strategy():
    assert ep.strategy_blocked({}, {KEY: 65}) is True  # the real 15:10 flat book against a filled entry
    assert ep.strategy_blocked({KEY: 64}, {KEY: 65}) is True
    assert ep.strategy_blocked({KEY: -64}, {KEY: -65}) is True


def test_ac7_the_opposite_side_blocks_the_strategy():
    assert ep.strategy_blocked({KEY: -65}, {KEY: 65}) is True
    assert ep.strategy_blocked({KEY: 130}, {KEY: -65}) is True


# ---- the response carries the exact Kite form text, only from a real basket -----------------------------------------

def _real_basket():
    from ofo.execution.basket import build_basket  # noqa: PLC0415
    from ofo.execution.freeze import FreezeCheck  # noqa: PLC0415

    priced = ep.price_legs("1", "NIFTY", [_leg(Action.BUY)], _catalogue(), _quotes(_live_quote()))

    class _Funds:
        def available_funds(self):
            return D("1003")

        def zerodha_required(self, orders):
            return D("354.25")

    return build_basket(priced.plan, _catalogue(), 1, freeze_check=lambda p: FreezeCheck((), ()),
                        margin_source=_Funds())


def test_ac1_basket_post_is_the_real_basket_text_and_nothing_else():
    from ofo_app.basket_post import BasketPost, BasketPostRefused, _check  # noqa: PLC0415

    basket = _real_basket()
    post = BasketPost.of(basket, "kitekey")
    form = post.as_form()
    assert form["url"] == "https://kite.zerodha.com/connect/basket" and form["api_key"] == "kitekey"
    (sent,) = json.loads(form["data"], parse_float=D)
    assert {k: v for k, v in sent.items() if k != "price"} == {k: v for k, v in REAL_ORDER.items() if k != "price"}
    assert sent["price"] == D("3.35")
    with pytest.raises(TypeError):
        BasketPost("kitekey", form["data"], ("OFS1V1L0",))
    with pytest.raises(TypeError):
        BasketPost.of(tuple(basket), "kitekey")
    for tampered in (form["data"].replace('"readonly": true', '"readonly": false'),
                     form["data"].replace("OFS1V1L0", "OFS1V9L0"), form["data"].replace("3.35", "3.4"),
                     form["data"].replace(', "tag": "OFS1V1L0"', "")):
        with pytest.raises(BasketPostRefused):
            _check(tampered, basket)


# ---- the route on the database (core proof) -------------------------------------------------------------------------

class _Replay:
    """Fake transport for both Zerodha clients, answering with recorded replies."""

    def __init__(self, *, funds: str, basket_total: str, orders: str | None, positions: str) -> None:
        self.funds, self.basket_total, self.orders, self.positions = funds, basket_total, orders, positions

    def _reply(self, name: str) -> dict:
        return json.loads((REPLIES / f"{name}.json").read_text(encoding="utf-8"), parse_float=D)

    def __call__(self, method, url, headers, body):
        if url.endswith("/user/margins"):
            return 200, '{"status": "success", "data": {"equity": {"enabled": true, "net": %s}}}' % self.funds  # noqa: UP031
        if "/margins/basket" in url:
            return 200, _basket_reply(self.basket_total)
        if url.endswith("/orders"):
            data = [] if self.orders is None else _rows(self._reply(self.orders))
            return 200, json.dumps({"status": "success", "data": data}, default=str)
        if url.endswith("/portfolio/positions"):
            data = self._reply(self.positions)
            return 200, json.dumps({"status": "success", "data": data.get("data", data)}, default=str)
        raise AssertionError(url)


def _rows(reply):
    return reply["data"] if isinstance(reply, dict) and "data" in reply else reply


def _basket_reply(total: str) -> str:
    """The shape of the real 15:07 basket-margin reply (fetch.json margin_raw), with ``final.total`` set to the
    recorded figure of the basket in question (entry 354.25 from basket-121848.json; exit -214.5 as recorded)."""
    return ('{"status":"success","data":{"initial":{"total":0},"final":{"option_premium":0,"total":%s},'  # noqa: UP031
            '"orders":[{"total":0}],"charges":{"total":0}}}' % total)


def _session_for(replay):
    class _S:
        api_key = "kitekey"
        reads = KiteReads(api_key="kitekey", access_token="tok", transport=replay)  # noqa: S106
        margin = KiteMargin(api_key="kitekey", access_token="tok", transport=replay)  # noqa: S106
    return _S()


class _Quotes:
    def __init__(self) -> None:
        self.quote = ep.quote_from_kite(_live_quote())

    def leg_quote(self, instrument_id, token):
        return self.quote if token == TOKEN else None

    def underlying_price(self, underlying):
        return (D("23094.95"), datetime.datetime(2026, 10, 16, 15, 7, 17, tzinfo=AT.tzinfo))  # fetch.json spot


async def _strategy_one(conn, user: str, app_role: str) -> int:
    """Strategy id 1 (the real tags OFS1V1...): saved through the store, then given id 1 as the owner role (the
    application role cannot write ``id``), then the transaction continues as the application role."""
    from ofo.strategy import stored_form as sf  # noqa: PLC0415
    from ofo_app.catalogue_store import apply_update  # noqa: PLC0415
    from ofo_app.strategy_store import build_definition, save_draft  # noqa: PLC0415
    from sqlalchemy import text  # noqa: PLC0415

    taken = (await conn.execute(text("SELECT user_ref FROM public.strategies WHERE id = 1"))).first()
    if taken is not None:
        pytest.fail(f"strategy id 1 is already stored in the shared test DB (user {taken[0]!r}); the core needs it")
    await apply_update(conn, [_listed()], as_of=datetime.datetime(2026, 10, 16, 9, 0, tzinfo=AT.tzinfo))
    cid = (await conn.execute(text("SELECT c.id FROM public.catalogue_contracts c JOIN public.broker_instruments b "
                                   "ON b.contract_id = c.id WHERE b.broker_symbol = :s AND NOT c.retired"),
                              {"s": REAL_ORDER["tradingsymbol"]})).scalar_one()
    saved = await build_definition(conn, "NIFTY", [sf.LegChoice(int(cid), Action.BUY, 65, None)],
                                   rules_ref=None, risk_limits={}, preferences={})
    made = await save_draft(conn, user, saved)
    await conn.execute(text("SET LOCAL session_replication_role = replica"))
    await conn.execute(text("UPDATE public.strategies SET id = 1 WHERE id = :s"), {"s": made.id})
    await conn.execute(text("UPDATE public.strategy_history SET strategy_id = 1 WHERE strategy_id = :s"),
                       {"s": made.id})
    await conn.execute(text("SET LOCAL session_replication_role = origin"))
    await conn.execute(text(f'SET LOCAL ROLE "{app_role}"'))
    return 1


async def _post(app, strategy_id: int, action: str):
    from test_strategy_store import _client  # noqa: PLC0415

    async with _client(app) as ac:
        return await ac.post(f"/strategies/{strategy_id}/execute", json={"action": action})


@pytest.mark.usefixtures("app_engine")
async def test_core_real_order_entry_then_exit(app_engine, admin_engine, monkeypatch):
    """AC-1 core: ENTRY -> BUY 65 LIMIT 3.35 tagged OFS1V1L0 (plan 1 stored open); a re-press is refused (one open
    plan); plan 1 closed filled 65 -> EXIT on the real FLAT 15:10 book is refused (AC-7 shortfall); EXIT on the real
    +65 book -> SELL 65 LIMIT 3.30 tagged OFS1V2L0 (plan 2 stored open). Every other field equals the real basket."""
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
            entry = _Replay(funds="1003", basket_total="354.25", orders=None, positions="positions-151006")
            app.dependency_overrides[route.get_kite_session] = lambda: _session_for(entry)
            resp = await _post(app, sid, "ENTRY")
            assert resp.status_code == 200, resp.text
            body = resp.json()
            (order,) = body["orders"]
            assert body["plan_number"] == 1 and body["tags"] == [REAL_ORDER["tag"]]
            for key in ("exchange", "tradingsymbol", "transaction_type", "order_type", "product", "quantity",
                        "readonly", "tag", "variety"):
                assert order[key] == REAL_ORDER[key], key
            assert order["price"] == "3.35"
            (sent,) = json.loads(body["basket"]["data"], parse_float=D)
            assert {k: v for k, v in sent.items() if k != "price"} == {k: v for k, v in REAL_ORDER.items()
                                                                        if k != "price"}
            assert sent["price"] == D("3.35") and body["basket"]["api_key"] == "kitekey"
            (open_plan,) = await plans.plans_for(conn, user, sid)
            assert (open_plan.plan_number, open_plan.status, open_plan.orders[0].tag) == (1, "open", "OFS1V1L0")

            again = await _post(app, sid, "ENTRY")  # one open plan per strategy
            assert again.status_code == 409, again.text

            await plans.close_plan(conn, user, sid, 1, reason="filled", filled={"OFS1V1L0": 65})
            flat = _Replay(funds="671.5", basket_total="-214.5", orders="orders-122104", positions="positions-151006")
            app.dependency_overrides[route.get_kite_session] = lambda: _session_for(flat)
            short = await _post(app, sid, "EXIT")  # Zerodha holds 0 of the strategy's 65: blocked (AC-7)
            assert short.status_code == 409, short.text
            assert len(await plans.plans_for(conn, user, sid)) == 1  # nothing stored, no number consumed

            held = _Replay(funds="671.5", basket_total="-214.5", orders="orders-122104", positions="positions-122104")
            app.dependency_overrides[route.get_kite_session] = lambda: _session_for(held)
            resp = await _post(app, sid, "EXIT")
            assert resp.status_code == 200, resp.text
            (sell,) = resp.json()["orders"]
            assert (sell["transaction_type"], sell["quantity"], sell["price"], sell["tag"]) == ("SELL", 65, "3.30",
                                                                                              "OFS1V2L0")
            stored = await plans.plans_for(conn, user, sid)
            assert [(p.plan_number, p.action, p.status) for p in stored] == [(1, "ENTRY", "closed"),
                                                                             (2, "EXIT", "open")]
        finally:
            await trans.rollback()


@pytest.mark.usefixtures("app_engine")
async def test_two_interleaved_exits_give_one_basket_and_refuse_the_other(app_engine, admin_engine, monkeypatch):
    """Two EXIT presses that BOTH pass ``next_plan_number`` before either stores (the interleaving the strategy row
    lock prevents across connections): exactly one basket is answered and stored; the other is refused 409."""
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
            entry = _Replay(funds="1003", basket_total="354.25", orders=None, positions="positions-151006")
            app.dependency_overrides[route.get_kite_session] = lambda: _session_for(entry)
            assert (await _post(app, sid, "ENTRY")).status_code == 200
            await plans.close_plan(conn, user, sid, 1, reason="filled", filled={"OFS1V1L0": 65})
            held = _Replay(funds="671.5", basket_total="-214.5", orders="orders-122104", positions="positions-122104")
            app.dependency_overrides[route.get_kite_session] = lambda: _session_for(held)

            real_record, inner = plans.record_plan, []

            async def _second_press_first(*args, **kwargs):
                if not inner:  # the first press, between its number and its store: the second press runs whole
                    inner.append(await _post(app, sid, "EXIT"))
                return await real_record(*args, **kwargs)

            monkeypatch.setattr(plans, "record_plan", _second_press_first)
            outer = await _post(app, sid, "EXIT")
            codes = sorted([outer.status_code, inner[0].status_code])
            assert codes == [200, 409], (outer.text, inner[0].text)
            stored = await plans.plans_for(conn, user, sid)
            assert [(p.plan_number, p.action) for p in stored] == [(1, "ENTRY"), (2, "EXIT")]
        finally:
            await trans.rollback()
