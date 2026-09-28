"""Current eligibility: what Zerodha permits right now, for one contract.

REQ-053 AC-1/AC-2: Zerodha's response is the final authority on eligibility; this structure is
kept separate from the contract catalogue (`ofo.instruments.catalogue.Catalogue`) — the catalogue
never merges eligibility into a contract record, and this registry never deletes a catalogue entry.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class EligibilityStatus:
    """A point-in-time eligibility read from Zerodha for one instrument."""

    instrument_token: int
    tradable: bool
    checked_at: datetime
    reason: Optional[str] = None


class EligibilityRegistry:
    """Holds the latest known `EligibilityStatus` per `instrument_token`.

    Deliberately has no reference to `Catalogue` and no method that writes into one — eligibility
    and the contract catalogue are separate structures (AC-2).
    """

    def __init__(self) -> None:
        self._status: dict[int, EligibilityStatus] = {}

    def record(self, status: EligibilityStatus) -> None:
        self._status[status.instrument_token] = status

    def get(self, instrument_token: int) -> Optional[EligibilityStatus]:
        return self._status.get(instrument_token)

    def is_tradable(self, instrument_token: int) -> bool:
        """Fail closed: an instrument with no recorded eligibility check is not tradable."""
        status = self._status.get(instrument_token)
        return status is not None and status.tradable
