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

from ofo.errors import UserFacingError, display_text, render
from ofo.marketdata.availability import MonitoringStatus


def disconnect_error(last_updated: datetime.datetime) -> UserFacingError:
    """The four-part message (REQ-065 AC-2) from the catalogue template ``marketdata_disconnected`` (W-024 round 9):
    AC-5's exact sentence is its what-happened part. ``last_updated`` must be timezone-aware, shown in IST."""
    if not isinstance(last_updated, datetime.datetime) or last_updated.tzinfo is None:
        raise ValueError(f"last_updated must be a timezone-aware datetime, got {last_updated!r}")
    return render("marketdata_disconnected", time=last_updated)


def disconnect_message(last_updated: datetime.datetime) -> str:
    """The AC-5 status sentence: the what-happened part of :func:`disconnect_error`."""
    return disconnect_error(last_updated).what_happened


@dataclass(frozen=True)
class DisconnectStatus:
    """The AC-5 status shown for a strategy paused because the feed is disconnected. ``error`` is the four-part
    message; ``message`` its AC-5 sentence; ``text`` what the user is shown (all four parts)."""

    error: UserFacingError
    last_updated: datetime.datetime

    def __post_init__(self) -> None:
        if type(self.error) is not UserFacingError:
            raise TypeError(f"DisconnectStatus needs a UserFacingError from render(), got {type(self.error).__name__}")

    @property
    def message(self) -> str:
        return self.error.what_happened

    @property
    def text(self) -> str:
        return display_text(self.error)


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
    return DisconnectStatus(error=disconnect_error(last_updated), last_updated=last_updated)
