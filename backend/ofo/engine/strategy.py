"""Strategy aggregation, net premium and the scenario grid (spec/business-rules/scenario-calculations.md §1, §3, §4)."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Sequence

from ofo.engine.legs import Action, Leg, expiry_pnl, live_pnl, require_decimal


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


class PriceBasis(Enum):
    """Which per-unit price a net premium uses: the entry price, or the current LTP."""

    ENTRY = "entry"
    LTP = "ltp"


def net_premium(strategy: Strategy, price: PriceBasis) -> Decimal:
    """Strategy net premium in rupees, credit positive (§3: net premium is strategy-level).

    Each SELL option leg adds ``price x quantity`` and each BUY option leg subtracts it. Futures legs have no
    premium and add 0, with or without an LTP. With ``PriceBasis.LTP`` an option leg without an LTP raises.
    Example: BUY 75 x 23000 CE @ 100, SELL 150 x 23200 CE @ 60 -> 9,000 - 7,500 = +1,500.
    """
    if not isinstance(price, PriceBasis):
        raise ValueError(f"price must be a PriceBasis, got {price!r}")
    total = Decimal(0)
    for leg in strategy.legs:
        if not leg.is_option:
            continue
        if price is PriceBasis.LTP:
            if leg.ltp is None:
                raise ValueError("an LTP net premium needs an LTP on every option leg; this leg has none")
            unit = leg.ltp
        else:
            unit = leg.entry_price
        total += (unit if leg.action is Action.SELL else -unit) * leg.quantity
    return total
