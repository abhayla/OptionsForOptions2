"""Strategy-level metrics from the exact at-expiry payoff (scenario-calculations.md §3).

Max profit, max loss and breakevens are strategy-level and computed from the payoff, never typed; legs carry
none (§3, T1 #98). For a single-expiry strategy the at-expiry payoff is piecewise linear in the underlying level
with kinks only at the option strikes, so it is fully determined by its exact value at each strike plus the slope
of the two tails. Nothing is sampled on a grid.

Conventions (documented, because the spec does not fix them):

- **Tails.** A tail whose slope is non-zero is reported as ``UNLIMITED`` in that direction, for the lower tail
  as well as the upper one (the payoff is treated as unbounded; the index-cannot-go-below-zero floor is not used).
- **Max loss** is the magnitude of the lowest payoff (the §6 Iron Condor's lowest payoff −₹8,175 is reported as
  ``8175``). A strategy whose lowest payoff is a profit reports a negative max loss.
- **Breakevens** are every level > 0 where the payoff is zero: a sign change between kinks (interpolated
  exactly), a zero exactly at a kink, and a zero on a tail. A flat zero segment between kinks reports its two
  end points; a flat zero tail reports only its kink end point. A crossing whose exact value does not terminate
  in decimal (e.g. a third of a point) is rounded half-even to 0.01 points; all others are exact.
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
    max_loss: Decimal | _Unlimited
    breakevens: tuple[Decimal, ...]


def _tail_slope(leg: Leg, upper: bool) -> int:
    """Payoff slope (rupees per point) of one leg beyond all strikes: above them if ``upper``, else below."""
    if leg.instrument is Instrument.FUT:
        long_slope = 1
    elif leg.instrument is Instrument.CE:
        long_slope = 1 if upper else 0
    else:
        long_slope = 0 if upper else -1
    sign = 1 if leg.action is Action.BUY else -1
    return sign * long_slope * leg.quantity


def _to_decimal(value: Fraction) -> Decimal:
    """Exact Decimal when ``value`` terminates in base 10, else rounded half-even to 0.01."""
    with localcontext() as ctx:
        ctx.prec = 60
        result = Decimal(value.numerator) / Decimal(value.denominator)
    if Fraction(result) == value:
        return result
    return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)


def _breakevens(kinks: list[Decimal], values: list[Decimal], low_slope: int, high_slope: int) -> list[Fraction]:
    found: set[Fraction] = set()
    first, last = Fraction(kinks[0]), Fraction(kinks[-1])
    if low_slope != 0:
        x = first - Fraction(values[0]) / low_slope
        if x < first:
            found.add(x)
    for i, (kink, value) in enumerate(zip(kinks, values)):
        if value == 0:
            found.add(Fraction(kink))
        if i + 1 < len(kinks):
            nxt = values[i + 1]
            if (value < 0 < nxt) or (nxt < 0 < value):
                k0, k1 = Fraction(kink), Fraction(kinks[i + 1])
                v0, v1 = Fraction(value), Fraction(nxt)
                found.add(k0 + (0 - v0) * (k1 - k0) / (v1 - v0))
    if high_slope != 0:
        x = last - Fraction(values[-1]) / high_slope
        if x > last:
            found.add(x)
    return sorted(x for x in found if x > 0)


def strategy_metrics(strategy: Strategy) -> StrategyMetrics:
    """Exact max profit, max loss and breakevens of a single-expiry strategy's at-expiry payoff."""
    if not strategy.is_single_expiry:
        raise MultiExpiryError(
            "exact at-expiry metrics need every leg on one expiry; this strategy has "
            f"{len({leg.expiry for leg in strategy.legs})} expiries (estimated metrics are a separate item)"
        )
    strikes = sorted({leg.strike for leg in strategy.legs if leg.is_option})
    # A futures-only payoff is one straight line: any single anchor point defines it.
    kinks = strikes or [Decimal(0)]
    values = [strategy.expiry_pnl_at(k) for k in kinks]
    low_slope = sum(_tail_slope(leg, upper=False) for leg in strategy.legs)
    high_slope = sum(_tail_slope(leg, upper=True) for leg in strategy.legs)

    max_profit: Decimal | _Unlimited = UNLIMITED if (high_slope > 0 or low_slope < 0) else max(values)
    max_loss: Decimal | _Unlimited = UNLIMITED if (high_slope < 0 or low_slope > 0) else -min(values)
    breakevens = tuple(_to_decimal(x) for x in _breakevens(kinks, values, low_slope, high_slope))
    return StrategyMetrics(max_profit=max_profit, max_loss=max_loss, breakevens=breakevens)
