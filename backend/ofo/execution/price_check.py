"""Circuit-band check for a leg's limit price (W-078, ADR-080).

ADR-080: "a price outside the day's circuit band blocks that leg with the reason, never a silent clamp". The band is
the quote's ``lower_circuit_limit`` / ``upper_circuit_limit`` (inclusive: a price exactly on the band passes).
Returns None when the price is inside, else the four-part catalogue message. Never changes the price.
"""
from __future__ import annotations

from decimal import Decimal

from ofo.errors import UserFacingError, render
from ofo.errors.gate_slots import LegValue


def _exact(value: object, name: str) -> Decimal:
    # Kite prints a whole-number price or band as a JSON integer: an int is exact and accepted; a float is refused.
    if isinstance(value, int) and not isinstance(value, bool):
        return Decimal(value)
    if isinstance(value, bool) or not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{name} must be a finite Decimal or int (floats are refused), got {value!r}")
    return value


def circuit_block(limit: Decimal, lower: Decimal, upper: Decimal, leg: LegValue) -> UserFacingError | None:
    limit, lower, upper = _exact(limit, "limit"), _exact(lower, "lower"), _exact(upper, "upper")
    if lower > upper:
        raise ValueError(f"lower circuit {lower} is above upper circuit {upper}")
    if lower <= limit <= upper:
        return None
    return render("gate_price_outside_circuit", leg=leg, limit=limit, lower=lower, upper=upper)
