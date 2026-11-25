"""GC-TP step 4a: the Paper tab's SERVER totals over every paper strategy (screens 050-053 totals strip; ADR-008).

Core proof: three real paper strategies of tests/fixtures/paper/before-2026-10-29.json are seeded as orders on the test
catalogue's four condor contracts: 48 (open, one leg exited), 50 (fully exited) and 46 (open). ``GET /paper/strategies``
answers a ``totals`` block whose booked / unbooked / total equal the per-strategy figures summed by hand in this test,
to the paisa, and whose Decay equals the engine's per-unit decay x signed net quantity summed here (REQ-145 AC-2,
F-63). A price that is not live makes unbooked / total absent with the reason, never a partial sum (REQ-109 AC-5).
"""
from __future__ import annotations

import datetime
import json
import os
import pathlib
from decimal import ROUND_HALF_EVEN, Decimal
from http import HTTPStatus

import pytest
from ofo.charges import ChargeOrder, ChargeRates, charges_for_order
from ofo.charges.round_trip import to_paise_up
from ofo.engine.inputs import LegInput, StrategyInput
from ofo.engine.legs import Action, Instrument
from ofo.engine.model import expiry_model, implied_vol, iv_price, leg_decay_unrounded, model_inputs
from ofo.errors.explanations import render_explanation
from ofo.market_calendar import next_open
from ofo.outcome import read_snapshot
from ofo.scenario.spot import spot_reading
from ofo.settings import calc as _fq_calc
from ofo.settings import defaults as _fq_defaults
from ofo_app import paper_store, paper_trigger_store
from ofo_app import strategy_store as store
from ofo_app.paper_reasons import reason_text
from ofo_app.routes.outcome import load_charge_rates
from sqlalchemy import text
from test_paper_routes import AT, FIXTURE, MINUS
from test_strategy_store import _client, _ids, _saved_in
from test_strategy_tracking import _RETIRE, IDS, _frame, _setup

_FQ = _fq_calc.forward_quality(_fq_defaults())

D = Decimal
ROOT = pathlib.Path(__file__).resolve().parent.parent
PAISE = D("0.01")
#: The Kite-reproduced rate set (tests/charges/test_rates_reproduce_kite.py, read 2026-10-15).
RATES = ChargeRates(brokerage_per_order=D("20"), stt_sell_rate=D("0.0015"), stt_exercise_rate=D("0.0015"),
                    transaction_rates={"NSE_FO": D("0.0003553"), "BSE_FO": D("0.000325")}, sebi_rate=D("0.000001"),
                    stamp_buy_rate=D("0.00003"), gst_rate=D("0.18"), read_on=datetime.date(2026, 10, 15),
                    source_url="https://zerodha.com/charges (F&O options)")


@pytest.fixture
async def db(app_engine):
    async with app_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


def _fixture(strategy_id: int) -> dict:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return next(s for s in data["strategies"] if s["strategy_id"] == strategy_id)


def _new(contract: int, side: str, qty: int, price: str, kind: str = "open", at: datetime.datetime = AT):  # noqa: PLR0913 - one order
    return paper_store.NewOrder(contract, side, qty, D(price), kind, at)


def _flip(side: str) -> str:
    return "SELL" if side == "BUY" else "BUY"


async def _strategy(db, stored, legs: list[tuple[int, dict]], at: datetime.datetime, *, new: bool = True):
    """A paper strategy from fixture legs placed on the given contract indexes (one exit order per exited leg)."""
    target = stored
    if new:
        target = await store.save_draft(db, stored.user_ref, await _saved_in(db, stored.user_ref, await _ids(db)))
    ids = stored.saved.contract_ids
    orders = [_new(ids[i], leg["action"], leg["quantity"], leg["entry_price"], at=at) for i, leg in legs]
    orders += [_new(ids[i], _flip(leg["action"]), leg["quantity"], leg["exit_price"], "exit", at=at)
               for i, leg in legs if leg["exit_price"] is not None]
    await paper_store.place(db, stored.user_ref, target.id, orders)
    return target


