"""The scenario's spot gate (REQ-072 AC-2/AC-3; REQ-049 AC-4).

Every scenario is built on a ``SpotReading`` (level, time, health), never on a bare level:

- AVAILABLE: computed, no data label.
- STALE / DELAYED: computed, and every output carries the label ("stale since HH:MM IST" / "delayed, as of HH:MM
  IST") - shown as such, never presented as live.
- UNHEALTHY / UNAVAILABLE, or no reading at all: refused (:class:`SpotRefused`).
"""
from __future__ import annotations

import datetime

from ofo.engine.inputs import SpotReading, StrategyInput
from ofo.marketdata.quote import NormalizedQuote
from ofo.rules.inputs import DataHealth

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30), "IST")
_REFUSED = (DataHealth.UNHEALTHY, DataHealth.UNAVAILABLE)


class SpotRefused(ValueError):
    """The index value is missing or unusable; the calculation is refused, never computed silently."""


def data_label(reading: SpotReading) -> str | None:
    hhmm = reading.at.astimezone(IST).strftime("%H:%M")
    if reading.health is DataHealth.STALE:
        return f"stale since {hhmm} IST"
    if reading.health is DataHealth.DELAYED:
        return f"delayed, as of {hhmm} IST"
    return None


def check_spot(inputs: StrategyInput) -> tuple[SpotReading, str | None]:
    """(reading, label) for a usable spot; :class:`SpotRefused` for a missing or unavailable one."""
    reading = inputs.spot
    if reading is None:
        raise SpotRefused("no spot reading: a scenario is never built on a bare level (REQ-072 AC-2)")
    if reading.health in _REFUSED:
        raise SpotRefused(f"the {inputs.underlying} spot is {reading.health.value}; the scenario is refused")
    return reading, data_label(reading)


def spot_reading(quote: NormalizedQuote | None) -> SpotReading:
    """The reading of a live index quote (its last price, exchange time and health); refuses a missing quote."""
    if quote is None or quote.ltp is None:
        raise SpotRefused("the index value is missing; the scenario is refused")
    return SpotReading(level=quote.ltp, at=quote.timestamp, health=quote.health)
