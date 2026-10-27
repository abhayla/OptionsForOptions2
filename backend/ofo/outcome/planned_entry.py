"""The planned-entry price rule of a draft leg (W-068; ADR-068 item 1, ADR-020 Q185, ADR-008).

ADR-068 (1): "A draft leg's entry price is its planned entry: the leg's LTP captured when the leg is added (or the mid of
bid and ask when no LTP exists)". ADR-020 Q185 "no fake prices": a quote that is not live gives NO price - never a
default, a last-known value or zero.

Rule: only a quote whose health is AVAILABLE counts as live; outside market hours also the last price held from the
session that closed (ADR-200 (1), (4); ``planning_price_usable``). A positive LTP wins. With no LTP at all, the mid of a
positive bid and ask is used. Both are rounded half-up to 0.01 (the precision the outcome route takes). Anything else
gives ``None``. Standard library only; the route only calls this.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from ofo.marketdata.quote import NormalizedQuote, is_live_price
from ofo.rules.inputs import DataHealth
from ofo.money import PAISE as _CENT



@dataclass(frozen=True)
class PlannedEntry:
    price: Decimal
    source: Literal["ltp", "mid"]


def planning_price_usable(quote: NormalizedQuote | None, *, market_closed: bool) -> bool:
    """May ``quote``'s price be used to PLAN (capture an entry, compute the outcome)? Never an order rule: every order,
    basket and margin-for-order path keeps requiring a live (AVAILABLE) quote (ADR-119, ADR-200 (3)).

    In market hours: only an AVAILABLE quote (a STALE one is an old price, ADR-015). Outside market hours (ADR-119
    calendar, ``feed_health.market_closed_for``): also the price the feed holds from the session that closed (ADR-200
    (1), (4)), which the feed health marks STALE whatever frames arrive; it is used only when the quote itself is sound
    (no validation error, no declared delay) and its time is readable (fail closed, standing item c). An UNAVAILABLE
    (session ended) or UNHEALTHY quote never counts."""
    if quote is None:
        return False
    if quote.health is DataHealth.AVAILABLE:
        return True
    return (market_closed and quote.health is DataHealth.STALE and not quote.validation_errors
            and quote.source.declared_delay_seconds == 0
            and isinstance(quote.timestamp, datetime.datetime) and quote.timestamp.utcoffset() is not None)


def planned_entry_of(quote: NormalizedQuote | None, *, market_closed: bool = False) -> PlannedEntry | None:
    """The planned entry of one quote, or None when there is no usable price (``planning_price_usable``): a live
    quote, or outside market hours the last price held from the session that closed (ADR-200 (1))."""
    if quote is None or not planning_price_usable(quote, market_closed=market_closed):
        return None
    if quote.ltp is not None:
        if is_live_price(quote.ltp):
            return PlannedEntry(quote.ltp.quantize(_CENT, rounding=ROUND_HALF_UP), "ltp")
        return None
    if is_live_price(quote.bid) and is_live_price(quote.ask):
        return PlannedEntry(((quote.bid + quote.ask) / 2).quantize(_CENT, rounding=ROUND_HALF_UP), "mid")
    return None
