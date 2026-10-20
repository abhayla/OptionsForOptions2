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
from ofo.charges.rates import ChargeRates
from ofo.engine import Action, Instrument
from ofo.instruments import Catalogue
from ofo_app import execute_plan as ep
from ofo_app.execute_replay import AT, CORE_ID, REPLIES, TOKEN, real_basket, real_order, recorded_text
from ofo_app.execute_replay import DepthQuotes, RecordedKite, live_quote, session_for
from ofo_app.execute_replay import listed_contract as _listed
from ofo_app.execute_replay import pro_grant as _pro_grant  # noqa: F401 - imported by other route tests
from ofo_app.execute_replay import store_strategy_one

ROOT = Path(__file__).resolve().parents[1]
REAL_BASKET = real_basket()
REAL_ORDER = real_order()
KEY = ("NIFTY", Instrument.CE, D("23650"), datetime.date(2026, 10, 19))
_live_quote = live_quote
_Replay = RecordedKite
_session_for = session_for
#: W-102: the stored seed rate set (migration 0012, read 2026-10-15), handed to the route in place of the database read
RATES = ChargeRates(
    brokerage_per_order=D("20"), stt_sell_rate=D("0.0015"), stt_exercise_rate=D("0.0015"),
    transaction_rates={"NSE_FO": D("0.0003553"), "BSE_FO": D("0.000325")}, sebi_rate=D("0.000001"),
    stamp_buy_rate=D("0.00003"), gst_rate=D("0.18"), read_on=datetime.date(2026, 10, 15),
    source_url="https://zerodha.com/charges (F&O options), read 2026-10-15; F-35")


def _quotes(quote: object):
    return lambda iid, token: ep.quote_from_kite(quote) if token == TOKEN else None


def _catalogue() -> Catalogue:
    cat = Catalogue()
    cat.load([_listed()])
    return cat


def _leg(action: Action, quantity: int = 65) -> ep.LegToPrice:
    return ep.LegToPrice(CORE_ID, action, quantity, None)


# ---- the book floor: today's orders decide the next plan number and whether an earlier basket is still open --------

def _book(status: str, tag: str = "Q0001010") -> list[dict]:
    rows = json.loads(recorded_text("orders-122104.json"), parse_float=D)
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
    assert ep.book_floor(_book("OPEN", "Q000C030"), 1) == (0, False)
    assert ep.book_floor(_book("OPEN", "Q000C030"), 12) == (3, True)
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
        BasketPost("kitekey", form["data"], ("Q0001010",))
    with pytest.raises(TypeError):
        BasketPost.of(tuple(basket), "kitekey")
    for tampered in (form["data"].replace('"readonly": true', '"readonly": false'),
                     form["data"].replace("Q0001010", "Q0001090"), form["data"].replace("3.35", "3.4"),
                     form["data"].replace(', "tag": "Q0001010"', "")):
        with pytest.raises(BasketPostRefused):
            _check(tampered, basket)


# ---- W-102: the cost in the reply, from the sealed basket's own orders ---------------------------------------------

def _cost_body(rates, funds=D("1003"), required=D("572.00")) -> dict:
    from ofo_app.api_models import emit  # noqa: PLC0415
    from ofo_app.routes import execute as route  # noqa: PLC0415

    cost = route.cost_out(_real_basket().orders, rates, route.Figures(funds, required, AT))
    return json.loads(emit(cost))


def test_ac1_cost_of_the_real_entry_basket_is_strings_from_the_one_calculator():
    """AC-8 (W-102): the real sealed ENTRY basket (BUY 65 @ 3.35): 65 x 3.35 = 217.75 paid -> "-217.75"; charges
    23.6980820035 (hand computation in tests/execution/test_execute_cost.py) -> "23.70"; funds and margin exactly as
    handed in from the gate's read, each a 2-decimal string, never a JSON number."""
    assert _cost_body(RATES) == {"net_premium": "-217.75", "charges": "23.70", "charges_note": None,
                                 "funds_available": "1003.00", "margin_required": "572.00",
                                 "figures_read_at": "2026-10-16T15:07:21+05:30"}


