"""The scenario level set: which market levels the table and the payoff graph show (REQ-034 AC-2..AC-5, AC-8).

Spec: scenario-calculations.md §4 (Q33B = E, Q33C, Q33D = C, Q213; ADR-042). Every level is index POINTS, never ₹.

1. **Default range (Q33B = E).** It covers spot, every strike, every breakeven, every risk boundary (strike where
   the payoff reaches its max loss) and, when IV and days are given, spot +/- the expected move, plus
   ``margin_steps`` steps beyond the outermost of them; and at least ``min_half_width_points`` each side of spot
   rounded to the anchor. The range is therefore not necessarily centred on spot. The user may override it.
2. **Grid (Q33C).** Columns are multiples of the anchor, ``step_points`` apart.
3. **Inserted columns (Q33D = C).** The exact current level (CURRENT) and every breakeven inside the range
   (ZERO_PNL) are added at their price positions. A level that is already a grid column gets the flag instead of a
   second column. The current level is always present, even when a user range excludes it (AC-2).
4. **Breakeven summary (Q213).** Lower BE / Upper BE are reported alongside; a missing one is ``None`` (shown "—").

Breakevens, max loss and every P&L come from the engine (:func:`ofo.engine.strategy_metrics`), never re-derived.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal
from enum import Enum
from typing import Final

from ofo.engine import UNLIMITED, strategy_metrics
from ofo.engine.inputs import StrategyInput
from ofo.engine.legs import require_price
from ofo.scenario.config import ScenarioConfig
from ofo.scenario.spot import check_spot

DAYS_IN_YEAR: Final = Decimal(365)
MAX_EXPECTED_MOVE_DAYS: Final = 3660
MAX_IV: Final = Decimal("5")


class ColumnKind(Enum):
    GRID = "grid"
    CURRENT = "current"
    ZERO_PNL = "zero_pnl"


@dataclass(frozen=True)
class LevelColumn:
    """One scenario column: an index level (points) and why it is there (a grid level can also be CURRENT)."""

    level: Decimal
    kinds: frozenset[ColumnKind]

    @property
    def is_current(self) -> bool:
        return ColumnKind.CURRENT in self.kinds

    @property
    def is_zero_pnl(self) -> bool:
        return ColumnKind.ZERO_PNL in self.kinds


@dataclass(frozen=True)
class ExpectedMove:
    """Optional expected-move input: annualised IV as a fraction (0.12 = 12 %) and calendar days to expiry."""

    iv: Decimal
    days: int

    def __post_init__(self) -> None:
        if not isinstance(self.iv, Decimal) or not self.iv.is_finite() or not 0 < self.iv <= MAX_IV:
            raise ValueError(f"expected-move iv must be a Decimal fraction in (0, {MAX_IV}], got {self.iv!r}")
        if isinstance(self.days, bool) or not isinstance(self.days, int):
            raise ValueError(f"expected-move days must be an integer, got {self.days!r}")
        if not 0 < self.days <= MAX_EXPECTED_MOVE_DAYS:
            raise ValueError(f"expected-move days must be within [1, {MAX_EXPECTED_MOVE_DAYS}], got {self.days}")

    def points(self, spot: Decimal) -> Decimal:
        """One-standard-deviation move in points: spot x IV x sqrt(days / 365), rounded up to a whole point."""
        move = spot * self.iv * (Decimal(self.days) / DAYS_IN_YEAR).sqrt()
        return move.to_integral_value(rounding=ROUND_CEILING)


@dataclass(frozen=True)
class RangeOverride:
    """A user-chosen range. Both ends are grid levels: multiples of the anchor, a whole number of steps apart."""

    start: Decimal
    end: Decimal


@dataclass(frozen=True)
class LevelSet:
    index: str
    current: Decimal
    step: Decimal
    start: Decimal
    end: Decimal
    customised: bool
    columns: tuple[LevelColumn, ...]
    breakevens: tuple[Decimal, ...]
    lower_be: Decimal | None
    upper_be: Decimal | None
    risk_boundaries: tuple[Decimal, ...]
    expected_move_points: Decimal | None
    spot_at: datetime | None = None  # REQ-072 AC-3: the spot's time, recorded beside the calculation
    data_label: str | None = None  # "stale since HH:MM IST" etc. (REQ-049 AC-4); None when live

    @property
    def levels(self) -> tuple[Decimal, ...]:
        return tuple(column.level for column in self.columns)


def _floor_to(value: Decimal, unit: Decimal) -> Decimal:
    return (value / unit).to_integral_value(rounding=ROUND_FLOOR) * unit


def _ceil_to(value: Decimal, unit: Decimal) -> Decimal:
    return (value / unit).to_integral_value(rounding=ROUND_CEILING) * unit


def _lower_upper(inputs: StrategyInput, breakevens: tuple[Decimal, ...], step: Decimal) -> tuple[Decimal | None, ...]:
    """Lower/Upper BE summary values (Q213).

    Two or more breakevens: the lowest and the highest. Exactly one: it is the edge of the profit zone, so it is the
    Lower BE when the payoff is a profit above it (e.g. a long call) and the Upper BE when the profit lies below it
    (e.g. a short call). None: both missing.
    """
    if not breakevens:
        return (None, None)
    if len(breakevens) >= 2:
        return (breakevens[0], breakevens[-1])
    only = breakevens[0]
    if inputs.strategy.expiry_pnl_at(only + step) > 0:
        return (only, None)
    return (None, only)


def _check_override(override: RangeOverride, config: ScenarioConfig) -> tuple[Decimal, Decimal]:
    if not isinstance(override, RangeOverride):
        raise ValueError(f"override must be a RangeOverride, got {override!r}")
    for name, value in (("start", override.start), ("end", override.end)):
        if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
            raise ValueError(f"range {name} must be a positive decimal.Decimal of points, got {value!r}")
        if value % config.anchor_points != 0:
            raise ValueError(f"range {name} {value} is not a multiple of the anchor {config.anchor_points} points")
    if override.end <= override.start:
        raise ValueError(f"range end {override.end} must be above range start {override.start}")
    if (override.end - override.start) % config.step_points != 0:
        raise ValueError(
            f"range {override.start}..{override.end} is not a whole number of {config.step_points}-point steps"
        )
    return override.start, override.end


def build_level_set(
    inputs: StrategyInput,
    config: ScenarioConfig,
    *,
    expected_move: ExpectedMove | None = None,
    override: RangeOverride | None = None,
) -> LevelSet:
    """The one level set every scenario consumer (table and payoff graph) uses (AC-8)."""
    if not isinstance(inputs, StrategyInput):
        raise ValueError(f"inputs must be a StrategyInput, got {inputs!r}")
    if not isinstance(config, ScenarioConfig):
        raise ValueError(f"config must be a ScenarioConfig, got {config!r}")
    if config.index != inputs.underlying:
        raise ValueError(f"config is for {config.index}, the strategy is on {inputs.underlying}")
    if expected_move is not None and not isinstance(expected_move, ExpectedMove):
        raise ValueError(f"expected_move must be an ExpectedMove, got {expected_move!r}")
    reading, label = check_spot(inputs)  # refuses a missing/unavailable spot; never a bare level (REQ-072 AC-2)
    spot = require_price(reading.level, "current level", allow_zero=False)
    strategy = inputs.strategy
    metrics = strategy_metrics(strategy)  # raises MultiExpiryError: no exact at-expiry payoff to lay out
    strikes = sorted({leg.strike for leg in strategy.legs if leg.is_option})
    risk_boundaries: tuple[Decimal, ...] = ()
    if metrics.min_pnl is not UNLIMITED and metrics.max_loss != 0:
        risk_boundaries = tuple(k for k in strikes if strategy.expiry_pnl_at(k) == metrics.min_pnl)
    move = expected_move.points(spot) if expected_move is not None else None

    step, anchor = config.step_points, config.anchor_points
    if override is not None:
        start, end = _check_override(override, config)
        customised = True
    else:
        keys = [spot, *strikes, *metrics.breakevens, *risk_boundaries]
        if move is not None:
            keys += [spot - move, spot + move]
        centre = (spot / anchor).to_integral_value(rounding=ROUND_HALF_UP) * anchor
        margin = step * config.margin_steps
        low = min(centre - config.min_half_width_points, min(keys) - margin)
        high = max(centre + config.min_half_width_points, max(keys) + margin)
        start = max(_floor_to(low, anchor), anchor)
        end = start + _ceil_to(max(high - start, step), step)
        customised = False

    count = (end - start) / step + 1
    if count > config.max_columns:
        raise ValueError(
            f"{config.index} range {start}..{end} needs {count} columns at a {step}-point step; "
            f"the configured maximum is {config.max_columns}"
        )
    kinds: dict[Decimal, set[ColumnKind]] = {}
    level = start
    while level <= end:
        kinds.setdefault(level, set()).add(ColumnKind.GRID)
        level += step
    kinds.setdefault(spot, set()).add(ColumnKind.CURRENT)
    for be in metrics.breakevens:
        if start <= be <= end:
            kinds.setdefault(be, set()).add(ColumnKind.ZERO_PNL)
    # Decimal("23000") and Decimal("23000.00") are equal and hash alike, so an equal level never adds a column.
    columns = tuple(LevelColumn(lvl, frozenset(k)) for lvl, k in sorted(kinds.items()))
    lower_be, upper_be = _lower_upper(inputs, metrics.breakevens, step)
    return LevelSet(
        index=config.index,
        current=spot,
        spot_at=reading.at,
        data_label=label,
        step=step,
        start=start,
        end=end,
        customised=customised,
        columns=columns,
        breakevens=metrics.breakevens,
        lower_be=lower_be,
        upper_be=upper_be,
        risk_boundaries=risk_boundaries,
        expected_move_points=move,
    )
