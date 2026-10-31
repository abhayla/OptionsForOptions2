"""ofo.engine.adjust_money pnl_now and adjustment_cost: exact values, the ADJ-02 numbers, empty legs."""
from __future__ import annotations

from decimal import Decimal as D

from ofo.engine import adjust_money

# ADJ-02 (lot 65, 2 lots = 130): (side, entry, current ltp, bid, ask)
ADJ02 = [("BUY", "21.75", "0.85", "0.80", "0.90"), ("SELL", "41.80", "2.70", "2.65", "2.75"),
         ("SELL", "42.00", "84.10", "83.65", "84.55"), ("BUY", "18.00", "29.50", "29.35", "29.65")]
QTY = 130


def test_adj02_pnl_premium_left_and_cost_are_the_scenarios_numbers():
    pnl = adjust_money.pnl_now(D(0), [(s, D(e), D(ltp), QTY) for s, e, ltp, _, _ in ADJ02])
    left = adjust_money.premium_left([(s, D(ltp), QTY) for s, _, ltp, _, _ in ADJ02])
    cost = adjust_money.adjustment_cost([(D(b), D(a), QTY) for *_, b, a in ADJ02], D(40))
    assert (pnl, left, cost) == (D("-1612.00"), D("7338.50"), D("342.00"))


def test_pnl_now_adds_booked():
    assert adjust_money.pnl_now(D("100"), [("BUY", D("10"), D("12"), 5)]) == D("110")
    assert adjust_money.pnl_now(D("100"), [("SELL", D("10"), D("12"), 5)]) == D("90")


def test_empty_legs():
    assert adjust_money.pnl_now(D("7"), []) == D("7")
    assert adjust_money.adjustment_cost([], D(40)) == D(0)


def test_with_booked():
    assert adjust_money.with_booked(D("-5"), D("12.5")) == D("7.5")
