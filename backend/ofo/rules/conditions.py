"""Rule conditions: comparisons over named inputs, composed with AND/OR (REQ-041 AC-4, AC-8; ADR-009 Q146/Q147).

Boundary semantics are explicit in the operator, never implied: ``GTE``/``LTE`` include the threshold (a value
exactly AT the threshold satisfies the comparison), ``GT``/``LT`` exclude it.

V1 complexity limit (Q147 "controlled complexity"): a configurable default of at most 2 group levels and at most
5 comparisons per rule. Depth counts group nodes on the longest path: a lone comparison is depth 0,
``A AND B`` is depth 1, ``A AND (B OR C)`` is depth 2.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Union

from ofo.rules.inputs import InputName, Snapshot, require_finite


class Op(Enum):
    GTE = ">="  # inclusive: value == threshold satisfies
    GT = ">"  # exclusive
    LTE = "<="  # inclusive
    LT = "<"  # exclusive

    def holds(self, value: Decimal, threshold: Decimal) -> bool:
        if self is Op.GTE:
            return value >= threshold
        if self is Op.GT:
            return value > threshold
        if self is Op.LTE:
            return value <= threshold
        return value < threshold


@dataclass(frozen=True)
class Compare:
    """One comparison ``<input> <op> <threshold>``."""

    input: InputName
    op: Op
    threshold: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.input, InputName):
            raise ValueError(f"input must be an InputName, got {self.input!r}")
        if not isinstance(self.op, Op):
            raise ValueError(f"op must be an Op, got {self.op!r}")
        require_finite(self.threshold, "threshold")


@dataclass(frozen=True)
class AllOf:
    """AND: every child must hold."""

    children: tuple[Condition, ...]

    def __post_init__(self) -> None:
        _check_children(self, "AllOf")


@dataclass(frozen=True)
class AnyOf:
    """OR: at least one child must hold."""

    children: tuple[Condition, ...]

    def __post_init__(self) -> None:
        _check_children(self, "AnyOf")


@dataclass(frozen=True)
class Always:
    """The empty condition of an immediate entry ("Enter now", Q17): reads no input and always holds."""


Condition = Union[Compare, AllOf, AnyOf, Always]


def _check_children(node: AllOf | AnyOf, label: str) -> None:
    children = tuple(node.children)
    if len(children) < 2:
        raise ValueError(f"{label} needs at least two conditions, got {len(children)}")
    for child in children:
        if not isinstance(child, (Compare, AllOf, AnyOf)):
            raise ValueError(f"{label} children must be Compare, AllOf or AnyOf, got {child!r}")
    object.__setattr__(node, "children", children)


@dataclass(frozen=True)
class ComplexityLimits:
    """V1 rule complexity limits (Q147). The defaults are a configurable setting, not an owner-stated number."""

    max_depth: int = 2
    max_leaves: int = 5

    def __post_init__(self) -> None:
        for name in ("max_depth", "max_leaves"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer, got {value!r}")


DEFAULT_LIMITS = ComplexityLimits()


def depth(condition: Condition) -> int:
    if isinstance(condition, (AllOf, AnyOf)):
        return 1 + max(depth(child) for child in condition.children)
    return 0


def leaves(condition: Condition) -> tuple[Compare, ...]:
    if isinstance(condition, Compare):
        return (condition,)
    if isinstance(condition, (AllOf, AnyOf)):
        return tuple(leaf for child in condition.children for leaf in leaves(child))
    return ()


def check_complexity(condition: Condition, limits: ComplexityLimits = DEFAULT_LIMITS) -> None:
    """Raise ``ValueError`` when ``condition`` exceeds ``limits``."""
    if not isinstance(condition, (Compare, AllOf, AnyOf, Always)):
        raise ValueError(f"condition must be Compare, AllOf, AnyOf or Always, got {condition!r}")
    d, n = depth(condition), len(leaves(condition))
    if d > limits.max_depth:
        raise ValueError(f"rule is nested {d} levels deep; the V1 limit is {limits.max_depth}")
    if n > limits.max_leaves:
        raise ValueError(f"rule has {n} comparisons; the V1 limit is {limits.max_leaves}")


@dataclass(frozen=True)
class Observation:
    """One comparison as evaluated: the exact input value against its threshold."""

    input: InputName
    op: Op
    threshold: Decimal
    value: Decimal
    held: bool


def decide(condition: Condition, snapshot: Snapshot) -> tuple[bool, tuple[Observation, ...]]:
    """Evaluate a condition whose inputs are ALL present; return (holds, the observations that decided it).

    AND true: every child. AND false: the failing children. OR true: the holding children. OR false: every child.
    """
    if isinstance(condition, Always):
        return True, ()
    if isinstance(condition, Compare):
        value = snapshot.get(condition.input)
        if value is None:
            raise ValueError(f"{condition.input.value} is missing; check missing inputs before deciding")
        held = condition.op.holds(value, condition.threshold)
        return held, (Observation(condition.input, condition.op, condition.threshold, value, held),)
    results = [decide(child, snapshot) for child in condition.children]
    if isinstance(condition, AllOf):
        holds = all(r[0] for r in results)
        chosen = results if holds else [r for r in results if not r[0]]
    else:
        holds = any(r[0] for r in results)
        chosen = [r for r in results if r[0]] if holds else results
    return holds, tuple(obs for r in chosen for obs in r[1])
