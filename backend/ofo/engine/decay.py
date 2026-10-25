"""Time-decay estimate over calendar days (REQ-085 AC-3), in the engine because it is a money figure (ADR-008).

The position's theta total is per CALENDAR day (``black_scholes`` convention), so the change over ``days`` days is
``theta_total * days``, rounded half-even to the whole rupee. Exact ``Decimal`` only; a float or a bool is refused.
"""
from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal

_RUPEE = Decimal(1)


def decay_estimate(theta_total: Decimal, days: int) -> Decimal:
    """The estimated change in the position's value over ``days`` calendar days (negative: the position loses)."""
    if type(theta_total) is not Decimal or not theta_total.is_finite():
        raise ValueError(f"theta_total must be a finite Decimal, got {theta_total!r}")
    if type(days) is not int or days < 0:
        raise ValueError(f"days must be a whole number >= 0, got {days!r}")
    return (theta_total * days).quantize(_RUPEE, rounding=ROUND_HALF_EVEN)