def test_ac1_no_rates_gives_null_charges_and_the_catalogue_note_never_a_number():
    """AC-8 (W-102): no rate set -> charges null and the note saying charges are not included; the premium stays."""
    body = _cost_body(None)
    assert body["charges"] is None and body["net_premium"] == "-217.75"
    assert body["charges_note"] == "Charges and taxes are not included: the charge rates could not be read."


def test_ac1_zerodha_figures_not_confirmed_stay_null_never_zero():
    """AC-8 (W-102): a failed Zerodha read gives None for both (the gate blocks it anyway); the reply never shows 0."""
    body = _cost_body(RATES, funds=None, required=None)
    assert (body["funds_available"], body["margin_required"]) == (None, None)


# ---- the route on the database (core proof) -------------------------------------------------------------------------

#: Zerodha reads of one accepted Execute press, as on main before W-102 (read from the code: the order book, the
#: circuit-band quote, funds + basket margin in ``_zerodha_margin``, positions, funds + basket margin again inside
#: ``checked_basket``). The cost reuses the first funds/margin read and adds none.
KITE_READS_PER_EXECUTE = {"orders": 1, "quote": 1, "funds": 2, "basket_margin": 2, "positions": 1}


def _kite_reads(replay: _Replay) -> dict[str, int]:
    kinds = {"orders": "/orders", "quote": "/quote?i=", "funds": "/user/margins", "basket_margin": "/margins/basket",
             "positions": "/portfolio/positions"}
    counts = {kind: sum(1 for url in replay.calls if part in url) for kind, part in kinds.items()}
    assert sum(counts.values()) == len(replay.calls), replay.calls  # a read of any other kind fails here
    return counts


def _assert_cost(body: dict, replay: _Replay, expected: tuple[str, str, str, str]) -> None:
    """W-102: the reply's cost (net premium, charges, funds, margin), every money field a 2-decimal string, read at the
    pinned route clock, and the press asked Zerodha exactly what it asked before W-102 (the cost adds no read)."""
    net, charges, funds, margin = expected
    assert body["cost"] == {"net_premium": net, "charges": charges, "charges_note": None, "funds_available": funds,
                            "margin_required": margin, "figures_read_at": AT.isoformat()}
    assert _kite_reads(replay) == KITE_READS_PER_EXECUTE


def _rows_of(replay: _Replay, *, orders: list | None = None, positions: list | None = None) -> _Replay:
    replay.order_rows, replay.position_rows = orders, positions
    return replay


def _Quotes() -> DepthQuotes:  # the quote seam the route tests install
    """The depth source: depth and last price only, NO band (as the live feed). The band comes from Zerodha's quote."""
    return DepthQuotes(ep.quote_from_kite(_live_quote()))


async def _strategy_one(conn, user: str, app_role: str, units: int = 65) -> int:
    """Strategy id 1 (the real tags OFS1V1...), stored by the replay module's one copy; fails when id 1 is taken."""
    from sqlalchemy import text  # noqa: PLC0415

    taken = (await conn.execute(text("SELECT user_ref FROM public.strategies WHERE id = 1"))).first()
    if taken is not None:
        pytest.fail(f"strategy id 1 is already stored in the shared test DB (user {taken[0]!r}); the core needs it")
    return await store_strategy_one(conn, user, app_role, units)


async def _post(app, strategy_id: int, action: str):
    from test_strategy_store import _client  # noqa: PLC0415

    async with _client(app) as ac:
        return await ac.post(f"/strategies/{strategy_id}/execute", json={"action": action})


