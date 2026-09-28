"""Admin service for the qualifying Zerodha Client ID list (REQ-020 AC-1..AC-5; ADR-024 Q70; REQ-064).

Spec: REQ-020 (import, validation, search/filter, per-ID status, import history, audit, export); ADR-024 Q70
("duplicates/malformed IDs validated before applying"); ADR-022 (the Client ID is the identity); REQ-064 AC-2
(audit is append-only).

Import is two-step. ``preview_import`` returns a dry-run report that classifies every data row. ``apply_import``
re-runs that classification against the list as it is NOW and refuses (``ImportRefusedError``) while any row is a
problem (malformed or duplicated within the file); the admin resolves a problem by editing the row's value or by
explicitly excluding the row in the ``ImportRequest``. A row whose ID is already on the list is not a problem: it
is skipped, so re-importing the same file changes nothing. Every change writes one audit entry.

Not decided by the spec, so not decided here: what removing an ID does to an already-granted entitlement
(ADR-024 consequences). This module only removes the list entry and audits it; entitlement status is an input
from the entitlement engine (``record_entitlement_status``), never computed here.
"""
from __future__ import annotations

import csv
import datetime
import io
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Callable, Mapping

from ofo.admin.client_id import MalformedClientIdError, normalise_client_id
from ofo.admin.qualifying_store import (
    Actor,
    AuditEntry,
    EntitlementStatus,
    ImportRecord,
    QualifyingEntry,
    QualifyingRepository,
    VerificationStatus,
)

CLIENT_ID_COLUMN = "client_id"
EXPORT_COLUMNS = (
    "client_id",
    "verification_status",
    "verified_at",
    "platform_user_id",
    "entitlement_status",
    "added_by",
    "added_at",
)


class RowCategory(Enum):
    NEW = "NEW"
    ALREADY_ON_LIST = "ALREADY_ON_LIST"
    DUPLICATE_IN_FILE = "DUPLICATE_IN_FILE"
    MALFORMED = "MALFORMED"
    EXCLUDED = "EXCLUDED"


PROBLEM_CATEGORIES = frozenset({RowCategory.DUPLICATE_IN_FILE, RowCategory.MALFORMED})


@dataclass(frozen=True)
class ImportRequest:
    """A CSV file plus the admin's resolutions: per-row replacement values and explicitly excluded rows.

    Row numbers are spreadsheet line numbers: the header is row 1, the first data row is row 2.
    """

    file_name: str
    csv_text: str
    edits: Mapping[int, str] = field(default_factory=dict)
    excluded_rows: frozenset[int] = frozenset()


@dataclass(frozen=True)
class ImportRow:
    row_number: int
    raw_value: str
    client_id: str | None
    category: RowCategory
    message: str
    edited: bool


@dataclass(frozen=True)
class ImportReport:
    file_name: str
    rows: tuple[ImportRow, ...]

    @property
    def problems(self) -> tuple[ImportRow, ...]:
        return tuple(r for r in self.rows if r.category in PROBLEM_CATEGORIES)

    def rows_in(self, category: RowCategory) -> tuple[ImportRow, ...]:
        return tuple(r for r in self.rows if r.category is category)


class ImportRefusedError(ValueError):
    """Apply was refused because the report still has unresolved problem rows."""

    def __init__(self, report: ImportReport) -> None:
        self.report = report
        rows = ", ".join(f"row {r.row_number} ({r.category.value})" for r in report.problems)
        super().__init__(f"import of {report.file_name!r} refused; unresolved: {rows}")


class _Unset:
    """Marker for 'field not given' in ``edit`` (None is a real value: unlink the user)."""


UNSET = _Unset()


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _require_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _safe_cell(value: str | None) -> str:
    """Neutralise spreadsheet formula injection in exported cells."""
    if value is None:
        return ""
    return "'" + value if value[:1] in ("=", "+", "-", "@") else value


