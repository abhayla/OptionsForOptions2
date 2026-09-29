"""REQ-041 AC-3: V1 exit conditions (profit target, max loss, time, underlying level) and the rule's chosen action."""
import datetime
from decimal import Decimal as D

import pytest

from ofo.engine import Action, Instrument, Leg, Strategy
from ofo.rules import (
    DataHealth,
    Direction,
    InputName,
    Outcome,
    ProposedOrder,
    Rule,
    RuleAction,
    RuleKind,
    Snapshot,
    Compare,
    Op,
    evaluate,
    exit_max_loss,
    exit_profit_target,
    exit_time,
    exit_underlying_level,
    respond,
)

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
EXPIRY = datetime.date(2026, 10, 27)
LEGS = (
    Leg(Action.BUY, Instrument.PE, D("22800"), EXPIRY, 75, D("42.50"), D("38.20")),
    Leg(Action.SELL, Instrument.PE, D("23000"), EXPIRY, 75, D("86.00"), D("72.50")),
    Leg(Action.SELL, Instrument.CE, D("23400"), EXPIRY, 75, D("91.50"), D("78.00")),
    Leg(Action.BUY, Instrument.CE, D("23600"), EXPIRY, 75, D("44.00"), D("39.50")),
)
CONDOR = Strategy(LEGS)


def snap(at: datetime.time = datetime.time(10, 0), **values: str) -> Snapshot:
    moment = datetime.datetime.combine(datetime.date(2026, 10, 20), at, tzinfo=IST)
    return Snapshot({InputName[k.upper()]: D(v) for k, v in values.items()}, moment, DataHealth.AVAILABLE)


def test_profit_target_and_max_loss_boundaries():
    """AC-3: profit target 3,000 triggers at 3,000 not 2,999.99; max loss 5,000 at -5,000 not -4,999.99."""
    pt = exit_profit_target("x-pt", D("3000"), action=RuleAction.ALERT_ONLY)
    ml = exit_max_loss("x-ml", D("5000"), action=RuleAction.ALERT_ONLY)
    assert evaluate(pt, snap(live_pnl="3000")).outcome is Outcome.TRIGGERED
    assert evaluate(pt, snap(live_pnl="2999.99")).outcome is Outcome.NOT_TRIGGERED
    assert evaluate(ml, snap(live_pnl="-5000")).outcome is Outcome.TRIGGERED
    assert evaluate(ml, snap(live_pnl="-4999.99")).outcome is Outcome.NOT_TRIGGERED
    assert evaluate(ml, snap(live_pnl="5000")).outcome is Outcome.NOT_TRIGGERED  # a profit is never a max loss
    for bad in (D("0"), D("-5000")):
        with pytest.raises(ValueError, match="> 0"):
            exit_max_loss("x", bad, action=RuleAction.ALERT_ONLY)


def test_time_exit():
    """AC-3: DTE <= 1 triggers at DTE 1 and 0, not 2; with 'from 15:00' both conditions must hold."""
    dte = exit_time("x-dte", days_to_expiry=1, action=RuleAction.ALERT_ONLY)
    assert [evaluate(dte, snap(dte=v)).outcome for v in ("2", "1", "0")] == [
        Outcome.NOT_TRIGGERED, Outcome.TRIGGERED, Outcome.TRIGGERED]
    clock = exit_time("x-clock", days_to_expiry=0, at_or_after=datetime.time(15, 0), action=RuleAction.ALERT_ONLY)
    assert evaluate(clock, snap(at=datetime.time(14, 59), dte="0")).outcome is Outcome.NOT_TRIGGERED
    assert evaluate(clock, snap(at=datetime.time(15, 0), dte="0")).outcome is Outcome.TRIGGERED
    assert evaluate(clock, snap(at=datetime.time(15, 0), dte="1")).outcome is Outcome.NOT_TRIGGERED
    with pytest.raises(ValueError, match="non-negative integer"):
        exit_time("x", days_to_expiry=-1, action=RuleAction.ALERT_ONLY)


