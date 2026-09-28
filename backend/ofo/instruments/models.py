"""Contract: one row of Zerodha's public instrument list, parsed into typed fields.

Money and strike/tick values are `decimal.Decimal`; quantities are `int`. Never float.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

# Instrument types that carry a strike (options).
OPTION_TYPES = frozenset({"CE", "PE"})
FUTURE_TYPE = "FUT"


@dataclass(frozen=True)
class Contract:
    """A single instrument row: identity + contract terms. Immutable by identity.

    `instrument_token` is Zerodha's stable numeric identity for this instrument.
    """

    instrument_token: int
    exchange_token: int
    tradingsymbol: str
    name: str
    expiry: Optional[date]
    strike: Decimal
    tick_size: Decimal
    lot_size: int
    instrument_type: str
    segment: str
    exchange: str

    def is_option(self) -> bool:
        return self.instrument_type in OPTION_TYPES

    def is_future(self) -> bool:
        return self.instrument_type == FUTURE_TYPE
