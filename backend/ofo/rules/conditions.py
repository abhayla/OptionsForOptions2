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


class Truth(Enum):
    """Three-valued (Kleene) truth: UNKNOWN when an input the branch needs is missing or not healthy."""

    TRUE = "true"
    FALSE = "false"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Decision:
    truth: Truth
    observations: tuple[Observation, ...]  # the proven values that decided it; empty when UNKNOWN
    unknown: tuple[InputName, ...]  # inputs that left it UNKNOWN; empty when decided


def decide(condition: Condition, snapshot: Snapshot) -> Decision:
    """Kleene evaluation (decision recorded in REQ-041, owner delegation ADR-045; spec basis ADR-015).

    A comparison whose input is missing or unhealthy is UNKNOWN. OR is TRUE if any branch is proven TRUE (reporting
    only the TRUE branches), FALSE only if every branch is proven FALSE, else UNKNOWN. AND is FALSE if any branch is
    proven FALSE (reporting only the FALSE branches), TRUE only if every branch is TRUE, else UNKNOWN.
    """
    if isinstance(condition, Always):
        return Decision(Truth.TRUE, (), ())
    if isinstance(condition, Compare):
        value = snapshot.usable(condition.input)
        if value is None:
            return Decision(Truth.UNKNOWN, (), (condition.input,))
        held = condition.op.holds(value, condition.threshold)
        observation = Observation(condition.input, condition.op, condition.threshold, value, held)
        return Decision(Truth.TRUE if held else Truth.FALSE, (observation,), ())
    results = [decide(child, snapshot) for child in condition.children]
    deciding, other = (Truth.FALSE, Truth.TRUE) if isinstance(condition, AllOf) else (Truth.TRUE, Truth.FALSE)
    if any(r.truth is deciding for r in results):
        chosen = [r for r in results if r.truth is deciding]
        return Decision(deciding, tuple(o for r in chosen for o in r.observations), ())
    if all(r.truth is other for r in results):
        return Decision(other, tuple(o for r in results for o in r.observations), ())
    unknown = tuple(dict.fromkeys(name for r in results if r.truth is Truth.UNKNOWN for name in r.unknown))
    return Decision(Truth.UNKNOWN, (), unknown)
