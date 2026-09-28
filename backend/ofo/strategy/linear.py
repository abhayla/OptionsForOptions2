"""Integer linear expressions over template parameters, and an exact solver for them.

Spec: spec/requirements/REQ-028.md AC-3/AC-4. A template leg's strike is written as a linear expression
of the template's parameters, in strike steps from the at-the-money strike (for example ``-p - w_put``).
Resolving evaluates the expression; matching solves the expressions backwards from observed strikes.
Everything is exact (``int`` / ``Fraction``), never float.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction
from typing import Mapping, Sequence

_TERM = r"(?:\d+\*[a-z][a-z0-9_]*|\d+|[a-z][a-z0-9_]*)"
_EXPRESSION = re.compile(rf"[+-]?{_TERM}(?:[+-]{_TERM})*")
_TOKEN = re.compile(r"([+-]?)(?:(\d+)\*([a-z][a-z0-9_]*)|(\d+)|([a-z][a-z0-9_]*))")


class ExpressionError(ValueError):
    """A strike expression is malformed or names an unknown parameter."""


@dataclass(frozen=True)
class LinearExpr:
    """``const + sum(coefficient * param)``, with integer coefficients and constant."""

    coefficients: tuple[tuple[str, int], ...]
    const: int

    @property
    def params(self) -> frozenset[str]:
        return frozenset(name for name, _ in self.coefficients)

    @property
    def is_constant(self) -> bool:
        return not self.coefficients

    def evaluate(self, values: Mapping[str, int]) -> int:
        return self.const + sum(coefficient * values[name] for name, coefficient in self.coefficients)


def parse_expression(source: object, known_params: frozenset[str]) -> LinearExpr:
    """Parse an ``int`` or a string like ``"-p - 2*w"`` into a :class:`LinearExpr`; fail on anything else."""
    if isinstance(source, bool):
        raise ExpressionError(f"a strike expression cannot be a boolean, got {source!r}")
    if isinstance(source, int):
        return LinearExpr(coefficients=(), const=source)
    if not isinstance(source, str):
        raise ExpressionError(f"a strike expression must be an int or a string, got {source!r}")
    compact = re.sub(r"\s+", "", source)
    if not _EXPRESSION.fullmatch(compact):
        raise ExpressionError(f"malformed strike expression {source!r}")
    coefficients: dict[str, int] = {}
    const = 0
    for sign, multiplier, scaled_name, number, bare_name in _TOKEN.findall(compact):
        factor = -1 if sign == "-" else 1
        if number:
            const += factor * int(number)
            continue
        name = scaled_name or bare_name
        if name not in known_params:
            raise ExpressionError(f"strike expression {source!r} names unknown parameter {name!r}")
        coefficients[name] = coefficients.get(name, 0) + factor * (int(multiplier) if multiplier else 1)
    kept = tuple(sorted((name, c) for name, c in coefficients.items() if c != 0))
    return LinearExpr(coefficients=kept, const=const)


def _eliminate(rows: list[list[Fraction]], n_unknowns: int) -> tuple[list[list[Fraction]], list[int]]:
    """Gauss-Jordan on an augmented matrix (last column = right-hand side). Returns (rows, pivot columns)."""
    rows = [row[:] for row in rows]
    pivots: list[int] = []
    rank = 0
    for column in range(n_unknowns):
        pivot = next((r for r in range(rank, len(rows)) if rows[r][column] != 0), None)
        if pivot is None:
            continue
        rows[rank], rows[pivot] = rows[pivot], rows[rank]
        lead = rows[rank][column]
        rows[rank] = [value / lead for value in rows[rank]]
        for r in range(len(rows)):
            if r != rank and rows[r][column] != 0:
                factor = rows[r][column]
                rows[r] = [a - factor * b for a, b in zip(rows[r], rows[rank])]
        pivots.append(column)
        rank += 1
    return rows, pivots


def rank_of(expressions: Sequence[LinearExpr], params: Sequence[str]) -> int:
    """Rank of the coefficient matrix of ``expressions`` over ``params``."""
    rows = [[Fraction(dict(e.coefficients).get(p, 0)) for p in params] + [Fraction(0)] for e in expressions]
    _, pivots = _eliminate(rows, len(params))
    return len(pivots)


def solve_integer(
    equations: Sequence[tuple[LinearExpr, int]], params: Sequence[str]
) -> dict[str, int] | None:
    """Solve ``expr == value`` for every equation. Returns the unique integer solution, or ``None`` when
    the system is inconsistent, under-determined, or its unique solution is not all integers."""
    rows = [
        [Fraction(dict(e.coefficients).get(p, 0)) for p in params] + [Fraction(value - e.const)]
        for e, value in equations
    ]
    reduced, pivots = _eliminate(rows, len(params))
    if len(pivots) != len(params):
        return None
    for row in reduced[len(pivots):]:
        if row[-1] != 0:
            return None
    solution: dict[str, int] = {}
    for index, column in enumerate(pivots):
        value = reduced[index][-1]
        if value.denominator != 1:
            return None
        solution[params[column]] = int(value)
    return solution
