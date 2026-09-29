"""Core proof (W-013): rules evaluated against snapshots whose live P&L comes from the W-001 engine.

The golden Iron Condor (scenario-calculations.md §6) is re-priced with varied LTPs as the market rallies into the
short 23,400 call. Its P&L moves in steps of 3.75 (a 0.05 tick x 75 units), so a live P&L of exactly -5,000 is not
reachable from real tick prices: the nearest values are -4,998.75 and -5,002.50. The exact-threshold boundary is
therefore proven twice: at -4,500 (reachable) through the engine, and at -5,000 on a snapshot carrying that value.
"""
import datetime
from decimal import Decimal as D

import pytest

from ofo.engine import Action, Instrument, Leg, Strategy
from ofo.rules import (
    DataHealth,
    Direction,
    InputName,
    Outcome,
    RuleAction,
    Snapshot,
    entry_level_reached,
    evaluate,
    exit_max_loss,
    exit_profit_target,
    exit_underlying_level,
    snapshot_from_strategy,
)

EXPIRY = datetime.date(2026, 10, 27)
QTY = 75
AS_OF = datetime.datetime(2026, 10, 20, 11, 15, tzinfo=datetime.timezone(datetime.timedelta(hours=5, minutes=30)))


def condor(ltp1: str, ltp2: str, ltp3: str, ltp4: str) -> Strategy:
    """The §6 legs and entry prices, with the given LTPs."""
    return Strategy((
        Leg(Action.BUY, Instrument.PE, D("22800"), EXPIRY, QTY, D("42.50"), D(ltp1)),
        Leg(Action.SELL, Instrument.PE, D("23000"), EXPIRY, QTY, D("86.00"), D(ltp2)),
        Leg(Action.SELL, Instrument.CE, D("23400"), EXPIRY, QTY, D("91.50"), D(ltp3)),
        Leg(Action.BUY, Instrument.CE, D("23600"), EXPIRY, QTY, D("44.00"), D(ltp4)),
    ))


# (underlying level, LTPs, engine live P&L) - the P&L column is asserted against the engine below.
LEVELS = {
    "golden": (D("23200"), ("38.20", "72.50", "78.00", "39.50"), D("1365.00")),
    "rally": (D("23380"), ("20.00", "30.00", "180.00", "100.00"), D("75.00")),
    "loss_4500": (D("23460"), ("5.00", "10.00", "300.00", "154.00"), D("-4500.00")),
    "near_5000": (D("23480"), ("5.00", "10.00", "300.00", "147.35"), D("-4998.75")),
    "past_5000": (D("23481"), ("5.00", "10.00", "300.05", "147.35"), D("-5002.50")),
}


def snap(name: str, health: DataHealth = DataHealth.AVAILABLE) -> Snapshot:
    level, ltps, _ = LEVELS[name]
    return snapshot_from_strategy(condor(*ltps), underlying_level=level, as_of=AS_OF, data_health=health,
                                  source="golden-condor")


def test_snapshot_live_pnl_is_the_engines():
    """AC-4: LIVE_PNL in the snapshot is exactly Strategy.live_pnl() at every level."""
    for name, (_, ltps, expected) in LEVELS.items():
        assert condor(*ltps).live_pnl() == expected, name
        assert snap(name).get(InputName.LIVE_PNL) == expected, name


def test_max_loss_5000_triggers_at_or_below_and_reports_the_value():
    """AC-3: max loss 5,000 is not triggered at -4,998.75 and is triggered at -5,002.50, reporting that value."""
    rule = exit_max_loss("x-max-loss", D("5000"), action=RuleAction.ALERT_AND_PREPARE_ORDERS)
    for name in ("golden", "rally", "loss_4500", "near_5000"):
        result = evaluate(rule, snap(name))
        assert result.outcome is Outcome.NOT_TRIGGERED, name
        assert result.observations[0].value == LEVELS[name][2]

    hit = evaluate(rule, snap("past_5000"))
    assert hit.outcome is Outcome.TRIGGERED
    (obs,) = hit.observations
    assert (obs.input, obs.value, obs.threshold, obs.held) == (InputName.LIVE_PNL, D("-5002.50"), D("-5000"), True)
    assert hit.reason == "live_pnl -5002.50 <= -5000"
    assert hit.as_of == AS_OF and hit.data_health is DataHealth.AVAILABLE and hit.source == "golden-condor"


