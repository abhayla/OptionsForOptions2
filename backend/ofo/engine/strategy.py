"""Strategy aggregation and the scenario grid (spec/business-rules/scenario-calculations.md §1, §4)."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

from ofo.engine.legs import Leg, expiry_pnl, live_pnl, require_decimal


@dataclass(frozen=True)
class Strategy:
    """An ordered, non-empty set of legs. Every number is the sum of its legs' numbers."""

    legs: tuple[Leg, ...]

    def __post_init__(self) -> None:
        legs = tuple(self.legs)
        if not legs:
            raise ValueError("a strategy needs at least one leg")
        for leg in legs:
            if not isinstance(leg, Leg):
                raise ValueError(f"every leg must be a Leg, got {leg!r}")
        object.__setattr__(self, "legs", legs)

    @property
    def is_single_expiry(self) -> bool:
        return len({leg.expiry for leg in self.legs}) == 1

    def expiry_pnl_at(self, level: Decimal) -> Decimal:
        """Strategy expiry P&L at ``level`` = sum of every leg's expiry P&L there (§1)."""
        return sum((expiry_pnl(leg, level) for leg in self.legs), Decimal(0))

    def live_pnl(self) -> Decimal:
        """Strategy live P&L = sum of every leg's live P&L; any leg without an LTP raises."""
        return sum((live_pnl(leg) for leg in self.legs), Decimal(0))


@dataclass(frozen=True)
class ScenarioGrid:
    """At-expiry scenario table: one filled row per leg plus the strategy total row."""

    levels: tuple[Decimal, ...]
    leg_rows: tuple[tuple[Decimal, ...], ...]
    totals: tuple[Decimal, ...]


def scenario_grid(strategy: Strategy, levels: Sequence[Decimal]) -> ScenarioGrid:
    """Compute every cell (every leg x every level, including out-of-the-money legs) and the totals.

    No cell is ever left blank (§1, T1 #93/#95): an out-of-the-money leg's cell is its premium result.
    """
    checked = tuple(require_decimal(level, "level") for level in levels)
    if not checked:
        raise ValueError("a scenario grid needs at least one level")
    leg_rows = tuple(tuple(expiry_pnl(leg, level) for level in checked) for leg in strategy.legs)
    totals = tuple(sum((row[i] for row in leg_rows), Decimal(0)) for i in range(len(checked)))
    return ScenarioGrid(levels=checked, leg_rows=leg_rows, totals=totals)
