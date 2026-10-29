"""What-if target arithmetic (REQ-084 AC-1, AC-4; ADR-008): the level limits, the breakeven search at a target time and
the Greek totals, in the engine so no money or level figure is computed outside it. ``ofo.outcome.target`` only calls
these and shapes the answer."""
from __future__ import annotations

import datetime
from collections.abc import Sequence
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_EVEN, Decimal
from typing import Final

from ofo.engine.black_scholes import Greeks
from ofo.engine.model import ModelInputs, estimate
from ofo.money import PAISE

#: REQ-084 AC-1: the target level's span either side of spot (10%), snapped inward to the strike step.
TARGET_SPAN: Final = Decimal("0.10")


def target_level_limits(spot: Decimal, step: Decimal) -> tuple[Decimal, Decimal]:
    """Spot -10% .. +10%, each end snapped inward to a multiple of ``step`` (REQ-084 AC-1)."""
    low = (spot * (1 - TARGET_SPAN) / step).to_integral_value(rounding=ROUND_CEILING) * step
    high = (spot * (1 + TARGET_SPAN) / step).to_integral_value(rounding=ROUND_FLOOR) * step
    return low, high


def add_booked(value: Decimal | None, booked: Decimal | None) -> Decimal | None:
    """GC-TP R-18 (ADR-209): a what-if figure plus the paper strategy's booked P&L, exact (ADR-008); the figure unchanged
    when nothing is booked (``booked`` None) and absent when the figure is."""
    return value if value is None or booked is None else value + booked


def add_booked_all(values: Sequence[Decimal] | None, booked: Decimal | None) -> tuple[Decimal, ...] | None:
    """:func:`add_booked` for every point of a curve (the same booked amount at each level)."""
    return None if values is None else tuple(v if booked is None else v + booked for v in values)


def breakevens_at(model: ModelInputs, levels: Sequence[Decimal], totals: Sequence[Decimal],
                  at: datetime.datetime, shift: Decimal = Decimal(0)) -> tuple[Decimal, ...]:
    """The levels where the target-time estimate crosses zero: each sign change on the curve (``levels``/``totals``),
    narrowed by halving with the engine's estimate to the paisa (the level nearer zero wins). GC-TP fix1 (ADR-209):
    ``shift`` is a flat amount (the booked P&L) added to the open-legs estimate everywhere, so the levels found are
    where open-legs P&L = -shift; ``totals`` stay the open-legs curve. One solver: a shift of 0 is the old answer."""
    totals = [t + shift for t in totals]
    found: list[Decimal] = []
    for i, (level, total) in enumerate(zip(levels, totals, strict=True)):
        if total == 0:
            found.append(level)
            continue
        if i + 1 == len(levels) or totals[i + 1] == 0 or (total > 0) == (totals[i + 1] > 0):
            continue
        lo, hi, lo_val = level, levels[i + 1], total
        while hi - lo > PAISE:
            mid = ((lo + hi) / 2).quantize(PAISE, rounding=ROUND_HALF_EVEN)
            if mid in (lo, hi):
                break
            val = estimate(model, mid, at).total + shift
            if val == 0:
                lo = hi = mid
                break
            if (val > 0) == (lo_val > 0):
                lo, lo_val = mid, val
            else:
                hi = mid
        if lo == hi:
            found.append(lo)
        else:
            hi_val = estimate(model, hi, at).total + shift
            found.append(lo if abs(lo_val) <= abs(hi_val) else hi)
    return tuple(found)


def greeks_total(rows: Sequence[Greeks]) -> Greeks:
    """The UNROUNDED sum of position Greeks, each Greek read by name; the caller rounds once at its boundary."""
    return Greeks(
        delta=sum((g.delta for g in rows), Decimal(0)),
        gamma=sum((g.gamma for g in rows), Decimal(0)),
        theta=sum((g.theta for g in rows), Decimal(0)),
        vega=sum((g.vega for g in rows), Decimal(0)),
    )
