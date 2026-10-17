"""W-102 the cost of the real 2026-10-16 baskets (REQ-056 AC-8; ADR-097), no database.

Real legs (tests_app/test_execute_route.py core): ENTRY BUY 65 NIFTY 23650 CE (expiry 2026-10-19) LIMIT 3.35 on
NSE_FO; EXIT SELL 65 LIMIT 3.30. Rates = the stored seed set (migration 0012, read 2026-10-15): brokerage 20,
STT sell 0.0015, NSE transaction 0.0003553, SEBI 0.000001, stamp buy 0.00003, GST 0.18.

Hand computation, ENTRY (premium 65 x 3.35 = 217.75, paid -> -217.75):
  transaction 217.75 x 0.0003553 = 0.077366575; SEBI 217.75 x 0.000001 = 0.00021775; stamp 217.75 x 0.00003 = 0.0065325;
  STT 0 (BUY); GST (20 + 0.00021775 + 0.077366575) x 0.18 = 20.077584325 x 0.18 = 3.6139651785;
  total 20 + 0.077366575 + 0.00021775 + 0.0065325 + 3.6139651785 = 23.6980820035.
Hand computation, EXIT (premium 65 x 3.30 = 214.50, received -> +214.50):
  STT 214.50 x 0.0015 = 0.32175; transaction 214.50 x 0.0003553 = 0.07621185; SEBI 0.0002145; stamp 0 (SELL);
  GST (20 + 0.0002145 + 0.07621185) x 0.18 = 3.613756743; total 24.011933093.
  Cross-check: Zerodha's own basket-margin reply for this exit (margins-basket-exit-150717.json, orders[0].charges)
  printed transaction_tax 0.32175, exchange_turnover_charge 0.07621185..., total 24.011933093.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal as D

import pytest
from ofo.charges.calculator import ChargeOrder
from ofo.charges.rates import ChargeRates
from ofo.execution.cost import BasketCost, basket_cost, signed_premium
from ofo.instruments.models import NSE_FO

RATES = ChargeRates(
    brokerage_per_order=D("20"), stt_sell_rate=D("0.0015"), stt_exercise_rate=D("0.0015"),
    transaction_rates={"NSE_FO": D("0.0003553"), "BSE_FO": D("0.000325")}, sebi_rate=D("0.000001"),
    stamp_buy_rate=D("0.00003"), gst_rate=D("0.18"), read_on=date(2026, 10, 15),
    source_url="https://zerodha.com/charges (F&O options), read 2026-10-15; F-35")
ENTRY = ChargeOrder(NSE_FO, "BUY", 65, D("3.35"))
EXIT = ChargeOrder(NSE_FO, "SELL", 65, D("3.30"))


def test_ac8_real_entry_costs_217_75_paid_and_23_698_charges() -> None:
    """AC-8: the real ENTRY: net premium -217.75 (65 x 3.35 paid), charges 23.6980820035 (module docstring)."""
    assert basket_cost([ENTRY], RATES) == BasketCost(D("-217.75"), D("23.6980820035"))


def test_ac8_real_exit_receives_214_50_and_charges_match_zerodhas_reply() -> None:
    """AC-8: the real EXIT: +214.50 received (65 x 3.30), charges 24.011933093 = Zerodha's own figure."""
    assert basket_cost([EXIT], RATES) == BasketCost(D("214.50"), D("24.011933093"))


def test_ac8_a_two_leg_basket_nets_buy_against_sell() -> None:
    """AC-8: BUY 217.75 paid + SELL 214.50 received = -3.25; charges 23.6980820035 + 24.011933093 = 47.7100150965."""
    assert basket_cost([ENTRY, EXIT], RATES) == BasketCost(D("-3.25"), D("47.7100150965"))


def test_ac8_the_sign_follows_the_side() -> None:
    """AC-8: a BUY is negative, a SELL positive (65 x 3.35 = 217.75; 65 x 3.30 = 214.50)."""
    assert (signed_premium(ENTRY), signed_premium(EXIT)) == (D("-217.75"), D("214.50"))


def test_ac8_no_rates_gives_no_charges_never_a_default() -> None:
    """AC-8: rates None -> charges None (not 0, not a default set); the premium is still exact."""
    assert basket_cost([ENTRY], None) == BasketCost(D("-217.75"), None)


@pytest.mark.parametrize("quantity", [0, -65])
def test_ac8_a_quantity_of_zero_or_below_is_refused(quantity: int) -> None:
    """AC-8: no order of 0 or negative units can be costed (the calculator's own order type refuses it)."""
    with pytest.raises(ValueError, match="quantity"):
        basket_cost([ChargeOrder(NSE_FO, "BUY", quantity, D("3.35"))], RATES)


def test_ac8_a_float_price_an_empty_basket_and_a_foreign_order_are_refused() -> None:
    """AC-8: float money, no orders, an object that is not a ChargeOrder, and rates of another type all raise."""
    with pytest.raises(ValueError, match="Decimal"):
        ChargeOrder(NSE_FO, "BUY", 65, 3.35)  # type: ignore[arg-type]
    for rates in (RATES, None):  # without rates the calculator never runs, so the cost's own check must refuse
        with pytest.raises(ValueError, match="no orders"):
            basket_cost([], rates)
    with pytest.raises(ValueError, match="ChargeOrder"):
        basket_cost([("NSE_FO", "BUY", 65, D("3.35"))], RATES)  # type: ignore[list-item]
    with pytest.raises(ValueError, match="rates"):
        basket_cost([ENTRY], {"brokerage_per_order": D("20")})  # type: ignore[arg-type]


def test_ac8_a_side_outside_buy_sell_has_no_sign() -> None:
    """AC-8: a side that slipped past the order type (forced through object.__setattr__) is refused, never signed."""
    odd = ChargeOrder(NSE_FO, "BUY", 65, D("3.35"))
    object.__setattr__(odd, "side", "HOLD")
    with pytest.raises(ValueError, match="side"):
        signed_premium(odd)