@pytest.mark.usefixtures("app_engine")
async def test_core_real_order_entry_then_exit(app_engine, admin_engine, monkeypatch):  # noqa: PLR0915
    """AC-1 core: ENTRY -> BUY 65 LIMIT 3.35 tagged OFS1V1L0 (plan 1 stored open, one ``order_prepared`` audited,
    W-103); a re-press is refused (one open plan, no audit row); plan 1 closed filled 65 -> EXIT on the real FLAT
    15:10 book is refused (AC-7 shortfall); EXIT on the real +65 book -> SELL 65 LIMIT 3.30 tagged OFS1V2L0 (plan 2
    stored open). Every other field equals the real basket."""
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
            entry = _Replay(funds="1003", basket_total="354.25", orders=None, positions="positions-151006")
            app.dependency_overrides[route.get_kite_session] = lambda: _session_for(entry)
            head = await audit_head(conn)
            resp = await _post(app, sid, "ENTRY")
            assert resp.status_code == 200, resp.text
            # W-103: ONE order_prepared, built from the stored plan, in the plan's transaction
            assert await audit_since(conn, head) == [("order_prepared", "plan:1:1", {
                "strategy_id": 1, "plan_number": 1, "action": "ENTRY", "tags": "Q0001010"})]
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
            # W-102 cost: 65 x 3.35 = 217.75 paid; charges 23.6980820035 -> 23.70 (tests/execution/test_execute_cost.py
            # docstring); funds 1003 and margin 354.25 + (217.75 - option_premium 0) = 572.00 (ADR-094 top-up) from the
            # gate's one read; read at the pinned route clock
            _assert_cost(body, entry, ("-217.75", "23.70", "1003.00", "572.00"))
            (open_plan,) = await plans.plans_for(conn, user, sid)
            assert (open_plan.plan_number, open_plan.status, open_plan.orders[0].tag) == (1, "open", "Q0001010")

            # one open plan per strategy: the open-plan refusal, and a refused press writes no audit event
            head = await audit_head(conn)
            await _refused_with(app, sid, "ENTRY", "An order this execution depends on is not in place yet")
            assert await audit_since(conn, head) == []

            await plans.close_plan(conn, user, sid, 1, reason="filled", filled={"Q0001010": 65})
            flat = _Replay(funds="671.5", basket_total="-214.5", orders="orders-122104", positions="positions-151006")
            app.dependency_overrides[route.get_kite_session] = lambda: _session_for(flat)
            # Zerodha holds 0 of the strategy's 65: blocked (AC-7), by the reconciliation-mismatch refusal
            await _refused_with(app, sid, "EXIT", "do not match what we recorded")
            assert len(await plans.plans_for(conn, user, sid)) == 1  # nothing stored, no number consumed

            held = _Replay(funds="671.5", basket_total="-214.5", orders="orders-122104", positions="positions-122104")
            app.dependency_overrides[route.get_kite_session] = lambda: _session_for(held)
            head = await audit_head(conn)
            resp = await _post(app, sid, "EXIT")
            assert resp.status_code == 200, resp.text
            assert await audit_since(conn, head) == [("order_prepared", "plan:1:2", {
                "strategy_id": 1, "plan_number": 2, "action": "EXIT", "tags": "Q0001020"})]
            from ofo_app.audit_store import load_log  # noqa: PLC0415
            _, anchor = await load_log(conn)  # the hash chain verifies with the new events in it
            assert anchor.count == head + 1
            (sell,) = resp.json()["orders"]
            assert (sell["transaction_type"], sell["quantity"], sell["price"], sell["tag"]) == ("SELL", 65, "3.30",
                                                                                              "Q0001020")
            # W-102: 65 x 3.30 = 214.50 received; charges 24.011933093 -> 24.01 (= Zerodha's own figure in the real
            # exit reply); the real exit reply's final.total -214.5 is a closing basket, so the gate's margin is 0.00
            # (ADR-094 / #321: a release is never a credit); funds 671.5 from the same read
            _assert_cost(resp.json(), held, ("214.50", "24.01", "671.50", "0.00"))
            stored = await plans.plans_for(conn, user, sid)
            assert [(p.plan_number, p.action, p.status) for p in stored] == [(1, "ENTRY", "closed"),
                                                                             (2, "EXIT", "open")]

            await _third_exit_refused(app, conn, user, sid)
        finally:
            await trans.rollback()


