"""The market-data provider interface (REQ-048 AC-2). Product code depends on this, never on a vendor module (AC-3).

Operations: live quote stream, option-chain snapshot, instrument/contract master, underlying quote, futures quote,
optional historical data, health/status, source metadata. An operation a provider does not offer raises
``NotSupported`` (V1 Kite: futures quote and historical data).
"""
from __future__ import annotations

import abc
import datetime
from dataclasses import dataclass
from typing import Callable, Sequence

from ofo.instruments.models import ListedContract
from ofo.marketdata.quote import NormalizedQuote, SourceMetadata
from ofo.rules.inputs import DataHealth

QuoteListener = Callable[[NormalizedQuote], None]


class NotSupported(Exception):
    """The provider does not offer this operation."""


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
