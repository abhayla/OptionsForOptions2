"""GC-ICLIVE-B D-15 / D-17: every price-derived figure of the builder summary says which prices it uses.

Core: the real C11 case of 2026-11-23: a sold 65-unit leg planned at 23.85 (Get 1,550.25) and filled at 23.70 (Get
1,540.50). Hand arithmetic: 23.70 x 65 = 1,540.50; 23.85 x 65 = 1,550.25. Time value beside the credit uses the SAME
prices as the credit (contract D-16/D-17: entry prices, signed so premium received is negative), never a live price.
Proof: the tests below; the live price (30.00) must not move the time value, the entry price (23.70) does.
"""
import datetime
from decimal import Decimal as D

from ofo.engine.legs import Action, Instrument, Leg
from ofo.outcome import money

EXPIRY = datetime.date(2026, 11, 25)
Q = 65


def sold_put(entry, ltp=None):
    return Leg(Action.SELL, Instrument.PE, D("25300"), EXPIRY, Q, D(entry), None if ltp is None else D(ltp))


def test_c11_credit_at_fills_and_at_plan_by_hand():
    assert money.net_premium((sold_put("23.70"),)).amount == D("1540.50")  # 23.70 x 65
    assert money.net_premium((sold_put("23.85"),)).amount == D("1550.25")  # 23.85 x 65


def test_time_value_uses_the_credit_prices_not_the_live_price():
    # spot 25400: the sold 25300 put has no intrinsic value, so time = -(entry) x 65 whatever the live price is
    quiet = money.time_and_intrinsic((sold_put("23.70", ltp="30.00"),), D("25400"))
    moved = money.time_and_intrinsic((sold_put("23.70", ltp="12.00"),), D("25400"))
    assert (quiet.intrinsic, quiet.time) == (D("0.00"), D("-1540.50"))
    assert (moved.intrinsic, moved.time) == (quiet.intrinsic, quiet.time)  # frozen with the credit beside it


def test_time_value_needs_no_live_price_only_the_entry_price_and_the_spot():
    v = money.time_and_intrinsic((sold_put("23.70"),), D("25400"))  # no ltp at all
    assert (v.time, v.reason) == (D("-1540.50"), None)
    assert money.time_and_intrinsic((sold_put("23.70"),), None).time is None  # no spot: absent, with its reason


def test_time_value_is_entry_premium_minus_intrinsic_at_the_spot():
    # spot 25250: intrinsic 50 per unit (sold, so -3,250.00); entry premium -1,540.50 - (-3,250.00) = +1,709.50
    v = money.time_and_intrinsic((sold_put("23.70"),), D("25250"))
    assert (v.intrinsic, v.time) == (D("-3250.00"), D("1709.50"))


def test_plan_line_states_the_plan_credit_beside_the_fill_credit():
    legs = (sold_put("23.70"),)
    line = money.plan_line(legs, {"i1": D("23.85")}, ["i1"])
    assert line == "Plan: Get ₹1,550.25 at plan prices"


def test_plan_line_absent_states():
    legs = (sold_put("23.70"),)
    assert money.plan_line(legs, {}, ["i1"]) is None  # plan with no entry prices: no line, no made-up figure
    assert money.plan_line(legs, {"i1": None}, ["i1"]) is None


def test_basis_texts():
    assert money.basis_text("plan") == "At plan prices"
    assert money.basis_text("paper_fills") == "At paper fill prices"
