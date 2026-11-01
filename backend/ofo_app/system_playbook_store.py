"""The admin's versions of the 12 system playbooks (REQ-169 AC-2..AC-4; ADR-222 (9), (10)). Schema: migration 0034.

- Append-only: a save, a restore and an approval each write the type's NEXT version; nothing is ever updated or deleted
  (the database guard refuses it, SQLSTATE OF034, whatever this module does). The current version is the newest.
- Every write carries who (the admin from the guarded route, never a body field), a required reason, and one audit
  event (ADMIN_CHANGE_RECORDED) in the same savepoint: both or neither.
- Every saved body passes the same store check a user's playbook passes (``playbook_store.check_body``); the route runs
  the user editor's whole pre-save check (``routes.playbooks.precheck``) before calling here.
- ``base_version`` is the version the admin's editor read: a save on top of a newer version is refused
  (``system_playbook_version_stale``), never a silent overwrite of another admin's change.
- A user's copy and a strategy's plan hold their own body: no write here touches them (ADR-222 (9)).
The caller commits.
"""
from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass
from typing import Any

from ofo.adjustment.playbook_types import SHOWN_NAMES
from ofo.audit.catalogue import EventType
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from ofo_app import audit_store
from ofo_app import playbook_store as pbs

REASON_REQUIRED = "system_playbook_reason_required"
VERSION_NOT_FOUND = "system_playbook_version_not_found"
VERSION_STALE = "system_playbook_version_stale"
ALREADY_APPROVED = "system_playbook_already_approved"
REASON_MAX = 500
AUDIT_SAVED = "system_playbook_version_saved"
AUDIT_RESTORED = "system_playbook_version_restored"
AUDIT_APPROVED = "system_playbook_approved"
APPROVED = "approved"

_COLUMNS = "strategy_type, version, status, body::text, reason, saved_by, restored_from, saved_at"
_HISTORY = text(f"SELECT {_COLUMNS} FROM public.system_playbook_versions "  # noqa: S608 - constant columns
                "WHERE strategy_type = :type ORDER BY version DESC")
_ONE = text(f"SELECT {_COLUMNS} FROM public.system_playbook_versions "  # noqa: S608 - constant columns
            "WHERE strategy_type = :type AND version = :version")
_LOCK = text("SELECT pg_advisory_xact_lock(hashtext('system_playbook_versions:' || :type))")
_INSERT = text("INSERT INTO public.system_playbook_versions (strategy_type, version, status, body, reason, saved_by, "  # noqa: S608 - constant columns
               "restored_from) VALUES (:type, :version, :status, CAST(:body AS JSONB), :reason, :saved_by, "
               f":restored_from) RETURNING {_COLUMNS}")


@dataclass(frozen=True)
class SystemVersion:
    strategy_type: str
    version: int
    status: str
    body: dict
    reason: str
    saved_by: str
    restored_from: int | None
    saved_at: datetime.datetime


def _version(row: Any) -> SystemVersion:
    return SystemVersion(strategy_type=row[0], version=row[1], status=row[2], body=pbs._load(row[3]),
                         reason=row[4], saved_by=row[5], restored_from=row[6], saved_at=row[7])


def _type(strategy_type: object) -> str:
    if not isinstance(strategy_type, str) or strategy_type not in SHOWN_NAMES:
        raise pbs.PlaybookStoreError(pbs.BODY_INVALID, f"strategy type {strategy_type!r}", field="strategy_type")
    return strategy_type


def _reason(reason: object) -> str:
    folded = " ".join(reason.split()) if isinstance(reason, str) else ""
    if not folded or len(folded) > REASON_MAX:
        raise pbs.PlaybookStoreError(REASON_REQUIRED, "a system playbook version needs a reason")
    return folded


async def history(conn: Any, strategy_type: str) -> list[SystemVersion]:
    """Every stored version of the type, newest (current) first."""
    rows = (await conn.execute(_HISTORY, {"type": _type(strategy_type)})).all()
    if not rows:  # 0034 seeds all 12: none is a broken database, never an empty history
        raise RuntimeError(f"no stored version of the system playbook for {strategy_type}")
    return [_version(r) for r in rows]


async def current(conn: Any, strategy_type: str) -> SystemVersion:
    return (await history(conn, strategy_type))[0]


