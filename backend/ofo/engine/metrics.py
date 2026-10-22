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
- **Loss regions** (ADR-072) are the open intervals of the underlying where the payoff is below zero (exactly zero is
  not a loss), read from the same payoff: between consecutive knots (0, every strike, every exact zero) the payoff is
  linear, so its sign at the midpoint is its sign on the whole interval; the upper tail's sign is taken one point past
  the last knot. Signs are decided in exact fractions before any 0.01 rounding of a bound. Never inferred from the
  breakevens: a zero can be a touch or the end of a flat stretch. A single zero point between two loss intervals (a
  touch from below, always at a strike) does not split the region: it is carried as the region's "except" level
  (issue #172), so regions never touch. Likewise a profit or zero stretch between two loss regions that is narrower
  than the 0.01 display step (both edges round to one level) is carried as an "except" level - the stretch's
  highest-P&L knot, a strike - never merged away (W-066 round 8).
- **Multi-expiry** strategies have no exact at-expiry payoff and raise ``MultiExpiryError``.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from fractions import Fraction
from typing import Final

from ofo.engine import legs
from ofo.engine.legs import Instrument, Leg
from ofo.engine.strategy import Strategy
from ofo.money import HUNDREDTH


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


#: One expiry loss region: ``(lower, upper)``, or ``(lower, upper, excepts)`` when single zero points split the loss
#: inside it (``excepts`` = those levels, ascending, strictly inside; issue #172). None = an open end.
LossRegion = (tuple[Decimal | None, Decimal | None]
              | tuple[Decimal | None, Decimal | None, tuple[Decimal, ...]])


@dataclass(frozen=True)
class StrategyMetrics:
    max_profit: Decimal | _Unlimited
    min_pnl: Decimal | _Unlimited
    max_loss: Decimal | _Unlimited
    breakevens: tuple[Decimal, ...]
    #: Expiry loss regions (P&L below zero), ordered and never touching (ADR-072); see ``LossRegion``.
    loss_regions: tuple[LossRegion, ...] = ()


def _upper_tail_slope(leg: Leg) -> int:
    """Payoff slope (rupees per point) of one leg above every strike: calls and futures move, puts are flat.

    The sign comes from the engine's one P&L convention: the leg's P&L change when its long value rises by the
    long slope (1 for CE/FUT, 0 for PE), i.e. ``position_pnl(leg, slope) - position_pnl(leg, 0)``.
    """
    long_slope = Decimal(0) if leg.instrument is Instrument.PE else Decimal(1)
    change = legs.position_pnl(leg, long_slope) - legs.position_pnl(leg, Decimal(0))
    return int(change)


def _to_decimal(value: Fraction) -> Decimal:
    """Exact Decimal when ``value`` terminates in base 10, else rounded half-even to 0.01 points."""
    with localcontext() as ctx:
        ctx.prec = 60
        result = Decimal(value.numerator) / Decimal(value.denominator)
    if Fraction(result) == value:
        return result
    return result.quantize(HUNDREDTH, rounding=ROUND_HALF_EVEN)


def _shown(level: Decimal) -> Decimal:
    """``level`` as the display prints it: rounded half-even to the 0.01 point step (engine.display.format_points)."""
    return level.quantize(HUNDREDTH, rounding=ROUND_HALF_EVEN)


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


def _loss_regions(points: list[Decimal], values: list[Decimal], upper_slope: int,
                  zeros: list[Fraction]) -> tuple[LossRegion, ...]:
    """The open intervals of [0, inf) where the payoff is below zero, merged across a knot whose own P&L is below zero
    or exactly zero (then the knot is carried as an "except" level of the region)."""
    pts = [Fraction(p) for p in points]
    vals = [Fraction(v) for v in values]

    def pnl(x: Fraction) -> Fraction:
        if x >= pts[-1]:
            return vals[-1] + upper_slope * (x - pts[-1])
        for i in range(len(pts) - 1):
            if pts[i] <= x <= pts[i + 1]:
                return vals[i] + (vals[i + 1] - vals[i]) * (x - pts[i]) / (pts[i + 1] - pts[i])
        raise AssertionError("unreachable: x lies inside [0, last strike]")

    knots = sorted(set(pts) | set(zeros))
    # one entry per interval: (lower, upper-or-None, is_loss); the last interval is the open upper tail
    intervals = [(knots[i], knots[i + 1], pnl((knots[i] + knots[i + 1]) / 2) < 0) for i in range(len(knots) - 1)]
    intervals.append((knots[-1], None, pnl(knots[-1] + 1) < 0))
    # one entry per region: [lower, upper, exact zero points inside it]. Two loss intervals meeting at a knot are ONE
    # region: merged plainly when the knot's own P&L is below zero, and with the knot as an "except" level when it is
    # exactly zero (a single zero point inside a loss; ADR-072, issue #172), never two touching regions.
    regions: list[list] = []
    for lo, hi, is_loss in intervals:
        if not is_loss:
            continue
        if regions and regions[-1][1] == lo:
            if pnl(lo) == 0:
                regions[-1][2].append(lo)
            regions[-1][1] = hi
        else:
            regions.append([None if lo == 0 and pnl(lo) < 0 else lo, hi, []])
    # Edges are shown rounded to 0.01, so two edges can round to one level: a region narrower than a paisa becomes a
    # single-level region (lower == upper, kept: ADR-072 names every loss region). Two regions whose edges PRINT as one
    # level (compared at the 0.01 display step, so an exact edge like 22,399.995 counts too) across a real (exact) gap
    # - a profit or zero stretch narrower than the display step - are never joined silently, nor listed as touching:
    # they become one region with the gap's best level as an "except" level (W-066 round 8, verifier's shape E). That
    # level is the knot of the gap with the highest P&L, so its own P&L is >= 0 (a positive gap peaks at a strike).
    out: list[list] = []
    prev_hi: Fraction | None = None
    for lo, hi, excepts in regions:
        d_lo = None if lo is None else _to_decimal(lo)
        d_hi = None if hi is None else _to_decimal(hi)
        d_ex = [_to_decimal(z) for z in excepts]
        if out and lo is not None and out[-1][1] is not None and _shown(d_lo) <= _shown(out[-1][1]):
            # the gap's ends are exact zeros (knots), so the best knot's P&L is >= 0 by construction
            best = max((k for k in knots if prev_hi <= k <= lo), key=lambda k: (pnl(k), -k))
            out[-1][1] = d_hi
            out[-1][2].append(_to_decimal(best))
            out[-1][2].extend(d_ex)
        else:
            out.append([d_lo, d_hi, d_ex])
        prev_hi = hi
    # An except level is a strike (a zero inside a loss is a kink) and each side of it is negative up to at least the
    # next strike, so it stays strictly inside its rounded region; the LevelRegions slot refuses it otherwise.
    return tuple((lo, hi, tuple(ex)) if ex else (lo, hi) for lo, hi, ex in out)


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
    zeros = _breakevens(points, values, upper_slope)
    breakevens = tuple(_to_decimal(x) for x in zeros)
    return StrategyMetrics(max_profit=max_profit, min_pnl=min_pnl, max_loss=max_loss, breakevens=breakevens,
                           loss_regions=_loss_regions(points, values, upper_slope, zeros))


def loss_regions_after_charges(strategy: Strategy, charges: Decimal) -> tuple[LossRegion, ...]:
    """W-125 (REQ-082 AC-2): the loss regions of a single-expiry strategy's expiry P&L LESS ``charges`` (a flat amount
    taken off every level, ADR-082). Same region logic as ``strategy_metrics`` (a region is found by walking the pieces,
    never inferred from breakevens alone); ``charges`` of 0 gives ``strategy_metrics(strategy).loss_regions``."""
    if not strategy.is_single_expiry:
        raise MultiExpiryError("loss regions need every leg on one expiry")
    points = [Decimal(0), *sorted({leg.strike for leg in strategy.legs if leg.is_option})]
    values = [strategy.expiry_pnl_at(p) - charges for p in points]
    upper_slope = sum(_upper_tail_slope(leg) for leg in strategy.legs)
    return _loss_regions(points, values, upper_slope, _breakevens(points, values, upper_slope))