async def _seed_three(db):
    """48 on contracts 0-3 at the fixture's prices (leg 2 exited: its price 100), 50 on contract 0 (fully exited),
    46 on contracts 2 (BUY 187.35) and 3 (SELL 107.30). 46 was started FIRST (earliest first order), 50 last."""
    app, stored, provider, clock, last = await _setup(db)
    s48, s50, s46 = _fixture(48), _fixture(50), _fixture(46)
    first = await _strategy(db, stored, list(enumerate(s48["legs"])), AT, new=False)
    exited = await _strategy(db, stored, [(0, s50["legs"][0])], AT + datetime.timedelta(hours=1))
    oldest = await _strategy(db, stored, [(2, s46["legs"][0]), (3, s46["legs"][1])], AT - datetime.timedelta(hours=1))
    for iid, leg in zip(IDS, s48["legs"], strict=True):
        provider.on_frame(_frame(provider, iid, leg["current_price"] or "100"), last)
    return app, provider, clock, last, {"48": first.id, "50": exited.id, "46": oldest.id,
                                        "contracts": stored.saved.contract_ids}


async def _list(app) -> dict:
    async with _client(app) as c:
        reply = await c.get("/paper/strategies")
    assert reply.status_code == HTTPStatus.OK, reply.text
    return reply.json()


def _hand_decay(provider, last, held: dict[str, int]) -> Decimal:
    """Independent of the route: per contract, the engine's per-unit decay of a BOUGHT unit to the next open, times
    the signed net quantity summed by hand; rounded once to the paisa (the P&L table's TOTAL row rule)."""
    snap = read_snapshot(provider, "NIFTY", list(held), last, D("0.065"), None, quality=_FQ)
    until = next_open(snap.valuation)
    total = D(0)
    for key, qty in held.items():
        c = snap.legs[key].contract.contract
        kind = Instrument(c.instrument_type)
        em = expiry_model(spot_reading(snap.spot), snap.forwards[c.expiry], underlying="NIFTY")
        iv = implied_vol(em, kind, iv_price(snap.legs[key].quote), c.strike).iv
        leg = LegInput("NIFTY", key, Action.BUY, kind, c.strike, c.expiry, 1, D("1"), None, iv)
        unit = leg_decay_unrounded(model_inputs(StrategyInput("NIFTY", spot_reading(snap.spot), snap.valuation,
                                                              snap.rate, (leg,)), snap.forwards), leg, until)
        assert unit < 0, (key, unit)  # a bought option loses time value overnight: the sign check is independent
        total += unit * qty
    return total.quantize(PAISE, rounding=ROUND_HALF_EVEN)


# --- the core proof ---------------------------------------------------------------------------------------------------

async def test_core_totals_equal_the_three_real_strategies_summed_by_hand_to_the_paisa(db):
    app, provider, _clock, last, sid = await _seed_three(db)
    body = await _list(app)
    by_id = {s["strategy_id"]: s for s in body["strategies"]}
    # by hand: 48 is the fixture's own figures; 50 = (217.70 - 183.30) x 65; 46 = (100 - 187.35) x 65 +
    # (107.30 - 258.80) x 65 at the prices contracts 2 and 3 carry for 48
    hand = {sid["48"]: (D("-1504.75"), D("10361.00")), sid["50"]: (D("2236.00"), D("0.00")),
            sid["46"]: (D("0.00"), D("-87.35") * 65 + D("-151.50") * 65)}
    for strategy_id, (booked, unbooked) in hand.items():
        shown = by_id[strategy_id]
        assert (D(shown["booked"]), D(shown["unbooked"]), D(shown["total"])) == (booked, unbooked, booked + unbooked)
    totals = body["totals"]
    assert (D(totals["booked"]), D(totals["unbooked"]), D(totals["total"])) == (
        D("731.25"), D("-5164.25"), D("-4433.00"))
    assert totals["booked"] == "731.25" and totals["total"] == "-4433.00"  # exact, to the paisa
    assert (totals["booked_text"], totals["unbooked_text"], totals["total_text"], totals["totals_reason"]) == (
        "+731.25", MINUS + "5,164.25", MINUS + "4,433.00", None)
    # decay: 48 holds +65 / -65 / 0 / +65 on contracts 0-3; 46 holds +65 on 2 and -65 on 3; 50 holds nothing
    held = {IDS[0]: 65, IDS[1]: -65, IDS[2]: 65, IDS[3]: 65 - 65}
    expected = _hand_decay(provider, last, {k: q for k, q in held.items() if q})
    assert (D(totals["decay"]), totals["decay_reason"]) == (expected, None)
    assert totals["decay_text"] == str(render_explanation("summary_paisa_signed", amount=expected))
    _save(body)


