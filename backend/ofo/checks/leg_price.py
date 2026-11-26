"""ADR-330 (12): the leg-price condition (a leg's stop level). Pure: the LIVE leg price is passed in (None when not
live), never read. Met / NotMet / NotComputable; equality is Met both ways (stops.crossed's rule). Decimal only."""
from __future__ import annotations

from decimal import Decimal

from ofo.checks.outcome import Outcome, at_or_beyond


def leg_price(level: Decimal | None, direction: str, price: Decimal | None) -> Outcome:
    return at_or_beyond(level, direction, price)