def test_underlying_level_exit():
    """AC-3: 'at or below 22,900' triggers at 22,900 and not at 22,900.05."""
    rule = exit_underlying_level("x-lvl", D("22900"), Direction.AT_OR_BELOW, action=RuleAction.ALERT_ONLY)
    assert evaluate(rule, snap(underlying_level="22900")).outcome is Outcome.TRIGGERED
    assert evaluate(rule, snap(underlying_level="22900.05")).outcome is Outcome.NOT_TRIGGERED


def test_exit_action_is_required_and_is_the_rules_choice():
    """AC-3: every exit builder needs an explicit action; there is no default."""
    for build in (lambda: exit_profit_target("x", D("1")), lambda: exit_max_loss("x", D("1")),
                  lambda: exit_time("x", days_to_expiry=0),
                  lambda: exit_underlying_level("x", D("1"), Direction.AT_OR_ABOVE)):
        with pytest.raises(TypeError, match="action"):
            build()


def test_alert_only_prepares_nothing():
    """AC-3: 'Alert me' gives the decision-support alert with the triggering value and no proposal."""
    rule = exit_max_loss("x-ml", D("5000"), action=RuleAction.ALERT_ONLY)
    result = evaluate(rule, snap(live_pnl="-5002.50"))
    response = respond(rule, result, strategy_id="S-1", strategy=CONDOR)
    assert response.proposal is None
    assert response.alert == "Your rule was triggered: Max loss 5000 (live_pnl -5002.50 <= -5000)."


def test_alert_and_prepare_builds_closing_orders_never_submitted():
    """AC-3: 'alert + prepare exit orders' builds one opposite order per leg, Prepared, needing user confirmation."""
    rule = exit_max_loss("x-ml", D("5000"), action=RuleAction.ALERT_AND_PREPARE_ORDERS)
    result = evaluate(rule, snap(live_pnl="-5002.50"))
    response = respond(rule, result, strategy_id="S-1", strategy=CONDOR)
    proposal = response.proposal
    assert (proposal.strategy_id, proposal.rule_id, proposal.status, proposal.requires_user_confirmation) == (
        "S-1", "x-ml", "Prepared", True)
    assert proposal.orders == (
        ProposedOrder("S-1", Action.SELL, Instrument.PE, D("22800"), EXPIRY, 75),
        ProposedOrder("S-1", Action.BUY, Instrument.PE, D("23000"), EXPIRY, 75),
        ProposedOrder("S-1", Action.BUY, Instrument.CE, D("23400"), EXPIRY, 75),
        ProposedOrder("S-1", Action.SELL, Instrument.CE, D("23600"), EXPIRY, 75),
    )
    assert response.alert.startswith("Your rule was triggered")


def test_respond_refuses_untriggered_or_unowned():
    """AC-3: no response for a rule that did not trigger, could not be evaluated, or has no strategy id."""
    rule = exit_max_loss("x-ml", D("5000"), action=RuleAction.ALERT_AND_PREPARE_ORDERS)
    for values in ({"live_pnl": "-4999.99"}, {}):
        with pytest.raises(ValueError, match="was not triggered"):
            respond(rule, evaluate(rule, snap(**values)), strategy_id="S-1", strategy=CONDOR)
    hit = evaluate(rule, snap(live_pnl="-6000"))
    with pytest.raises(ValueError, match="strategy_id"):
        respond(rule, hit, strategy_id="", strategy=CONDOR)
    other = exit_max_loss("x-other", D("5000"), action=RuleAction.ALERT_ONLY)
    with pytest.raises(ValueError, match="not 'x-other'"):
        respond(other, hit, strategy_id="S-1", strategy=CONDOR)
    adj = Rule("a", RuleKind.ADJUSTMENT, Compare(InputName.LIVE_PNL, Op.LTE, D("0")),
               RuleAction.ALERT_AND_PREPARE_ORDERS)
    with pytest.raises(ValueError, match="adjustment orders"):
        respond(adj, evaluate(adj, snap(live_pnl="-1")), strategy_id="S-1", strategy=CONDOR)
