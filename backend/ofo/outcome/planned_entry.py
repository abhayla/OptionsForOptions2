"""The planned-entry price rule of a draft leg (W-068; ADR-068 item 1, ADR-020 Q185, ADR-008).

ADR-068 (1): "A draft leg's entry price is its planned entry: the leg's LTP captured when the leg is added (or the mid of
bid and ask when no LTP exists)". ADR-020 Q185 "no fake prices": a quote that is not live gives NO price - never a
default, a last-known value or zero.

Rule: only a quote whose health is AVAILABLE counts as live. A positive LTP wins. With no LTP at all, the mid of a
positive bid and ask is used. Both are rounded half-up to 0.01 (the precision the outcome route takes). Anything else
gives ``None``. Standard library only; the route only calls this.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from ofo.marketdata.quote import NormalizedQuote
from ofo.rules.inputs import DataHealth

_CENT = Decimal("0.01")


@dataclass(frozen=True)
class PlannedEntry:
    price: Decimal
    source: Literal["ltp", "mid"]


def planned_entry_of(quote: NormalizedQuote | None) -> PlannedEntry | None:
    """The planned entry of one live quote, or None when there is no live price."""
    if quote is None or quote.health is not DataHealth.AVAILABLE:
        return None
    if quote.ltp is not None:
        if quote.ltp > 0:
            return PlannedEntry(quote.ltp.quantize(_CENT, rounding=ROUND_HALF_UP), "ltp")
        return None
    if quote.bid is not None and quote.ask is not None and quote.bid > 0 and quote.ask > 0:
        return PlannedEntry(((quote.bid + quote.ask) / 2).quantize(_CENT, rounding=ROUND_HALF_UP), "mid")
    return None
