"""A strategy's rule plan: entry, adjustment and exit rules, the last two optional (REQ-041 AC-5; ADR-009 Q153 = C).

A plan with no exit or no adjustment rule is valid and still monitored; the missing part is explained once, never
blocked (Q141, Q155: "You may want to consider defining an exit condition").
"""
from __future__ import annotations
from ofo.errors.explanations import render_explanation

from dataclasses import dataclass

from ofo.rules.inputs import Snapshot
from ofo.rules.model import Evaluation, Rule, RuleKind, evaluate

NO_EXIT_RULE = render_explanation("plan_no_exit_rule")
NO_ADJUSTMENT_RULE = render_explanation("plan_no_adjustment_rule")


@dataclass(frozen=True)
class RulePlan:
    entry: tuple[Rule, ...] = ()
    adjustment: tuple[Rule, ...] = ()
    exit: tuple[Rule, ...] = ()

    def __post_init__(self) -> None:
        seen: set[str] = set()
        for bucket, kind in (("entry", RuleKind.ENTRY), ("adjustment", RuleKind.ADJUSTMENT), ("exit", RuleKind.EXIT)):
            rules = tuple(getattr(self, bucket))
            for rule in rules:
                if not isinstance(rule, Rule):
                    raise ValueError(f"{bucket} rules must be Rule, got {rule!r}")
                if rule.kind is not kind:
                    raise ValueError(f"rule {rule.rule_id!r} is a {rule.kind.value} rule; it cannot be filed under {bucket}")
                if rule.rule_id in seen:
                    raise ValueError(f"rule id {rule.rule_id!r} appears twice in the plan")
                seen.add(rule.rule_id)
            object.__setattr__(self, bucket, rules)

    @property
    def rules(self) -> tuple[Rule, ...]:
        return self.entry + self.adjustment + self.exit

    @property
    def monitored(self) -> bool:
        """Every plan is monitored, with or without exit/adjustment rules (Q153 = C)."""
        return True

    def explanations(self) -> tuple[str, ...]:
        """What a missing optional part means for the user; empty when both parts exist."""
        notes = []
        if not self.exit:
            notes.append(NO_EXIT_RULE)
        if not self.adjustment:
            notes.append(NO_ADJUSTMENT_RULE)
        return tuple(notes)


def evaluate_plan(plan: RulePlan, snapshot: Snapshot) -> tuple[Evaluation, ...]:
    """Evaluate every rule of the plan against one snapshot, in plan order (entry, adjustment, exit)."""
    if not isinstance(plan, RulePlan):
        raise ValueError(f"expected a RulePlan, got {plan!r}")
    return tuple(evaluate(rule, snapshot) for rule in plan.rules)
