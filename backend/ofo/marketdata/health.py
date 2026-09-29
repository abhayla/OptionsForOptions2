"""Data health derivation (REQ-049 AC-2): explicit inputs in, one of five health states out.

``HealthThresholds`` are configuration, not a spec-stated number (REQ-049 "Open: Staleness thresholds are an
implementation setting"); the defaults below are labelled orchestrator defaults so nobody mistakes them for an
owner decision.

Priority when more than one condition applies (worst first): no feed -> unavailable; a timestamp more than the
clock-skew tolerance ahead of ``now`` -> unhealthy (the source clock cannot be trusted); a validation failure
(including "no price at all": AC-2) -> unhealthy; older than the freshness limit -> stale; a source-declared delay
beyond the tolerance -> delayed; otherwise -> available. A timestamp within the clock-skew tolerance of the future
is treated as age 0 (fresh), never as an error: building a quote never raises for a future timestamp.
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
    clock_skew_tolerance: datetime.timedelta = datetime.timedelta(seconds=2)

    def __post_init__(self) -> None:
        for name in ("stale_after", "delayed_after", "clock_skew_tolerance"):
            value = getattr(self, name)
            if not isinstance(value, datetime.timedelta):
                raise ValueError(f"{name} must be a datetime.timedelta, got {value!r}")
            if value < datetime.timedelta(0):
                raise ValueError(f"{name} must be >= 0, got {value}")


ORCHESTRATOR_DEFAULT_THRESHOLDS = HealthThresholds()


@dataclass(frozen=True)
class HealthResult:
    """The derived health plus, when it is not obvious from the quote's own validation_errors, why."""

    health: DataHealth
    reason: str = ""


def evaluate_health(
    *,
    timestamp: datetime.datetime,
    now: datetime.datetime,
    feed_connected: bool,
    declared_delay_seconds: Decimal,
    validation_failed: bool,
    thresholds: HealthThresholds = ORCHESTRATOR_DEFAULT_THRESHOLDS,
) -> HealthResult:
    """Derive a quote's :class:`DataHealth` from explicit inputs only (REQ-049 AC-2). Never raises on a future
    timestamp: within ``thresholds.clock_skew_tolerance`` it is treated as fresh; beyond it, unhealthy."""
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
        return HealthResult(DataHealth.UNAVAILABLE)

    raw_age = now - timestamp
    if raw_age < -thresholds.clock_skew_tolerance:
        ahead_by = timestamp - now
        return HealthResult(
            DataHealth.UNHEALTHY,
            reason=(
                f"timestamp is {ahead_by} ahead of now, beyond the "
                f"{thresholds.clock_skew_tolerance} clock-skew tolerance (orchestrator default)"
            ),
        )
    age = max(raw_age, datetime.timedelta(0))  # within tolerance: treated as age 0 (fresh)

    if validation_failed:
        return HealthResult(DataHealth.UNHEALTHY)
    if age > thresholds.stale_after:
        return HealthResult(DataHealth.STALE)
    if declared_delay_seconds > Decimal(str(thresholds.delayed_after.total_seconds())):
        return HealthResult(DataHealth.DELAYED)
    return HealthResult(DataHealth.AVAILABLE)


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

    Field validation runs first (raises on hard-invalid input, never on a future timestamp); the health that comes
    out then reflects ``validation_errors`` (soft anomalies like a crossed quote or no price at all), the quote's
    own age against ``now`` (with clock-skew tolerance), a source-declared delay, and whether the feed is
    connected. A health-evaluation reason (e.g. a future timestamp beyond tolerance) is appended to the returned
    quote's ``validation_errors`` alongside any static ones, so both are visible in one place.
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
    result = evaluate_health(
        timestamp=provisional.timestamp,
        now=now,
        feed_connected=feed_connected,
        declared_delay_seconds=provisional.source.declared_delay_seconds,
        validation_failed=bool(provisional.validation_errors),
        thresholds=thresholds,
    )
    final = dataclasses.replace(provisional, health=result.health)
    if result.reason:
        object.__setattr__(final, "validation_errors", final.validation_errors + (result.reason,))
    return final
