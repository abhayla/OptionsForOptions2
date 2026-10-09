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
    d = StrategyDefinition("NIFTY", tuple(PlannedLeg(iid, action, 1, entry, VALUATION) for iid, action, entry in legs))
    snap = read_snapshot(provider, "NIFTY", [iid for iid, _, _ in legs], VALUATION, RATE)
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
