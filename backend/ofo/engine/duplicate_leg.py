"""The one duplicate-leg decision, shared by the real-order gate (ofo.execution.safety) and Add to Paper.

Lives here, outside ofo.execution, so paper code can use it without importing an order module (order-path closure scan).
"""
from __future__ import annotations

import datetime
from collections.abc import Sequence
from decimal import Decimal

from ofo.engine.legs import Instrument, Leg
from ofo.errors import LegValue, UserFacingError, render

ContractKey = tuple[datetime.date, str, Decimal | None]


def contract_key(expiry: datetime.date | None, instrument_type: str, strike: Decimal | None) -> ContractKey:
    return (expiry, instrument_type, None if instrument_type == Instrument.FUT.value else strike)


def duplicate_leg_message(number: int, value: LegValue, other: int) -> UserFacingError:
    """The gate_duplicate_leg sentence for leg `number` repeating leg `other`."""
    return render("gate_duplicate_leg", leg=value, other=other)


def paper_duplicate_leg(legs: Sequence[Leg], underlying: str) -> UserFacingError | None:
    """Add to Paper (ADR-319 (3), REQ-030 AC-11): the first leg that repeats an earlier leg's contract AND action. A buy
    and a sell of one contract stay two legs here; the live gate (which ignores the action) is unchanged."""
    seen: dict[tuple[ContractKey, object], int] = {}
    for number, leg in enumerate(legs, start=1):
        key = (contract_key(leg.expiry, leg.instrument.value, leg.strike), leg.action)
        if key in seen:
            return duplicate_leg_message(number, LegValue(number, leg, underlying), seen[key])
        seen[key] = number
    return None