@pytest.mark.usefixtures("app_engine")
async def test_w100_entry_band_comes_from_zerodhas_quote_and_an_unknown_one_refuses_the_leg(app_engine, admin_engine,
                                                                                            monkeypatch):
    """W-100 (ADR-080): the depth source carries no band; ENTRY with a reply lacking the contract, or a failed /quote
    read, is refused ``gate_price_band_unknown``; a band whose top (3.30) is under the 3.35 ask refuses the leg as
    outside the band; the recorded band (0.05 - 81.55) lets it through. Nothing is stored by a refusal."""
    from ofo_app import execution_plan_store as plans  # noqa: PLC0415
    from ofo_app.routes import execute as route  # noqa: PLC0415
    from test_strategy_followups import _ConnMaker  # noqa: PLC0415
    from test_strategy_store import _app, _user  # noqa: PLC0415

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("TEST_CATALOGUE_DATE", "2026-10-16")
    sym = REAL_ORDER["tradingsymbol"]
    narrow = json.loads((REPLIES / "quote-150720.json").read_text(encoding="utf-8"))
    narrow["data"][f"NFO:{sym}"]["upper_circuit_limit"] = "3.30"
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            user = _user()
            sid = await _strategy_one(conn, user, app_engine.url.username)
            app = _app(_ConnMaker(conn), user)
            app.dependency_overrides[route.get_quote_reader] = _Quotes
            app.dependency_overrides[route.get_execute_clock] = lambda: (lambda: AT)

            async def entry(quote_text: str | None, phrase: str) -> None:
                replay = _Replay(funds="1003", basket_total="354.25", orders=None, positions="positions-151006")
                replay.quote_text = quote_text
                app.dependency_overrides[route.get_kite_session] = lambda: _session_for(replay)
                await _refused_with(app, sid, "ENTRY", phrase)
                assert not await plans.plans_for(conn, user, sid)

            await entry(_NO_CONTRACT_QUOTE, "could not read today's price band")
            await entry("{}", "could not read today's price band")  # a whole-reply failure: no bands at all
            await entry(json.dumps(narrow), "outside today's price band")
            ok = _Replay(funds="1003", basket_total="354.25", orders=None, positions="positions-151006")
            app.dependency_overrides[route.get_kite_session] = lambda: _session_for(ok)
            assert (await _post(app, sid, "ENTRY")).status_code == 200
        finally:
            await trans.rollback()


async def audit_since(conn, after_seq: int) -> list[tuple[str, str, dict]]:
    """W-103: the audit rows appended after ``after_seq`` as (event_type, correlation_id, decoded payload)."""
    from ofo_app.audit_store import decode_payload  # noqa: PLC0415
    from sqlalchemy import text  # noqa: PLC0415

    rows = (await conn.execute(text("SELECT event_type, correlation_id, payload::text AS p FROM public.audit_events "
                                    "WHERE seq > :s ORDER BY seq"), {"s": after_seq})).all()
    return [(r.event_type, r.correlation_id, decode_payload(json.loads(r.p))) for r in rows]


async def audit_head(conn) -> int:
    from ofo_app.audit_store import read_anchor  # noqa: PLC0415

    return (await read_anchor(conn)).count


async def _refused_with(app, sid: int, action: str, phrase: str) -> None:
    resp = await _post(app, sid, action)
    assert resp.status_code == 409, resp.text
    assert phrase in resp.text, resp.text


async def _third_exit_refused(app, conn, user: str, sid: int) -> None:
    """Round 2 review CRITICAL: plan 2 closed exited -> net 0 -> a THIRD EXIT press is refused (no SELL 65 short on
    a flat account) and nothing is stored."""
    from ofo_app import execution_plan_store as plans  # noqa: PLC0415
    from ofo_app.routes import execute as route  # noqa: PLC0415

    await plans.close_plan(conn, user, sid, 2, reason="exited", filled={"Q0001020": 65})
    done = _rows_of(_Replay(funds="1003", basket_total="-214.5", orders=None, positions="positions-151006"),
                    orders=_book("COMPLETE") + _book("COMPLETE", "Q0001020"))
    app.dependency_overrides[route.get_kite_session] = lambda: _session_for(done)
    third = await _post(app, sid, "EXIT")
    assert third.status_code == 409, third.text
    assert "would open or add to a position" in third.text
    assert [p.plan_number for p in await plans.plans_for(conn, user, sid)] == [1, 2]  # nothing stored


