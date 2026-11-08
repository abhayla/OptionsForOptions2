"""ofo.engine.adjust_money pnl_now, premium_left and cost_with_spread: exact values, the ADJ-02 numbers, empty legs.

The old ``adjustment_cost`` (full spread of every open leg + Rs 40 a leg) is deleted (ADR-221, ADR-222 (8)); an
approach's cost is ``compare.approach_cost`` over ``cost_with_spread``."""
from __future__ import annotations

from decimal import Decimal as D

from ofo.engine import adjust_money

# ADJ-02 (lot 65, 2 lots = 130): (side, entry, current ltp, bid, ask)
ADJ02 = [("BUY", "21.75", "0.85", "0.80", "0.90"), ("SELL", "41.80", "2.70", "2.65", "2.75"),
         ("SELL", "42.00", "84.10", "83.65", "84.55"), ("BUY", "18.00", "29.50", "29.35", "29.65")]
QTY = 130


def test_adj02_pnl_and_premium_left_are_the_scenarios_numbers():
    pnl = adjust_money.pnl_now(D(0), [(s, D(e), D(ltp), QTY) for s, e, ltp, _, _ in ADJ02])
    left = adjust_money.premium_left([(s, D(ltp), QTY) for s, _, ltp, _, _ in ADJ02])
    assert (pnl, left) == (D("-1612.00"), D("7338.50"))


def test_cost_with_spread_is_charges_plus_half_the_spread_times_quantity():
    # 2.65/2.75 and 83.65/84.55 at 130: 0.05 x 130 + 0.45 x 130 = 65.00, plus Rs 27.35 of charges
    assert adjust_money.cost_with_spread(D("27.35"), [(D("2.65"), D("2.75"), QTY), (D("83.65"), D("84.55"), QTY)]) \
        == D("92.35")


def test_the_old_per_leg_cost_helper_is_gone():
    assert not hasattr(adjust_money, "adjustment_cost")


def test_pnl_now_adds_booked():
    assert adjust_money.pnl_now(D("100"), [("BUY", D("10"), D("12"), 5)]) == D("110")
    assert adjust_money.pnl_now(D("100"), [("SELL", D("10"), D("12"), 5)]) == D("90")


def test_empty_legs():
    assert adjust_money.pnl_now(D("7"), []) == D("7")
    assert adjust_money.cost_with_spread(D(0), []) == D(0)


def test_with_booked():
    assert adjust_money.with_booked(D("-5"), D("12.5")) == D("7.5")


def test_fell_at_least_pct_boundary():
    assert adjust_money.fell_at_least_pct(D("100"), D("20"), 80) is True      # exactly 80%
    assert adjust_money.fell_at_least_pct(D("100"), D("20.01"), 80) is False  # 79.99%
    assert adjust_money.fell_at_least_pct(D("0"), D("0"), 80) is False        # no entry
