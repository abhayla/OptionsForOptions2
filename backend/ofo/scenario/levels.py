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
4. **Graph levels (GC-BM F-8, REQ-083 AC-7).** The payoff GRAPH also takes every option leg's strike inside the range
   (:func:`graph_level_set`) so its line has its kinks exactly at the strikes; the scenario TABLE keeps the columns of
   point 3 only.
5. **Breakeven summary (Q213).** Lower BE / Upper BE are reported alongside; a missing one is ``None`` (shown "—").

Breakevens, max loss and every P&L come from the engine (:func:`ofo.engine.strategy_metrics`), never re-derived.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal, localcontext
from enum import Enum
from typing import Final

from ofo.engine import UNLIMITED, strategy_metrics
from ofo.engine.metrics import LossRegion
from ofo.engine.legs import require_price
from ofo.engine.model import ModelInputs
from ofo.scenario.config import ScenarioConfig

DAYS_IN_YEAR: Final = Decimal(365)
MAX_EXPECTED_MOVE_DAYS: Final = 3660
MAX_IV: Final = Decimal("5")


class ColumnKind(Enum):
    GRID = "grid"
    CURRENT = "current"
    ZERO_PNL = "zero_pnl"
    STRIKE = "strike"  # GC-BM F-8: graph-only (graph_level_set); never a scenario-table column (Q33D = C)


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

    def exact_points(self, spot: Decimal) -> Decimal:
        """THE expected-move formula (REQ-027 Q254, scenario-calculations section 4): one standard deviation in points,
        spot x IV x sqrt(calendar days / 365), unrounded. The default range and the SD block both read it."""
        return spot * self.iv * (Decimal(self.days) / DAYS_IN_YEAR).sqrt()

    def points(self, spot: Decimal) -> Decimal:
        """One-standard-deviation move in points, rounded up to a whole point (the default range)."""
        return self.exact_points(spot).to_integral_value(rounding=ROUND_CEILING)


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


def _lower_upper(
    inputs: ModelInputs, loss_regions: tuple[LossRegion, ...], breakevens: tuple[Decimal, ...], step: Decimal
) -> tuple[Decimal | None, ...]:
    """Lower/Upper BE summary values (Q213, ADR-089).

    Two or more breakevens: the lowest and the highest. Exactly one, from the engine's ``loss_regions`` (ADR-072):
    loss below only -> Lower BE; loss above only -> Upper BE; loss on both sides -> both labels; no loss region at all
    -> the profit side decides (profit above -> Lower BE, below -> Upper BE). None: both missing.
    """
    if not breakevens:
        return (None, None)
    if len(breakevens) >= 2:
        return (breakevens[0], breakevens[-1])
    only = breakevens[0]
    split = any(len(region) == 3 and only in region[2] for region in loss_regions)  # a zero point inside one region
    loss_below = split or any(region[1] == only for region in loss_regions)
    loss_above = split or any(region[0] == only for region in loss_regions)
    if loss_below and loss_above:  # the profit zone is that single point: the level is both edges
        return (only, only)
    if loss_below:
        return (only, None)
    if loss_above:
        return (None, only)
    # No loss region at all (P&L >= 0 everywhere): the profit side decides.
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


def resolve_range(
    config: ScenarioConfig, start: Decimal | None, end: Decimal | None
) -> RangeOverride | None:
    """The range override for a user's pick (REQ-034 AC-4), refusing anything off the allow-list.

    ``start`` and ``end`` come together; both sit on the Admin anchor grid (AC-5: rounded 100-point levels for NIFTY),
    a whole number of the Admin step apart, with at most ``max_columns`` columns. The step is never the user's.
    """
    if (start is None) != (end is None):
        raise ValueError("a range needs both its start and its end")
    if start is None or end is None:
        return None
    override = RangeOverride(start, end)
    _check_override(override, config)
    columns = (end - start) / config.step_points + 1
    if columns > config.max_columns:
        raise ValueError(f"range {start}..{end} needs {columns} columns; the maximum is {config.max_columns}")
    return override


