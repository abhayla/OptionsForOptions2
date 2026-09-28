"""Adjustment rules: global defaults with per-strategy overrides (REQ-041 AC-7; ADR-011 Q57 = C).

Rules live in named slots (e.g. ``"short-strike-threatened"``). Resolution for one strategy:

1. every global default slot, in its own order, unless the strategy overrides that slot;
2. a strategy override of a global slot REPLACES it in place, or removes it when the override is ``DISABLED``;
3. strategy slots that have no global default are appended, in the strategy's order.

Only adjustment rules take part. Unknown or wrong-kind entries raise; nothing is silently dropped.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping

from ofo.rules.model import Rule, RuleKind


class _Disabled(Enum):
    DISABLED = "disabled"


DISABLED = _Disabled.DISABLED  # a strategy override that switches a global default off for that strategy


class Origin(Enum):
    GLOBAL_DEFAULT = "global_default"
    STRATEGY_OVERRIDE = "strategy_override"


@dataclass(frozen=True)
class ResolvedRule:
    slot: str
    rule: Rule
    origin: Origin


def _check_slot(slot: object) -> str:
    if not isinstance(slot, str) or not slot.strip():
        raise ValueError(f"a rule slot must be a non-empty string, got {slot!r}")
    return slot


def _check_adjustment(rule: object, where: str) -> Rule:
    if not isinstance(rule, Rule):
        raise ValueError(f"{where} must be a Rule, got {rule!r}")
    if rule.kind is not RuleKind.ADJUSTMENT:
        raise ValueError(f"{where} is a {rule.kind.value} rule; defaults and overrides hold adjustment rules only")
    return rule


def resolve_adjustment_rules(
    global_defaults: Mapping[str, Rule],
    overrides: Mapping[str, Rule | _Disabled],
) -> tuple[ResolvedRule, ...]:
    """The effective adjustment rules of one strategy, each labelled with where it came from."""
    resolved: list[ResolvedRule] = []
    for slot, rule in global_defaults.items():
        _check_slot(slot)
        _check_adjustment(rule, f"global default {slot!r}")
        if slot in overrides:
            override = overrides[slot]
            if override is DISABLED:
                continue
            resolved.append(ResolvedRule(slot, _check_adjustment(override, f"override {slot!r}"),
                                         Origin.STRATEGY_OVERRIDE))
        else:
            resolved.append(ResolvedRule(slot, rule, Origin.GLOBAL_DEFAULT))
    for slot, override in overrides.items():
        _check_slot(slot)
        if slot in global_defaults:
            continue
        if override is DISABLED:
            raise ValueError(f"override {slot!r} disables a slot that has no global default")
        resolved.append(ResolvedRule(slot, _check_adjustment(override, f"override {slot!r}"),
                                     Origin.STRATEGY_OVERRIDE))
    ids = [r.rule.rule_id for r in resolved]
    if len(ids) != len(set(ids)):
        raise ValueError(f"resolved adjustment rules repeat a rule id: {ids}")
    return tuple(resolved)