def _save(body: dict) -> None:
    """GC-TP step 4b's frontend fixture is this real reply (no personal data in it), written only when asked."""
    out = os.environ.get("PAPER_FIXTURE_OUT")
    if out:
        pathlib.Path(out).write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


async def test_newest_strategy_first_by_first_order_time_then_id_with_counts_and_contract_ids(db):
    app, _provider, _clock, _last, sid = await _seed_three(db)
    body = await _list(app)
    assert [s["strategy_id"] for s in body["strategies"]] == [sid["50"], sid["48"], sid["46"]]
    counts = {s["strategy_id"]: (s["open_count"], s["position_count"]) for s in body["strategies"]}
    assert counts == {sid["48"]: (3, 4), sid["50"]: (0, 1), sid["46"]: (2, 2)}
    assert all(isinstance(p["contract_id"], int) for s in body["strategies"] for p in s["positions"])


async def test_same_first_order_time_falls_back_to_the_newest_id(db):
    app, stored, *_ = await _setup(db)
    leg = _fixture(50)["legs"][0]
    first = await _strategy(db, stored, [(0, leg)], AT, new=False)
    second = await _strategy(db, stored, [(0, leg)], AT)
    assert [s["strategy_id"] for s in (await _list(app))["strategies"]] == [second.id, first.id]


# --- answer states ----------------------------------------------------------------------------------------------------

async def test_one_expired_contract_leaves_its_strategy_out_of_every_figure_and_says_so(db):
    """D-40 (ADR-324): strategy 48 holds the retired contract, so it is left out; 50 and 46 can be priced and every
    header figure (booked too, so Total = Booked + Unbooked) is the sum over those two."""
    app, _provider, _clock, _last, sid = await _seed_three(db)
    await db.execute(text(_RETIRE), {"id": sid["contracts"][1]})  # held only by strategy 48 (SELL 65)
    body = await _list(app)
    totals = body["totals"]
    rows = {s["strategy_id"]: s for s in body["strategies"]}
    assert rows[sid["48"]]["unbooked"] is None
    booked = D(rows[sid["50"]]["booked"]) + D(rows[sid["46"]]["booked"])
    unbooked = D(rows[sid["50"]]["unbooked"]) + D(rows[sid["46"]]["unbooked"])
    assert (totals["booked"], totals["unbooked"], totals["total"]) == (
        str(booked), str(unbooked), str(booked + unbooked))
    assert totals["booked"] == "2236.00"  # 731.25 over all three, minus 48's booked -1,504.75
    assert (totals["totals_reason"], totals["decay_reason"], totals["decay"] is None) == (None, None, False)
    assert (totals["left_out_count"], totals["left_out_text"]) == (1, "1 strategy left out: its contract has expired.")


async def test_stale_prices_make_the_totals_absent_with_prices_not_live(db):
    app, _provider, clock, last, _sid = await _seed_three(db)
    clock.now = last + datetime.timedelta(minutes=10)
    totals = (await _list(app))["totals"]
    assert (totals["booked"], totals["unbooked"], totals["total"], totals["totals_reason"], totals["decay_reason"]) == (
        "731.25", None, None, "prices_not_live", "prices_not_live")


async def test_no_iv_drops_only_the_decay_with_its_reason(db):
    app, provider, _clock, last, _sid = await _seed_three(db)
    provider.on_frame(_frame(provider, IDS[0], "30000"), last)  # a call above the index: no volatility solves it
    totals = (await _list(app))["totals"]
    assert totals["unbooked"] is not None and totals["total"] is not None
    assert (totals["decay"], totals["decay_text"], totals["decay_reason"]) == (None, None, "no_iv")


