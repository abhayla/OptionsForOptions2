"""What a triggered rule does: an alert, and for ALERT_AND_PREPARE_ORDERS a proposal the user reviews.

ADR-009 (Q5 = B, Q18 = D): V1 never places an order; "prepare" only builds a ``Proposal`` with status Prepared that
needs the user's confirmation (invariant: no order without a user confirmation event). Every proposed order carries
its strategy id (ADR-002). Wording is decision-support (ADR-003, ADR-011 Q149): "Your rule was triggered".
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from decimal import Decimal

from ofo.engine import Action, Instrument, Leg, Strategy
from ofo.rules.model import Evaluation, Outcome, Rule, RuleAction, RuleKind, describe


@dataclass(frozen=True)
class ProposedOrder:
    strategy_id: str
    action: Action
    instrument: Instrument
    strike: Decimal | None
    expiry: datetime.date
    quantity: int


@dataclass(frozen=True)
class Proposal:
    """Orders prepared for review. Never submitted by this module."""

    strategy_id: str
    rule_id: str
    orders: tuple[ProposedOrder, ...]
    status: str = "Prepared"
    requires_user_confirmation: bool = True


@dataclass(frozen=True)
class RuleResponse:
    alert: str
    proposal: Proposal | None


def _order(strategy_id: str, leg: Leg, action: Action) -> ProposedOrder:
    return ProposedOrder(strategy_id, action, leg.instrument, leg.strike, leg.expiry, leg.quantity)


def respond(rule: Rule, evaluation: Evaluation, *, strategy_id: str, strategy: Strategy) -> RuleResponse:
    """The alert (always) and, when the rule chose it, the prepared entry or exit orders of a triggered rule."""
    if evaluation.rule_id != rule.rule_id:
        raise ValueError(f"evaluation is for rule {evaluation.rule_id!r}, not {rule.rule_id!r}")
    if evaluation.outcome is not Outcome.TRIGGERED:
        raise ValueError(f"rule {rule.rule_id!r} was not triggered ({evaluation.outcome.value}); nothing to respond")
    if not isinstance(strategy_id, str) or not strategy_id.strip():
        raise ValueError("every prepared order belongs to a strategy: strategy_id is required")
    detail = describe(evaluation.observations) or "no condition"
    alert = f"Your rule was triggered: {rule.description or rule.rule_id} ({detail})."
    if rule.action is RuleAction.ALERT_ONLY:
        return RuleResponse(alert, None)
    if rule.kind is RuleKind.EXIT:
        opposite = {Action.BUY: Action.SELL, Action.SELL: Action.BUY}
        orders = tuple(_order(strategy_id, leg, opposite[leg.action]) for leg in strategy.legs)
    elif rule.kind is RuleKind.ENTRY:
        orders = tuple(_order(strategy_id, leg, leg.action) for leg in strategy.legs)
    else:
        raise ValueError("adjustment orders depend on the adjustment chosen (ADR-011); not prepared by this module")
    return RuleResponse(alert, Proposal(strategy_id, rule.rule_id, orders))
