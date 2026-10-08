"""The one rule model for entry, adjustment and exit rules, and its evaluation (REQ-041 AC-1; ADR-009).

Evaluation uses three-valued (Kleene) logic (decided under owner delegation ADR-045 and recorded in REQ-041; spec
basis ADR-015 "never claim a trigger without the data that proves it"). An input that is missing, or whose data
health is not ``available``, is unknown; a comparison on it is unknown. The rule is TRIGGERED or NOT_TRIGGERED only
when the proven values decide it (an OR with one proven-true branch triggers; an AND with one proven-false branch
does not), otherwise CANNOT_EVALUATE naming the inputs it needs. ``Evaluation.missing`` always lists every input the
rule reads that was unusable, whatever the outcome, so a trigger record shows what was not known.
"""
from __future__ import annotations
from ofo.errors.explanations import ExplanationText, join_explanations, render_explanation

import datetime
from dataclasses import dataclass, field
from enum import Enum

from ofo.rules.conditions import (
    DEFAULT_LIMITS,
    Always,
    ComplexityLimits,
    Condition,
    Observation,
    Truth,
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

    missing = tuple(name for name in rule.inputs if snapshot.usable(name) is None)
    decision = decide(rule.condition, snapshot)
    if decision.truth is Truth.UNKNOWN:
        return result(Outcome.CANNOT_EVALUATE, missing=missing,
                      reason=render_explanation("rule_cannot_decide", inputs=tuple(_why(snapshot, n) for n in decision.unknown)))
    outcome = Outcome.TRIGGERED if decision.truth is Truth.TRUE else Outcome.NOT_TRIGGERED
    return result(outcome, observations=decision.observations, missing=missing,
                  reason=describe(decision.observations))


def _why(snapshot: Snapshot, name: InputName) -> str:
    health = snapshot.health_of(name)
    return render_explanation("rule_input_state", input=name.value,
                              state="missing" if health is DataHealth.AVAILABLE else health.value)


def describe(observations: tuple[Observation, ...]) -> ExplanationText:
    """The deciding values as one explanation line, e.g. ``live_pnl -5002.50 <= -5000`` (empty when none)."""
    return join_explanations(tuple(render_explanation("rule_observation", input=o.input.value, value=o.value,
                                                      op=o.op.value, threshold=o.threshold) for o in observations),
                             "; ")
