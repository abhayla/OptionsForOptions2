"""The one home of the two-decimal step (ADR-008: money is exact `Decimal`, never float).

Standard library only. `tests/test_one_home_constants.py` fails when `Decimal("0.01")` is written anywhere else
under `backend/`.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Final

#: One hundredth: the two-decimal step of quantities that are not rupees (index points, strikes, percentages) and the
#: 1% fraction cap of charge rates.
HUNDREDTH: Final = Decimal("0.01")
#: One paisa: the step of every rupee amount and premium.
PAISE: Final = HUNDREDTH


def paise_to_rupees(paise: int) -> Decimal:
    """A whole number of paise (an exchange file's price column, e.g. NSE BasePric 2311920) as exact rupees (23119.20).
    Only an int is accepted (never a bool, float or str)."""
    if type(paise) is not int:
        raise TypeError(f"paise must be an int, got {type(paise).__name__}")
    return Decimal(paise) * PAISE


def zerodha_paise(value: Decimal | int) -> Decimal:
    """One Kite money figure rounded HALF-UP to the paisa (ADR-099, ADR-101), where the figure is parsed.

    Kite's replies carry float noise (68498.85000000001); read with `parse_float=Decimal` the tail is kept exactly, and
    a gate that compares it unrounded shows a shortfall that does not exist. Only a finite `Decimal` or `int` is
    accepted: a float or a string raises `TypeError`, NaN / Infinity or a figure too large to round raise `ValueError`.
    A tiny negative figure never comes back as -0.00 (adding zero gives +0.00)."""
    if type(value) is not Decimal and type(value) is not int:
        raise TypeError(f"a Kite money figure must be Decimal or int, got {type(value).__name__}")
    amount = Decimal(value)
    if not amount.is_finite():
        raise ValueError("a Kite money figure must be finite")
    try:
        return amount.quantize(PAISE, rounding=ROUND_HALF_UP) + 0
    except InvalidOperation:  # too many digits to hold at the paisa (1e26 and above)
        raise ValueError("a Kite money figure is too large to round to the paisa") from None
