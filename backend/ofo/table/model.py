"""The single strategy table: a pure data model, no HTML/web framework (REQ-035 AC-1, AC-2, AC-6, AC-7).

One :class:`Table` per strategy: a row per leg plus a strategy TOTAL row, columns in the AC-2 locked order (see
``columns.py``), scenario level columns taken from :mod:`ofo.scenario` (never recomputed here), and Lower/Upper
Breakeven summary columns (Q213) from the same level set. Every money/points cell comes straight from the engine
(``ofo.engine``/``ofo.scenario``); this module formats and arranges, it never invents a P&L number.

- **P&L %** (documented here; the spec is silent on this exact ratio): ``unrealized P&L / |entry value| x 100``,
  rounded half-even to 0.01 %. An entry value of 0 (only possible with a 0 entry price) gives a cell with no value
  and the reason "entry value is zero", never a divide error.
- **AC-6**: IV and Greeks are the platform's Black-Scholes (``ofo.engine.black_scholes``) computed from the leg's
  own IV, when the leg has one; a leg with no IV (or a futures leg, which has none) gets ``None`` cells with a
  reason. A vendor Greek passed on the input (``LegInput.greeks``) is carried on the cell as ``vendor`` only — it
  never replaces the platform value (AC-6).
- **Position-level Greeks** (implementation decision, spec silent on aggregation): a leg's Greek cell is its
  per-unit Black-Scholes Greek x quantity x (+1 BUY / -1 SELL), i.e. the leg's contribution to the strategy's net
  exposure — the same sign convention the engine's P&L uses (``position_pnl``). The TOTAL row sums the legs' Greek
  cells when every option leg has one; otherwise it is ``None`` with a reason (never a partial sum reported as the
  total).
- **Status** (implementation decision, spec silent beyond the column's existence): ITM/ATM/OTM of an option leg at
  the strategy input's current underlying level; a futures leg (no strike) and the TOTAL row show no value, with a
  reason.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from enum import Enum
from typing import Sequence

from ofo.engine.black_scholes import Greeks, bs_greeks, year_fraction
from ofo.engine.display import format_points, format_rupees
from ofo.engine.inputs import LegInput, StrategyInput
from ofo.engine.legs import Action, Instrument, live_pnl
from ofo.scenario.levels import LevelSet
from ofo.scenario.views import ScenarioValues
from ofo.table.columns import (
    HEADER_LABELS,
    LEADING_COLUMNS,
    TRAILING_COLUMNS,
    ColumnId,
    UXLevel,
    is_visible,
)

_PERCENT_STEP = Decimal("0.01")
TOTAL_ROW_ID = "TOTAL"


class CellKind(Enum):
    MONEY = "money"
    POINTS = "points"
    PERCENT = "percent"
    GREEK = "greek"
    IV = "iv"
    QUANTITY = "quantity"
    TEXT = "text"


@dataclass(frozen=True)
class Cell:
    """One table cell. ``value`` is ``None`` exactly when the value does not apply or cannot be computed."""

    value: Decimal | str | int | None
    display: str
    kind: CellKind
    reason: str | None = None
    vendor: Decimal | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, CellKind):
            raise ValueError(f"kind must be a CellKind, got {self.kind!r}")
        if not isinstance(self.display, str):
            raise ValueError(f"display must be a string, got {self.display!r}")
        if self.value is None and self.reason is None:
            raise ValueError("a cell with no value must carry a reason")


@dataclass(frozen=True)
class ColumnSpec:
    id: object  # ColumnId for a fixed column, Decimal (the level) for a scenario column
    label: str
    kind: CellKind
    is_scenario_level: bool = False


@dataclass(frozen=True)
class Row:
    row_id: str  # a 1-based leg number as a string, or TOTAL_ROW_ID
    cells: dict[object, Cell]

    def cell(self, column_id: object) -> Cell:
        return self.cells[column_id]


@dataclass(frozen=True)
class Table:
    columns: tuple[ColumnSpec, ...]
    rows: tuple[Row, ...]

    @property
    def column_ids(self) -> tuple[object, ...]:
        return tuple(c.id for c in self.columns)


def _text(value: str | None) -> Cell:
    if value is None:
        return Cell(None, "—", CellKind.TEXT, reason="not applicable")
    return Cell(value, value, CellKind.TEXT)


def _money(value: Decimal | None, reason: str | None = None) -> Cell:
    if value is None:
        return Cell(None, "—", CellKind.MONEY, reason=reason or "not available")
    return Cell(value, format_rupees(value), CellKind.MONEY)


def _points(value: Decimal | None, reason: str | None = None) -> Cell:
    if value is None:
        return Cell(None, "—", CellKind.POINTS, reason=reason or "not available")
    return Cell(value, format_points(value), CellKind.POINTS)


def _percent_cell(value: Decimal | None, reason: str | None = None) -> Cell:
    if value is None:
        return Cell(None, "—", CellKind.PERCENT, reason=reason or "not available")
    return Cell(value, f"{value}%", CellKind.PERCENT)


def _greek_cell(value: Decimal | None, vendor: Decimal | None, reason: str | None) -> Cell:
    if value is None:
        return Cell(None, "—", CellKind.GREEK, reason=reason or "not available", vendor=vendor)
    return Cell(value, str(value), CellKind.GREEK, vendor=vendor)


def _quantity_cell(value: int) -> Cell:
    return Cell(value, str(value), CellKind.QUANTITY)


def _percent(numerator: Decimal, denominator: Decimal) -> Decimal:
    """``numerator / denominator x 100`` rounded half-even to 0.01, computed at high precision first."""
    with localcontext() as ctx:
        ctx.prec = 50
        ratio = (numerator / denominator) * 100
    return ratio.quantize(_PERCENT_STEP, rounding=ROUND_HALF_EVEN)


def _status(leg: LegInput, spot: Decimal) -> Cell:
    if leg.instrument is Instrument.FUT:
        return _text(None)
    strike = leg.strike
    if strike == spot:
        return _text("ATM")
    if leg.instrument is Instrument.CE:
        return _text("ITM" if strike < spot else "OTM")
    return _text("ITM" if strike > spot else "OTM")


def _leg_greeks(leg: LegInput, inputs: StrategyInput) -> tuple[Greeks | None, str | None]:
    if leg.instrument is Instrument.FUT:
        return None, "a futures leg has no Greeks"
    if leg.iv is None:
        return None, "no implied volatility for this leg"
    years = year_fraction(inputs.valuation_time, leg.expiry, days_in_year=inputs.days_in_year)
    greeks = bs_greeks(
        leg.instrument, inputs.underlying_level, leg.strike, years, inputs.rate, leg.iv,
        days_in_year=inputs.days_in_year,
    )
    return greeks, None


def _signed(value: Decimal, action: Action, quantity: int) -> Decimal:
    sign = Decimal(1) if action is Action.BUY else Decimal(-1)
    return value * sign * quantity


def _leg_row(index: int, leg: LegInput, inputs: StrategyInput, level_columns: Sequence[Decimal],
             scenario: ScenarioValues | None, leg_position: int) -> Row:
    core = leg.leg
    entry_value = core.entry_price * core.quantity
    current_value = core.ltp * core.quantity if core.ltp is not None else None
    unrealized = live_pnl(core) if core.ltp is not None else None
    if unrealized is None:
        pnl_percent = None
        pct_reason = "no LTP for this leg"
    elif entry_value == 0:
        pnl_percent = None
        pct_reason = "entry value is zero"
    else:
        pnl_percent = _percent(unrealized, abs(entry_value))
        pct_reason = None

    greeks, greek_reason = _leg_greeks(leg, inputs)
    vendor = leg.greeks

    cells: dict[object, Cell] = {
        ColumnId.LEG: _text(str(index)),
        ColumnId.ACTION: _text(core.action.value),
        ColumnId.INSTRUMENT: _text(core.instrument.value),
        ColumnId.EXPIRY: _text(core.expiry.isoformat()),
        ColumnId.STRIKE: _points(core.strike) if core.strike is not None
        else _points(None, "a futures leg has no strike"),
        ColumnId.QUANTITY: _quantity_cell(core.quantity),
        ColumnId.ENTRY_PRICE: _money(core.entry_price),
        ColumnId.LTP: _money(core.ltp, "no LTP for this leg"),
        ColumnId.ENTRY_VALUE: _money(entry_value),
        ColumnId.CURRENT_VALUE: _money(current_value, "no LTP for this leg"),
        ColumnId.UNREALIZED_PNL: _money(unrealized, "no LTP for this leg"),
        ColumnId.PNL_PERCENT: _percent_cell(pnl_percent, pct_reason),
        ColumnId.IV: (Cell(leg.iv, f"{leg.iv}", CellKind.IV) if leg.iv is not None
                       else Cell(None, "—", CellKind.IV, reason=greek_reason)),
        ColumnId.DELTA: _greek_cell(None if greeks is None else greeks.delta,
                                     None if vendor is None else vendor.delta, greek_reason),
        ColumnId.GAMMA: _greek_cell(None if greeks is None else greeks.gamma,
                                     None if vendor is None else vendor.gamma, greek_reason),
        ColumnId.THETA: _greek_cell(None if greeks is None else greeks.theta,
                                     None if vendor is None else vendor.theta, greek_reason),
        ColumnId.VEGA: _greek_cell(None if greeks is None else greeks.vega,
                                    None if vendor is None else vendor.vega, greek_reason),
    }
    for level in level_columns:
        if scenario is None or not scenario.available or scenario.leg_rows is None:
            cells[level] = _money(None, "no scenario view is available")
        else:
            cells[level] = _money(scenario.leg_rows[leg_position][level_columns.index(level)])
    cells[ColumnId.LOWER_BE] = _text(None)
    cells[ColumnId.UPPER_BE] = _text(None)
    cells[ColumnId.STATUS] = _status(leg, inputs.underlying_level)
    return Row(str(index), cells)


def _total_row(inputs: StrategyInput, level_set: LevelSet | None, level_columns: Sequence[Decimal],
               scenario: ScenarioValues | None) -> Row:
    legs = inputs.legs
    entry_value = sum((leg.premium * leg.quantity for leg in legs), Decimal(0))
    have_all_ltp = all(leg.ltp is not None for leg in legs)
    if have_all_ltp:
        current_value = sum((leg.ltp * leg.quantity for leg in legs), Decimal(0))
        unrealized = sum((live_pnl(leg.leg) for leg in legs), Decimal(0))
        pnl_percent = _percent(unrealized, abs(entry_value)) if entry_value != 0 else None
        pct_reason = None if entry_value != 0 else "entry value is zero"
    else:
        current_value = None
        unrealized = None
        pnl_percent = None
        pct_reason = "not every leg has an LTP"

    greek_values: dict[str, Decimal] = {"delta": Decimal(0), "gamma": Decimal(0), "theta": Decimal(0),
                                         "vega": Decimal(0)}
    every_option_has_greeks = True
    for leg in legs:
        if not leg.leg.is_option:
            continue
        greeks, reason = _leg_greeks(leg, inputs)
        if greeks is None:
            every_option_has_greeks = False
            break
        for name in greek_values:
            greek_values[name] += _signed(getattr(greeks, name), leg.action, leg.quantity)
    if not every_option_has_greeks:
        greek_values = {name: None for name in greek_values}
        greek_reason = "not every leg has an implied volatility"
    else:
        greek_reason = None

    cells: dict[object, Cell] = {
        ColumnId.LEG: _text(None),
        ColumnId.ACTION: _text(None),
        ColumnId.INSTRUMENT: _text(None),
        ColumnId.EXPIRY: _text(None),
        ColumnId.STRIKE: _text(None),
        ColumnId.QUANTITY: _text(None),
        ColumnId.ENTRY_PRICE: _text(None),
        ColumnId.LTP: _text(None),
        ColumnId.ENTRY_VALUE: _money(entry_value),
        ColumnId.CURRENT_VALUE: _money(current_value, "not every leg has an LTP"),
        ColumnId.UNREALIZED_PNL: _money(unrealized, "not every leg has an LTP"),
        ColumnId.PNL_PERCENT: _percent_cell(pnl_percent, pct_reason),
        ColumnId.IV: _text(None),
        ColumnId.DELTA: _greek_cell(greek_values["delta"], None, greek_reason),
        ColumnId.GAMMA: _greek_cell(greek_values["gamma"], None, greek_reason),
        ColumnId.THETA: _greek_cell(greek_values["theta"], None, greek_reason),
        ColumnId.VEGA: _greek_cell(greek_values["vega"], None, greek_reason),
    }
    for i, level in enumerate(level_columns):
        if scenario is None or not scenario.available or scenario.totals is None:
            cells[level] = _money(None, "no scenario view is available")
        else:
            cells[level] = _money(scenario.totals[i])
    if level_set is not None:
        cells[ColumnId.LOWER_BE] = _points(level_set.lower_be, "no lower breakeven")
        cells[ColumnId.UPPER_BE] = _points(level_set.upper_be, "no upper breakeven")
    else:
        cells[ColumnId.LOWER_BE] = _points(None, "no scenario view is available")
        cells[ColumnId.UPPER_BE] = _points(None, "no scenario view is available")
    cells[ColumnId.STATUS] = _text(None)
    return Row(TOTAL_ROW_ID, cells)


def build_table(
    inputs: StrategyInput,
    *,
    level_set: LevelSet | None = None,
    scenario: ScenarioValues | None = None,
) -> Table:
    """Build the one strategy table (AC-1): a row per leg, a TOTAL row, columns in the AC-2 locked order.

    ``level_set``/``scenario`` are optional so a table can be built without a scenario view (its level columns are
    then empty); when given, they must come from :mod:`ofo.scenario` (``build_level_set``/``scenario_values``) —
    this function never recomputes a scenario level or a P&L number itself.
    """
    if not isinstance(inputs, StrategyInput):
        raise ValueError(f"inputs must be a StrategyInput, got {inputs!r}")
    if level_set is not None and not isinstance(level_set, LevelSet):
        raise ValueError(f"level_set must be a LevelSet, got {level_set!r}")
    if scenario is not None and not isinstance(scenario, ScenarioValues):
        raise ValueError(f"scenario must be a ScenarioValues, got {scenario!r}")
    if (level_set is None) != (scenario is None):
        raise ValueError("level_set and scenario must be given together, or not at all")

    level_columns: tuple[Decimal, ...] = level_set.levels if level_set is not None else ()

    columns = [ColumnSpec(cid, HEADER_LABELS[cid], _leading_kind(cid)) for cid in LEADING_COLUMNS]
    columns += [ColumnSpec(level, format_points(level), CellKind.MONEY, is_scenario_level=True)
                for level in level_columns]
    columns += [ColumnSpec(cid, HEADER_LABELS[cid], _trailing_kind(cid)) for cid in TRAILING_COLUMNS]

    rows = [
        _leg_row(i, leg, inputs, level_columns, scenario, i - 1)
        for i, leg in enumerate(inputs.legs, start=1)
    ]
    rows.append(_total_row(inputs, level_set, level_columns, scenario))
    return Table(tuple(columns), tuple(rows))


def _leading_kind(cid: ColumnId) -> CellKind:
    return {
        ColumnId.LEG: CellKind.TEXT,
        ColumnId.ACTION: CellKind.TEXT,
        ColumnId.INSTRUMENT: CellKind.TEXT,
        ColumnId.EXPIRY: CellKind.TEXT,
        ColumnId.STRIKE: CellKind.POINTS,
        ColumnId.QUANTITY: CellKind.QUANTITY,
        ColumnId.ENTRY_PRICE: CellKind.MONEY,
        ColumnId.LTP: CellKind.MONEY,
        ColumnId.ENTRY_VALUE: CellKind.MONEY,
        ColumnId.CURRENT_VALUE: CellKind.MONEY,
        ColumnId.UNREALIZED_PNL: CellKind.MONEY,
        ColumnId.PNL_PERCENT: CellKind.PERCENT,
        ColumnId.IV: CellKind.IV,
        ColumnId.DELTA: CellKind.GREEK,
        ColumnId.GAMMA: CellKind.GREEK,
        ColumnId.THETA: CellKind.GREEK,
        ColumnId.VEGA: CellKind.GREEK,
    }[cid]


def _trailing_kind(cid: ColumnId) -> CellKind:
    return {
        ColumnId.LOWER_BE: CellKind.POINTS,
        ColumnId.UPPER_BE: CellKind.POINTS,
        ColumnId.STATUS: CellKind.TEXT,
    }[cid]


def visible_columns(table: Table, level: UXLevel) -> tuple[ColumnSpec, ...]:
    """The column specs ``level`` shows, in the table's own (locked) order (AC-7).

    A scenario level column (``is_scenario_level``) is visible at every level. A fixed column is filtered by
    :func:`ofo.table.columns.is_visible`. Never reorders ``table.columns``.
    """
    if not isinstance(table, Table):
        raise ValueError(f"table must be a Table, got {table!r}")
    return tuple(
        col for col in table.columns
        if col.is_scenario_level or is_visible(col.id, level)
    )