async def test_a_fully_exited_strategy_counts_in_booked_and_decays_nothing(db):
    app, stored, *_ = await _setup(db)
    await _strategy(db, stored, [(0, _fixture(50)["legs"][0])], AT, new=False)
    app.dependency_overrides[load_charge_rates] = lambda: None  # charges are covered by the step 8a tests below
    body = await _list(app)
    assert body["strategies"][0]["state"] == "EXITED"
    zero = str(render_explanation("summary_paisa_signed", amount=D("0")))
    assert body["totals"] == {"booked": "2236.00", "booked_text": "+2,236.00", "unbooked": "0.00",
                              "unbooked_text": zero, "total": "2236.00", "total_text": "+2,236.00",
                              "totals_reason": None, "decay": "0.00", "decay_text": zero, "decay_reason": None,
                              "charges": None, "charges_text": None, "charges_reason": "rates_unavailable",
                              # ADR-210: each reason code carries its sentence (GC-TPD); a None code, None text
                              "totals_reason_text": None, "decay_reason_text": None,
                              "charges_reason_text": str(reason_text("rates_unavailable")),
                              "totals_as_of": None,  # GC-LIVE L3a: no paused book, no pause time
                              "left_out_count": 0, "left_out_text": None,  # D-40: nothing expired
                              # ADR-301 to ADR-311: the after-charges figures wait for the same missing rates
                              "total_after": None, "total_after_text": None, "booked_after": None,
                              "booked_after_text": None, "unbooked_after": None, "unbooked_after_text": None,
                              "charges_paid": None, "charges_paid_text": None, "charges_to_close": None,
                              "charges_to_close_text": None, "after_charges_reason": "rates_unavailable",
                              "booked_after_reason": "rates_unavailable",
                              "after_charges_reason_text": str(reason_text("rates_unavailable")),
                              "booked_after_reason_text": str(reason_text("rates_unavailable"))}


async def test_no_paper_strategies_answers_an_empty_list_and_zero_totals(db):
    app, *_ = await _setup(db)
    app.dependency_overrides[load_charge_rates] = lambda: RATES
    body = await _list(app)
    zero = str(render_explanation("summary_paisa_signed", amount=D("0")))
    assert body["strategies"] == []
    assert body["totals"] == {"booked": "0.00", "booked_text": zero, "unbooked": "0.00", "unbooked_text": zero,
                              "total": "0.00", "total_text": zero, "totals_reason": None, "decay": "0.00",
                              "decay_text": zero, "decay_reason": None, "charges": "0.00",
                              "charges_text": str(render_explanation("paper_charges", amount=D("0"))),
                              "charges_reason": None, "totals_reason_text": None, "decay_reason_text": None,
                              "charges_reason_text": None, "totals_as_of": None,
                              "left_out_count": 0, "left_out_text": None,
                              # ADR-301 to ADR-311: nothing traded, so every after-charges figure is zero
                              "total_after": "0.00", "total_after_text": zero, "booked_after": "0.00",
                              "booked_after_text": zero, "unbooked_after": "0.00", "unbooked_after_text": zero,
                              "charges_paid": "0.00",
                              "charges_paid_text": str(render_explanation("paper_charges", amount=D("0"))),
                              "charges_to_close": "0.00",
                              "charges_to_close_text": str(render_explanation("paper_charges", amount=D("0"))),
                              "after_charges_reason": None, "booked_after_reason": None,
                              "after_charges_reason_text": None, "booked_after_reason_text": None}


# --- alerts carry the strategy name -----------------------------------------------------------------------------------

async def test_each_alert_row_names_its_strategy(db):
    app, stored, *_ = await _setup(db)
    await _strategy(db, stored, [(0, _fixture(46)["legs"][0])], AT, new=False)
    tid = await paper_trigger_store.add(db, stored.id, paper_trigger_store.NewTrigger(
        "conditional_exit", "above", D("23100"), underlying="NIFTY"))
    assert await paper_trigger_store.claim_fire(db, tid)
    dash = render_explanation("cell_dash")
    what = render_explanation("paper_stop_reason_index", underlying="NIFTY", direction="above", level=D("23100"))
    body = str(render_explanation("paper_alert_body", what=what, count=1,
                                  prices=render_explanation("paper_alert_leg", contract=dash, price=dash)))
    await paper_trigger_store.add_alert(db, stored.id, tid, str(render_explanation("paper_alert_title", name=dash)),
                                        body)
    async with _client(app) as c:
        alerts = (await c.get("/paper/alerts")).json()["alerts"]
        book = (await c.get(f"/paper/strategies/{stored.id}")).json()
    assert [(a["strategy_id"], a["strategy_name"]) for a in alerts] == [(stored.id, book["name"])]
    assert alerts[0]["strategy_name"]



