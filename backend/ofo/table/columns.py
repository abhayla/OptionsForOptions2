"""The locked column order for the single strategy table (REQ-035 AC-2, AC-7).

Column order (AC-2, locked): Leg, Action, Instrument, Expiry, Strike, Quantity, Entry Price, LTP, Entry Value,
Current Value, Unrealized P&L, P&L %, IV, Delta, Gamma, Theta, Vega, then the market-level scenario columns (one per
:class:`ofo.scenario.levels.LevelColumn`, in the level set's own order), then Lower Breakeven, Upper Breakeven, Status.

One column set for everyone (ADR-168 (4), (5)): every column is shown to every user; there is no level switch and no
per-level filter.
"""
from __future__ import annotations

from enum import Enum

from ofo.errors.explanations import render_explanation


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

#: Each heading is a catalogue render (W-066): template `table_column_label`, words in `COLUMN_LABEL_TEXT`.
HEADER_LABELS: dict[ColumnId, str] = {cid: render_explanation("table_column_label", column=cid) for cid in ColumnId}
