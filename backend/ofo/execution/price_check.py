"""Circuit-band check for a leg's limit price (W-078, ADR-080).

ADR-080: "a price outside the day's circuit band blocks that leg with the reason, never a silent clamp". The band is
the quote's ``lower_circuit_limit`` / ``upper_circuit_limit`` (inclusive: a price exactly on the band passes).
Returns None when the price is inside, else the four-part catalogue message. Never changes the price.
"""
from __future__ import annotations

from decimal import Decimal

from ofo.errors import UserFacingError, render
from ofo.errors.gate_slots import LegValue


def circuit_block(limit: Decimal, lower: Decimal, upper: Decimal, leg: LegValue) -> UserFacingError | None:
    for name, value in (("limit", limit), ("lower", lower), ("upper", upper)):
        if isinstance(value, bool) or not isinstance(value, Decimal) or not value.is_finite():
            raise ValueError(f"{name} must be a finite Decimal (floats are refused), got {value!r}")
    if lower > upper:
        raise ValueError(f"lower circuit {lower} is above upper circuit {upper}")
    if lower <= limit <= upper:
        return None
    return render("gate_price_outside_circuit", leg=leg, limit=limit, lower=lower, upper=upper)
