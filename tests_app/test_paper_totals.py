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
from ofo_app import paper_store, paper_trigger_store
from ofo_app import strategy_store as store
from ofo_app.routes.outcome import load_charge_rates
from sqlalchemy import text
from test_paper_routes import AT, FIXTURE, MINUS
from test_strategy_store import _client, _ids, _saved_in
from test_strategy_tracking import _RETIRE, IDS, _frame, _setup

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
    snap = read_snapshot(provider, "NIFTY", list(held), last, D("0.065"), None)
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

async def test_one_open_contract_not_live_drops_unbooked_total_and_decay_but_keeps_booked(db):
    app, _provider, _clock, _last, sid = await _seed_three(db)
    await db.execute(text(_RETIRE), {"id": sid["contracts"][1]})  # held only by strategy 48 (SELL 65)
    totals = (await _list(app))["totals"]
    assert (totals["booked"], totals["unbooked"], totals["total"], totals["totals_reason"]) == (
        "731.25", None, None, "contract_retired")
    assert (totals["unbooked_text"], totals["total_text"], totals["decay"], totals["decay_reason"]) == (
        None, None, None, "contract_retired")


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
                              "charges": None, "charges_text": None, "charges_reason": "rates_unavailable"}


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
                              "charges_reason": None}


# --- alerts carry the strategy name -----------------------------------------------------------------------------------

async def test_each_alert_row_names_its_strategy(db):
    app, stored, *_ = await _setup(db)
    await _strategy(db, stored, [(0, _fixture(46)["legs"][0])], AT, new=False)
    tid = await paper_trigger_store.add(db, stored.id, paper_trigger_store.NewTrigger(
        "conditional_exit", "above", D("23100"), underlying="NIFTY"))
    assert await paper_trigger_store.claim_fire(db, tid)
    dash = render_explanation("cell_dash")
    what = render_explanation("paper_stop_reason_index", underlying="NIFTY", direction="above", level=D("23100"))
    body = str(render_explanation("paper_alert_body", name=dash, what=what, count=1,
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