async def version(conn: Any, strategy_type: str, number: int) -> SystemVersion:
    if type(number) is not int:
        raise pbs.PlaybookStoreError(VERSION_NOT_FOUND, f"version {number!r}", version=str(number))
    row = (await conn.execute(_ONE, {"type": _type(strategy_type), "version": number})).one_or_none()
    if row is None:
        raise pbs.PlaybookStoreError(VERSION_NOT_FOUND, f"{strategy_type} version {number}", version=str(number))
    return _version(row)


async def _append(conn: Any, admin: str, base: SystemVersion, *, status: str, body: dict,  # noqa: PLR0913
                  reason: str, restored_from: int | None, action: str) -> SystemVersion:
    """The next version and its audit event, both or neither."""
    words = (f"{action}: {SHOWN_NAMES[base.strategy_type]} version {base.version + 1}"
             + (f" (restored from version {restored_from})" if restored_from is not None else "")
             + f"; reason: {reason}")
    try:
        async with conn.begin_nested():
            row = (await conn.execute(_INSERT, {
                "type": base.strategy_type, "version": base.version + 1, "status": status, "body": pbs._dump(body),
                "reason": reason, "saved_by": admin, "restored_from": restored_from})).one()
            await audit_store.append(conn, EventType.ADMIN_CHANGE_RECORDED, actor=admin,
                                     correlation_id=f"sysplay-{uuid.uuid4().hex}",
                                     payload={"action": action, "reason": words})
    except IntegrityError:  # another admin wrote the same next version first (primary key): the caller re-reads
        raise pbs.PlaybookStoreError(VERSION_STALE, f"{base.strategy_type} moved past version {base.version}",
                                     version=str(base.version)) from None
    return _version(row)


async def _base(conn: Any, strategy_type: str, base_version: int) -> SystemVersion:
    strategy_type = _type(strategy_type)
    await conn.execute(_LOCK, {"type": strategy_type})  # one writer per type at a time; the primary key backs it
    now = await current(conn, strategy_type)
    if type(base_version) is not int or base_version != now.version:
        raise pbs.PlaybookStoreError(VERSION_STALE, f"{strategy_type} is at version {now.version}",
                                     version=str(now.version))
    return now


async def save(conn: Any, admin: str, strategy_type: str, body: object, reason: object,  # noqa: PLR0913
               base_version: int) -> SystemVersion:
    """AC-2: the admin's edited body as the next version; it keeps the current version's approval state."""
    reason = _reason(reason)
    now = await _base(conn, strategy_type, base_version)
    if not isinstance(body, dict):
        raise pbs.PlaybookStoreError(pbs.BODY_INVALID, "playbook body field body", field="body")
    if "status" in body and body["status"] != now.status:  # approval changes only through approve(), never a save
        raise pbs.PlaybookStoreError(pbs.BODY_INVALID, "playbook body field status", field="status")
    checked = pbs.check_body({**body, "status": now.status}, now.strategy_type)
    return await _append(conn, admin, now, status=now.status, body=checked, reason=reason, restored_from=None,
                         action=AUDIT_SAVED)


async def restore(conn: Any, admin: str, strategy_type: str, number: int, reason: object,  # noqa: PLR0913
                  base_version: int) -> SystemVersion:
    """AC-2 "Restore this version": a NEW version copying an earlier one's body and status; nothing is overwritten."""
    reason = _reason(reason)
    now = await _base(conn, strategy_type, base_version)
    earlier = await version(conn, now.strategy_type, number)
    checked = pbs.check_body(earlier.body, now.strategy_type)  # a stored body the check now refuses is never restored
    return await _append(conn, admin, now, status=earlier.status, body=checked, reason=reason,
                         restored_from=earlier.version, action=AUDIT_RESTORED)


async def approve(conn: Any, admin: str, strategy_type: str, reason: object, base_version: int) -> SystemVersion:
    """AC-3: a Draft system playbook marked approved, as a new version with the same numbers."""
    reason = _reason(reason)
    now = await _base(conn, strategy_type, base_version)
    if now.status == APPROVED:
        raise pbs.PlaybookStoreError(ALREADY_APPROVED, f"{now.strategy_type} version {now.version} is approved")
    checked = pbs.check_body({**now.body, "status": APPROVED}, now.strategy_type)
    return await _append(conn, admin, now, status=APPROVED, body=checked, reason=reason, restored_from=None,
                         action=AUDIT_APPROVED)
