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


def test_time_value_stays_on_the_live_price_pending_the_owner_decision():
    # D-17 is stopped (REQ-081 AC-3 "current premium minus intrinsic" against the contract line): live price, as before
    v = money.time_and_intrinsic((sold_put("23.70", ltp="30.00"),), D("25400"))
    assert (v.intrinsic, v.time) == (D("0.00"), D("-1950.00"))  # -(30.00 x 65)
    assert money.time_and_intrinsic((sold_put("23.70"),), D("25400")).time is None  # no live price: absent


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
