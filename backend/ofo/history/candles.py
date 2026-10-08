"""Kite's own one-minute candles as ``MinuteBar``s (W-062, ADR-067, ADR-066: internal use only). Standard library only.

The body of ``/instruments/historical/<token>/minute?oi=1`` is parsed from text with ``parse_float=Decimal`` so no
price ever passes through a float (F-33). A candle row is ``[time, open, high, low, close, volume, oi]``. An index row
carries volume 0 and OI 0: those become ``None`` here (an index has neither).
"""
from __future__ import annotations

import datetime
import json
from decimal import Decimal
from typing import Protocol

from ofo.history.bars import BarSource, MinuteBar, minute_of


class CandleError(ValueError):
    """A body that is not a Kite success body of candle rows: refused, the day stays provisional."""


class MinuteCandleSource(Protocol):
    """The separate historical provider of REQ-051 AC-4: Kite's candles for one instrument and a time range."""

    def minute_candles(self, instrument_id: str, start: datetime.datetime, end: datetime.datetime) -> list[MinuteBar]:
        ...


def parse_candles(body: str, instrument_id: str, *, index: bool = False) -> list[MinuteBar]:
    try:
        parsed = json.loads(body, parse_float=Decimal)
        if parsed.get("status") != "success":
            raise CandleError("not a success body")
        rows = parsed["data"]["candles"]
        if not isinstance(rows, list):
            raise CandleError("candles is not a list")
        return [_row(instrument_id, row, index) for row in rows]
    except CandleError:
        raise
    except (ValueError, KeyError, TypeError, AttributeError, IndexError, ArithmeticError) as exc:
        raise CandleError(f"malformed candle body: {type(exc).__name__}") from None


def _row(instrument_id: str, row: object, index: bool) -> MinuteBar:
    if not isinstance(row, list) or len(row) < 7:
        raise CandleError("a candle row needs 7 fields")
    at = datetime.datetime.strptime(row[0], "%Y-%m-%dT%H:%M:%S%z")
    prices = [Decimal(str(v)) if isinstance(v, int) and not isinstance(v, bool) else v for v in row[1:5]]
    if not all(isinstance(p, Decimal) for p in prices):
        raise CandleError("a price is not a number")
    volume, oi = row[5], row[6]
    if isinstance(volume, bool) or not isinstance(volume, int) or isinstance(oi, bool) or not isinstance(oi, int):
        raise CandleError("volume and oi must be whole numbers")
    return MinuteBar(instrument_id, minute_of(at), prices[0], prices[1], prices[2], prices[3],
                     None if index else volume, None if index else oi, BarSource.KITE)


class InMemoryCandleSource:
    """A fake historical provider for tests: candles are given up front; the range filter is applied like the real one."""

    def __init__(self, bars: list[MinuteBar]) -> None:
        self._bars = list(bars)
        self.calls = 0

    def minute_candles(self, instrument_id: str, start: datetime.datetime, end: datetime.datetime) -> list[MinuteBar]:
        self.calls += 1
        return [b for b in self._bars if b.instrument_id == instrument_id and start <= b.minute <= end]
