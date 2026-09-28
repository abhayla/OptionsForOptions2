"""The one rule model for entry, adjustment and exit rules, and its evaluation (REQ-041 AC-1; ADR-009).

Evaluation fails closed (ADR-015, REQ-049 "important rules are never triggered silently from stale data"):

- the snapshot's data health is not ``available`` and the rule reads any input -> ``CANNOT_EVALUATE``;
- any input the rule reads is missing from the snapshot -> ``CANNOT_EVALUATE`` naming every missing input.

A rule is never reported ``NOT_TRIGGERED`` from missing or unhealthy data, even when the inputs that are present
would already decide an AND/OR: the whole rule is only decided on complete, healthy data.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from enum import Enum

from ofo.rules.conditions import (
    DEFAULT_LIMITS,
    Always,
    ComplexityLimits,
    Condition,
    Observation,
    check_complexity,
    decide,
    leaves,
)
from ofo.rules.inputs import DataHealth, InputName, Snapshot


class RuleKind(Enum):
    ENTRY = "entry"
    ADJUSTMENT = "adjustment"
    EXIT = "exit"


class RuleAction(Enum):
    """What happens when the rule triggers; chosen by the rule, never defaulted (Q18 = D).

    V1 never places an order (ADR-009 invariant): ALERT_AND_PREPARE_ORDERS only builds a proposal the user reviews.
    For an exit rule this is "alert + prepare exit orders".
    """

    ALERT_ONLY = "alert_only"
    ALERT_AND_PREPARE_ORDERS = "alert_and_prepare_orders"


class Outcome(Enum):
    TRIGGERED = "triggered"
    NOT_TRIGGERED = "not_triggered"
    CANNOT_EVALUATE = "cannot_evaluate"


@dataclass(frozen=True)
class Rule:
    """One rule: ``kind`` + ``condition`` + ``action``. The same model for every kind (AC-1)."""

    rule_id: str
    kind: RuleKind
    condition: Condition
    action: RuleAction
    description: str = ""
    limits: ComplexityLimits = field(default=DEFAULT_LIMITS, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.rule_id, str) or not self.rule_id.strip():
            raise ValueError("rule_id must be a non-empty string")
        if not isinstance(self.kind, RuleKind):
            raise ValueError(f"kind must be a RuleKind, got {self.kind!r}")
        if not isinstance(self.action, RuleAction):
            raise ValueError(f"action must be a RuleAction (the rule's own choice), got {self.action!r}")
        if not isinstance(self.limits, ComplexityLimits):
            raise ValueError(f"limits must be ComplexityLimits, got {self.limits!r}")
        check_complexity(self.condition, self.limits)
        if isinstance(self.condition, Always) and self.kind is not RuleKind.ENTRY:
            raise ValueError("only an entry rule can be unconditional (Enter now)")

    @property
    def inputs(self) -> tuple[InputName, ...]:
        """Every input the rule reads, in first-use order, without repeats."""
        return tuple(dict.fromkeys(leaf.input for leaf in leaves(self.condition)))


@dataclass(frozen=True)
class Evaluation:
    """The result of one rule against one snapshot: what a trigger record stores (domain-model §7)."""

    rule_id: str
    kind: RuleKind
    action: RuleAction
    outcome: Outcome
    observations: tuple[Observation, ...]
    missing: tuple[InputName, ...]
    as_of: datetime.datetime
    data_health: DataHealth
    source: str
    reason: str


def evaluate(rule: Rule, snapshot: Snapshot) -> Evaluation:
    """Evaluate ``rule`` against ``snapshot``; fail closed on unhealthy or missing data."""
    if not isinstance(rule, Rule):
        raise ValueError(f"expected a Rule, got {rule!r}")
    if not isinstance(snapshot, Snapshot):
        raise ValueError(f"expected a Snapshot, got {snapshot!r}")

    def result(outcome: Outcome, observations=(), missing=(), reason: str = "") -> Evaluation:
        return Evaluation(
            rule_id=rule.rule_id,
            kind=rule.kind,
            action=rule.action,
            outcome=outcome,
            observations=tuple(observations),
            missing=tuple(missing),
            as_of=snapshot.as_of,
            data_health=snapshot.data_health,
            source=snapshot.source,
            reason=reason,
        )

    inputs = rule.inputs
    if inputs and snapshot.data_health is not DataHealth.AVAILABLE:
        return result(
            Outcome.CANNOT_EVALUATE,
            reason=f"market data is {snapshot.data_health.value}; the rule is not evaluated on it",
        )
    missing = tuple(name for name in inputs if snapshot.get(name) is None)
    if missing:
        names = ", ".join(name.value for name in missing)
        return result(Outcome.CANNOT_EVALUATE, missing=missing, reason=f"missing input(s): {names}")
    holds, observations = decide(rule.condition, snapshot)
    outcome = Outcome.TRIGGERED if holds else Outcome.NOT_TRIGGERED
    return result(outcome, observations=observations, reason=describe(observations))


def describe(observations: tuple[Observation, ...]) -> str:
    """Plain text of the deciding values, e.g. ``live_pnl -5002.50 <= -5000``."""
    return "; ".join(f"{o.input.value} {o.value} {o.op.value} {o.threshold}" for o in observations)