# --- GC-TP step 8a: Charges beside P&L (REQ-109 AC-10, ADR-207 (7), Sensibull 050) ------------------------------------

async def _hand_charges(db, strategy_id: int) -> Decimal:
    """Independent of the route: the calculator called order by order on the stored orders (all NIFTY options, none a
    settle), summed exactly and rounded UP to the paisa once."""
    orders = await paper_store.load(db, strategy_id)
    exact = sum((charges_for_order(ChargeOrder("NSE_FO", o.order.side, o.order.quantity, o.order.price), RATES).total
                 for o in orders), D(0))
    return to_paise_up(exact)


async def test_each_strategy_carries_its_charges_beside_an_unchanged_pnl_and_the_totals_sum_them(db):
    app, _provider, _clock, _last, sid = await _seed_three(db)
    before = await _list(app)  # rates as the database has them: the P&L figures must not depend on the charges
    app.dependency_overrides[load_charge_rates] = lambda: RATES
    body = await _list(app)
    by_id = {s["strategy_id"]: s for s in body["strategies"]}
    hand = {sid[k]: await _hand_charges(db, sid[k]) for k in ("48", "50", "46")}
    for strategy_id, charges in hand.items():
        shown = by_id[strategy_id]
        assert (D(shown["charges"]), shown["charges_reason"]) == (charges, None)
        assert shown["charges_text"] == str(render_explanation("paper_charges", amount=charges))
        old = next(s for s in before["strategies"] if s["strategy_id"] == strategy_id)
        assert (shown["booked"], shown["unbooked"], shown["total"]) == (old["booked"], old["unbooked"], old["total"])
    assert D(body["totals"]["charges"]) == sum(hand.values(), D(0))
    assert body["totals"]["total"] == "-4433.00"  # charges are beside the total, never subtracted from it
    async with _client(app) as c:
        book = (await c.get(f"/paper/strategies/{sid['48']}")).json()
    assert (D(book["charges"]), book["total"]) == (hand[sid["48"]], by_id[sid["48"]]["total"])


async def test_no_rates_makes_every_charges_figure_absent_with_its_reason_never_zero(db):
    app, _provider, _clock, _last, sid = await _seed_three(db)
    app.dependency_overrides[load_charge_rates] = lambda: None
    body = await _list(app)
    for shown in body["strategies"]:
        assert (shown["charges"], shown["charges_text"], shown["charges_reason"]) == (None, None, "rates_unavailable")
    t = body["totals"]
    assert (t["charges"], t["charges_text"], t["charges_reason"], t["total"]) == (
        None, None, "rates_unavailable", "-4433.00")
    async with _client(app) as c:
        book = (await c.get(f"/paper/strategies/{sid['46']}")).json()
    assert (book["charges"], book["charges_reason"]) == (None, "rates_unavailable")


# --- D-40 (23 Nov live test, ADR-324): expired strategies are left out of the header; a plain reason, not an error ---
# Real case: PATH-60 / PATH-61 hold open legs on expired contracts. Here one open contract is retired: 46 is the expired
# strategy; 48 (hand figures -1,504.75 / +10,361.00 / +8,856.25) and 50 are the strategies that can be priced.

async def test_expired_strategy_is_left_out_of_every_header_figure_and_the_line_says_how_many(db):
    app, _provider, _clock, _last, seeded = await _seed_three(db)
    await db.execute(text(_RETIRE), {"id": seeded["contracts"][2]})  # 46's BUY leg: its contract has expired
    body = await _list(app)
    rows = {s["strategy_id"]: s for s in body["strategies"]}
    expired = rows[seeded["46"]]
    assert expired["unbooked"] is None and [u["expired"] for u in expired["unpriced_legs"]] == [True]
    kept = [rows[seeded["48"]], rows[seeded["50"]]]
    assert (D(kept[0]["booked"]), D(kept[0]["unbooked"]), D(kept[0]["total"])) == (
        D("-1504.75"), D("10361.00"), D("8856.25"))
    totals = body["totals"]
    booked = sum((D(s["booked"]) for s in kept), D(0))
    unbooked = sum((D(s["unbooked"]) for s in kept), D(0))
    assert (D(totals["booked"]), D(totals["unbooked"]), D(totals["total"])) == (booked, unbooked, booked + unbooked)
    assert totals["totals_reason"] is None and totals["totals_reason_text"] is None
    assert totals["decay"] is not None and totals["decay_reason"] is None
    assert totals["left_out_count"] == 1
    assert totals["left_out_text"] == render_explanation("paper_totals_left_out_one")
    assert totals["left_out_text"] == "1 strategy left out: its contract has expired."


