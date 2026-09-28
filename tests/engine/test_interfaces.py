"""Margin-planning and charges interfaces (REQ-032 AC-6; IC §5)."""
import ast
from decimal import Decimal as D
from pathlib import Path

import pytest

import ofo.engine.interfaces as interfaces
from ofo.engine.interfaces import (
    ChargesBreakdown,
    ChargesModel,
    MarginPlanner,
    MarginRequirement,
    estimate_charges,
    plan_margin,
    pnl_after_charges,
)


class FakeBroker:
    """Test double standing in for a broker adapter; the only place a number comes from."""

    def __init__(self, margin=D("41250.00"), charges=(("brokerage", D("80.00")), ("gst", D("14.40")))):
        self.seen = []
        self.margin, self.charges = margin, charges

    def margin_for(self, strategy):
        self.seen.append(strategy)
        return self.margin if not isinstance(self.margin, D) else MarginRequirement(self.margin, "fake basket")

    def charges_for(self, strategy):
        self.seen.append(strategy)
        return ChargesBreakdown(self.charges)


def test_engine_uses_margin_and_charges_through_the_interfaces(condor_inputs):
    """AC-6: a provider implementing the protocols supplies margin and charges; the engine nets charges off P&L."""
    fake, strategy = FakeBroker(), condor_inputs.strategy
    assert isinstance(fake, MarginPlanner) and isinstance(fake, ChargesModel)
    assert plan_margin(strategy, fake) == MarginRequirement(D("41250.00"), "fake basket")
    charges = estimate_charges(strategy, fake)
    assert charges.total == D("94.40")
    assert pnl_after_charges(strategy.live_pnl(), charges) == D("1270.60")  # 1,365.00 - 94.40
    assert fake.seen == [strategy, strategy]


def test_interfaces_fail_closed_on_contract_breaks(condor_inputs):
    """AC-6: a provider that is not one, or that answers with the wrong type or float money, is refused."""
    strategy = condor_inputs.strategy
    with pytest.raises(ValueError, match="MarginPlanner"):
        plan_margin(strategy, object())
    with pytest.raises(ValueError, match="ChargesModel"):
        estimate_charges(strategy, object())
    with pytest.raises(ValueError, match="not a MarginRequirement"):
        plan_margin(strategy, FakeBroker(margin=41250.0))
    with pytest.raises(ValueError, match="charge 'gst'"):
        estimate_charges(strategy, FakeBroker(charges=(("gst", D(14.4)),)))
    with pytest.raises(ValueError, match="source"):
        MarginRequirement(D("100.00"), "")
    with pytest.raises(ValueError, match="at least one"):
        ChargesBreakdown(())


def test_no_hard_coded_rates_or_broker_calls():
    """AC-6: the interfaces module holds no numeric rate (0, the empty sum, is the only number) and imports no
    broker/network client."""
    tree = ast.parse(Path(interfaces.__file__).read_text(encoding="utf-8"))
    numbers = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and type(n.value) in (int, float)]
    assert set(numbers) <= {0}
    imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import | ast.ImportFrom) for a in n.names}
    modules = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not any("kite" in m.lower() or "zerodha" in m.lower() for m in imported | modules)
