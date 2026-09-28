"""The single strategy table: a pure data model, no HTML/web framework (REQ-035 AC-1, AC-2, AC-6, AC-7).

One :class:`Table` per strategy: a row per leg plus a strategy TOTAL row, columns in the AC-2 locked order (see
``columns.py``), scenario level columns taken from :mod:`ofo.scenario` (never recomputed here), and Lower/Upper
Breakeven summary columns (Q213) from the same level set. Every money/points cell comes straight from the engine
(``ofo.engine``/``ofo.scenario``); this module formats and arranges, it never invents a P&L number.

- **P&L %** (documented here; the spec is silent on this exact ratio): a leg's P&L % is
  ``unrealized P&L / |entry value| x 100``, rounded half-even to 0.01 %; an entry value of 0 gives no value and the
  reason "entry value is zero", never a divide error. The **TOTAL row's P&L % is always "—"** (fix round, verifier
  finding): the owner-reviewed source table leaves the strategy total blank, and gross entry value would mislead
  for a net-credit strategy (e.g. the §6 Iron Condor collects a credit, so "% of entry value" has no agreed meaning)
  — open owner question, not computed here.
- **AC-6, Greeks are POSITION-level, one unit throughout the table** (fix round, verifier finding: leg cells were
  per-unit while the TOTAL row was position-level — two units in one column is the defect). A leg's Delta/Gamma/
  Theta/Vega cell is the platform Black-Scholes per-unit Greek x quantity x sign (+1 BUY / -1 SELL) — the same
  sign convention as ``position_pnl`` — so ``TOTAL = sum of the leg cells`` exactly, for every Greek. The per-unit
  (unsigned) Black-Scholes value is kept as ``Cell.per_unit``, a secondary field for Advanced display (e.g. "the
  option's Delta is 0.41; your position Delta is -30.94"). A futures leg has no Black-Scholes Greeks, but it is not
  excluded from the total (the prior round's bug): its per-unit Delta is 1 (a future's linear payoff has slope 1),
  Gamma/Theta/Vega 0, so a SELL 75 x FUT leg's Delta cell and its share of TOTAL Delta are both -75. Its IV cell
  stays "—" (a futures leg has no implied volatility). A vendor Greek passed on the input (``LegInput.greeks``) is
  carried on the cell as ``vendor`` only — it never replaces the platform value.
- **Status** (fix round: settled by the tables the owner reviewed in T1, not computed from moneyness — the prior
  ITM/ATM/OTM rule was a defect, moneyness is not in the AC-2 column list). A leg's Status is whatever state the
  caller passes in for that leg (``leg_statuses``, e.g. "Open" — an enum defined elsewhere, not computed here); the
  TOTAL row's Status is the strategy's health, passed in as a :class:`StrategyHealth` (REQ-043 AC-2; ADR-010 lines
  29-30, the owner's exact labels: "Healthy", "Watch", "Adjustment opportunity", "Exit condition reached"). Neither
  is computed by this module; a missing status shows "—".
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

# A futures leg's per-unit Greeks (implementation decision, spec silent): linear payoff, slope 1, no volatility
# sensitivity. Signed by _position_greeks like every other leg (BUY +1, SELL -1, x quantity).
_FUTURES_PER_UNIT_GREEKS = Greeks(delta=Decimal(1), gamma=Decimal(0), theta=Decimal(0), vega=Decimal(0))


class CellKind(Enum):
    MONEY = "money"
    POINTS = "points"
    PERCENT = "percent"
    GREEK = "greek"
    IV = "iv"
    QUANTITY = "quantity"
    TEXT = "text"


class StrategyHealth(Enum):
    """REQ-043 AC-2; ADR-010 lines 29-30 (Q20 = B, T1 #41): the owner's exact four labels. Rule-based, no
    prediction (AC-3); never invented or computed by this table module — passed in by the caller."""

    HEALTHY = "Healthy"
    WATCH = "Watch"
    ADJUSTMENT_OPPORTUNITY = "Adjustment opportunity"
    EXIT_CONDITION_REACHED = "Exit condition reached"


@dataclass(frozen=True)
class Cell:
    """One table cell. ``value`` is ``None`` exactly when the value does not apply or cannot be computed.

    ``per_unit`` is a secondary field (Greek cells only): the platform Black-Scholes per-unit value, before the
    quantity/sign scaling that makes ``value`` a position-level number — kept for Advanced display, never the
    primary value (AC-6 fix round).
    """

    value: Decimal | str | int | None
    display: str
    kind: CellKind
    reason: str | None = None
    vendor: Decimal | None = None
    per_unit: Decimal | None = None

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


def _text(value: str | None, reason: str | None = None) -> Cell:
    if value is None:
        return Cell(None, "—", CellKind.TEXT, reason=reason or "not applicable")
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


def _greek_cell(position_value: Decimal | None, vendor: Decimal | None, per_unit_value: Decimal | None,
                reason: str | None) -> Cell:
    if position_value is None:
        return Cell(None, "—", CellKind.GREEK, reason=reason or "not available", vendor=vendor,
                    per_unit=per_unit_value)
    return Cell(position_value, str(position_value), CellKind.GREEK, vendor=vendor, per_unit=per_unit_value)


def _quantity_cell(value: int) -> Cell:
    return Cell(value, str(value), CellKind.QUANTITY)


def _percent(numerator: Decimal, denominator: Decimal) -> Decimal:
    """``numerator / denominator x 100`` rounded half-even to 0.01, computed at high precision first."""
    with localcontext() as ctx:
        ctx.prec = 50
        ratio = (numerator / denominator) * 100
    return ratio.quantize(_PERCENT_STEP, rounding=ROUND_HALF_EVEN)


def _leg_per_unit_greeks(leg: LegInput, inputs: StrategyInput) -> tuple[Greeks | None, str | None]:
    """The platform's per-unit Black-Scholes Greeks for one leg (AC-6), or ``None`` with a reason.

    A futures leg always has a value (:data:`_FUTURES_PER_UNIT_GREEKS`, never excluded from a total). An option
    leg with no IV has none.
    """
    if leg.instrument is Instrument.FUT:
        return _FUTURES_PER_UNIT_GREEKS, None
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


def _position_greeks(per_unit: Greeks, action: Action, quantity: int) -> Greeks:
    """Position-level Greeks: per-unit x quantity x sign (AC-6 fix round — the table's one Greek unit)."""
    return Greeks(
        delta=_signed(per_unit.delta, action, quantity),
        gamma=_signed(per_unit.gamma, action, quantity),
        theta=_signed(per_unit.theta, action, quantity),
        vega=_signed(per_unit.vega, action, quantity),
    )


def _iv_cell(leg: LegInput) -> Cell:
    if leg.instrument is Instrument.FUT:
        return Cell(None, "—", CellKind.IV, reason="a futures leg has no implied volatility")
    if leg.iv is None:
        return Cell(None, "—", CellKind.IV, reason="no implied volatility for this leg")
    return Cell(leg.iv, f"{leg.iv}", CellKind.IV)


def _leg_row(index: int, leg: LegInput, inputs: StrategyInput, level_columns: Sequence[Decimal],
             scenario: ScenarioValues | None, leg_position: int, status: str | None) -> Row:
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

    per_unit, greek_reason = _leg_per_unit_greeks(leg, inputs)
    position = _position_greeks(per_unit, core.action, core.quantity) if per_unit is not None else None
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
        ColumnId.IV: _iv_cell(leg),
        ColumnId.DELTA: _greek_cell(None if position is None else position.delta,
                                     None if vendor is None else vendor.delta,
                                     None if per_unit is None else per_unit.delta, greek_reason),
        ColumnId.GAMMA: _greek_cell(None if position is None else position.gamma,
                                     None if vendor is None else vendor.gamma,
                                     None if per_unit is None else per_unit.gamma, greek_reason),
        ColumnId.THETA: _greek_cell(None if position is None else position.theta,
                                     None if vendor is None else vendor.theta,
                                     None if per_unit is None else per_unit.theta, greek_reason),
        ColumnId.VEGA: _greek_cell(None if position is None else position.vega,
                                    None if vendor is None else vendor.vega,
                                    None if per_unit is None else per_unit.vega, greek_reason),
    }
    for level in level_columns:
        if scenario is None or not scenario.available or scenario.leg_rows is None:
            cells[level] = _money(None, "no scenario view is available")
        else:
            cells[level] = _money(scenario.leg_rows[leg_position][level_columns.index(level)])
    cells[ColumnId.LOWER_BE] = _text(None)
    cells[ColumnId.UPPER_BE] = _text(None)
    cells[ColumnId.STATUS] = _text(status, "no status was given for this leg")
    return Row(str(index), cells)


def _total_row(inputs: StrategyInput, level_set: LevelSet | None, level_columns: Sequence[Decimal],
               scenario: ScenarioValues | None, health: "StrategyHealth | None") -> Row:
    legs = inputs.legs
    entry_value = sum((leg.premium * leg.quantity for leg in legs), Decimal(0))
    have_all_ltp = all(leg.ltp is not None for leg in legs)
    if have_all_ltp:
        current_value = sum((leg.ltp * leg.quantity for leg in legs), Decimal(0))
        unrealized = sum((live_pnl(leg.leg) for leg in legs), Decimal(0))
    else:
        current_value = None
        unrealized = None

    # TOTAL row P&L % is always "—" (fix round): the owner-reviewed source leaves it blank; gross entry value
    # misleads for a net-credit strategy. Open owner question — never computed here.
    pnl_percent_reason = "not shown for the strategy total (open owner question: gross entry value misleads " \
                          "for a net-credit strategy)"

    greek_values: dict[str, Decimal] = {"delta": Decimal(0), "gamma": Decimal(0), "theta": Decimal(0),
                                         "vega": Decimal(0)}
    every_leg_has_greeks = True
    for leg in legs:
        per_unit, _reason = _leg_per_unit_greeks(leg, inputs)
        if per_unit is None:
            every_leg_has_greeks = False
            break
        position = _position_greeks(per_unit, leg.action, leg.quantity)
        for name in greek_values:
            greek_values[name] += getattr(position, name)
    if not every_leg_has_greeks:
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
        ColumnId.PNL_PERCENT: _percent_cell(None, pnl_percent_reason),
        ColumnId.IV: _text(None),
        ColumnId.DELTA: _greek_cell(greek_values["delta"], None, None, greek_reason),
        ColumnId.GAMMA: _greek_cell(greek_values["gamma"], None, None, greek_reason),
        ColumnId.THETA: _greek_cell(greek_values["theta"], None, None, greek_reason),
        ColumnId.VEGA: _greek_cell(greek_values["vega"], None, None, greek_reason),
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
    cells[ColumnId.STATUS] = _text(health.value if health is not None else None, "no strategy health was given")
    return Row(TOTAL_ROW_ID, cells)


def build_table(
    inputs: StrategyInput,
    *,
    level_set: LevelSet | None = None,
    scenario: ScenarioValues | None = None,
    leg_statuses: Sequence[str | None] | None = None,
    strategy_health: StrategyHealth | None = None,
) -> Table:
    """Build the one strategy table (AC-1): a row per leg, a TOTAL row, columns in the AC-2 locked order.

    ``level_set``/``scenario`` are optional so a table can be built without a scenario view (its level columns are
    then empty); when given, they must come from :mod:`ofo.scenario` (``build_level_set``/``scenario_values``) —
    this function never recomputes a scenario level or a P&L number itself.

    ``leg_statuses`` (parallel to ``inputs.legs``, one text or ``None`` per leg) and ``strategy_health`` are the
    Status column's caller-supplied values (fix round: Status is not computed here — see the module docstring).
    """
    if not isinstance(inputs, StrategyInput):
        raise ValueError(f"inputs must be a StrategyInput, got {inputs!r}")
    if level_set is not None and not isinstance(level_set, LevelSet):
        raise ValueError(f"level_set must be a LevelSet, got {level_set!r}")
    if scenario is not None and not isinstance(scenario, ScenarioValues):
        raise ValueError(f"scenario must be a ScenarioValues, got {scenario!r}")
    if (level_set is None) != (scenario is None):
        raise ValueError("level_set and scenario must be given together, or not at all")
    if leg_statuses is not None and len(leg_statuses) != len(inputs.legs):
        raise ValueError(
            f"leg_statuses must have one entry per leg ({len(inputs.legs)}), got {len(leg_statuses)}"
        )
    if strategy_health is not None and not isinstance(strategy_health, StrategyHealth):
        raise ValueError(f"strategy_health must be a StrategyHealth, got {strategy_health!r}")

    level_columns: tuple[Decimal, ...] = level_set.levels if level_set is not None else ()
    statuses = list(leg_statuses) if leg_statuses is not None else [None] * len(inputs.legs)

    columns = [ColumnSpec(cid, HEADER_LABELS[cid], _leading_kind(cid)) for cid in LEADING_COLUMNS]
    columns += [ColumnSpec(level, format_points(level), CellKind.MONEY, is_scenario_level=True)
                for level in level_columns]
    columns += [ColumnSpec(cid, HEADER_LABELS[cid], _trailing_kind(cid)) for cid in TRAILING_COLUMNS]

    rows = [
        _leg_row(i, leg, inputs, level_columns, scenario, i - 1, statuses[i - 1])
        for i, leg in enumerate(inputs.legs, start=1)
    ]
    rows.append(_total_row(inputs, level_set, level_columns, scenario, strategy_health))
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
