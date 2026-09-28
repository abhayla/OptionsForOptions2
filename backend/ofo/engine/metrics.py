"""Strategy-level metrics from the exact at-expiry payoff (scenario-calculations.md §3).

Max profit, max loss and breakevens are strategy-level and computed from the payoff, never typed; legs carry
none (§3, T1 #98). For a single-expiry strategy the at-expiry payoff is piecewise linear in the underlying level
with kinks only at the option strikes, so it is fully determined by its exact value at each strike plus the slope
of the two tails. Nothing is sampled on a grid.

Conventions (orchestrator decision under ADR-045, spec basis REQ-033 AC-6 "computed from the payoff"):

- **Lower bound.** An index level cannot go below 0, so the payoff is evaluated at Market = 0 as well as at
  every strike; the downside is always finite and never reported as ``UNLIMITED`` (a SELL 23,000 PE at 80 x 75
  loses at most 1,719,000). Only the **upper tail** (beyond the highest strike) can be ``UNLIMITED``: max profit
  when its slope is positive, max loss when negative.
- **min_pnl / max_loss.** ``min_pnl`` is the signed lowest payoff (``UNLIMITED`` when unbounded below).
  ``max_loss`` is its positive magnitude when it is a loss, and 0 when the strategy cannot lose (then ``min_pnl``
  shows the guaranteed result). The §6 Iron Condor has ``min_pnl`` -8175 and ``max_loss`` 8175.
- **Breakevens** are every level > 0 where the payoff is zero: a sign change between points (interpolated
  exactly), a zero exactly at a strike, and a zero on the upper tail. A flat zero segment between strikes reports
  its two end points; a flat zero upper tail reports only its strike end point. A crossing whose exact value does
  not terminate in decimal (e.g. a third of a point) is rounded half-even to 0.01 points; all others are exact.
- **Multi-expiry** strategies have no exact at-expiry payoff and raise ``MultiExpiryError``.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from fractions import Fraction
from typing import Final

from ofo.engine.legs import Action, Instrument, Leg
from ofo.engine.strategy import Strategy


class _Unlimited:
    """Sentinel for a max profit or max loss with no bound."""

    _instance: _Unlimited | None = None

    def __new__(cls) -> _Unlimited:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "UNLIMITED"


UNLIMITED: Final = _Unlimited()


class MultiExpiryError(ValueError):
    """Exact at-expiry metrics were asked for a strategy whose legs expire on different dates."""


@dataclass(frozen=True)
class StrategyMetrics:
    max_profit: Decimal | _Unlimited
    min_pnl: Decimal | _Unlimited
    max_loss: Decimal | _Unlimited
    breakevens: tuple[Decimal, ...]


def _upper_tail_slope(leg: Leg) -> int:
    """Payoff slope (rupees per point) of one leg above every strike: calls and futures move, puts are flat."""
    long_slope = 0 if leg.instrument is Instrument.PE else 1
    sign = 1 if leg.action is Action.BUY else -1
    return sign * long_slope * leg.quantity


def _to_decimal(value: Fraction) -> Decimal:
    """Exact Decimal when ``value`` terminates in base 10, else rounded half-even to 0.01 points."""
    with localcontext() as ctx:
        ctx.prec = 60
        result = Decimal(value.numerator) / Decimal(value.denominator)
    if Fraction(result) == value:
        return result
    return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)


def _breakevens(points: list[Decimal], values: list[Decimal], upper_slope: int) -> list[Fraction]:
    """Zeros of the payoff over [0, inf): at a point, between two points, or on the upper tail; levels > 0 only."""
    found: set[Fraction] = set()
    for i, (point, value) in enumerate(zip(points, values)):
        if value == 0:
            found.add(Fraction(point))
        if i + 1 < len(points):
            nxt = values[i + 1]
            if (value < 0 < nxt) or (nxt < 0 < value):
                k0, k1 = Fraction(point), Fraction(points[i + 1])
                v0, v1 = Fraction(value), Fraction(nxt)
                found.add(k0 + (0 - v0) * (k1 - k0) / (v1 - v0))
    last = Fraction(points[-1])
    if upper_slope != 0:
        x = last - Fraction(values[-1]) / upper_slope
        if x > last:
            found.add(x)
    return sorted(x for x in found if x > 0)


def strategy_metrics(strategy: Strategy) -> StrategyMetrics:
    """Exact max profit, min P&L, max loss and breakevens of a single-expiry strategy's at-expiry payoff."""
    if not strategy.is_single_expiry:
        raise MultiExpiryError(
            "exact at-expiry metrics need every leg on one expiry; this strategy has "
            f"{len({leg.expiry for leg in strategy.legs})} expiries (estimated metrics are a separate item)"
        )
    # The payoff on [0, inf) is linear between 0 and the strikes; its extremes lie at these points or on the
    # upper tail. Strikes are validated > 0, so 0 is always the first point.
    points = [Decimal(0)] + sorted({leg.strike for leg in strategy.legs if leg.is_option})
    values = [strategy.expiry_pnl_at(p) for p in points]
    upper_slope = sum(_upper_tail_slope(leg) for leg in strategy.legs)

    max_profit: Decimal | _Unlimited = UNLIMITED if upper_slope > 0 else max(values)
    min_pnl: Decimal | _Unlimited = UNLIMITED if upper_slope < 0 else min(values)
    if min_pnl is UNLIMITED:
        max_loss: Decimal | _Unlimited = UNLIMITED
    else:
        max_loss = -min_pnl if min_pnl < 0 else Decimal(0)
    breakevens = tuple(_to_decimal(x) for x in _breakevens(points, values, upper_slope))
    return StrategyMetrics(max_profit=max_profit, min_pnl=min_pnl, max_loss=max_loss, breakevens=breakevens)
