"""What a triggered rule does: an alert, and for ALERT_AND_PREPARE_ORDERS a proposal the user reviews.

ADR-009 (Q5 = B, Q18 = D): V1 never places an order; "prepare" only builds a ``Proposal`` with status Prepared that
needs the user's confirmation (invariant: no order without a user confirmation event). Every proposed order carries
its strategy id (ADR-002). Wording is decision-support (ADR-003, ADR-011 Q149): "Your rule was triggered".

ADR-092 (issue 63): every proposed order is the whole leg as ONE order, never split for the freeze limit; ``respond``
checks each against its stored limit (``ofo.execution.freeze.require_within_freeze``). A leg not below its KNOWN
limit prepares NO proposal: the alert is still given and ``blocked`` carries the reason and the limit. A leg with no
entry, no stored limit or an unusable one is proposed with the warning in ``warnings`` (ADR-081, ADR-037: never a
block); a stale limit adds the age warning, dated by the evaluation's IST day.
"""
from __future__ import annotations
from ofo.errors.explanations import render_explanation

import datetime
from dataclasses import dataclass
from decimal import Decimal

from collections.abc import Mapping

from ofo.engine import Action, Instrument, Leg, Strategy
from ofo.errors import UserFacingError
from ofo.execution.freeze import ContractFreeze, FreezeRefused, require_within_freeze, terms_symbol
from ofo.timeutil import IST
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


#: The key of a leg's stored freeze limit: one strategy has one underlying, so instrument, strike and expiry name it.
LegKey = tuple[Instrument, Decimal | None, datetime.date]


@dataclass(frozen=True)
class RuleResponse:
    alert: str
    proposal: Proposal | None
    blocked: tuple[UserFacingError, ...] = ()  # ADR-092: why no proposal was prepared (freeze limit)
    warnings: tuple[UserFacingError, ...] = ()  # ADR-081: legs proposed with no stored freeze limit


def _order(strategy_id: str, leg: Leg, action: Action) -> ProposedOrder:
    return ProposedOrder(strategy_id, action, leg.instrument, leg.strike, leg.expiry, leg.quantity)


def respond(rule: Rule, evaluation: Evaluation, *, strategy_id: str, strategy: Strategy,
            freeze_limits: Mapping[LegKey, ContractFreeze] | None) -> RuleResponse:
    """The alert (always) and, when the rule chose it, the prepared entry or exit orders of a triggered rule.
    ``freeze_limits`` is a REQUIRED argument (ADR-092), naming each leg's trading symbol: no proposal is prepared for
    a leg not below its usable known stored limit; a leg with none (or no entry) is proposed with the warning."""
    if evaluation.rule_id != rule.rule_id:
        raise ValueError(f"evaluation is for rule {evaluation.rule_id!r}, not {rule.rule_id!r}")
    if evaluation.outcome is not Outcome.TRIGGERED:
        raise ValueError(f"rule {rule.rule_id!r} was not triggered ({evaluation.outcome.value}); nothing to respond")
    if not isinstance(strategy_id, str) or not strategy_id.strip():
        raise ValueError("every prepared order belongs to a strategy: strategy_id is required")
    detail = describe(evaluation.observations) or render_explanation("rule_no_condition_detail")
    alert = render_explanation("rule_alert", rule=rule.shown_name, detail=detail)
    if rule.action is RuleAction.ALERT_ONLY:
        return RuleResponse(alert, None)
    if rule.kind is RuleKind.EXIT:
        opposite = {Action.BUY: Action.SELL, Action.SELL: Action.BUY}
        orders = tuple(_order(strategy_id, leg, opposite[leg.action]) for leg in strategy.legs)
    elif rule.kind is RuleKind.ENTRY:
        orders = tuple(_order(strategy_id, leg, leg.action) for leg in strategy.legs)
    else:
        raise ValueError("adjustment orders depend on the adjustment chosen (ADR-011); not prepared by this module")
    limits = {} if freeze_limits is None else freeze_limits
    blocked, warnings = _freeze_findings(orders, limits, evaluation.as_of.astimezone(IST).date())
    if blocked:
        return RuleResponse(alert, None, blocked)
    return RuleResponse(alert, Proposal(strategy_id, rule.rule_id, orders), (), warnings)


def _freeze_findings(orders: tuple[ProposedOrder, ...], limits: Mapping[LegKey, ContractFreeze], today: datetime.date,
                     ) -> tuple[tuple[UserFacingError, ...], tuple[UserFacingError, ...]]:
    """ADR-092 per proposed order: (blocks above a usable known stored limit, warnings for no usable stored limit or
    a stale one). A leg with no entry is named from its terms and warned, never refused (ADR-081)."""
    blocked: list[UserFacingError] = []
    warnings: list[UserFacingError] = []
    for order in orders:
        found = limits.get((order.instrument, order.strike, order.expiry))
        if isinstance(found, ContractFreeze):
            symbol, stored = found.symbol, found.stored
        else:
            symbol, stored = terms_symbol(order.instrument, order.strike, order.expiry), None
        try:
            warnings.extend(require_within_freeze(symbol, order.quantity, stored, today=today))
        except FreezeRefused as exc:
            blocked.append(exc.message)
    return tuple(blocked), tuple(warnings)