class QualifyingListService:
    """Admin operations on the qualifying list. Every mutating call takes the acting ``Actor`` explicitly."""

    def __init__(
        self, repository: QualifyingRepository, clock: Callable[[], datetime.datetime] = _utc_now
    ) -> None:
        self._repo = repository
        self._clock = clock

    # ----- clock and audit -------------------------------------------------------------------------------

    def _now(self) -> datetime.datetime:
        now = self._clock()
        if now.tzinfo is None:
            raise ValueError("clock must return a timezone-aware datetime")
        return now

    def _audit(
        self,
        actor: Actor,
        at: datetime.datetime,
        action: str,
        client_id: str,
        before: QualifyingEntry | None,
        after: QualifyingEntry | None,
        import_id: str | None = None,
    ) -> None:
        self._repo.append_audit(
            AuditEntry(
                sequence=len(self._repo.audit_entries()) + 1,
                actor_id=actor.actor_id,
                at=at,
                action=action,
                client_id=client_id,
                before=before.snapshot() if before else None,
                after=after.snapshot() if after else None,
                import_id=import_id,
            )
        )

    @staticmethod
    def _require_actor(actor: object) -> Actor:
        if not isinstance(actor, Actor):
            raise ValueError("an explicit Actor is required for every change")
        return actor

    def _require_entry(self, client_id: str) -> QualifyingEntry:
        entry = self._repo.get(normalise_client_id(client_id))
        if entry is None:
            raise ValueError(f"{client_id.strip().upper()} is not on the qualifying list")
        return entry

    # ----- manual add / edit / remove (AC-1) --------------------------------------------------------------

    def add(self, client_id: str, actor: Actor) -> QualifyingEntry:
        actor = self._require_actor(actor)
        normalised = normalise_client_id(client_id)
        if self._repo.get(normalised) is not None:
            raise ValueError(f"{normalised} is already on the qualifying list")
        now = self._now()
        entry = self._new_entry(normalised, actor, now)
        self._repo.insert(entry)
        self._audit(actor, now, "add", normalised, None, entry)
        return entry

    @staticmethod
    def _new_entry(client_id: str, actor: Actor, now: datetime.datetime) -> QualifyingEntry:
        return QualifyingEntry(
            client_id=client_id,
            verification_status=VerificationStatus.UNVERIFIED,
            verified_at=None,
            platform_user_id=None,
            entitlement_status=EntitlementStatus.NOT_EVALUATED,
            added_by=actor.actor_id,
            added_at=now,
        )

    def edit(
        self,
        client_id: str,
        actor: Actor,
        *,
        new_client_id: str | _Unset = UNSET,
        verification_status: VerificationStatus | _Unset = UNSET,
        platform_user_id: str | None | _Unset = UNSET,
    ) -> QualifyingEntry:
        """Change an entry's Client ID (typo correction), verification status or linked platform user."""
        actor = self._require_actor(actor)
        before = self._require_entry(client_id)
        now = self._now()
        after = before
        if not isinstance(verification_status, _Unset):
            if not isinstance(verification_status, VerificationStatus):
                raise ValueError("verification_status must be a VerificationStatus")
            verified_at = now if verification_status is VerificationStatus.VERIFIED else None
            if verification_status is not before.verification_status:
                after = replace(after, verification_status=verification_status, verified_at=verified_at)
        if not isinstance(platform_user_id, _Unset):
            user = None if platform_user_id is None else _require_text(platform_user_id, "platform_user_id")
            after = replace(after, platform_user_id=user)
        renamed = False
        if not isinstance(new_client_id, _Unset):
            target = normalise_client_id(new_client_id)
            if target != before.client_id:
                if before.verification_status is VerificationStatus.VERIFIED or before.platform_user_id:
                    raise ValueError(
                        f"{before.client_id} is verified or linked to a user; remove it and add the new ID instead"
                    )
                if self._repo.get(target) is not None:
                    raise ValueError(f"{target} is already on the qualifying list")
                after = replace(after, client_id=target)
                renamed = True
        if after == before:
            raise ValueError(f"edit of {before.client_id} changes nothing")
        if renamed:
            self._repo.delete(before.client_id)
            self._repo.insert(after)
        else:
            self._repo.update(after)
        self._audit(actor, now, "edit", after.client_id, before, after)
        return after

    def record_entitlement_status(
        self, client_id: str, status: EntitlementStatus, actor: Actor
    ) -> QualifyingEntry:
        """Record the entitlement engine's status for an ID (input only; not computed here)."""
        actor = self._require_actor(actor)
        if not isinstance(status, EntitlementStatus):
            raise ValueError("status must be an EntitlementStatus")
        before = self._require_entry(client_id)
        if status is before.entitlement_status:
            raise ValueError(f"entitlement status of {before.client_id} is already {status.value}")
        after = replace(before, entitlement_status=status)
        now = self._now()
        self._repo.update(after)
        self._audit(actor, now, "entitlement_status", after.client_id, before, after)
        return after

    def remove(self, client_id: str, actor: Actor) -> None:
        """Take an ID off the list. Its audit history is kept (append-only)."""
        actor = self._require_actor(actor)
        before = self._require_entry(client_id)
        now = self._now()
        self._repo.delete(before.client_id)
        self._audit(actor, now, "remove", before.client_id, before, None)

    # ----- CSV import (AC-1, AC-2) ------------------------------------------------------------------------

    @staticmethod
    def _read_rows(request: ImportRequest) -> list[tuple[int, str]]:
        _require_text(request.file_name, "file_name")
        if not isinstance(request.csv_text, str):
            raise ValueError("csv_text must be a string")
        records = list(csv.reader(io.StringIO(request.csv_text.lstrip("﻿"))))
        if not records:
            raise ValueError(f"{request.file_name!r} is empty")
        header = [cell.strip().lower() for cell in records[0]]
        if header.count(CLIENT_ID_COLUMN) != 1:
            raise ValueError(f"{request.file_name!r} must have exactly one '{CLIENT_ID_COLUMN}' header column")
        column = header.index(CLIENT_ID_COLUMN)
        rows = [(n, rec[column] if column < len(rec) else "") for n, rec in enumerate(records[1:], start=2)]
        if not rows:
            raise ValueError(f"{request.file_name!r} has no data rows")
        known = {n for n, _ in rows}
        for n in set(request.edits) | set(request.excluded_rows):
            if n not in known:
                raise ValueError(f"row {n} does not exist in {request.file_name!r}")
        both = set(request.edits) & set(request.excluded_rows)
        if both:
            raise ValueError(f"rows {sorted(both)} are both edited and excluded")
        return rows

    def _classify_one(
        self, row_number: int, raw: str, seen: dict[str, int], edited: bool
    ) -> ImportRow:
        try:
            client_id = normalise_client_id(raw)
        except MalformedClientIdError as exc:
            return ImportRow(row_number, raw, None, RowCategory.MALFORMED, str(exc), edited)
        if client_id in seen:
            return ImportRow(
                row_number, raw, client_id, RowCategory.DUPLICATE_IN_FILE,
                f"{client_id} also appears on row {seen[client_id]}", edited,
            )
        seen[client_id] = row_number
        if self._repo.get(client_id) is not None:
            return ImportRow(
                row_number, raw, client_id, RowCategory.ALREADY_ON_LIST, f"{client_id} is already on the list", edited
            )
        return ImportRow(row_number, raw, client_id, RowCategory.NEW, f"{client_id} will be added", edited)

    def preview_import(self, request: ImportRequest) -> ImportReport:
        """Dry run: classify every data row; changes nothing."""
        seen: dict[str, int] = {}
        rows: list[ImportRow] = []
        for row_number, raw in self._read_rows(request):
            if row_number in request.excluded_rows:
                rows.append(ImportRow(row_number, raw, None, RowCategory.EXCLUDED, "excluded by admin", False))
                continue
            edited = row_number in request.edits
            value = request.edits[row_number] if edited else raw
            rows.append(self._classify_one(row_number, value, seen, edited))
        return ImportReport(request.file_name.strip(), tuple(rows))

    @staticmethod
    def _refuse_if_problems(report: ImportReport) -> None:
        if report.problems:
            raise ImportRefusedError(report)

    def apply_import(self, request: ImportRequest, actor: Actor) -> ImportRecord:
        """Apply an import: refused while any problem row is unresolved; adds only NEW rows, all or nothing."""
        actor = self._require_actor(actor)
        report = self.preview_import(request)
        self._refuse_if_problems(report)
        new_ids = [r.client_id for r in report.rows_in(RowCategory.NEW)]
        if len(set(new_ids)) != len(new_ids) or any(self._repo.get(cid) is not None for cid in new_ids):
            raise ValueError("import plan would add an ID twice; nothing was applied")
        now = self._now()
        import_id = f"IMP-{len(self._repo.import_records()) + 1:04d}"
        for client_id in new_ids:
            entry = self._new_entry(client_id, actor, now)
            self._repo.insert(entry)
            self._audit(actor, now, "import_add", client_id, None, entry, import_id=import_id)
        record = ImportRecord(
            import_id=import_id,
            actor_id=actor.actor_id,
            at=now,
            file_name=report.file_name,
            total_rows=len(report.rows),
            added=len(new_ids),
            already_on_list=len(report.rows_in(RowCategory.ALREADY_ON_LIST)),
            edited_rows=sum(1 for r in report.rows if r.edited),
            excluded_rows=len(report.rows_in(RowCategory.EXCLUDED)),
        )
        self._repo.append_import(record)
        return record

    # ----- read side: search/filter (AC-3), history and audit (AC-4), export (AC-5) ------------------------

    def get(self, client_id: str) -> QualifyingEntry | None:
        return self._repo.get(normalise_client_id(client_id))

    def search(
        self,
        *,
        id_prefix: str | None = None,
        verification_status: VerificationStatus | None = None,
        entitlement_status: EntitlementStatus | None = None,
        linked: bool | None = None,
    ) -> tuple[QualifyingEntry, ...]:
        """Entries matching every given filter, sorted by Client ID."""
        prefix = None
        if id_prefix is not None:
            prefix = _require_text(id_prefix, "id_prefix").upper()
            if not prefix.isalnum() or not prefix.isascii():
                raise ValueError("id_prefix must be letters and digits only")
        if verification_status is not None and not isinstance(verification_status, VerificationStatus):
            raise ValueError("verification_status must be a VerificationStatus")
        if entitlement_status is not None and not isinstance(entitlement_status, EntitlementStatus):
            raise ValueError("entitlement_status must be an EntitlementStatus")
        return tuple(
            e
            for e in self._repo.all_entries()
            if (prefix is None or e.client_id.startswith(prefix))
            and (verification_status is None or e.verification_status is verification_status)
            and (entitlement_status is None or e.entitlement_status is entitlement_status)
            and (linked is None or (e.platform_user_id is not None) is linked)
        )

    def import_history(self) -> tuple[ImportRecord, ...]:
        return self._repo.import_records()

    def audit_trail(self, client_id: str | None = None) -> tuple[AuditEntry, ...]:
        """All audit entries, or those touching one Client ID (including as the before-value of a rename)."""
        entries = self._repo.audit_entries()
        if client_id is None:
            return entries
        target = normalise_client_id(client_id)
        return tuple(
            a for a in entries
            if a.client_id == target or (a.before is not None and a.before["client_id"] == target)
        )

    def export_csv(self, entries: tuple[QualifyingEntry, ...] | None = None) -> str:
        """CSV of the given entries (default: the whole list), one row per ID, header first."""
        rows = self._repo.all_entries() if entries is None else entries
        out = io.StringIO()
        writer = csv.writer(out, lineterminator="\n")
        writer.writerow(EXPORT_COLUMNS)
        for entry in rows:
            snap = entry.snapshot()
            writer.writerow([_safe_cell(snap[c]) for c in EXPORT_COLUMNS])
        return out.getvalue()
