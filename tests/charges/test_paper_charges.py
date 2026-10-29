"""GC-TP step 8a: a paper strategy's Charges from the charges engine (REQ-109 AC-10, ADR-207 (7), ADR-082).

Real input: strategy 63's 8 recorded paper orders (frontend/tests/fixtures/paper-book-63.json, NIFTY options, 65 units
each) at the rates of the Kite-reproduced set (tests/charges/test_rates_reproduce_kite.py, 2026-10-15).
"""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from ofo.charges import ChargeOrder, charges_for_order
from ofo.charges.calculator import exercise_stt
from ofo.charges.paper_charges import PaperFill, charges_sum, paper_charges
from ofo.charges.round_trip import ChargesNotComputable, to_paise_up
from tests.charges.test_rates_reproduce_kite import rates

BOOK_63 = Path(__file__).resolve().parents[2] / "frontend" / "tests" / "fixtures" / "paper-book-63.json"


def book_63_fills() -> list[PaperFill]:
    data = json.loads(BOOK_63.read_text(encoding="utf-8"))
    return [PaperFill(o["kind"], o["side"], o["quantity"], Decimal(o["price"]), True) for o in data["orders"]]


def test_strategy_63_charges_are_the_engine_sum_order_by_order():
    fills = book_63_fills()
    assert [str(f.price) for f in fills] == ["72.60", "102.00", "122.25", "80.95", "132.00", "108.00", "77.45",
                                              "63.25"]
    got = paper_charges(fills, "NIFTY", rates())
    by_hand = [charges_for_order(ChargeOrder("NSE_FO", f.side, f.quantity, f.price), rates()).total for f in fills]
    assert list(got.per_order) == by_hand
    assert got.total == sum(by_hand, Decimal(0))
    assert got.shown == to_paise_up(got.total)
    assert got.shown >= got.total and got.shown - got.total < Decimal("0.01")


def test_one_order_components_match_a_hand_calculation():
    # BUY 65 NIFTY 22600 PE at 72.60: premium 4,719.00
    premium = Decimal("72.60") * 65
    brokerage = Decimal("20")
    transaction = premium * Decimal("0.0003553")  # 1.6766607
    sebi = premium * Decimal("0.000001")  # 0.004719
    stamp = premium * Decimal("0.00003")  # 0.14157 (a buy)
    gst = (brokerage + sebi + transaction) * Decimal("0.18")
    got = charges_for_order(ChargeOrder("NSE_FO", "BUY", 65, Decimal("72.60")), rates())
    assert (got.brokerage, got.stt, got.exchange_transaction, got.sebi, got.stamp, got.gst) == (
        brokerage, Decimal(0), transaction, sebi, stamp, gst)
    assert got.total == Decimal("25.725598046")
    assert paper_charges([book_63_fills()[0]], "NIFTY", rates()).per_order == (Decimal("25.725598046"),)


def test_a_bought_itm_option_settled_pays_exercise_stt_only():
    settle = PaperFill("settle", "SELL", 65, Decimal("40.50"), True)  # closes a long at intrinsic 40.50
    got = paper_charges([settle], "NIFTY", rates())
    assert got.per_order == (exercise_stt(Decimal("40.50"), 65, rates()),)
    assert got.total == Decimal("40.50") * 65 * Decimal("0.0015")


def test_a_sold_option_settled_in_the_money_costs_nothing():
    settle = PaperFill("settle", "BUY", 65, Decimal("40.50"), True)  # closes a short: STT on exercise is the holder's
    assert paper_charges([settle], "NIFTY", rates()).total == 0


@pytest.mark.parametrize("side", ["BUY", "SELL"])
def test_an_otm_settle_at_zero_costs_nothing(side):
    assert paper_charges([PaperFill("settle", side, 65, Decimal("0"), True)], "NIFTY", rates()).per_order == (0,)


def test_a_sensex_order_uses_the_bse_rate():
    fill = PaperFill("open", "SELL", 20, Decimal("150.00"), True)
    expected = charges_for_order(ChargeOrder("BSE_FO", "SELL", 20, Decimal("150.00")), rates()).total
    assert paper_charges([fill], "SENSEX", rates()).total == expected


@pytest.mark.parametrize(("fills", "underlying"), [
    ([PaperFill("open", "BUY", 65, Decimal("100"), False)], "NIFTY"),  # futures: no rate here
    ([PaperFill("open", "BUY", 65, Decimal("100"), True)], "BANKNIFTY"),  # no known segment
    ([PaperFill("teleport", "BUY", 65, Decimal("100"), True)], "NIFTY"),  # no rule for the kind
    ([PaperFill("exit", "SELL", 65, Decimal("0"), True)], "NIFTY"),  # the calculator refuses a 0 order price
    ([], "NIFTY"),
])
def test_not_computable_is_refused_never_zero(fills, underlying):
    with pytest.raises(ChargesNotComputable):
        paper_charges(fills, underlying, rates())


def test_totals_sum_or_absent_never_partial():
    assert charges_sum([Decimal("25.73"), Decimal("10.01")]) == Decimal("35.74")
    assert charges_sum([Decimal("25.73"), None]) is None
    assert charges_sum([]) == 0