def test_max_loss_boundary_exactly_at_threshold_through_the_engine():
    """AC-3: max loss 4,500 triggers when engine live P&L is exactly -4,500.00 (inclusive boundary)."""
    rule = exit_max_loss("x-4500", D("4500"), action=RuleAction.ALERT_ONLY)
    result = evaluate(rule, snap("loss_4500"))
    assert result.outcome is Outcome.TRIGGERED
    assert result.observations[0].value == D("-4500.00")
    # One tick better (-4,496.25) is not a trigger.
    better = snapshot_from_strategy(condor("5.00", "10.00", "300.00", "154.05"), underlying_level=D("23460"),
                                    as_of=AS_OF, data_health=DataHealth.AVAILABLE)
    assert better.get(InputName.LIVE_PNL) == D("-4496.25")
    assert evaluate(rule, better).outcome is Outcome.NOT_TRIGGERED


def test_max_loss_5000_boundary_exactly_at_threshold():
    """AC-3: a live P&L of exactly -5,000 triggers max loss 5,000; -4,999.99 does not."""
    rule = exit_max_loss("x-max-loss", D("5000"), action=RuleAction.ALERT_ONLY)
    at = Snapshot({InputName.LIVE_PNL: D("-5000")}, AS_OF, DataHealth.AVAILABLE)
    above = Snapshot({InputName.LIVE_PNL: D("-4999.99")}, AS_OF, DataHealth.AVAILABLE)
    assert evaluate(rule, at).outcome is Outcome.TRIGGERED
    assert evaluate(rule, above).outcome is Outcome.NOT_TRIGGERED


def test_profit_target_exactly_at_engine_value():
    """AC-3: profit target 1,365 triggers at the golden live P&L of exactly 1,365.00; 1,365.01 does not."""
    at = exit_profit_target("x-pt", D("1365"), action=RuleAction.ALERT_ONLY)
    beyond = exit_profit_target("x-pt2", D("1365.01"), action=RuleAction.ALERT_ONLY)
    assert evaluate(at, snap("golden")).outcome is Outcome.TRIGGERED
    assert evaluate(beyond, snap("golden")).outcome is Outcome.NOT_TRIGGERED


def test_underlying_exit_and_entry_across_levels():
    """AC-2/AC-3: underlying-level rules flip exactly at the level across the rally snapshots."""
    exit_rule = exit_underlying_level("x-lvl", D("23460"), Direction.AT_OR_ABOVE, action=RuleAction.ALERT_ONLY)
    entry_rule = entry_level_reached("e-lvl", D("23380"), Direction.AT_OR_BELOW, action=RuleAction.ALERT_ONLY)
    outcomes = {name: (evaluate(exit_rule, snap(name)).outcome, evaluate(entry_rule, snap(name)).outcome)
                for name in LEVELS}
    assert outcomes == {
        "golden": (Outcome.NOT_TRIGGERED, Outcome.TRIGGERED),
        "rally": (Outcome.NOT_TRIGGERED, Outcome.TRIGGERED),
        "loss_4500": (Outcome.TRIGGERED, Outcome.NOT_TRIGGERED),
        "near_5000": (Outcome.TRIGGERED, Outcome.NOT_TRIGGERED),
        "past_5000": (Outcome.TRIGGERED, Outcome.NOT_TRIGGERED),
    }


@pytest.mark.parametrize("health", [h for h in DataHealth if h is not DataHealth.AVAILABLE])
def test_unhealthy_data_cannot_evaluate_even_past_the_threshold(health):
    """AC-3: at -5,002.50 on stale/delayed/unhealthy/unavailable data the rule is CANNOT_EVALUATE, not triggered."""
    rule = exit_max_loss("x-max-loss", D("5000"), action=RuleAction.ALERT_ONLY)
    result = evaluate(rule, snap("past_5000", health))
    assert result.outcome is Outcome.CANNOT_EVALUATE
    assert result.observations == ()
    assert result.data_health is health


def test_leg_without_ltp_leaves_live_pnl_missing_not_zero():
    """AC-4: a leg with no LTP means LIVE_PNL is missing, and the max-loss rule cannot be evaluated."""
    strategy = Strategy((
        Leg(Action.BUY, Instrument.PE, D("22800"), EXPIRY, QTY, D("42.50"), None),
        Leg(Action.SELL, Instrument.PE, D("23000"), EXPIRY, QTY, D("86.00"), D("72.50")),
    ))
    snapshot = snapshot_from_strategy(strategy, underlying_level=D("23200"), as_of=AS_OF,
                                      data_health=DataHealth.AVAILABLE)
    assert snapshot.get(InputName.LIVE_PNL) is None
    result = evaluate(exit_max_loss("x", D("5000"), action=RuleAction.ALERT_ONLY), snapshot)
    assert result.outcome is Outcome.CANNOT_EVALUATE
    assert result.missing == (InputName.LIVE_PNL,)
