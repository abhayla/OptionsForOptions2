"""Records and storage for the qualifying Client ID list (REQ-020, ADR-024, REQ-064 AC-2).

The service in ``qualifying.py`` talks only to the ``QualifyingRepository`` protocol, so a database-backed
repository can replace ``InMemoryQualifyingRepository`` later. The repository has no way to change or delete an
audit entry: the audit trail is append-only by construction (REQ-064 AC-2).
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping, Protocol


class VerificationStatus(Enum):
    """Whether the Client ID has been proven through Zerodha's official login (ADR-024 Q69)."""

    UNVERIFIED = "UNVERIFIED"
    VERIFIED = "VERIFIED"


class ListStatus(Enum):
    """Whether the ID currently qualifies. Removing an ID deactivates it (ADR-024 Q70); it is never deleted."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class EntitlementStatus(Enum):
    """Entitlement state reported by the entitlement engine; this module records it, never computes it."""

    NOT_EVALUATED = "NOT_EVALUATED"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


@dataclass(frozen=True)
class Actor:
    """Who made a change. Always passed in explicitly; there is no ambient current user."""

    actor_id: str

    def __post_init__(self) -> None:
        # Emptiness check only; actor_id is stored verbatim and never matched against a strict character set.
        if not isinstance(self.actor_id, str) or not self.actor_id.strip():
            raise ValueError("actor_id must be a non-empty string")


@dataclass(frozen=True)
class QualifyingEntry:
    """One qualifying Client ID and its per-ID status fields (REQ-020 AC-3)."""

    client_id: str
    list_status: ListStatus
    verification_status: VerificationStatus
    verified_at: datetime.datetime | None
    platform_user_id: str | None
    entitlement_status: EntitlementStatus
    added_by: str
    added_at: datetime.datetime

    def snapshot(self) -> Mapping[str, str | None]:
        """Read-only text view of the entry, used as audit before/after and for export."""
        return MappingProxyType(
            {
                "client_id": self.client_id,
                "list_status": self.list_status.value,
                "verification_status": self.verification_status.value,
                "verified_at": self.verified_at.isoformat() if self.verified_at else None,
                "platform_user_id": self.platform_user_id,
                "entitlement_status": self.entitlement_status.value,
                "added_by": self.added_by,
                "added_at": self.added_at.isoformat(),
            }
        )


@dataclass(frozen=True)
class AuditEntry:
    """One immutable audit record: who, when, what, before/after (REQ-020 AC-4, REQ-064)."""

    sequence: int
    actor_id: str
    at: datetime.datetime
    action: str
    client_id: str
    before: Mapping[str, str | None] | None
    after: Mapping[str, str | None] | None
    import_id: str | None = None


@dataclass(frozen=True)
class ImportRecord:
    """One applied import in the import history (REQ-020 AC-4)."""

    import_id: str
    actor_id: str
    at: datetime.datetime
    file_name: str
    total_rows: int
    added: int
    already_on_list: int
    reactivated: int
    edited_rows: int
    excluded_rows: int


class QualifyingRepository(Protocol):
    """Storage port. ``insert`` refuses an existing ID and ``update``/``delete`` refuse a missing one."""

    def get(self, client_id: str) -> QualifyingEntry | None: ...
    def insert(self, entry: QualifyingEntry) -> None: ...
    def update(self, entry: QualifyingEntry) -> None: ...
    def delete(self, client_id: str) -> None: ...
    def all_entries(self) -> tuple[QualifyingEntry, ...]: ...
    def append_audit(self, entry: AuditEntry) -> None: ...
    def audit_entries(self) -> tuple[AuditEntry, ...]: ...
    def append_import(self, record: ImportRecord) -> None: ...
    def import_records(self) -> tuple[ImportRecord, ...]: ...


class InMemoryQualifyingRepository:
    """In-memory ``QualifyingRepository``; audit and import history are append-only lists."""

    def __init__(self) -> None:
        self._entries: dict[str, QualifyingEntry] = {}
        self._audit: list[AuditEntry] = []
        self._imports: list[ImportRecord] = []

    def get(self, client_id: str) -> QualifyingEntry | None:
        return self._entries.get(client_id)

    def insert(self, entry: QualifyingEntry) -> None:
        if entry.client_id in self._entries:
            raise ValueError(f"{entry.client_id} is already on the qualifying list")
        self._entries[entry.client_id] = entry

    def update(self, entry: QualifyingEntry) -> None:
        if entry.client_id not in self._entries:
            raise ValueError(f"{entry.client_id} is not on the qualifying list")
        self._entries[entry.client_id] = entry

    def delete(self, client_id: str) -> None:
        if client_id not in self._entries:
            raise ValueError(f"{client_id} is not on the qualifying list")
        del self._entries[client_id]

    def all_entries(self) -> tuple[QualifyingEntry, ...]:
        return tuple(sorted(self._entries.values(), key=lambda e: e.client_id))

    def append_audit(self, entry: AuditEntry) -> None:
        self._audit.append(entry)

    def audit_entries(self) -> tuple[AuditEntry, ...]:
        return tuple(self._audit)

    def append_import(self, record: ImportRecord) -> None:
        self._imports.append(record)

    def import_records(self) -> tuple[ImportRecord, ...]:
        return tuple(self._imports)
