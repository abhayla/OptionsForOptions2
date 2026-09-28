"""Shared plain helpers for the entitlement tests (plain functions, so mutation tests can reuse them)."""

from datetime import datetime, timedelta, timezone

from ofo.entitlements.events import Audit

# India has no daylight saving, so a fixed +05:30 offset equals Asia/Kolkata for every instant used here.
IST = timezone(timedelta(hours=5, minutes=30), "Asia/Kolkata")
TICK = timedelta(microseconds=1)


def ist(year: int, month: int, day: int, hour: int = 0, minute: int = 0, second: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=IST)


def audit(at: datetime, reason: str = "test", actor: str = "system") -> Audit:
    return Audit(actor=actor, recorded_at=at, reason=reason)


# Scenario tests replay dated histories, so they run the ledger against a fixed clock far after every
# date they use. Tests of the clock guard itself pass their own clock.
TEST_NOW = datetime(9000, 1, 1, tzinfo=timezone.utc)


def fixed_clock(now: datetime):
    return lambda: now


def ledger_for(user_id: str, events: tuple = (), **settings):
    from ofo.entitlements.ledger import EntitlementLedger

    settings.setdefault("clock", fixed_clock(TEST_NOW))
    return EntitlementLedger(user_id, events, **settings)