_NO_CONTRACT_QUOTE = '{"status": "success", "data": {}}'  # Zerodha's reply without the contract


def _position_rows(**changes) -> list:
    data = json.loads((REPLIES / "positions-122104.json").read_text(encoding="utf-8"), parse_float=D)
    rows = data.get("data", data)["net"]
    return [{k: v for k, v in {**r, **changes}.items() if v is not None} for r in rows]


@pytest.mark.usefixtures("app_engine")
async def test_refusals_on_the_net_of_all_plans_after_a_partial_entry(app_engine, admin_engine, monkeypatch):
    """A 2-lot strategy (130 units); plan 1 filled 65 of 130 (partial; NFO fills whole lots).
    Refused, nothing stored, each by its own guard: ENTRY while held (ADR-105);
    EXIT while OFS1V1L0 is OPEN or carries an unknown status word; EXIT whose position product cannot be read
    (ADR-080 (1)); EXIT on a band-less quote (the gate asks to confirm; no confirmation step exists). Then EXIT sells
    exactly the net 65 = Zerodha's real 12:21 position (review MAJOR 2: round 2 refused it)."""
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
            sid = await _strategy_one(conn, user, app_engine.url.username, units=130)
            app = _app(_ConnMaker(conn), user)
            app.dependency_overrides[route.get_quote_reader] = _Quotes
            app.dependency_overrides[route.get_execute_clock] = lambda: (lambda: AT)
            entry = _Replay(funds="1003", basket_total="354.25", orders=None, positions="positions-151006")
            app.dependency_overrides[route.get_kite_session] = lambda: _session_for(entry)
            assert (await _post(app, sid, "ENTRY")).status_code == 200
            await plans.close_plan(conn, user, sid, 1, reason="partial", filled={"Q0001010": 65})

            def _with(**kw):
                replay = _rows_of(_Replay(funds="671.5", basket_total="-214.5", orders="orders-122104",
                                          positions="positions-122104"), **kw)
                app.dependency_overrides[route.get_kite_session] = lambda: _session_for(replay)

            async def _refused(action: str, phrase: str) -> None:
                resp = await _post(app, sid, action)
                assert resp.status_code == 409, resp.text
                assert phrase in resp.text, resp.text
                assert len(await plans.plans_for(conn, user, sid)) == 1

            _with()
            await _refused("ENTRY", "executes only a version that is")
            for status in ("OPEN", "SOMETHING NEW"):
                _with(orders=_book(status))
                await _refused("EXIT", "is not in place yet")
            _with(positions=_position_rows(product=None))
            await _refused("EXIT", "differs from the product")
            _with()
            replay = _Replay(funds="671.5", basket_total="-214.5", orders="orders-122104", positions="positions-122104")
            replay.quote_text = _NO_CONTRACT_QUOTE
            app.dependency_overrides[route.get_kite_session] = lambda: _session_for(replay)
            await _refused("EXIT", "Market data needed for execution")
            _with()
            resp = await _post(app, sid, "EXIT")
            assert resp.status_code == 200, resp.text
            (sell,) = resp.json()["orders"]
            assert (sell["transaction_type"], sell["quantity"], sell["tag"]) == ("SELL", 65, "Q0001020")
        finally:
            await trans.rollback()


# ---- ADR-105: one held-position function over every plan (no database) ---------------------------------------------

class _O:
    def __init__(self, side: str, filled: int | None, iid: str = "NFO-OPT:47189") -> None:
        self.instrument_id, self.transaction_type, self.filled_quantity = iid, side, filled


class _P:
    def __init__(self, number: int, *orders: _O) -> None:
        self.plan_number, self.orders = number, orders


def test_held_units_nets_every_plan_entry_plus_exit_minus():
    k = "NFO-OPT:47189"
    assert ep.held_units([_P(1, _O("BUY", 65))]) == {k: 65}
    assert ep.held_units([_P(1, _O("BUY", 65)), _P(2, _O("SELL", 65))]) == {}  # exited: flat
    assert ep.held_units([_P(1, _O("BUY", 30))]) == {k: 30}  # partial
    assert ep.held_units([_P(1, _O("BUY", 65)), _P(2, _O("SELL", 40)), _P(3, _O("SELL", None))]) == {k: 25}
    assert ep.held_units([_P(1, _O("SELL", 65))]) == {k: -65}
    assert ep.latest_filled_plan([_P(1, _O("BUY", 65)), _P(2, _O("SELL", 40)), _P(3, _O("SELL", None))]) == 2
    assert ep.latest_filled_plan([_P(1, _O("BUY", None))]) is None


