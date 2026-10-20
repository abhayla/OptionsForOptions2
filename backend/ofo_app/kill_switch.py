"""ADR-127: the owner's kill switch. One setting that refuses every basket build; flipping it is an audited event.

Spec basis: ADR-127 (1) "One server setting, changed only by the platform owner, refuses to build any basket ... at the
same gate as ADR-119"; (4) "Turning it on or off is an audited event"; REQ-063 AC-5 (audit payload allowlist).

Where the switch lives (technical call, no migration): the audit log itself. The state is the LATEST
``admin_change_recorded`` event whose action is ``kill_switch_on`` or ``kill_switch_off``; no such event means off. So
the setting survives a restart, the only way to change it is to append an audited event (state and audit cannot
disagree), the chain is tamper-evident, and the application role needs nothing new. ``admin_change_recorded`` and its
``action`` / ``reason`` fields are already declared in the database allowlist (migration 0002), so no migration is
needed. Every read is a fresh statement in the caller's transaction (READ COMMITTED): never cached, so a flip is seen
by the next gate. A read that fails or finds an action it does not know is ``None`` = unknown, and the gate treats
unknown as paused (fail closed).
"""
from __future__ import annotations

import uuid
from typing import Any

from ofo.audit.catalogue import EventType
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from ofo_app import audit_store

ACTION_ON = "kill_switch_on"
ACTION_OFF = "kill_switch_off"
OWNER_ACTOR = "owner"
REASON_MAX = 200

_LATEST = text(
    "SELECT payload ->> 'action' AS action FROM public.audit_events "
    "WHERE event_type = :t AND payload ->> 'action' IN (:on, :off) ORDER BY seq DESC LIMIT 1"
)


async def is_paused(conn: Any) -> bool | None:
    """True = on, False = off (no event yet, or the latest says off), None = could not be read or not understood."""
    try:
        row = (await conn.execute(_LATEST, {"t": EventType.ADMIN_CHANGE_RECORDED.value, "on": ACTION_ON,
                                            "off": ACTION_OFF})).first()
    except SQLAlchemyError:
        return None
    if row is None:
        return False
    if row.action == ACTION_ON:
        return True
    return False if row.action == ACTION_OFF else None


async def set_paused(conn: Any, paused: bool, *, reason: str, actor: str = OWNER_ACTOR) -> int:
    """Appends ONE audit event for the flip (in the caller's transaction; the caller commits) and returns its seq."""
    stored = await audit_store.append(
        conn, EventType.ADMIN_CHANGE_RECORDED, actor=actor, correlation_id=f"kill-switch:{uuid.uuid4().hex}",
        payload={"action": ACTION_ON if paused else ACTION_OFF, "reason": reason})
    return stored.seq


__all__ = ["ACTION_OFF", "ACTION_ON", "OWNER_ACTOR", "REASON_MAX", "is_paused", "set_paused"]
