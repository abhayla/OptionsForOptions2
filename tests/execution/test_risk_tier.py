"""The Execute review's risk tier rule at its boundaries (ADR-140, REQ-056 AC-6): 10% / 25% / above funds / unlimited /
funds unknown / limit set. Every expectation is a hand-written tier, never the rule's own arithmetic."""
from __future__ import annotations

import datetime
from decimal import Decimal as D

import pytest
from ofo.engine import Action, Instrument
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


def test_unknown_loss_is_at_least_elevated_never_a_silent_pass():
    """ADR-143 (owner 2026-10-20): the engine returned no worst case on an entry -> ELEVATED, reason LOSS_UNKNOWN,
    whatever the funds (known, unknown, zero) and whatever the limit."""
    for funds in (FUNDS, None, D(0)):
        for limit in (None, D("1000000")):
            got = tier(None, funds=funds, limit=limit)
            assert (got.tier, got.reason, got.percent_of_funds) == (Tier.ELEVATED, Reason.LOSS_UNKNOWN, None)


def test_unknown_loss_with_an_uncovered_short_is_exceptional():
    got = risk_tier(None, unlimited=False, funds=FUNDS, limit=None, unknown_loss=Reason.UNCOVERED_SHORT)
    assert (got.tier, got.reason, got.percent_of_funds) == (Tier.EXCEPTIONAL, Reason.UNCOVERED_SHORT, None)


def test_an_exit_with_no_known_loss_has_no_tier():
    for funds in (FUNDS, None):
        assert risk_tier(None, unlimited=False, funds=funds, limit=None, unknown_loss=None) is None


def test_the_reason_for_an_unknown_loss_is_chosen_from_the_legs_and_the_action():
    from ofo.execution.risk_tier import unknown_loss_reason  # noqa: PLC0415

    naked = [_leg(Action.SELL, Instrument.CE)]
    covered = [_leg(Action.SELL, Instrument.CE), _leg(Action.BUY, Instrument.CE)]
    assert unknown_loss_reason(naked, is_exit=False) is Reason.UNCOVERED_SHORT
    assert unknown_loss_reason(covered, is_exit=False) is Reason.LOSS_UNKNOWN
    assert unknown_loss_reason(naked, is_exit=True) is None  # an exit's closing orders say nothing about the risk left


def _leg(action, instrument, strike="23650"):
    from ofo.engine import Leg  # noqa: PLC0415

    return Leg(action, instrument, None if instrument is Instrument.FUT else D(strike), datetime.date(2026, 10, 27), 65,
               D("10"), D("10"))


def test_uncovered_short_needs_a_protective_buy_of_the_same_option_type():
    from ofo.execution.risk_tier import has_uncovered_short  # noqa: PLC0415

    sell_ce, buy_ce = _leg(Action.SELL, Instrument.CE), _leg(Action.BUY, Instrument.CE, "23800")
    buy_pe, sell_pe = _leg(Action.BUY, Instrument.PE), _leg(Action.SELL, Instrument.PE)
    assert has_uncovered_short([sell_ce]) is True                      # a naked short call
    assert has_uncovered_short([sell_ce, buy_ce]) is False             # a call spread
    assert has_uncovered_short([sell_ce, buy_pe]) is True              # a put does not protect a short call
    assert has_uncovered_short([sell_ce, buy_ce, sell_pe]) is True     # one covered side, one naked side
    assert has_uncovered_short([sell_ce, buy_ce, sell_pe, buy_pe]) is False
    assert has_uncovered_short([buy_ce]) is False                      # no short at all
    assert has_uncovered_short([_leg(Action.SELL, Instrument.FUT)]) is True
