"""The locked column order and per-UX-level visibility for the single strategy table (REQ-035 AC-2, AC-7).

Column order (AC-2, locked, never reordered by UX level): Leg, Action, Instrument, Expiry, Strike, Quantity,
Entry Price, LTP, Entry Value, Current Value, Unrealized P&L, P&L %, IV, Delta, Gamma, Theta, Vega, then the
market-level scenario columns (one per :class:`ofo.scenario.levels.LevelColumn`, in the level set's own order),
then Lower Breakeven, Upper Breakeven, Status.

UX-level visibility (AC-7, T1 #84, Q31 T1 #78-#79): the column ORDER never changes; what a level shows is a
filter over that fixed order.

- **Guided**: hides IV and every Greek column by default (Q31, T1 #78-#79) and hides P&L % and the Lower/Upper BE
  summary columns (added at Standard, below) — Guided keeps Leg/Action/Instrument/Expiry/Strike/Quantity, the
  live money fields, the scenario level columns and Status.
- **Standard**: adds % return (P&L %) and the Lower/Upper BE summary columns.
- **Advanced**: adds Greeks and IV assumptions (IV, Delta, Gamma, Theta, Vega).

The scenario level columns and Status are visible at every level (REQ-035 AC-2/AC-3: the table's core content).
"""
from __future__ import annotations

from enum import Enum


class ColumnId(Enum):
    """The fixed (non-scenario) columns, in their locked order."""

    LEG = "leg"
    ACTION = "action"
    INSTRUMENT = "instrument"
    EXPIRY = "expiry"
    STRIKE = "strike"
    QUANTITY = "quantity"
    ENTRY_PRICE = "entry_price"
    LTP = "ltp"
    ENTRY_VALUE = "entry_value"
    CURRENT_VALUE = "current_value"
    UNREALIZED_PNL = "unrealized_pnl"
    PNL_PERCENT = "pnl_percent"
    IV = "iv"
    DELTA = "delta"
    GAMMA = "gamma"
    THETA = "theta"
    VEGA = "vega"
    LOWER_BE = "lower_be"
    UPPER_BE = "upper_be"
    STATUS = "status"


#: Columns before the scenario level columns, in AC-2 order.
LEADING_COLUMNS: tuple[ColumnId, ...] = (
    ColumnId.LEG,
    ColumnId.ACTION,
    ColumnId.INSTRUMENT,
    ColumnId.EXPIRY,
    ColumnId.STRIKE,
    ColumnId.QUANTITY,
    ColumnId.ENTRY_PRICE,
    ColumnId.LTP,
    ColumnId.ENTRY_VALUE,
    ColumnId.CURRENT_VALUE,
    ColumnId.UNREALIZED_PNL,
    ColumnId.PNL_PERCENT,
    ColumnId.IV,
    ColumnId.DELTA,
    ColumnId.GAMMA,
    ColumnId.THETA,
    ColumnId.VEGA,
)

#: Columns after the scenario level columns, in AC-2 order.
TRAILING_COLUMNS: tuple[ColumnId, ...] = (
    ColumnId.LOWER_BE,
    ColumnId.UPPER_BE,
    ColumnId.STATUS,
)

HEADER_LABELS: dict[ColumnId, str] = {
    ColumnId.LEG: "Leg",
    ColumnId.ACTION: "Action",
    ColumnId.INSTRUMENT: "Instrument",
    ColumnId.EXPIRY: "Expiry",
    ColumnId.STRIKE: "Strike",
    ColumnId.QUANTITY: "Quantity",
    ColumnId.ENTRY_PRICE: "Entry Price",
    ColumnId.LTP: "LTP",
    ColumnId.ENTRY_VALUE: "Entry Value",
    ColumnId.CURRENT_VALUE: "Current Value",
    ColumnId.UNREALIZED_PNL: "Unrealized P&L",
    ColumnId.PNL_PERCENT: "P&L %",
    ColumnId.IV: "IV",
    ColumnId.DELTA: "Delta",
    ColumnId.GAMMA: "Gamma",
    ColumnId.THETA: "Theta",
    ColumnId.VEGA: "Vega",
    ColumnId.LOWER_BE: "Lower Breakeven",
    ColumnId.UPPER_BE: "Upper Breakeven",
    ColumnId.STATUS: "Status",
}


class UXLevel(Enum):
    GUIDED = "guided"
    STANDARD = "standard"
    ADVANCED = "advanced"


_ALWAYS_VISIBLE: frozenset[ColumnId] = frozenset(
    {
        ColumnId.LEG,
        ColumnId.ACTION,
        ColumnId.INSTRUMENT,
        ColumnId.EXPIRY,
        ColumnId.STRIKE,
        ColumnId.QUANTITY,
        ColumnId.ENTRY_PRICE,
        ColumnId.LTP,
        ColumnId.ENTRY_VALUE,
        ColumnId.CURRENT_VALUE,
        ColumnId.UNREALIZED_PNL,
        ColumnId.STATUS,
    }
)

_STANDARD_ADDS: frozenset[ColumnId] = frozenset({ColumnId.PNL_PERCENT, ColumnId.LOWER_BE, ColumnId.UPPER_BE})

_ADVANCED_ADDS: frozenset[ColumnId] = frozenset(
    {ColumnId.IV, ColumnId.DELTA, ColumnId.GAMMA, ColumnId.THETA, ColumnId.VEGA}
)

#: Which FIXED columns each UX level shows. Scenario level columns are visible at every level (not in this map).
VISIBLE_FIXED_COLUMNS: dict[UXLevel, frozenset[ColumnId]] = {
    UXLevel.GUIDED: _ALWAYS_VISIBLE,
    UXLevel.STANDARD: _ALWAYS_VISIBLE | _STANDARD_ADDS,
    UXLevel.ADVANCED: _ALWAYS_VISIBLE | _STANDARD_ADDS | _ADVANCED_ADDS,
}


def is_visible(column_id: ColumnId, level: UXLevel) -> bool:
    """Whether a fixed column id is visible at ``level``. Scenario level columns are always visible."""
    if not isinstance(level, UXLevel):
        raise ValueError(f"level must be a UXLevel, got {level!r}")
    return column_id in VISIBLE_FIXED_COLUMNS[level]
