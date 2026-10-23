"""A stored exchange freeze limit and the largest whole-lot order below it (ADR-092, ADR-081, findings F-36).

Freeze limits are exchange instrument data, so the read-only lookup lives with the instruments: the order review
(``ofo.execution.freeze``) and the leg-edit route (REQ-076 AC-5) both read it from here, and the leg-edit route reaches
no order module. F-36: ``MaxTradQty`` is the limit and the largest allowed order is ``MaxTradQty - 1``, so a leg is
allowed exactly when its units are BELOW the stored limit.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class StoredFreeze:
    """A freeze limit in units, the contract's lot size, and the date of the exchange file that showed it."""

    limit: int
    lot: int
    file_date: date

    def __post_init__(self) -> None:
        if isinstance(self.limit, bool) or not isinstance(self.limit, int) or self.limit <= 0:
            raise ValueError(f"limit must be a positive integer, got {self.limit!r}")
        if isinstance(self.lot, bool) or not isinstance(self.lot, int) or self.lot <= 0:
            raise ValueError(f"lot must be a positive integer, got {self.lot!r}")


def largest_allowed_units(stored: StoredFreeze) -> int:
    """The largest whole-lot order below the limit (NIFTY: 3,511 and lot 65 -> 3,510 = 54 lots)."""
    return (stored.limit - 1) // stored.lot * stored.lot


__all__ = ["StoredFreeze", "largest_allowed_units"]
