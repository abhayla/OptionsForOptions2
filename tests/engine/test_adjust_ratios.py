"""ofo.engine.adjust_ratios: exact (numerator, denominator) pairs; missing or non-positive denominators refused."""
from __future__ import annotations

from decimal import Decimal as D

import pytest
from ofo.engine.adjust_ratios import (
    loss_pct_of_margin,
    loss_pct_of_max_loss,
    premium_left_per_cost,
    profit_pct_of_max_profit,
)


def test_loss_pct_of_max_loss():
    assert loss_pct_of_max_loss(D("-1300"), D("26000")) == (D("130000"), D("26000"))  # 5%
    assert loss_pct_of_max_loss(D("500"), D("26000")) == (D("0"), D("26000"))  # a profit is no loss


def test_profit_pct_of_max_profit():
    assert profit_pct_of_max_profit(D("1300.50"), D("2601")) == (D("130050.00"), D("2601"))
    assert profit_pct_of_max_profit(D("-5"), D("2601")) == (D("0"), D("2601"))


def test_loss_pct_of_margin():
    assert loss_pct_of_margin(D("-4225"), D("211250")) == (D("422500"), D("211250"))  # 2.00% (ADJ-41)


def test_premium_left_per_cost():
    assert premium_left_per_cost(D("110.50"), D("212.00")) == (D("110.50"), D("212.00"))  # 0.5212 (ADJ-14)
    assert premium_left_per_cost(D("0"), D("212")) == (D("0"), D("212"))


@pytest.mark.parametrize(("fn", "args", "name"), [
    (loss_pct_of_max_loss, (D("-1"), D("0")), "max_loss"),
    (loss_pct_of_max_loss, (D("-1"), None), "max_loss"),
    (profit_pct_of_max_profit, (D("1"), D("0")), "max_profit"),
    (profit_pct_of_max_profit, (None, D("10")), "pnl"),
    (loss_pct_of_margin, (D("-1"), D("-5")), "margin"),
    (loss_pct_of_margin, (D("-1"), None), "margin"),
    (premium_left_per_cost, (D("10"), D("0")), "adjustment_cost"),
    (premium_left_per_cost, (D("10"), None), "adjustment_cost"),
    (premium_left_per_cost, (D("-1"), D("10")), "premium_left"),
    (loss_pct_of_max_loss, (D("-1"), 26000.0), "max_loss"),  # a float is not a Decimal
])
def test_missing_or_non_positive_denominator_is_refused(fn, args, name):
    with pytest.raises(ValueError, match=name):
        fn(*args)
