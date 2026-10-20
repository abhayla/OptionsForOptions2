"""The Execute review's risk tier rule at its boundaries (ADR-140, REQ-056 AC-6): 10% / 25% / above funds / unlimited /
funds unknown / limit set. Every expectation is a hand-written tier, never the rule's own arithmetic."""
from __future__ import annotations

from decimal import Decimal as D

import pytest
from ofo.execution.risk_tier import Reason, Tier, risk_tier

FUNDS = D("240000.00")


def tier(loss, *, funds=FUNDS, limit=None, unlimited=False):
    return risk_tier(None if loss is None else D(loss), unlimited=unlimited, funds=funds, limit=limit)


@pytest.mark.parametrize(("loss", "expected", "percent"), [
    ("5900.00", Tier.NORMAL, "2.5"),
    ("24000.00", Tier.NORMAL, "10.0"),        # exactly 10%: still NORMAL
    ("24000.01", Tier.ELEVATED, "10.0"),      # just above 10%
    ("70000.00", Tier.ELEVATED, "29.2"),
    ("60000.00", Tier.ELEVATED, "25.0"),      # no limit: above 10% is already ELEVATED
    ("240000.00", Tier.ELEVATED, "100.0"),    # exactly the funds is not EXCEPTIONAL
    ("0.00", Tier.NORMAL, "0.0"),
])
def test_no_limit_boundaries(loss, expected, percent):
    got = tier(loss)
    assert (got.tier, str(got.percent_of_funds), got.reason) == (expected, percent, None)


def test_above_funds_is_exceptional():
    got = tier("240000.01")
    assert (got.tier, got.reason, str(got.percent_of_funds)) == (Tier.EXCEPTIONAL, Reason.ABOVE_FUNDS, "100.0")


def test_unlimited_is_exceptional_whatever_the_funds():
    for funds in (FUNDS, None, D(0)):
        got = tier(None, funds=funds, unlimited=True, limit=D("1"))
        assert (got.tier, got.reason, got.percent_of_funds) == (Tier.EXCEPTIONAL, Reason.UNLIMITED, None)


def test_limit_set_within_limit_is_normal_even_above_10_percent():
    assert tier("50000.00", limit=D("50000.00")).tier is Tier.NORMAL      # 20.8% of funds, exactly at the limit
    assert tier("50000.01", limit=D("50000.00")).tier is Tier.ELEVATED    # one paisa over the limit
    assert tier("60000.00", limit=D("100000.00")).tier is Tier.NORMAL     # exactly 25%, within the limit
    assert tier("60000.01", limit=D("100000.00")).tier is Tier.ELEVATED   # above 25% beats a generous limit


def test_funds_unknown_decides_by_limit_alone_and_has_no_percentage():
    assert (tier("100.00", funds=None).tier, tier("100.00", funds=None).percent_of_funds) == (Tier.ELEVATED, None)
    assert tier("100.00", funds=None, limit=D("100.00")).tier is Tier.NORMAL
    assert tier("100.01", funds=None, limit=D("100.00")).tier is Tier.ELEVATED
    assert tier("100.00", funds=None, limit=D("100.00")).percent_of_funds is None


def test_funds_zero_never_divides():
    got = tier("1.00", funds=D(0))
    assert (got.tier, got.reason, got.percent_of_funds) == (Tier.EXCEPTIONAL, Reason.ABOVE_FUNDS, None)
    got = tier("0.00", funds=D(0))
    assert (got.tier, got.percent_of_funds) == (Tier.NORMAL, None)


def test_unknown_loss_has_no_tier():
    assert tier(None) is None
    assert tier(None, funds=None) is None
