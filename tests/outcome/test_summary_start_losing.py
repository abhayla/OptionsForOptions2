"""W-066 round 4: "where do I start losing" names where the loss is, decided by the engine's P&L just outside and just
inside each breakeven, never by one sample at the midpoint (a zero plateau between the breakevens picked the wrong one)."""
from decimal import Decimal

import pytest

from ofo.engine.legs import Action
from ofo.outcome import OutcomeState, PlannedLeg, StrategyDefinition, build_outcome, read_snapshot
from ofo.table import UXLevel

from marketdata._kite_fixture import all_instrument_ids, new_provider, replay
from outcome.test_same_engine import CONDOR, RATE, VALUATION, entries

OUTSIDE = "If NIFTY ends below 22,400 or above 22,800 at expiry."


@pytest.fixture(scope="module")
def provider():
    p, clock, items = new_provider()
    p.subscribe(all_instrument_ids(items))
    replay(p, clock)
    return p


def _start(provider, legs):
    legs = [(leg + (1,))[:4] for leg in legs]  # (id, action, entry[, lots])
    d = StrategyDefinition("NIFTY", tuple(PlannedLeg(iid, action, lots, entry, VALUATION)
                                          for iid, action, entry, lots in legs))
    snap = read_snapshot(provider, "NIFTY", [leg[0] for leg in legs], VALUATION, RATE)
    out = build_outcome(d, snap, UXLevel.STANDARD, VALUATION)
    assert out.state is OutcomeState.COMPUTED
    return str(out.summary.where_do_i_start_losing)


def test_the_w063_condor_loses_outside_its_breakevens(provider):
    e = entries(provider)
    text = _start(provider, [(i, a, e[i]) for i, a, _, _ in CONDOR])
    assert text.startswith("If NIFTY ends below ") and " or above " in text


def test_a_condor_with_every_entry_at_100_loses_outside_not_between(provider):
    """Net premium 0: the P&L is 0 on all of 22,400..22,800, the loss is outside it."""
    assert _start(provider, [(i, a, Decimal("100.00")) for i, a, _, _ in CONDOR]) == OUTSIDE


def test_a_long_strangle_loses_between_its_breakevens(provider):
    legs = [("NSE_FO:44624", Action.BUY, Decimal("100.00")), ("NSE_FO:44604", Action.BUY, Decimal("100.00"))]
    assert _start(provider, legs) == "If NIFTY ends between 22,200 and 23,000 at expiry."


def test_a_long_wide_strangle_loses_between(provider):
    legs = [("NSE_FO:44632", Action.BUY, Decimal("50.00")), ("NSE_FO:44595", Action.BUY, Decimal("50.00"))]
    assert _start(provider, legs) == "If NIFTY ends between 22,100 and 23,100 at expiry."


def test_a_zero_premium_long_strangle_never_loses(provider):
    legs = [("NSE_FO:44624", Action.BUY, Decimal("0")), ("NSE_FO:44604", Action.BUY, Decimal("0"))]
    assert _start(provider, legs) == "At no level at expiry."


# --- W-066 round 5 (ADR-072): the sentence names every loss region, from the engine's payoff, never from breakevens ---
BUY, SELL = Action.BUY, Action.SELL
D = Decimal


def test_a_zero_cost_bull_put_spread_loses_below_22400_only(provider):
    legs = [("NSE_FO:44604", SELL, D("100")), ("NSE_FO:44595", BUY, D("100"))]
    assert _start(provider, legs) == "If NIFTY ends below 22,400 at expiry."


def test_a_1x2_put_ratio_loses_in_one_region_below_its_lower_zero(provider):
    legs = [("NSE_FO:44604", BUY, D("100")), ("NSE_FO:44595", SELL, D("50"), 2)]
    assert _start(provider, legs) == "If NIFTY ends below 22,000 at expiry."


def test_two_call_butterflies_name_every_loss_region(provider):
    legs = [("NSE_FO:44592", BUY, D("150")), ("NSE_FO:44598", SELL, D("100"), 2), ("NSE_FO:44602", BUY, D("60")),
            ("NSE_FO:44624", BUY, D("150")), ("NSE_FO:44628", SELL, D("100"), 2), ("NSE_FO:44632", BUY, D("60"))]
    assert _start(provider, legs) == "If NIFTY ends below 22,220, between 22,380 and 22,820 or above 22,980 at expiry."


def test_a_zero_cost_bull_call_spread_never_loses(provider):
    legs = [("NSE_FO:44624", BUY, D("100")), ("NSE_FO:44632", SELL, D("100"))]
    assert _start(provider, legs) == "At no level at expiry."


def test_a_butterfly_costing_its_width_loses_everywhere_except_one_point(provider):
    legs = [("NSE_FO:44592", BUY, D("200")), ("NSE_FO:44598", SELL, D("100"), 2), ("NSE_FO:44602", BUY, D("100"))]
    assert _start(provider, legs) == "At every level except exactly 22,300 at expiry."


def test_a_strategy_losing_everywhere_makes_no_claim_about_breakevens(provider):
    legs = [("NSE_FO:44604", BUY, D("300")), ("NSE_FO:44595", SELL, D("50"))]
    assert _start(provider, legs) == "At every level at expiry."


def test_a_2_lot_ratio_loss_merges_across_an_inside_strike(provider):
    """Sell 2x22400CE @100, buy 22800CE @50: net credit 150, zero at 22,475, loss above it across the 22,800 strike."""
    legs = [("NSE_FO:44602", SELL, D("100"), 2), ("NSE_FO:44624", BUY, D("50"))]
    assert _start(provider, legs) == "If NIFTY ends above 22,475 at expiry."