async def test_no_expired_strategy_means_no_left_out_line(db):
    app, *_ = await _seed_three(db)
    totals = (await _list(app))["totals"]
    assert (totals["left_out_count"], totals["left_out_text"]) == (0, None)


async def test_a_price_that_is_not_live_still_blanks_the_totals_with_its_reason(db):
    app, _provider, clock, last, _seeded = await _seed_three(db)
    clock.now = last + datetime.timedelta(minutes=10)  # every price stale: not an expiry, so nothing is left out
    totals = (await _list(app))["totals"]
    assert (totals["unbooked"], totals["total"], totals["totals_reason"]) == (None, None, "prices_not_live")
    assert (totals["left_out_count"], totals["left_out_text"]) == (0, None)


async def test_a_book_on_expired_contracts_answers_200_with_the_plain_reason_the_card_shows(db):
    """The route is not the 500: it answers with the reason (the card's failure was in the browser, which read the
    catalogue for the book's expiry, found nothing and threw "unreadable paper book": see live-strategies.test.js)."""
    app, _provider, _clock, _last, seeded = await _seed_three(db)
    for cid in seeded["contracts"]:  # every contract of the books has expired and been retired
        await db.execute(text(_RETIRE), {"id": cid})
    async with _client(app) as c:
        single = await c.get(f"/paper/strategies/{seeded['46']}")
        listed = await c.get("/paper/strategies")
    assert single.status_code == HTTPStatus.OK, single.text
    body = single.json()
    assert (body["state"], body["pause_reason"], body["total"]) == ("PAUSED", "contract_retired", None)
    assert body["pause_reason_text"] == reason_text("contract_retired")
    assert body["unpriced_text"] and body["unpriced_text"].startswith("Expired contracts have no price: ")
    assert listed.status_code == HTTPStatus.OK, listed.text
    totals = listed.json()["totals"]
    open_books = 2  # 46 and 48 hold open legs (50 is fully exited)
    assert totals["left_out_count"] == open_books
    assert totals["left_out_text"] == render_explanation("paper_totals_left_out_many", count=open_books)


# --- D-40 round 2 (A1, A2, A4): the expiry decision does not depend on the connection or on the other legs -----------

async def test_a1_not_connected_with_an_expired_contract_still_leaves_that_strategy_out(db):
    """The broker is not connected (no market context) and strategy 46's contract has expired: the header names the
    strategy as left out; it does not blank with the contract_retired reason and a left-out count of 0."""
    from ofo_app.routes.outcome import get_market_context  # noqa: PLC0415

    app, _provider, _clock, _last, seeded = await _seed_three(db)
    await db.execute(text(_RETIRE), {"id": seeded["contracts"][2]})  # 46's BUY leg
    app.dependency_overrides[get_market_context] = lambda: None
    body = await _list(app)
    rows = {s["strategy_id"]: s for s in body["strategies"]}
    assert rows[seeded["46"]]["state"] == "NOT_CONNECTED" and rows[seeded["46"]]["expired_open"] is True
    assert rows[seeded["48"]]["expired_open"] is False
    totals = body["totals"]
    assert totals["totals_reason"] != "contract_retired" and totals["decay_reason"] != "contract_retired"
    assert (totals["left_out_count"], totals["left_out_text"]) == (1, "1 strategy left out: its contract has expired.")
    async with _client(app) as c:
        single = (await c.get(f"/paper/strategies/{seeded['46']}")).json()
    assert single["expired_open"] is True  # the per-strategy reply says it too (the card keys on this)
    assert [u["expired"] for u in single["unpriced_legs"]] == [True]  # and names the expired leg, connected or not
    assert single["unpriced_text"].startswith("Expired contracts have no price: ")


