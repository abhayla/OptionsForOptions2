"""Data health derivation (REQ-049 AC-2): explicit inputs in, one of five health states out.

``HealthThresholds`` are configuration, not a spec-stated number (REQ-049 "Open: Staleness thresholds are an
implementation setting"); the defaults below are labelled orchestrator defaults so nobody mistakes them for an
owner decision.

Priority when more than one condition applies (worst first): no feed / no quote -> unavailable; a validation
failure -> unhealthy (we do not trust what we have, whatever its age); older than the freshness limit -> stale;
a source-declared delay beyond the tolerance -> delayed; otherwise -> available.
"""
from __future__ import annotations

import dataclasses
import datetime
from dataclasses import dataclass
from decimal import Decimal

from ofo.marketdata.quote import NormalizedQuote, SourceMetadata
from ofo.rules.inputs import DataHealth


@dataclass(frozen=True)
class HealthThresholds:
    """orchestrator default (ADR-045) — not from the spec: REQ-049 leaves staleness thresholds implementation-defined."""

    stale_after: datetime.timedelta = datetime.timedelta(seconds=60)
    delayed_after: datetime.timedelta = datetime.timedelta(seconds=0)

    def __post_init__(self) -> None:
        for name in ("stale_after", "delayed_after"):
            value = getattr(self, name)
            if not isinstance(value, datetime.timedelta):
                raise ValueError(f"{name} must be a datetime.timedelta, got {value!r}")
            if value < datetime.timedelta(0):
                raise ValueError(f"{name} must be >= 0, got {value}")


ORCHESTRATOR_DEFAULT_THRESHOLDS = HealthThresholds()


def evaluate_health(
    *,
    timestamp: datetime.datetime,
    now: datetime.datetime,
    feed_connected: bool,
    declared_delay_seconds: Decimal,
    validation_failed: bool,
    thresholds: HealthThresholds = ORCHESTRATOR_DEFAULT_THRESHOLDS,
) -> DataHealth:
    """Derive a quote's :class:`DataHealth` from explicit inputs only (REQ-049 AC-2)."""
    if not isinstance(feed_connected, bool):
        raise ValueError(f"feed_connected must be a bool, got {feed_connected!r}")
    if not isinstance(timestamp, datetime.datetime) or timestamp.tzinfo is None:
        raise ValueError(f"timestamp must be a timezone-aware datetime, got {timestamp!r}")
    if not isinstance(now, datetime.datetime) or now.tzinfo is None:
        raise ValueError(f"now must be a timezone-aware datetime, got {now!r}")
    if not isinstance(thresholds, HealthThresholds):
        raise ValueError(f"thresholds must be a HealthThresholds, got {thresholds!r}")
    if not isinstance(declared_delay_seconds, Decimal) or isinstance(declared_delay_seconds, bool):
        raise ValueError(f"declared_delay_seconds must be a decimal.Decimal, got {declared_delay_seconds!r}")

    if not feed_connected:
        return DataHealth.UNAVAILABLE

    age = now - timestamp
    if age < datetime.timedelta(0):
        raise ValueError(f"timestamp {timestamp} is after now {now}")

    if validation_failed:
        return DataHealth.UNHEALTHY
    if age > thresholds.stale_after:
        return DataHealth.STALE
    if declared_delay_seconds > Decimal(str(thresholds.delayed_after.total_seconds())):
        return DataHealth.DELAYED
    return DataHealth.AVAILABLE


def build_quote(
    *,
    instrument_id: str,
    underlying: str,
    exchange: str,
    segment: str,
    instrument_type,
    expiry,
    strike,
    ltp,
    bid,
    ask,
    volume,
    oi,
    oi_change,
    iv,
    delta,
    gamma,
    theta,
    vega,
    timestamp: datetime.datetime,
    source: SourceMetadata,
    now: datetime.datetime,
    feed_connected: bool = True,
    thresholds: HealthThresholds = ORCHESTRATOR_DEFAULT_THRESHOLDS,
) -> NormalizedQuote:
    """Build a :class:`NormalizedQuote` with its ``health`` derived by :func:`evaluate_health`.

    Field validation runs first (raises on hard-invalid input); the health that comes out then reflects
    ``validation_errors`` (soft anomalies like a crossed quote), the quote's own age against ``now``, and whether
    the feed itself is connected.
    """
    provisional = NormalizedQuote(
        instrument_id=instrument_id,
        underlying=underlying,
        exchange=exchange,
        segment=segment,
        instrument_type=instrument_type,
        expiry=expiry,
        strike=strike,
        ltp=ltp,
        bid=bid,
        ask=ask,
        volume=volume,
        oi=oi,
        oi_change=oi_change,
        iv=iv,
        delta=delta,
        gamma=gamma,
        theta=theta,
        vega=vega,
        timestamp=timestamp,
        source=source,
        health=DataHealth.AVAILABLE,  # placeholder; replaced below once validation_errors is known
    )
    health = evaluate_health(
        timestamp=provisional.timestamp,
        now=now,
        feed_connected=feed_connected,
        declared_delay_seconds=provisional.source.declared_delay_seconds,
        validation_failed=bool(provisional.validation_errors),
        thresholds=thresholds,
    )
    return dataclasses.replace(provisional, health=health)
