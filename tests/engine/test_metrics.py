"""Strategy-level max profit, max loss and breakevens from the payoff (scenario-calculations.md §3)."""
import dataclasses
import datetime
from decimal import Decimal as D

import pytest

from ofo.engine import UNLIMITED, Action, Instrument, Leg, MultiExpiryError, Strategy, strategy_metrics

EXP = datetime.date(2026, 10, 27)
BUY, SELL = Action.BUY, Action.SELL
CE, PE, FUT = Instrument.CE, Instrument.PE, Instrument.FUT


def leg(action, instrument, strike, entry, qty=75, expiry=EXP):
    return Leg(action, instrument, None if strike is None else D(strike), expiry, qty, D(entry))


def test_legs_carry_no_breakeven_and_metrics_are_strategy_level():
    """AC-6: a leg has no breakeven / max profit / max loss; the strategy's come from its payoff."""
    field_names = {f.name for f in dataclasses.fields(Leg)}
    assert field_names == {"action", "instrument", "strike", "expiry", "quantity", "entry_price", "ltp"}
    single = leg(BUY, CE, "23000", "100")
    assert not any(hasattr(single, name) for name in ("breakeven", "breakevens", "max_profit", "max_loss"))

    # Long call: unlimited profit, loss = premium, breakeven on the upper tail.
    m = strategy_metrics(Strategy((single,)))
    assert (m.max_profit, m.max_loss, m.breakevens) == (UNLIMITED, D("7500"), (D("23100"),))
    # Short call: the other branch.
    m = strategy_metrics(Strategy((leg(SELL, CE, "23000", "100"),)))
    assert (m.max_profit, m.max_loss, m.breakevens) == (D("7500"), UNLIMITED, (D("23100"),))


def test_straddle_has_two_tail_breakevens():
    """AC-6: long straddle 23,000 CE 100 + PE 120, Qty 50 -> breakevens 22,780 / 23,220, max loss 11,000."""
    m = strategy_metrics(Strategy((leg(BUY, CE, "23000", "100", qty=50), leg(BUY, PE, "23000", "120", qty=50))))
    assert m.breakevens == (D("22780"), D("23220"))
    assert m.max_loss == D("11000")
    assert m.max_profit is UNLIMITED


def test_lower_tail_slope_is_unlimited_by_convention():
    """AC-6: a non-zero lower-tail slope is UNLIMITED (documented convention; the zero floor is not used)."""
    m = strategy_metrics(Strategy((leg(SELL, PE, "23000", "80"),)))
    assert m.max_profit == D("6000")
    assert m.max_loss is UNLIMITED
    assert m.breakevens == (D("22920"),)


def test_zero_exactly_at_a_kink_and_flat_zero_tail():
    """AC-6: bull call spread whose debit equals its width: zero at the 23,100 kink, flat zero above it.

    The flat zero tail reports only its kink end point.
    """
    m = strategy_metrics(Strategy((leg(BUY, CE, "23000", "150"), leg(SELL, CE, "23100", "50"))))
    assert m.breakevens == (D("23100"),)
    assert m.max_profit == D("0")
    assert m.max_loss == D("7500")


def test_flat_zero_segment_reports_both_end_points():
    """AC-6: a zero-credit iron condor is zero on 23,000..23,400; both end points are reported."""
    legs = (
        leg(BUY, PE, "22800", "10"),
        leg(SELL, PE, "23000", "10"),
        leg(SELL, CE, "23400", "10"),
        leg(BUY, CE, "23600", "10"),
    )
    m = strategy_metrics(Strategy(legs))
    assert m.breakevens == (D("23000"), D("23400"))
    assert (m.max_profit, m.max_loss) == (D("0"), D("15000"))


def test_non_terminating_breakeven_is_rounded_to_paise_of_a_point():
    """AC-6: tail slope 3 and value -10 at 23,000 -> 23,003.333... is reported as 23,003.33 (half-even)."""
    m = strategy_metrics(Strategy((leg(BUY, CE, "23000", "10", qty=1), leg(BUY, CE, "23000", "0", qty=2))))
    assert m.breakevens == (D("23003.33"),)


def test_futures_only_strategy():
    """AC-6: a BUY future breaks even at its entry; both tails are unbounded."""
    m = strategy_metrics(Strategy((leg(BUY, FUT, None, "24000"),)))
    assert m.breakevens == (D("24000"),)
    assert (m.max_profit, m.max_loss) == (UNLIMITED, UNLIMITED)


def test_multi_expiry_strategy_refuses_exact_metrics():
    """AC-6: legs on two expiries have no exact at-expiry payoff; the engine raises instead of guessing."""
    calendar = Strategy(
        (leg(SELL, CE, "23000", "100"), leg(BUY, CE, "23000", "180", expiry=datetime.date(2026, 11, 24)))
    )
    with pytest.raises(MultiExpiryError, match="one expiry"):
        strategy_metrics(calendar)
    assert issubclass(MultiExpiryError, ValueError)
