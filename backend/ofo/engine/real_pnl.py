"""Lane S (REQ-044 AC-3; ADR-008, ADR-016, ADR-018): Zerodha's per-contract P&L, checked by the engine.

Zerodha's positions row carries its own ``pnl``. Its formula is ``pnl = sell_value - buy_value + quantity x last_price
x multiplier``; the engine re-derives that figure, exact ``Decimal``, from the SAME row's fields and states the figure
only when the derived and the reported values agree to the paisa (both quantized to 0.01, ROUND_HALF_EVEN). Never
defaulted, never rounded toward agreement: a missing, null, boolean, float or non-decimal field is "not_available";
two figures that differ are "mismatch" and carry no value. Several Zerodha rows of one contract (NRML + MIS) are summed
(reported and derived) before the check. Pure: no float, no I/O.
"""
from __future__ import annotations

import re
from collections.abc import Hashable, Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from typing import Final

from ofo.money import PAISE

FIELDS: Final = ("pnl", "buy_value", "sell_value", "quantity", "last_price", "multiplier")
_LITERAL: Final = re.compile(r"-?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)")

STATED: Final = "stated"
NOT_AVAILABLE: Final = "not_available"
MISMATCH: Final = "mismatch"


@dataclass(frozen=True)
class BrokerPnl:
    """``value`` is set only in state "stated". ``reported`` / ``derived`` are the two paisa figures when both could be
    read (also on a mismatch, so the page can name them); None otherwise."""

    state: str
    value: Decimal | None
    reported: Decimal | None
    derived: Decimal | None


_NOT_AVAILABLE: Final = BrokerPnl(NOT_AVAILABLE, None, None, None)


def _exact(raw: object) -> Decimal | None:
    """One Zerodha figure as an exact finite Decimal, or None (absent, bool, float, not a plain decimal)."""
    if isinstance(raw, bool) or raw is None:
        return None
    if isinstance(raw, Decimal):
        return raw if raw.is_finite() else None
    if isinstance(raw, int):
        return Decimal(raw)
    if isinstance(raw, str) and _LITERAL.fullmatch(raw):
        try:
            return Decimal(raw)
        except InvalidOperation:
            return None
    return None


def _paisa(value: Decimal) -> Decimal:
    return value.quantize(PAISE, rounding=ROUND_HALF_EVEN) + 0  # + 0: a tiny negative is 0.00, never -0.00


def broker_contract_pnl(rows: Mapping[str, object] | Sequence[Mapping[str, object]]) -> BrokerPnl:
    """The checked P&L of ONE contract from its Zerodha row(s) (a mapping, or the sequence of rows of that contract)."""
    group = [rows] if isinstance(rows, Mapping) else list(rows)
    if not group:
        return _NOT_AVAILABLE
    reported = Decimal(0)
    derived = Decimal(0)
    for row in group:
        if not isinstance(row, Mapping):
            return _NOT_AVAILABLE
        got = {name: _exact(row.get(name)) for name in FIELDS}
        if any(v is None for v in got.values()):
            return _NOT_AVAILABLE  # never defaulted to 0
        reported += got["pnl"]  # type: ignore[operator]
        derived += (got["sell_value"] - got["buy_value"]  # type: ignore[operator]
                    + got["quantity"] * got["last_price"] * got["multiplier"])  # type: ignore[operator]
    reported_paisa, derived_paisa = _paisa(reported), _paisa(derived)
    if reported_paisa != derived_paisa:
        return BrokerPnl(MISMATCH, None, reported_paisa, derived_paisa)
    return BrokerPnl(STATED, derived_paisa, reported_paisa, derived_paisa)


def count_without_figure(figures: Sequence[BrokerPnl]) -> int:
    """How many contracts have no stated figure (the total's "N of M contracts have no figure")."""
    return sum(1 for f in figures if f.state != STATED)


def contracts_without_figure(rows: Sequence[tuple[Hashable, BrokerPnl]]) -> tuple[int, int]:
    """(contracts with no stated figure, distinct contracts) over (contract key, figure) rows: a contract held by two
    strategies is ONE contract, and has no figure if any of its rows has none."""
    states: dict[Hashable, bool] = {}
    for key, figure in rows:
        states[key] = states.get(key, True) and figure.state == STATED
    return sum(1 for ok in states.values() if not ok), len(states)


def broker_total(figures: Sequence[BrokerPnl]) -> Decimal | None:
    """The exact sum of the rows' values, only when there is at least one row and EVERY row is stated; else None."""
    if not figures or any(f.state != STATED or f.value is None for f in figures):
        return None
    return _paisa(sum((f.value for f in figures), Decimal(0)))  # type: ignore[misc]