async def test_a2_one_expired_leg_among_live_ones_leaves_the_whole_strategy_out(db):
    """Strategy 48 holds three open legs; one contract has expired, the other two are priced. 48 is left out whole:
    none of its booked or priced figures reach the header."""
    app, _provider, _clock, _last, sid = await _seed_three(db)
    await db.execute(text(_RETIRE), {"id": sid["contracts"][1]})  # held only by 48
    body = await _list(app)
    rows = {s["strategy_id"]: s for s in body["strategies"]}
    priced = [p for p in rows[sid["48"]]["positions"] if p["ltp"] is not None]
    assert priced, "48 must still have live-priced legs for this case"
    assert rows[sid["48"]]["expired_open"] is True
    kept_booked = D(rows[sid["50"]]["booked"]) + D(rows[sid["46"]]["booked"])
    assert D(body["totals"]["booked"]) == kept_booked
    assert body["totals"]["left_out_count"] == 1


async def test_a4_an_expired_strategy_and_stale_prices_the_stale_reason_wins_and_the_count_stays(db):
    """Mixed: 46 has expired and every price is stale. The strategies that can be priced are stale, so the figures say
    prices_not_live (never contract_retired), and the left-out line still counts the expired one."""
    app, _provider, clock, last, sid = await _seed_three(db)
    await db.execute(text(_RETIRE), {"id": sid["contracts"][2]})
    clock.now = last + datetime.timedelta(minutes=10)
    totals = (await _list(app))["totals"]
    assert (totals["unbooked"], totals["total"], totals["totals_reason"]) == (None, None, "prices_not_live")
    assert (totals["left_out_count"], totals["left_out_text"]) == (1, "1 strategy left out: its contract has expired.")


# --- D-36: a finished book (no open leg) costs the list no pricing, decay or live-figure work ------------------------

_FINISHED = 6
_STATEMENTS = 6  # the list's fixed database work
_WORK = ("_prices", "_figures", "_summary", "_decay", "_charges", "_after")


async def _seed_finished_and_one_open(db):
    app, stored, provider, _clock, last = await _setup(db)
    s48, s50 = _fixture(48), _fixture(50)
    for n in range(_FINISHED):
        await _strategy(db, stored, [(0, s50["legs"][0])], AT + datetime.timedelta(minutes=n + 1), new=n > 0)
    await _strategy(db, stored, list(enumerate(s48["legs"])), AT, new=True)
    for iid, leg in zip(IDS, s48["legs"], strict=True):
        provider.on_frame(_frame(provider, iid, leg["current_price"] or "100"), last)
    app.dependency_overrides[load_charge_rates] = lambda: RATES
    return app


async def test_d36_the_list_does_fixed_database_work_and_finished_books_cost_only_cheap_arithmetic(db, monkeypatch):
    from ofo_app.routes import paper as route  # noqa: PLC0415
    from sqlalchemy import event  # noqa: PLC0415
    app = await _seed_finished_and_one_open(db)
    seen = {name: {"finished": 0, "open": 0} for name in _WORK}

    def counted(name):
        original = getattr(route, name)

        def wrapper(*args, **kwargs):
            first = args[0]
            if name == "_prices":
                held = first  # the open contract ids
            elif name == "_decay":
                held = [p for p in first["positions"] if p["net_quantity"] != 0]
            else:
                held = route._open_ids(first)
            seen[name]["open" if held else "finished"] += 1
            return original(*args, **kwargs)
        return wrapper
    for name in _WORK:
        monkeypatch.setattr(route, name, counted(name))
    statements: list[str] = []
    sync = db.sync_connection

    def record(_conn, _cursor, statement, *_rest):
        statements.append(statement)
    event.listen(sync, "before_cursor_execute", record)
    try:
        body = await _list(app)
    finally:
        event.remove(sync, "before_cursor_execute", record)
    # D-36 count (measured 2026-11-25, 6 finished + 1 open): the per-book helpers run once per finished book, pure
    # arithmetic of about 0.3 ms each (6 books: 2 ms in all); the database work is a fixed 6 statements whatever the
    # count of strategies and no broker is called. Finished books cost nothing measurable, so nothing is skipped.
    assert {name: seen[name]["finished"] for name in _WORK} == dict.fromkeys(_WORK, _FINISHED)
    assert len(statements) == _STATEMENTS
    assert len(body["strategies"]) == _FINISHED + 1
