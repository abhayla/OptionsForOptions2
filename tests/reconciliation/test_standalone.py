"""REQ-060 AC-7: standalone positions are recorded with their quantity and are not mismatches; Zerodha's net quantity
per contract is compared with the strategy legs plus the recorded standalone quantity; a broker position in no
strategy and not recorded standalone is offered the grouping choice (Q24) and blocks no strategy; a mismatch blocks
only the strategy whose contract quantity disagrees.

The spec's own example: strategy SELL 25,000 CE x 50 plus standalone x 25; Zerodha x 75 -> no mismatch; Zerodha
x 50 -> that strategy is blocked.
"""
from __future__ import annotations

from decimal import Decimal as D

import pytest

import ofo.reconciliation.compare as compare_module
from ofo.engine import Action, Instrument
from ofo.reconciliation.compare import MismatchKind, ReconciliationError, compare
from ofo.strategy.definition import DefinitionLeg, StrategyDefinition
from recon_fixtures import EXPIRY, at, clock, executed

CE25000 = ("NIFTY", Instrument.CE, D("25000"), EXPIRY)
CE25500 = ("NIFTY", Instrument.CE, D("25500"), EXPIRY)
SELL_25000_X50 = StrategyDefinition("NIFTY", (DefinitionLeg(Action.SELL, Instrument.CE, D("25000"), EXPIRY, 50),))
OTHER = StrategyDefinition("NIFTY", (DefinitionLeg(Action.SELL, Instrument.CE, D("25500"), EXPIRY, 75),))


def strategies():
    return {"S-25000": executed(SELL_25000_X50, "e1"), "S-25500": executed(OTHER, "e2")}


def test_ac7_spec_example_x75_is_no_mismatch():
    """AC-7: -50 strategy + -25 standalone = -75 expected; Zerodha -75 -> no mismatch, nothing blocked."""
    report = compare({CE25000: -75, CE25500: -75}, strategies(), {CE25000: -25}, at=at(10), clock=clock)
    assert report.mismatches == () and report.blocked_strategy_ids == frozenset()


def test_ac7_spec_example_x50_blocks_that_strategy_only():
    """AC-7: Zerodha -50 on 25000 CE -> difference +25, S-25000 blocked, S-25500 not."""
    report = compare({CE25000: -50, CE25500: -75}, strategies(), {CE25000: -25}, at=at(10), clock=clock)
    (m,) = report.mismatches
    assert m.strategy_ids == ("S-25000",) and m.difference == ((CE25000, 25),)
    assert m.platform_state == ((CE25000, -75),) and m.kind is MismatchKind.QUANTITY_MISMATCH
    assert report.blocked_strategy_ids == frozenset({"S-25000"})


def test_ac7_ungrouped_broker_position_offers_grouping_and_blocks_none():
    """AC-7: 26000 CE x 25 in no strategy, not recorded -> grouping choice, no strategy blocked."""
    ce26000 = ("NIFTY", Instrument.CE, D("26000"), EXPIRY)
    report = compare({CE25000: -75, CE25500: -75, ce26000: -25}, strategies(), {CE25000: -25}, at=at(10),
                     clock=clock)
    (m,) = report.mismatches
    assert m.kind is MismatchKind.UNEXPECTED_BROKER_POSITION and not m.blocks
    assert "add to an existing strategy, create a new strategy, or leave it standalone" in m.next_action
    assert report.blocked_strategy_ids == frozenset()


def test_ac7_recorded_standalone_alone_on_a_contract_is_no_mismatch():
    """AC-7: a standalone-only contract matching its recorded quantity is not reported."""
    report = compare({CE25000: -50, CE25500: -75, ("NIFTY", Instrument.PE, D("24000"), EXPIRY): 75},
                     strategies(), {("NIFTY", Instrument.PE, D("24000"), EXPIRY): 75}, at=at(10), clock=clock)
    assert report.mismatches == ()


@pytest.mark.parametrize("bad", [{CE25000: "25"}, {CE25000: 2.5}, "CE25000", {("NIFTY", "CE", D("25000"), EXPIRY): 25}])
def test_ac7_rejects_invalid_standalone_records(bad):
    """AC-7 (input domain): a malformed standalone record is refused, never read as zero."""
    with pytest.raises(ReconciliationError):
        compare({CE25000: -75}, strategies(), bad, at=at(10), clock=clock)


def test_ac7_mutant_ignoring_standalone_is_caught(monkeypatch):
    """AC-7 mutation: an allocation rule that drops the standalone quantity flags the x75 example."""
    real_rule = compare_module.expected_units

    def without_standalone(actives, standalone):
        return real_rule(actives, {})

    monkeypatch.setattr(compare_module, "expected_units", without_standalone)
    report = compare({CE25000: -75, CE25500: -75}, strategies(), {CE25000: -25}, at=at(10), clock=clock)
    assert report.blocked_strategy_ids == frozenset({"S-25000"})      # the mutant is visible: the spec says none


def test_ac7_mutant_blocking_on_unheld_contract_is_caught(monkeypatch):
    """AC-7 mutation: attributing an ungrouped broker position to every strategy would block both; the real rule
    blocks none."""
    ce26000 = ("NIFTY", Instrument.CE, D("26000"), EXPIRY)
    broker = {CE25000: -75, CE25500: -75, ce26000: -25}
    real = compare(broker, strategies(), {CE25000: -25}, at=at(10), clock=clock)
    assert real.blocked_strategy_ids == frozenset()
    monkeypatch.setattr(compare_module, "holders_of", lambda contract, actives, proposals: tuple(sorted(actives)))
    mutated = compare(broker, strategies(), {CE25000: -25}, at=at(10), clock=clock)
    assert mutated.blocked_strategy_ids == frozenset({"S-25000", "S-25500"}) != real.blocked_strategy_ids
