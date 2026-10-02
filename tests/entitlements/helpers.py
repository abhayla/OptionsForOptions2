"""Shared plain helpers for the entitlement tests (plain functions, so mutation tests can reuse them).

The ledger stamps every new event's ``recorded_at`` from its own clock (ADR-023 Q225 clarification), so
tests record an event by SETTING the ledger's clock to the moment it happens (``at`` / ``record``), with
realistic 2026 clocks. Nothing here uses a far-future clock: round 5's year-9000 clock hid the hole
where a caller-supplied past ``recorded_at`` was accepted.
"""

from datetime import datetime, timedelta, timezone

from ofo.entitlements.events import Audit, AuditNote, NewGrant

# India has no daylight saving, so a fixed +05:30 offset equals Asia/Kolkata for every instant used here.
IST = timezone(timedelta(hours=5, minutes=30), "Asia/Kolkata")
TICK = timedelta(microseconds=1)


def ist(year: int, month: int, day: int, hour: int = 0, minute: int = 0, second: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=IST)


def note(reason: str = "test", actor: str = "system") -> AuditNote:
    """Who and why for a NEW event; the ledger adds when."""
    return AuditNote(actor=actor, reason=reason)


def stamped(at: datetime, reason: str = "test", actor: str = "system") -> Audit:
    """A RECORDED audit, for building stored history the way the store adapter would hand it back."""
    return Audit(actor=actor, recorded_at=at, reason=reason)


# A ledger's clock before any test moves it: a realistic 2026 instant, before every date the tests use.
START = datetime(2026, 1, 1, tzinfo=timezone.utc)


class StepClock:
    """A ledger clock the test moves by hand: ``clock()`` returns ``now``."""

    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def fixed_clock(now: datetime) -> StepClock:
    return StepClock(now)


def ledger_for(user_id: str, **settings):
    from ofo.entitlements.ledger import EntitlementLedger

    settings.setdefault("clock", StepClock(START))
    return EntitlementLedger(user_id, **settings)


def at(ledger, when: datetime):
    """Set ``ledger``'s clock to ``when`` (the moment the next event is recorded) and return the ledger."""
    ledger.clock.now = when
    return ledger


def record(ledger, draft, when: datetime | None = None):
    """Append ``draft`` with the ledger clock at ``when`` (default: the event's own date)."""
    if when is None:
        when = draft.granted_at if isinstance(draft, NewGrant) else draft.effective_at
    return at(ledger, when).append(draft)
