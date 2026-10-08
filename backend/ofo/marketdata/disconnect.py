"""The disconnect status text for an affected strategy (REQ-049 AC-5, ADR-015 Q182).

Exact wording, owner-cited: 'Live market data disconnected. Last updated: <time>. Live strategy monitoring is
paused.' The time is the quote's last update, shown in IST (ADR-015's own example: '10:42:17 AM'); a trigger is
never claimed for the gap (handled by :mod:`ofo.rules`, which cannot evaluate on a non-``available`` input).

:func:`disconnect_status_for_strategy` ties this message to exactly one cause: a strategy PAUSED because the feed
itself is disconnected. A strategy paused for another reason (e.g. one quote stale while the feed stays connected)
gets no disconnect message - that would misreport the cause.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass

from ofo.marketdata.availability import MonitoringStatus
from ofo.rules.inputs import IST
from ofo import wording as shared_wording

_MESSAGE = "Live market data disconnected. Last updated: {time}. Live strategy monitoring is paused."


def disconnect_message(last_updated: datetime.datetime) -> str:
    """Build the AC-5 status text; ``last_updated`` must be timezone-aware, shown converted to IST."""
    if not isinstance(last_updated, datetime.datetime) or last_updated.tzinfo is None:
        raise ValueError(f"last_updated must be a timezone-aware datetime, got {last_updated!r}")
    ist_time = last_updated.astimezone(IST).strftime("%I:%M:%S %p")
    message = _MESSAGE.format(time=ist_time)
    shared_wording.check_platform_text(message, "disconnect_message")  # W-024 round 6: the check every platform message passes
    return message


@dataclass(frozen=True)
class DisconnectStatus:
    """The AC-5 status shown for a strategy paused because the feed is disconnected."""

    message: str
    last_updated: datetime.datetime


def disconnect_status_for_strategy(
    *,
    feed_connected: bool,
    monitoring_status: MonitoringStatus,
    last_updated: datetime.datetime,
) -> DisconnectStatus | None:
    """The disconnect status for a strategy, or ``None`` when it does not apply.

    Only returns a status when the feed is disconnected AND the strategy's monitoring is PAUSED as a result; a
    strategy that is active, or paused for a different reason while the feed stays connected, gets ``None``.
    """
    if not isinstance(feed_connected, bool):
        raise ValueError(f"feed_connected must be a bool, got {feed_connected!r}")
    if not isinstance(monitoring_status, MonitoringStatus):
        raise ValueError(f"monitoring_status must be a MonitoringStatus, got {monitoring_status!r}")
    if feed_connected or monitoring_status is not MonitoringStatus.PAUSED:
        return None
    return DisconnectStatus(message=disconnect_message(last_updated), last_updated=last_updated)