def test_version_state_is_derived_from_the_net():
    from ofo.execution.context import VersionState  # noqa: PLC0415

    held, flat = {"NFO-OPT:47189": 65}, {}
    assert ep.version_state("ENTRY", flat) is VersionState.ACTIVE
    assert ep.version_state("ENTRY", held) is VersionState.SUPERSEDED
    assert ep.version_state("EXIT", held) is VersionState.ACTIVE
    assert ep.version_state("EXIT", flat) is VersionState.SUPERSEDED


def test_exit_legs_close_exactly_the_net_opposite_side():
    legs = ep.exit_legs({"NFO-OPT:47189": 30, "NFO-OPT:1": -65}, lambda t: t)
    assert [(leg.instrument_id, leg.action, leg.quantity) for leg in legs] == [("NFO-OPT:1", Action.BUY, 65),
                                                                                ("NFO-OPT:47189", Action.SELL, 30)]
    assert ep.exit_legs({}, lambda t: t) == []


async def test_an_equity_row_in_the_positions_reply_does_not_block_reconciliation(caplog):
    """GC-3L 2026-10-19: the owner's own stock trades (CNC) sat in Zerodha's net positions; the reader refused the
    whole reply, reconciliation became unknown (None) and every Execute was refused RECONCILIATION_MISMATCH. The
    stock row is ignored (reported), the strategy's own contract is still compared."""
    from types import SimpleNamespace  # noqa: PLC0415

    from ofo_app.routes import execute as route  # noqa: PLC0415

    stocks = json.loads((REPLIES / "positions-20261019-with-stocks.json").read_text(encoding="utf-8"),
                        parse_float=D)["data"]["net"][:2]  # FRANKLININD, LIQUIDBEES (CNC)
    catalogue = _catalogue()

    def request(rows: list) -> SimpleNamespace:
        reads = SimpleNamespace(fetch_positions=lambda: {"net": rows, "day": []})
        return SimpleNamespace(session=SimpleNamespace(reads=reads), strategy_id=15)

    def held(units: dict) -> SimpleNamespace:
        return SimpleNamespace(units=units)

    entry_req = request(stocks)  # the strategy holds nothing; Zerodha holds only stocks
    with caplog.at_level("INFO", logger="ofo_app.kite_replies"):
        positions = await route._positions(entry_req, catalogue)
    assert positions is not None and positions.ignored == ("NSE:FRANKLININD", "NSE:LIQUIDBEES")
    assert [r.getMessage() for r in caplog.records] == [
        "execute strategy 15: positions read ignored 2 non-platform rows: NSE:FRANKLININD, NSE:LIQUIDBEES"]
    assert route._reconciliation(entry_req, held({}), positions, catalogue, "NIFTY") == frozenset()

    core = route._feed_key(CORE_ID)
    exit_req = request([*stocks, *_position_rows()])  # the strategy's 65 next to the stocks
    positions = await route._positions(exit_req, catalogue)
    assert positions.net == {KEY: 65}
    assert route._reconciliation(exit_req, held({core: 65}), positions, catalogue, "NIFTY") == frozenset()
    assert route._reconciliation(exit_req, held({core: 130}), positions, catalogue, "NIFTY") == frozenset({"15"})