def build_level_set(
    inputs: ModelInputs,
    config: ScenarioConfig,
    *,
    expected_move: ExpectedMove | None = None,
    override: RangeOverride | None = None,
) -> LevelSet:
    """The one level set every scenario consumer (table and payoff graph) uses (AC-8).

    ``inputs`` is a gated :class:`~ofo.engine.model.ModelInputs` (REQ-072 AC-2): the spot was refused there if it was
    missing or unavailable; CURRENT and the range stay on that spot (ADR-061).
    """
    if not isinstance(inputs, ModelInputs):
        raise ValueError(f"inputs must be a ModelInputs (ofo.engine.model.model_inputs), got {inputs!r}")
    if not isinstance(config, ScenarioConfig):
        raise ValueError(f"config must be a ScenarioConfig, got {config!r}")
    if config.index != inputs.underlying:
        raise ValueError(f"config is for {config.index}, the strategy is on {inputs.underlying}")
    if expected_move is not None and not isinstance(expected_move, ExpectedMove):
        raise ValueError(f"expected_move must be an ExpectedMove, got {expected_move!r}")
    spot = require_price(inputs.spot_level, "current level", allow_zero=False)
    strategy = inputs.strategy
    # G-065 (REQ-148 AC-6): legs on more than one expiry have no exact at-expiry payoff, so no breakeven, loss region or
    # risk boundary exists to lay out; the levels then rest on the spot, the strikes and the expected move only.
    metrics = strategy_metrics(strategy) if strategy.is_single_expiry else None
    breakevens = () if metrics is None else metrics.breakevens
    strikes = sorted({leg.strike for leg in strategy.legs if leg.is_option})
    risk_boundaries: tuple[Decimal, ...] = ()
    if metrics is not None and metrics.min_pnl is not UNLIMITED and metrics.max_loss != 0:
        risk_boundaries = tuple(k for k in strikes if strategy.expiry_pnl_at(k) == metrics.min_pnl)
    move = expected_move.points(spot) if expected_move is not None else None

    step, anchor = config.step_points, config.anchor_points
    if override is not None:
        start, end = _check_override(override, config)
        customised = True
    else:
        keys = [spot, *strikes, *breakevens, *risk_boundaries]
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
    for be in breakevens:
        if start <= be <= end:
            kinds.setdefault(be, set()).add(ColumnKind.ZERO_PNL)
    # Decimal("23000") and Decimal("23000.00") are equal and hash alike, so an equal level never adds a column.
    columns = tuple(LevelColumn(lvl, frozenset(k)) for lvl, k in sorted(kinds.items()))
    lower_be, upper_be = (None, None) if metrics is None else _lower_upper(inputs, metrics.loss_regions,
                                                                           breakevens, step)
    return LevelSet(
        index=config.index,
        current=spot,
        spot_at=inputs.spot_at,
        data_label=inputs.data_label,
        step=step,
        start=start,
        end=end,
        customised=customised,
        columns=columns,
        breakevens=breakevens,
        lower_be=lower_be,
        upper_be=upper_be,
        risk_boundaries=risk_boundaries,
        expected_move_points=move,
    )


def graph_level_set(level_set: LevelSet, inputs: ModelInputs) -> LevelSet:
    """The payoff GRAPH's levels (GC-BM F-8): ``level_set``'s columns plus every option leg's strike inside
    ``start..end``, marked ``STRIKE``. A strike that is already a column only gains the flag, so no level appears twice;
    a futures leg has no strike and adds nothing. The scenario table never uses this set (Q33D = C)."""
    if not isinstance(level_set, LevelSet):
        raise ValueError(f"level_set must be a LevelSet, got {level_set!r}")
    if not isinstance(inputs, ModelInputs):
        raise ValueError(f"inputs must be a ModelInputs (ofo.engine.model.model_inputs), got {inputs!r}")
    kinds: dict[Decimal, set[ColumnKind]] = {c.level: set(c.kinds) for c in level_set.columns}
    for leg in inputs.strategy.legs:
        if leg.is_option and level_set.start <= leg.strike <= level_set.end:
            kinds.setdefault(leg.strike, set()).add(ColumnKind.STRIKE)
    columns = tuple(LevelColumn(lvl, frozenset(k)) for lvl, k in sorted(kinds.items()))
    return replace(level_set, columns=columns)


def first_multiple_at_or_above(start: Decimal, step: Decimal) -> Decimal:
    """REQ-137 AC-1: the first index level that is a multiple of ``step`` at or above ``start`` (index points, not
    rupees): the payoff table's first row."""
    return (start / step).to_integral_value(rounding=ROUND_CEILING) * step


_TENTH: Final = Decimal("0.1")
_MOVE_PRECISION: Final = 50


def move_from_spot(level: Decimal, spot: Decimal | None) -> tuple[Decimal | None, str | None]:
    """REQ-137 AC-2 "Show %" (D-B26): a payoff-table level's move from spot in percent, (level - spot) x 100 / spot,
    exact; and its display, signed to one decimal half-up ("+2.1%", "-2.0%"; a figure that rounds to zero is "0.0%",
    never "-0.0%"). No spot (an answer without a live index price): (None, None)."""
    if spot is None:
        return None, None
    with localcontext(prec=_MOVE_PRECISION):
        pct = (level - spot) * 100 / spot
    shown = pct.quantize(_TENTH, ROUND_HALF_UP)
    from ofo.errors.explanations import render_explanation  # noqa: PLC0415 - late, as ofo.outcome.serialize does

    if shown == 0:  # the signed template would print "+0.0%"
        return pct, render_explanation("cell_percent", value=abs(shown))
    return pct, render_explanation("cell_percent_signed", value=shown)
