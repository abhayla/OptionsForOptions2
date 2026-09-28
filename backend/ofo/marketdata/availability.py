"""Per-strategy monitoring availability (REQ-049 AC-6, ADR-015 Q184, domain-model §5).

Availability is tracked per strategy, never app-wide: a strategy whose quotes are all healthy stays ACTIVE while
another strategy on stale or unavailable quotes goes PAUSED. Availability is a separate axis from strategy health
(ADR-010's four colours mean health only, never this); the four health colours are not reused here.

Only a quote whose health is ``available`` is usable, matching what :mod:`ofo.rules.inputs` (``Snapshot.usable``)
already treats as live: ``delayed``, ``stale``, ``unhealthy`` and ``unavailable`` all pause monitoring, because
none of them proves a current value.
"""
from __future__ import annotations

from enum import Enum
from typing import Mapping

from ofo.marketdata.quote import NormalizedQuote
from ofo.rules.inputs import DataHealth


class MonitoringStatus(Enum):
    """Availability of live monitoring for one strategy; never the ADR-010 health colours."""

    ACTIVE = "active"
    PAUSED = "paused"


def strategy_monitoring_status(needed_quotes: Mapping[str, NormalizedQuote | None]) -> MonitoringStatus:
    """A strategy is ACTIVE only while every quote it needs is present and ``available`` (AC-6).

    ``needed_quotes`` maps a role/instrument key (e.g. the instrument id) to the quote currently held for it, or
    ``None`` when nothing has arrived yet. A strategy that needs no quotes at all is not a valid input here — a
    strategy always needs at least its underlying.
    """
    quotes = dict(needed_quotes)
    if not quotes:
        raise ValueError("a strategy needs at least one quote to have a monitoring status")
    for key, quote in quotes.items():
        if quote is not None and not isinstance(quote, NormalizedQuote):
            raise ValueError(f"needed_quotes[{key!r}] must be a NormalizedQuote or None, got {quote!r}")
        if quote is None or quote.health is not DataHealth.AVAILABLE:
            return MonitoringStatus.PAUSED
    return MonitoringStatus.ACTIVE
