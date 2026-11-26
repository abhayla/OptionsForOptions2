"""ADR-330 (12): the index-level condition ("the index is above / below a level"). Pure: the LIVE index price is passed
in (None when it is not live), never read. Met / NotMet / NotComputable; equality is Met both ways (stops.crossed's
rule, kept exactly). Decimal only (ADR-008)."""
from __future__ import annotations

from decimal import Decimal

from ofo.checks.outcome import Outcome, at_or_beyond


def index_level(level: Decimal | None, direction: str, index_price: Decimal | None) -> Outcome:
    return at_or_beyond(level, direction, index_price)
