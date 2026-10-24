"""The market-data provider interface (REQ-048 AC-2). Product code depends on this, never on a vendor module (AC-3).

Operations: live quote stream, option-chain snapshot, instrument/contract master, underlying quote, futures quote,
optional historical data, health/status, source metadata. An operation a provider does not offer raises
``NotSupported`` (V1 Kite: historical data).
"""
from __future__ import annotations

import abc
import datetime
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Literal, Sequence

from ofo.engine.executable_price import Depth
from ofo.instruments.models import ListedContract
from ofo.marketdata.quote import NormalizedQuote, SourceMetadata
from ofo.rules.inputs import DataHealth

QuoteListener = Callable[[NormalizedQuote], None]


class NotSupported(Exception):
    """The provider does not offer this operation."""


#: Why a contract's day values cannot be given (REQ-080 AC-7, AC-8): never a silent null.
DayStatsReason = Literal["NOT_OFFERED", "NOT_HELD", "FEED_NOT_HEALTHY", "PACKET_WITHOUT_DAY_FIELDS"]
NOT_OFFERED: DayStatsReason = "NOT_OFFERED"
NOT_HELD: DayStatsReason = "NOT_HELD"
FEED_NOT_HEALTHY: DayStatsReason = "FEED_NOT_HEALTHY"
PACKET_WITHOUT_DAY_FIELDS: DayStatsReason = "PACKET_WITHOUT_DAY_FIELDS"


@dataclass(frozen=True)
class DayStats:
    """What a packet says about the trading day (REQ-080 AC-7); a field is ``None`` when the packet lacks it."""

    day_open: Decimal | None
    day_high: Decimal | None
    day_low: Decimal | None
    prev_close: Decimal | None  # the previous session's close (F-47)
    last_trade_ts: int | None  # epoch seconds, as the vendor sends it


@dataclass(frozen=True)
class DayStatsAnswer:
    """Day values or the reason there are none: exactly one of ``stats`` and ``reason`` is set."""

    stats: DayStats | None = None
    reason: DayStatsReason | None = None

    @classmethod
    def unavailable(cls, reason: DayStatsReason) -> DayStatsAnswer:
        return cls(None, reason)


@dataclass(frozen=True)
class ProviderStatus:
    health: DataHealth
    connected: bool
    session_ended: bool = False
    detail: str = ""


class MarketDataProvider(abc.ABC):
    @abc.abstractmethod
    def subscribe(self, instrument_ids: Sequence[str]) -> None:
        """Start receiving these instruments (one vendor subscription each; callers share via the fan-out)."""

    @abc.abstractmethod
    def unsubscribe(self, instrument_ids: Sequence[str]) -> None: ...

    @abc.abstractmethod
    def live_quote_stream(self, listener: QuoteListener) -> None:
        """Deliver every normalised update, in arrival order, to ``listener``."""

    @abc.abstractmethod
    def option_chain_snapshot(self, underlying: str, expiry: datetime.date) -> list[NormalizedQuote]: ...

    @abc.abstractmethod
    def instrument_master(self) -> list[ListedContract]: ...

    def last_quote_time(self, instrument_id: str) -> datetime.datetime | None:
        """ADR-077: the time (never the price) of the last quote held for an instrument whose subscription ended;
        None when none was kept. A provider that keeps no such time inherits this."""
        return None

    def latest_depth(self, instrument_id: str, now: datetime.datetime | None = None) -> Depth | None:
        """The 5-level depth of the latest full packet, or None (none held, not healthy, or a provider without depth:
        a provider that offers none inherits this)."""
        return None

    def latest_day_stats(self, instrument_id: str, now: datetime.datetime | None = None) -> DayStatsAnswer:
        """The day's open / high / low / previous close and last trade time, or the reason there are none. A provider
        that offers none inherits this and says ``NOT_OFFERED``."""
        return DayStatsAnswer.unavailable(NOT_OFFERED)

    @abc.abstractmethod
    def underlying_quote(self, underlying: str) -> NormalizedQuote | None: ...

    @abc.abstractmethod
    def futures_quote(self, underlying: str, expiry: datetime.date) -> NormalizedQuote | None: ...

    @abc.abstractmethod
    def historical(self, instrument_id: str, start: datetime.datetime, end: datetime.datetime) -> list[NormalizedQuote]: ...

    @abc.abstractmethod
    def status(self) -> ProviderStatus: ...

    @abc.abstractmethod
    def source_metadata(self) -> SourceMetadata: ...
