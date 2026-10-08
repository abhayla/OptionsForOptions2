"""The scenario's spot reading (REQ-072 AC-2/AC-3; REQ-049 AC-4).

Every scenario is built on a :class:`~ofo.engine.model.ModelInputs`, the one gate (:func:`ofo.engine.model.model_inputs`):

- AVAILABLE: computed, no data label.
- STALE / DELAYED: computed, and every output carries the label ("stale since HH:MM IST" / "delayed, as of HH:MM
  IST") - shown as such, never presented as live.
- UNHEALTHY / UNAVAILABLE, or no reading at all: refused (:class:`SpotRefused`).
"""
from __future__ import annotations

from ofo.engine.inputs import SpotReading
from ofo.engine.model import IST, SpotRefused, data_label
from ofo.marketdata.quote import NormalizedQuote

__all__ = ["IST", "SpotRefused", "data_label", "spot_reading"]


def spot_reading(quote: NormalizedQuote | None) -> SpotReading:
    """The reading of a live index quote (its last price, exchange time and health); refuses a missing quote."""
    if quote is None or quote.ltp is None:
        raise SpotRefused("the index value is missing; the scenario is refused")
    return SpotReading(level=quote.ltp, at=quote.timestamp, health=quote.health)
