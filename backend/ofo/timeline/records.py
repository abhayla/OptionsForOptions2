"""Rule-trigger records and their follow-ups (REQ-040 AC-3, AC-4; ADR-019 Q203; domain-model §7).

A ``RuleTriggerRecord`` is made ONLY from a rules ``Evaluation`` whose outcome is TRIGGERED, via
:meth:`RuleTriggerRecord.from_evaluation`; direct construction is refused, so a record can never carry values the
rule engine did not observe. It stores which rule (id and text), the exact deciding input values and their
thresholds, the evaluation timestamp, the market-data source, the data health and the active strategy version.

A ``FollowUp`` records what followed one trigger (AC-4): alert generated?, order prepared?, confirmation required?,
executed? and reconciliation succeeded? as yes/no, and what the broker reported as text.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from ofo.rules.conditions import Compare, Observation, leaves
from ofo.rules.inputs import DataHealth, InputName
from ofo.rules.model import Evaluation, Outcome, Rule, RuleAction, RuleKind
from ofo.strategy.versions import Version
from ofo.timeline.catalogue import FollowUpKind

MAX_TEXT = 2_000
#: Snapshot's default source; a trigger record must name a real market-data source (AC-3), so this is refused.
UNSPECIFIED_SOURCE = "unspecified"

_FROM_EVALUATION = object()  # construction token: only from_evaluation() holds it


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string, got {value!r}")
    if len(value) > MAX_TEXT:
        raise ValueError(f"{label} is {len(value)} characters; the limit is {MAX_TEXT}")
    return value


def _require_aware(value: object, label: str) -> datetime.datetime:
    if not isinstance(value, datetime.datetime) or value.tzinfo is None:
        raise ValueError(f"{label} must be a timezone-aware datetime, got {value!r}")
    return value


@dataclass(frozen=True)
class RuleTriggerRecord:
    """Why one rule fired: the rule, the exact values against their thresholds, when, from which data, which version."""

    rule_id: str
    rule_text: str
    rule_kind: RuleKind
    action: RuleAction
    observations: tuple[Observation, ...]
    missing: tuple[InputName, ...]
    timestamp: datetime.datetime
    source: str
    data_health: DataHealth
    active_version: int | None
    _token: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._token is not _FROM_EVALUATION:
            raise ValueError("a RuleTriggerRecord is made only by RuleTriggerRecord.from_evaluation()")
        # Spend the token so dataclasses.replace() (which copies init fields) cannot forge a changed copy.
        object.__setattr__(self, "_token", None)

    @classmethod
    def from_evaluation(
        cls, rule: Rule, evaluation: Evaluation, *, active_version: Version | None
    ) -> "RuleTriggerRecord":
        """Record a TRIGGERED evaluation of ``rule``. ``active_version`` is the strategy's active version, or None
        only for an entry rule (nothing has executed yet, so no version exists: ADR-019 Q135/Q190)."""
        if not isinstance(rule, Rule):
            raise ValueError(f"expected a Rule, got {rule!r}")
        if not isinstance(evaluation, Evaluation):
            raise ValueError(f"expected an Evaluation, got {evaluation!r}")
        if evaluation.outcome is not Outcome.TRIGGERED:
            raise ValueError(f"only a triggered evaluation is recorded as a trigger, got {evaluation.outcome.value}")
        if (evaluation.rule_id, evaluation.kind, evaluation.action) != (rule.rule_id, rule.kind, rule.action):
            raise ValueError(f"evaluation of rule {evaluation.rule_id!r} does not belong to rule {rule.rule_id!r}")
        _require_text(rule.description, "rule text (Rule.description)")
        _require_aware(evaluation.as_of, "evaluation timestamp")
        _require_text(evaluation.source, "market-data source")
        if evaluation.source == UNSPECIFIED_SOURCE:
            raise ValueError("a trigger record needs the real market-data source, not 'unspecified'")
        if not isinstance(evaluation.data_health, DataHealth):
            raise ValueError(f"data health must be a DataHealth, got {evaluation.data_health!r}")
        comparisons = set(leaves(rule.condition))
        for observation in evaluation.observations:
            _check_observation(observation, comparisons)
        for name in evaluation.missing:
            if name not in rule.inputs:
                raise ValueError(f"missing input {name!r} is not read by rule {rule.rule_id!r}")
        if active_version is None:
            if rule.kind is not RuleKind.ENTRY:
                raise ValueError(f"a {rule.kind.value} rule trigger needs the active strategy version")
            version_number = None
        elif isinstance(active_version, Version):
            version_number = active_version.number
        else:
            raise ValueError(f"active_version must be a Version or None, got {active_version!r}")
        return cls(
            rule_id=rule.rule_id,
            rule_text=rule.description,
            rule_kind=rule.kind,
            action=rule.action,
            observations=tuple(evaluation.observations),
            missing=tuple(evaluation.missing),
            timestamp=evaluation.as_of,
            source=evaluation.source,
            data_health=evaluation.data_health,
            active_version=version_number,
            _token=_FROM_EVALUATION,
        )

    def as_payload(self) -> dict[str, Any]:
        """Every field as plain data, for hashing into the timeline chain."""
        return {
            "rule_id": self.rule_id,
            "rule_text": self.rule_text,
            "rule_kind": self.rule_kind.value,
            "action": self.action.value,
            "observations": [
                {"input": o.input.value, "op": o.op.value, "threshold": o.threshold, "value": o.value}
                for o in self.observations
            ],
            "missing": [name.value for name in self.missing],
            "timestamp": self.timestamp,
            "source": self.source,
            "data_health": self.data_health.value,
            "active_version": self.active_version,
        }


def _check_observation(observation: object, comparisons: set[Compare]) -> None:
    if not isinstance(observation, Observation):
        raise ValueError(f"expected an Observation, got {observation!r}")
    if Compare(observation.input, observation.op, observation.threshold) not in comparisons:
        raise ValueError(f"observation {observation.input.value} {observation.op.value} {observation.threshold} "
                         "is not a comparison of this rule")
    if not isinstance(observation.value, Decimal) or not observation.value.is_finite():
        raise ValueError(f"observed value must be a finite Decimal, got {observation.value!r}")
    held = observation.op.holds(observation.value, observation.threshold)
    if not (held and observation.held):
        raise ValueError(f"observation {observation.input.value} {observation.value} {observation.op.value} "
                         f"{observation.threshold} does not hold, so it cannot explain a trigger")


@dataclass(frozen=True)
class FollowUp:
    """One thing that followed a trigger (AC-4). ``trigger_seq`` is the trigger's timeline sequence number.

    ``answer`` is a bool for every yes/no kind and non-empty text for ``BROKER_REPORTED`` (what the broker said).
    """

    kind: FollowUpKind
    trigger_seq: int
    at: datetime.datetime
    answer: bool | str
    note: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.kind, FollowUpKind):
            raise ValueError(f"kind must be a FollowUpKind, got {self.kind!r}")
        if isinstance(self.trigger_seq, bool) or not isinstance(self.trigger_seq, int) or self.trigger_seq < 0:
            raise ValueError(f"trigger_seq must be a non-negative integer, got {self.trigger_seq!r}")
        _require_aware(self.at, "follow-up time")
        if self.kind.is_yes_no:
            if not isinstance(self.answer, bool):
                raise ValueError(f"{self.kind.value} is answered yes/no (a bool), got {self.answer!r}")
        else:
            _require_text(self.answer, "broker report")
        if not isinstance(self.note, str) or len(self.note) > MAX_TEXT:
            raise ValueError(f"note must be a string of at most {MAX_TEXT} characters")

    def as_payload(self) -> dict[str, Any]:
        return {"kind": self.kind.value, "trigger_seq": self.trigger_seq, "at": self.at,
                "answer": self.answer, "note": self.note}