def test_held_products_come_from_zerodha_and_an_unread_or_mixed_product_is_left_out():
    from ofo.engine import Leg  # noqa: PLC0415
    from ofo.engine.product import Product  # noqa: PLC0415
    from ofo.execution.context import product_key  # noqa: PLC0415
    from ofo_app.kite_replies import ContractIndex, positions_from_reply  # noqa: PLC0415
    from ofo_app.routes.execute import held_products  # noqa: PLC0415

    leg = Leg(Action.BUY, Instrument.CE, D("23650"), datetime.date(2026, 10, 19), 65, D("3.35"))
    symbols = {product_key(leg): REAL_ORDER["tradingsymbol"]}
    index = ContractIndex.from_catalogue(_catalogue())

    def read(rows):
        return positions_from_reply({"net": rows, "day": []}, index)

    assert held_products((leg,), symbols, read(_position_rows())) == {product_key(leg): Product.NRML}
    assert held_products((leg,), symbols, read(_position_rows(product=None))) == {}
    assert held_products((leg,), symbols, read(_position_rows() + _position_rows(product="MIS"))) == {}
    assert held_products((leg,), symbols, None) == {}


def test_live_quotes_use_the_frames_own_time_and_the_underlying_quote(monkeypatch):
    """Review MINOR 6: the leg's health is judged on the quote's own time, never the read time; the underlying's
    price and time come from the live context's ``underlying_quote``."""
    from types import SimpleNamespace  # noqa: PLC0415

    from ofo_app import live_market  # noqa: PLC0415
    from ofo_app.routes.execute import LiveDepthQuotes  # noqa: PLC0415

    live = ep.quote_from_kite(_live_quote())
    frame_at = datetime.datetime(2026, 10, 16, 15, 0, tzinfo=AT.tzinfo)
    spot = SimpleNamespace(ltp=D("23094.95"), timestamp=frame_at)
    book = SimpleNamespace(get=lambda key, now: SimpleNamespace(ltp=D("3.30"), timestamp=frame_at))
    ctx = SimpleNamespace(provider=SimpleNamespace(book=book, underlying_quote=lambda u: spot))
    monkeypatch.setattr(live_market, "current_context", lambda: ctx)
    monkeypatch.setattr(live_market, "latest_depth", lambda key: live.depth)
    quotes = LiveDepthQuotes(lambda: AT)
    got = quotes.leg_quote(CORE_ID, TOKEN)
    assert (got.at, got.last_price, got.band) == (frame_at, D("3.30"), None)
    assert quotes.underlying_price("NIFTY") == (D("23094.95"), frame_at)
    monkeypatch.setattr(live_market, "current_context", lambda: None)
    assert quotes.leg_quote(CORE_ID, TOKEN) is None and quotes.underlying_price("NIFTY") is None


@pytest.mark.usefixtures("app_engine")
async def test_two_interleaved_exits_give_one_basket_and_refuse_the_other(app_engine, admin_engine, monkeypatch):
    """Two EXIT presses that BOTH pass ``next_plan_number`` before either stores (the interleaving the strategy row
    lock prevents across connections): exactly one basket is answered and stored; the other is refused 409. Both
    presses share ONE connection here (the rolled-back transaction), so this proves the route's refusal path, not the
    lock: the lock across two connections is proven by the store's own two-connection test (W-094)."""
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
            await plans.close_plan(conn, user, sid, 1, reason="filled", filled={"Q0001010": 65})
            held = _Replay(funds="671.5", basket_total="-214.5", orders="orders-122104", positions="positions-122104")
            app.dependency_overrides[route.get_kite_session] = lambda: _session_for(held)

            real_record, inner = plans.record_plan, []

            async def _second_press_first(*args, **kwargs):
                if not inner:  # the first press, between its number and its store: the second press runs whole
                    inner.append(None)  # marked BEFORE the second press, whose own store must not recurse
                    inner[0] = await _post(app, sid, "EXIT")
                return await real_record(*args, **kwargs)

            monkeypatch.setattr(plans, "record_plan", _second_press_first)
            outer = await _post(app, sid, "EXIT")
            codes = sorted([outer.status_code, inner[0].status_code])
            assert codes == [200, 409], (outer.text, inner[0].text)
            stored = await plans.plans_for(conn, user, sid)
            assert [(p.plan_number, p.action) for p in stored] == [(1, "ENTRY"), (2, "EXIT")]
        finally:
            await trans.rollback()


# ---- database-stamped facts are judged on the database clock (round 4, ADR-023) ------------------------------------

DB_NOW = datetime.datetime(2026, 10, 17, 7, 50, tzinfo=AT.tzinfo)  # database clock; route clock AT


