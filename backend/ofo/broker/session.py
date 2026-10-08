"""A broker session's lifecycle (W-058, REQ-015 AC-7, ADR-020, ADR-053).

Spec basis: REQ-015 AC-7 ("Zerodha authorization is treated as temporary (about one day; re-authentication daily);
its expiry never deletes identity, strategies or entitlements."); ADR-053 (the Zerodha session is logged out every
day and monitoring pauses visibly).

States: CONNECTED -> EXPIRED (Kite answered TokenException, or the expected expiry passed), DISCONNECTED (the user
disconnected) or REPLACED (a new successful login for the same user and broker). Every end state is terminal: a later
end leaves the session as it is, so the first end reason wins.

This module takes and returns only session data. It imports nothing from the strategy, account, entitlement or admin
packages and has no parameter that reaches them, so ending a session cannot touch a strategy or an entitlement
(a test asserts the imports).

Copy from: none - the legacy flow (algochanakya app/api/routes/auth.py:60-175, REFERENCE) has no session lifecycle.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace as _copy
from datetime import datetime, time, timedelta, timezone
from enum import Enum

#: India Standard Time: a fixed +05:30 offset, no daylight saving.
IST = timezone(timedelta(hours=5, minutes=30), "IST")
#: The time of day Kite's access tokens are expected to stop working (Kite docs: valid "till 6 AM on the next day").
KITE_EXPIRY_TIME_IST = time(6, 0)
BROKER_ZERODHA = "zerodha"


class SessionState(str, Enum):
    CONNECTED = "connected"
    EXPIRED = "expired"
    DISCONNECTED = "disconnected"
    REPLACED = "replaced"


class EndReason(str, Enum):
    """The stored end reason (broker_sessions.end_reason CHECK)."""

    EXPIRED = "expired"
    DISCONNECTED = "disconnected"
    REPLACED = "replaced"


_END_STATE = {
    EndReason.EXPIRED: SessionState.EXPIRED,
    EndReason.DISCONNECTED: SessionState.DISCONNECTED,
    EndReason.REPLACED: SessionState.REPLACED,
}


@dataclass(frozen=True)
class BrokerSession:
    user_ref: str
    broker: str
    started_at: datetime
    expected_expiry: datetime
    state: SessionState = SessionState.CONNECTED
    ended_at: datetime | None = None
    end_reason: EndReason | None = None

    @property
    def active(self) -> bool:
        return self.state is SessionState.CONNECTED


def _aware(at: datetime, name: str) -> datetime:
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return at


def expected_expiry(login_at: datetime) -> datetime:
    """The next 06:00 IST strictly after ``login_at``.

    This is an EXPECTATION, to be confirmed by the 2026-10-09 morning token-expiry measurement (F-31). Kite's own
    TokenException always wins: a session is EXPIRED as soon as Kite refuses its token, whatever this time says.
    The same rule holds every day of the week (a Saturday login expires on Sunday at 06:00 IST).
    """
    local = _aware(login_at, "login_at").astimezone(IST)
    candidate = datetime.combine(local.date(), KITE_EXPIRY_TIME_IST, tzinfo=IST)
    if candidate <= local:
        candidate = candidate + timedelta(days=1)
    return candidate


def start(user_ref: str, login_at: datetime, broker: str = BROKER_ZERODHA) -> BrokerSession:
    if not user_ref:
        raise ValueError("user_ref is required")
    if broker != BROKER_ZERODHA:
        raise ValueError(f"unsupported broker {broker!r}")
    return BrokerSession(user_ref=user_ref, broker=broker, started_at=_aware(login_at, "login_at"),
                         expected_expiry=expected_expiry(login_at))


def _end(session: BrokerSession, reason: EndReason, at: datetime) -> BrokerSession:
    _aware(at, "at")
    if not session.active:
        return session  # terminal: the first end reason wins
    return _copy(session, state=_END_STATE[reason], ended_at=at, end_reason=reason)


def expire_on_token_exception(session: BrokerSession, at: datetime) -> BrokerSession:
    """Kite answered TokenException: the session is EXPIRED now, before or after the expected expiry."""
    return _end(session, EndReason.EXPIRED, at)


def expire_on_clock(session: BrokerSession, now: datetime) -> BrokerSession:
    """EXPIRED once ``now`` reaches the expected expiry; otherwise unchanged."""
    if _aware(now, "now") >= session.expected_expiry:
        return _end(session, EndReason.EXPIRED, now)
    return session


def disconnect(session: BrokerSession, at: datetime) -> BrokerSession:
    return _end(session, EndReason.DISCONNECTED, at)


def replace(session: BrokerSession, at: datetime) -> BrokerSession:
    """A new successful login for the same user and broker ends this one."""
    return _end(session, EndReason.REPLACED, at)
