"""Append-only, immutable ledger of one user's entitlement events (REQ-017 AC-4)."""

from __future__ import annotations

from dataclasses import dataclass

from ofo.entitlements.events import EntitlementEvent, EntitlementGrant, EntitlementStatusChange


def _check_next(prior: tuple[EntitlementEvent, ...], event: EntitlementEvent) -> None:
    """Raise ``ValueError`` unless ``event`` may follow ``prior`` in an append-only ledger."""
    if not isinstance(event, (EntitlementGrant, EntitlementStatusChange)):
        raise ValueError(f"not an entitlement event: {event!r}")
    if prior and event.audit.recorded_at < prior[-1].audit.recorded_at:
        raise ValueError("events must be appended in recorded_at order; the ledger is append-only")
    granted_ids = {e.entitlement_id for e in prior if isinstance(e, EntitlementGrant)}
    if isinstance(event, EntitlementGrant):
        if event.entitlement_id in granted_ids:
            raise ValueError(f"entitlement {event.entitlement_id!r} already granted")
        return
    if event.entitlement_id not in granted_ids:
        raise ValueError(f"no entitlement {event.entitlement_id!r} to change")
    if any(isinstance(e, EntitlementStatusChange) and e.entitlement_id == event.entitlement_id for e in prior):
        raise ValueError(f"entitlement {event.entitlement_id!r} is already revoked or ended")


@dataclass(frozen=True)
class EntitlementLedger:
    """Every entitlement event of one user, in the order recorded.

    ``append`` returns a NEW ledger; nothing is ever edited or removed, so ``events`` is the complete
    audit history.
    """

    user_id: str
    events: tuple[EntitlementEvent, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.user_id, str) or not self.user_id.strip():
            raise ValueError("user_id must be a non-empty string")
        if not isinstance(self.events, tuple):
            raise ValueError("events must be a tuple")
        for index, event in enumerate(self.events):
            _check_next(self.events[:index], event)

    def append(self, event: EntitlementEvent) -> EntitlementLedger:
        """Return a new ledger with ``event`` added; raise ``ValueError`` if it is not a valid next event."""
        return EntitlementLedger(self.user_id, self.events + (event,))

    def grants(self) -> tuple[EntitlementGrant, ...]:
        return tuple(e for e in self.events if isinstance(e, EntitlementGrant))

    def grant(self, entitlement_id: str) -> EntitlementGrant:
        for grant in self.grants():
            if grant.entitlement_id == entitlement_id:
                return grant
        raise ValueError(f"no entitlement {entitlement_id!r} in ledger of {self.user_id!r}")

    def status_change(self, entitlement_id: str) -> EntitlementStatusChange | None:
        for event in self.events:
            if isinstance(event, EntitlementStatusChange) and event.entitlement_id == entitlement_id:
                return event
        return None