async def test_a_grant_stamped_on_the_database_clock_is_pro_while_the_route_clock_is_pinned_to_a_past_day(monkeypatch):
    from types import SimpleNamespace  # noqa: PLC0415

    from ofo.entitlements.engine import access_at  # noqa: PLC0415
    from ofo.entitlements.events import AccessLevel, NewGrant, Source  # noqa: PLC0415
    from ofo_app import entitlement_store  # noqa: PLC0415
    from ofo_app.routes import execute as route  # noqa: PLC0415
    from test_entitlement_store import note  # noqa: PLC0415

    stamp = entitlement_store.DatabaseStamp()
    stamp.recorded_at = DB_NOW
    ledger = entitlement_store.ledger_from_rows("u", [], clock=stamp).append(
        NewGrant("p", Source.PAID_MONTHLY, DB_NOW, datetime.timedelta(days=30), "pay", note()))
    assert access_at(ledger, AT).level is not AccessLevel.PRO  # the round-3 defect: judged on the pinned clock

    async def _load(conn, user_ref):
        return ledger

    monkeypatch.setattr(entitlement_store, "load", _load)
    req = SimpleNamespace(db=None, user_ref="u", now=AT)
    assert await route._pro_entitled(req, DB_NOW) is True


async def test_a_list_loaded_today_by_the_database_clock_is_healthy_while_the_route_clock_is_pinned_to_yesterday(
        monkeypatch):
    from types import SimpleNamespace  # noqa: PLC0415

    from ofo.execution.context import DataHealth, DataInput  # noqa: PLC0415
    from ofo_app import eligibility_from_zerodha as elig  # noqa: PLC0415
    from ofo_app.routes import execute as route  # noqa: PLC0415

    loaded = DB_NOW - datetime.timedelta(minutes=30)  # stamped by clock_timestamp() this morning

    async def _loaded_at(conn):
        return loaded

    monkeypatch.setattr(elig, "list_loaded_at", _loaded_at)
    req = SimpleNamespace(db=None, now=AT, clock=lambda: AT, quotes=SimpleNamespace(underlying_price=lambda u: None))
    health = await route._data_health(req, SimpleNamespace(quote_times=()), "NIFTY", DB_NOW)
    assert health[DataInput.INSTRUMENT_LIST] is DataHealth.HEALTHY
    assert route._list_health(loaded, DB_NOW - datetime.timedelta(days=1)) is DataHealth.STALE
    assert route._list_health(None, DB_NOW) is DataHealth.UNAVAILABLE


# ---- EXECUTE-REVIEW (REQ-056 AC-5/AC-9): the risk block is the engine's metrics as strings, never a made-up 0 ----

def _review_body(legs, action="ENTRY") -> dict:
    from ofo.engine import Strategy  # noqa: PLC0415
    from ofo_app.api_models import emit  # noqa: PLC0415
    from ofo_app.routes import execute as route  # noqa: PLC0415

    return json.loads(emit(route.review_out(Strategy(tuple(legs)), action)))


def _call(strike, expiry, qty, price, action=Action.BUY):
    from ofo.engine import Leg  # noqa: PLC0415

    return Leg(action, Instrument.CE, D(strike), expiry, qty, D(price), D(price))


def test_review_out_a_long_call_has_its_premium_as_max_loss_and_unlimited_profit():
    leg = _call("23650", datetime.date(2026, 10, 19), 65, "3.35")
    assert _review_body([leg]) == {"max_loss": "217.75", "max_loss_unlimited": False, "max_profit": None,
                                   "max_profit_unlimited": True}


def test_review_out_an_exit_and_a_multi_expiry_strategy_are_unknown_never_zero():
    near = _call("23650", datetime.date(2026, 10, 19), 65, "3.35")
    far = _call("23650", datetime.date(2026, 10, 26), 65, "5", Action.SELL)
    unknown = {"max_loss": None, "max_loss_unlimited": False, "max_profit": None, "max_profit_unlimited": False}
    assert _review_body([near], "EXIT") == unknown
    assert _review_body([near, far]) == unknown
