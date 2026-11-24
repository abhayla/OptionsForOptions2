"""D-13 / D-14 (23 Nov live test; ADR-306 (1)-(6), ADR-320 (2), ADR-263, ADR-008): one after-charges basis on the paper
book reply. No database.

D-13: the reply served ``profit_left`` / ``loss_left`` GROSS (the open legs' own range) beside a NET Max profit, so
Total after + Profit left did not reach Max profit (C4: profit_left 2,986.75 against max_profit 2,094).
D-14: three charge estimates in one reply: paid only (the Charges line), paid + exit at the AVERAGE price (inside Max
profit) and paid + exit at the LIVE price (inside Total after). C2 157 on its expiry day read +290.49 all day (round
trip 193.76) and settled at +387.01 (paid 97.24, no exit charges at settlement).

The C2-shaped book below (NIFTY, 1 lot of 65, expiry today): BUY 25200 PE @ 16.00, SELL 25300 PE @ 22.05,
SELL 25900 CE @ 4.10, BUY 26000 CE @ 2.70; live 3.10 / 4.20 / 1.05 / 0.60. Hand sums:
  credit = 22.05 - 16.00 + 4.10 - 2.70 = 7.45 per unit -> Max profit before charges 7.45 x 65 = 484.25.
  Total before = (22.05 - 4.20) + (4.10 - 1.05) - (16.00 - 3.10) - (2.70 - 0.60) = 17.85 + 3.05 - 12.90 - 2.10
  = 5.90 x 65 = 383.50.  Paid (calculator) 97.35; cost to close at live 94.90; Total after = 383.50 - 97.35 - 94.90
  = 191.25.  If held to expiry: 484.25 - 97.35 = 386.90; Profit left held = 386.90 - 191.25 = 195.65.
  If exited now: 484.25 - 192.25 = 292.00; Profit left = 292.00 - 191.25 = 100.75 (= the open range 484.25 - 383.50).
"""
from __future__ import annotations

import datetime
from decimal import Decimal as D
from types import SimpleNamespace

from ofo.charges import ChargeRates
from ofo.engine.extremes import BookExtremes
from ofo.engine.extremes_charges import BookAfterCharges
from ofo.engine.legs import Instrument
from ofo.engine.orderbook import PaperOrder
from ofo.tracking import paper as tracking_paper
from ofo_app.routes import paper as route

EXPIRY = datetime.date(2026, 11, 25)
T0 = datetime.datetime(2026, 11, 25, 4, 0, tzinfo=datetime.UTC)
LOT = 65
RATES = ChargeRates(
    brokerage_per_order=D("20"), stt_sell_rate=D("0.001"), stt_exercise_rate=D("0.00125"),
    transaction_rates={"NSE_FO": D("0.0003503"), "BSE_FO": D("0.000325")}, sebi_rate=D("0.000001"),
    stamp_buy_rate=D("0.00003"), gst_rate=D("0.18"), read_on=datetime.date(2026, 10, 15),
    source_url="https://zerodha.com/charges")
LEGS = ((1, Instrument.PE, "25200", "BUY", "16.00", "3.10"), (2, Instrument.PE, "25300", "SELL", "22.05", "4.20"),
        (3, Instrument.CE, "25900", "SELL", "4.10", "1.05"), (4, Instrument.CE, "26000", "BUY", "2.70", "0.60"))


def _book():
    orders, found, prices = [], {}, {}
    for cid, kind, strike, side, price, ltp in LEGS:
        paper_order = PaperOrder(str(cid), side, LOT, D(price), "open", T0)
        orders.append(SimpleNamespace(order=SimpleNamespace(
            contract_id=cid, kind="open", side=side, quantity=LOT, price=D(price), placed_at=T0,
            as_paper=lambda p=paper_order: p)))
        found[cid] = SimpleNamespace(contract_id=cid, stored=SimpleNamespace(listed=SimpleNamespace(
            contract=SimpleNamespace(name="NIFTY", instrument_type=kind.value, strike=D(strike), expiry=EXPIRY,
                                     lot_size=LOT))))
        prices[cid] = tracking_paper.Price(str(cid), tracking_paper.LIVE, D(ltp), T0)
    return orders, found, prices


def _reply(today: datetime.date | None):
    orders, found, prices = _book()
    charges = route._charges(orders, found, "NIFTY", RATES)
    when = {} if today is None else {"today": today}
    return (route._extremes(orders, found, prices, "NIFTY", RATES, **when)
            | charges | route._after(orders, found, prices, charges, "NIFTY", RATES))


def test_d13_served_profit_left_and_loss_left_are_after_charges_and_add_up() -> None:
    got = _reply(None)
    assert got["total_after"] == D("191.25")
    assert got["profit_left"] == got["profit_left_after"]
    assert got["loss_left"] == got["loss_left_after"]
    assert got["total_after"] + got["profit_left"] == got["max_profit"]  # ADR-306 (3), on the served fields
    assert got["total_after"] + got["loss_left"] == got["max_loss"]


def test_d14_the_charges_inside_max_profit_are_paid_plus_the_cost_to_close_now() -> None:
    got = _reply(None)
    assert (got["charges"], got["charges_to_close"]) == (D("97.35"), D("94.90"))
    assert abs(got["extremes_charges"] - (got["charges"] + got["charges_to_close"])) <= D("0.01")  # one exit cost
    assert got["max_profit"] == D("484.25") - got["extremes_charges"]


def test_d14_c2_157_expiry_day_shows_held_and_exited_pair() -> None:
    got = _reply(EXPIRY)
    assert got["max_profit_hold"] == D("386.90")  # 484.25 - 97.35 paid: no exit charges at settlement
    assert got["profit_left_hold"] == D("195.65")  # 386.90 - 191.25 Total after
    assert got["max_profit_hold"] - got["profit_left_hold"] == got["total_after"]
    assert got["max_profit"] - got["profit_left"] == got["total_after"]  # "If exited now": the usual pair
    assert got["max_profit_hold_text"] == "+386.90"


def test_d14_other_days_carry_no_pair() -> None:
    got = _reply(EXPIRY - datetime.timedelta(days=1))
    assert got["max_profit_hold"] is None
    assert got["profit_left_hold"] is None


def test_d14_c2_157_real_figures_hold_deducts_paid_only() -> None:
    from ofo.engine.extremes_charges import expiry_hold  # noqa: PLC0415 - the new engine function

    # The real case: Max profit before charges +484.25, paid 97.24. Held: 484.25 - 97.24 = +387.01 (the settlement).
    # The screen showed 484.25 - 193.76 (round trip) = +290.49 all day.
    before = BookExtremes(D("100.75"), D("-6399.25"), D("484.25"), D("-6015.75"), None)
    after = BookAfterCharges(D("383.50"), D("191.25"), D("97.24"), D("95.01"), None)
    assert expiry_hold(before, after) == (D("387.01"), D("195.76"))  # 387.01 - 191.25 = 195.76
