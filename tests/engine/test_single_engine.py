"""One engine serves every view; no component re-implements a formula (REQ-032 AC-1; ADR-008)."""
from decimal import Decimal as D

import pytest
from conftest import leg_input

from ofo.engine import UNLIMITED, Action, Instrument, Leg, Strategy, legs, scenario_grid, strategy_metrics
from ofo.engine.estimate import EstimatedNow, estimate_now, estimate_now_grid


def test_grid_live_and_estimate_share_one_sign_convention(condor_inputs, monkeypatch):
    """AC-1: patching the engine's one P&L sign convention (legs.position_pnl) changes the scenario grid, live P&L
    and the Estimated Now result together, so none of them carries its own formula."""
    strategy = condor_inputs.strategy
    before = (
        scenario_grid(strategy, [D("22000")]).totals[0],
        strategy.live_pnl(),
        estimate_now(condor_inputs, D("23200")).total,
    )
    assert before == (D("-8175.00"), D("1365.00"), D("1365.00"))

    calls = []

    def marker(leg, value):
        calls.append(value)
        return D("1")

    monkeypatch.setattr(legs, "position_pnl", marker)
    after = (
        scenario_grid(strategy, [D("22000")]).totals[0],
        strategy.live_pnl(),
        estimate_now(condor_inputs, D("23200")).total,
    )
    assert after == (D("4"), D("4"), D("4"))  # 4 legs x the patched 1 each, in all three views
    assert len(calls) == 12


def test_estimate_now_is_labelled_and_reuses_the_engine(condor_inputs):
    """AC-1: at the current level and valuation time the estimate re-prices each leg to its LTP (IV implied from
    that LTP), so Estimated Now equals live P&L; at another level it is a separate, labelled estimate."""
    now = estimate_now(condor_inputs, D("23200"))
    assert now.marks == (D("38.20"), D("72.50"), D("78.00"), D("39.50"))
    assert now.total == condor_inputs.strategy.live_pnl() == D("1365.00")

    up = estimate_now(condor_inputs, D("23500"))
    assert isinstance(up, EstimatedNow) and up.kind == "estimate"
    assert up.marks == (D("9.34"), D("19.35"), D("226.15"), D("131.71"))
    # (9.34-42.50)x75 + (86-19.35)x75 + (91.50-226.15)x75 + (131.71-44)x75
    assert up.leg_pnls == (D("-2487.00"), D("4998.75"), D("-10098.75"), D("6578.25"))
    assert up.total == D("-1008.75")
    assert up.total != condor_inputs.strategy.expiry_pnl_at(D("23500"))  # not the at-expiry number (-675)
    assert up.assumptions.ivs == tuple(leg.iv for leg in condor_inputs.legs)
    assert up.assumptions.rate == D("0.065") and up.assumptions.years_to_expiry[0] == D(10) / D(365)
    assert [e.total for e in estimate_now_grid(condor_inputs, [D("23200"), D("23500")])] == [now.total, up.total]


def test_futures_leg_estimate_uses_cost_of_carry(condor_inputs):
    """AC-1: a futures leg is marked at S e^(rT) and goes through the same sign convention."""
    from ofo.engine.inputs import StrategyInput

    fut = leg_input(Action.BUY, Instrument.FUT, None, "23250.00", "23240.00", contract="NIFTY26OCTFUT")
    inputs = StrategyInput("NIFTY", D("23200"), condor_inputs.valuation_time, D("0.065"), (fut,))
    est = estimate_now(inputs, D("23500"))
    assert est.marks == (D("23541.89"),)  # 23500 x e^(0.065 x 10/365)
    assert est.total == D("21891.75")  # (23541.89 - 23250.00) x 75


def test_estimate_without_iv_or_after_expiry_fails_closed(condor_inputs):
    """AC-1: an option leg without IV, a valuation after expiry, or a zero level is refused, never defaulted."""
    from dataclasses import replace

    no_iv = replace(condor_inputs, legs=(leg_input(Action.BUY, Instrument.PE, "22800", "42.50", "38.20"),))
    with pytest.raises(ValueError, match="no IV"):
        estimate_now(no_iv, D("23200"))
    late = replace(condor_inputs, valuation_time=condor_inputs.valuation_time.replace(day=28))
    with pytest.raises(ValueError, match="after the"):
        estimate_now(late, D("23200"))
    with pytest.raises(ValueError, match="level"):
        estimate_now(condor_inputs, D("0"))


def test_flipping_the_one_convention_flips_metrics(condor_inputs, monkeypatch):
    """AC-1: strategy metrics (values at strikes AND the upper-tail slope) come from legs.position_pnl; negating
    that one function swaps max profit and max loss, including an unlimited upside becoming an unlimited loss."""
    condor = condor_inputs.strategy
    long_call = Strategy((Leg(Action.BUY, Instrument.CE, D("23000"), condor.legs[0].expiry, 75, D("100.00")),))
    before_condor, before_call = strategy_metrics(condor), strategy_metrics(long_call)
    assert (before_condor.max_profit, before_condor.max_loss) == (D("6825.00"), D("8175.00"))
    assert (before_call.max_profit, before_call.max_loss) == (UNLIMITED, D("7500.00"))

    original = legs.position_pnl
    monkeypatch.setattr(legs, "position_pnl", lambda leg, value: -original(leg, value))
    after_condor, after_call = strategy_metrics(condor), strategy_metrics(long_call)
    assert (after_condor.max_profit, after_condor.max_loss) == (D("8175.00"), D("6825.00"))
    assert (after_call.max_profit, after_call.max_loss) == (D("7500.00"), UNLIMITED)
