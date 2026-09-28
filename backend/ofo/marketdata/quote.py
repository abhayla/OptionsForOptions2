"""The one normalized quote model every market-data source is converted into (REQ-049 AC-1).

Every field named in AC-1 is present: instrument id, underlying, exchange, segment, expiry, strike, CE/PE, LTP,
bid, ask, volume, OI, OI change, IV, Greeks, timestamp, source metadata, data health. Money and Greeks are exact
``Decimal``; volume/OI are integers; the timestamp is timezone-aware. ``health`` is supplied by the caller
(normally :func:`ofo.marketdata.health.build_quote`, which derives it from a :class:`HealthPolicy`) so this module
stays a pure value type with no clock dependency.

Invalid input raises ``ValueError`` (fail closed); a quote that is merely suspicious (e.g. a crossed market) is
still constructed but records the anomaly in ``validation_errors`` for :mod:`ofo.marketdata.health` to see.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from decimal import Decimal

from ofo.engine.legs import Instrument, require_price
from ofo.rules.inputs import DataHealth

MAX_VOLUME = 10**12  # absurd-size guard; no real instrument trades this many units in a session
MAX_IV_PERCENT = Decimal("1000")  # IV expressed as a percent; anything above this is corrupted data, not a spike


def _require_nonempty(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string, got {value!r}")
    return value


def _require_count(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an int, got {type(value).__name__}")
    if value < 0:
        raise ValueError(f"{name} must be >= 0, got {value}")
    if value > MAX_VOLUME:
        raise ValueError(f"{name} is {value}, over the absurd-size guard of {MAX_VOLUME}")
    return value


def _require_greek(value: Decimal, name: str, *, lo: Decimal, hi: Decimal) -> Decimal:
    if not isinstance(value, Decimal) or isinstance(value, bool) or not value.is_finite():
        raise ValueError(f"{name} must be a finite decimal.Decimal, got {value!r}")
    if not (lo <= value <= hi):
        raise ValueError(f"{name} must be within [{lo}, {hi}], got {value}")
    return value


@dataclass(frozen=True)
class SourceMetadata:
    """Who this quote came from and any delay the source itself declares (AC-1 'source metadata')."""

    provider: str
    feed_id: str
    declared_delay_seconds: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        _require_nonempty(self.provider, "provider")
        _require_nonempty(self.feed_id, "feed_id")
        if not isinstance(self.declared_delay_seconds, Decimal) or isinstance(self.declared_delay_seconds, bool):
            raise ValueError(f"declared_delay_seconds must be a decimal.Decimal, got {self.declared_delay_seconds!r}")
        if not self.declared_delay_seconds.is_finite() or self.declared_delay_seconds < 0:
            raise ValueError(f"declared_delay_seconds must be >= 0 and finite, got {self.declared_delay_seconds}")


@dataclass(frozen=True)
class NormalizedQuote:
    """One quote in the platform's one internal shape (AC-1). ``health`` is required, never defaulted."""

    instrument_id: str
    underlying: str
    exchange: str
    segment: str
    instrument_type: Instrument | None  # CE / PE / FUT; None for an underlying index quote
    expiry: datetime.date | None
    strike: Decimal | None
    ltp: Decimal | None
    bid: Decimal | None
    ask: Decimal | None
    volume: int | None
    oi: int | None
    oi_change: int | None
    iv: Decimal | None
    delta: Decimal | None
    gamma: Decimal | None
    theta: Decimal | None
    vega: Decimal | None
    timestamp: datetime.datetime
    source: SourceMetadata
    health: DataHealth
    validation_errors: tuple[str, ...] = field(default=(), init=False)

    def __post_init__(self) -> None:
        _require_nonempty(self.instrument_id, "instrument_id")
        _require_nonempty(self.underlying, "underlying")
        _require_nonempty(self.exchange, "exchange")
        _require_nonempty(self.segment, "segment")
        if self.instrument_type is not None and not isinstance(self.instrument_type, Instrument):
            raise ValueError(f"instrument_type must be an Instrument or None, got {self.instrument_type!r}")
        if self.instrument_type is None:
            if self.expiry is not None or self.strike is not None:
                raise ValueError("an underlying-index quote (instrument_type=None) carries no expiry or strike")
        elif self.instrument_type is Instrument.FUT:
            if self.strike is not None:
                raise ValueError("a futures quote has no strike")
            if not isinstance(self.expiry, datetime.date) or isinstance(self.expiry, datetime.datetime):
                raise ValueError(f"a futures quote needs a datetime.date expiry, got {self.expiry!r}")
        else:
            if not isinstance(self.expiry, datetime.date) or isinstance(self.expiry, datetime.datetime):
                raise ValueError(f"an option quote needs a datetime.date expiry, got {self.expiry!r}")
            require_price(self.strike, "strike", allow_zero=False)

        errors: list[str] = []
        for name in ("ltp", "bid", "ask"):
            value = getattr(self, name)
            if value is not None:
                require_price(value, name)
        if self.bid is not None and self.ask is not None and self.bid > self.ask:
            errors.append(f"crossed_quote: bid {self.bid} > ask {self.ask}")

        if self.volume is not None:
            _require_count(self.volume, "volume")
        if self.oi is not None:
            _require_count(self.oi, "oi")
        if self.oi_change is not None:
            if isinstance(self.oi_change, bool) or not isinstance(self.oi_change, int):
                raise ValueError(f"oi_change must be an int, got {type(self.oi_change).__name__}")
            if abs(self.oi_change) > MAX_VOLUME:
                errors.append(f"oi_change {self.oi_change} exceeds the absurd-size guard")

        if self.iv is not None:
            if not isinstance(self.iv, Decimal) or isinstance(self.iv, bool) or not self.iv.is_finite():
                raise ValueError(f"iv must be a finite decimal.Decimal, got {self.iv!r}")
            if self.iv < 0 or self.iv > MAX_IV_PERCENT:
                raise ValueError(f"iv must be within [0, {MAX_IV_PERCENT}] percent, got {self.iv}")
        if self.delta is not None:
            _require_greek(self.delta, "delta", lo=Decimal("-1"), hi=Decimal("1"))
        if self.gamma is not None:
            _require_greek(self.gamma, "gamma", lo=Decimal("0"), hi=Decimal("10"))
        if self.theta is not None:
            _require_greek(self.theta, "theta", lo=Decimal("-100000"), hi=Decimal("100000"))
        if self.vega is not None:
            _require_greek(self.vega, "vega", lo=Decimal("0"), hi=Decimal("100000"))

        if not isinstance(self.timestamp, datetime.datetime) or self.timestamp.tzinfo is None:
            raise ValueError(f"timestamp must be a timezone-aware datetime, got {self.timestamp!r}")

        if not isinstance(self.source, SourceMetadata):
            raise ValueError(f"source must be a SourceMetadata, got {self.source!r}")
        if not isinstance(self.health, DataHealth):
            raise ValueError(f"health must be a DataHealth, got {self.health!r}")

        object.__setattr__(self, "validation_errors", tuple(errors))
