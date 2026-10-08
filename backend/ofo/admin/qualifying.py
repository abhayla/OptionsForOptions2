"""Admin service for the qualifying Zerodha Client ID list (REQ-020 AC-1..AC-5; ADR-024 Q70; REQ-064).

Spec: REQ-020 (import, validation, search/filter, per-ID status, import history, audit, export); ADR-024 Q70
("duplicates/malformed IDs validated before applying"); ADR-022 (the Client ID is the identity); REQ-064 AC-2
(audit is append-only).

Import is two-step. ``preview_import`` returns a dry-run report that classifies every data row. ``apply_import``
re-runs that classification against the list as it is NOW and refuses (``ImportRefusedError``) while any row is a
problem (malformed or duplicated within the file); the admin resolves a problem by editing the row's value or by
explicitly excluding the row in the ``ImportRequest``. A row whose ID is already on the list and ACTIVE is not a
problem: it is skipped, so re-importing the same file changes nothing. A row whose ID is on the list but INACTIVE is
a problem (``INACTIVE_ON_LIST``) until the admin chooses to reactivate it (``reactivate_rows``) or exclude it; an
import never reactivates an ID silently. A fully blank line (empty, whitespace-only or commas-only) is skipped and
counted in ``ImportReport.blank_lines_ignored``; it is never a problem. Every change writes one audit entry.

Import reads only the ``client_id`` column. Importing an export into a fresh list therefore adds every ID as ACTIVE
and UNVERIFIED with no user link: list status, verification and associations are NOT restored. Import is for
adding IDs, not for restoring a backup.

Removing an ID DEACTIVATES it (ADR-024 Q70 "deactivate"; decided under ADR-045 from the admin's intent: free Pro
should stop, the record and its history stay, and the change is reversible with ``reactivate``). ``is_qualifying``
is the check complimentary-Pro matching (W-011) uses: only an ACTIVE entry qualifies, and a malformed ID
returns False (fail closed) rather than raising. Entitlement status is an input
from the entitlement engine (``record_entitlement_status``), never computed here.
"""
from __future__ import annotations
from ofo.errors.explanations import render_explanation

import csv
import datetime
import io
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Callable, Mapping

from ofo.admin import untrusted_text
from ofo.admin.client_id import MalformedClientIdError, normalise_client_id
from ofo.admin.qualifying_store import (
    Actor,
    AuditEntry,
    EntitlementStatus,
    ImportRecord,
    ListStatus,
    QualifyingEntry,
    QualifyingRepository,
    VerificationStatus,
)

CLIENT_ID_COLUMN = "client_id"
EXPORT_COLUMNS = (
    "client_id",
    "list_status",
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
    INACTIVE_ON_LIST = "INACTIVE_ON_LIST"
    REACTIVATE = "REACTIVATE"
    DUPLICATE_IN_FILE = "DUPLICATE_IN_FILE"
    MALFORMED = "MALFORMED"
    EXCLUDED = "EXCLUDED"


PROBLEM_CATEGORIES = frozenset(
    {RowCategory.DUPLICATE_IN_FILE, RowCategory.MALFORMED, RowCategory.INACTIVE_ON_LIST}
)


@dataclass(frozen=True)
class ImportRequest:
    """A CSV file plus the admin's resolutions: per-row replacement values, explicitly excluded rows, and rows
    whose INACTIVE ID the admin chose to reactivate.

    Row numbers are spreadsheet line numbers: the header is row 1, the first data row is row 2.
    """

    file_name: str
    csv_text: str
    edits: Mapping[int, str] = field(default_factory=dict)
    excluded_rows: frozenset[int] = frozenset()
    reactivate_rows: frozenset[int] = frozenset()


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
    blank_lines_ignored: int = 0

    @property
    def problems(self) -> tuple[ImportRow, ...]:
        return tuple(r for r in self.rows if r.category in PROBLEM_CATEGORIES)

    def rows_in(self, category: RowCategory) -> tuple[ImportRow, ...]:
        return tuple(r for r in self.rows if r.category is category)


class ImportRefusedError(ValueError):
    """Apply was refused because the report still has unresolved problem rows."""

    def __init__(self, report: ImportReport) -> None:
        self.report = report
        rows = tuple(render_explanation("import_row_ref", number=r.row_number, category=r.category.value)
                     for r in report.problems)
        super().__init__(render_explanation("import_refused", file=repr(report.file_name), rows=rows))


class _Unset:
    """Marker for 'field not given' in ``edit`` (None is a real value: unlink the user)."""


UNSET = _Unset()


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _require_text(value: object, name: str) -> str:
    """Non-empty free text (file name, platform user id). Not for anything checked against a strict character set:
    those go through ``untrusted_text.ascii_token``. Unicode strip() is acceptable here because the value is stored
    and displayed, never matched against a pattern or used as a list key."""
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
            raise ValueError(f"{client_id!r} is not on the qualifying list")
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
            list_status=ListStatus.ACTIVE,
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

    def _set_list_status(self, client_id: str, actor: Actor, status: ListStatus, action: str) -> QualifyingEntry:
        actor = self._require_actor(actor)
        before = self._require_entry(client_id)
        if before.list_status is status:
            raise ValueError(f"{before.client_id} is already {status.value}")
        after = replace(before, list_status=status)
        now = self._now()
        self._repo.update(after)
        self._audit(actor, now, action, after.client_id, before, after)
        return after

    def remove(self, client_id: str, actor: Actor) -> QualifyingEntry:
        """Deactivate an ID: it stops qualifying, but the entry and its audit history stay (reversible)."""
        return self._set_list_status(client_id, actor, ListStatus.INACTIVE, "deactivate")

    def reactivate(self, client_id: str, actor: Actor) -> QualifyingEntry:
        """Make a deactivated ID qualify again."""
        return self._set_list_status(client_id, actor, ListStatus.ACTIVE, "reactivate")

    def is_qualifying(self, client_id: str) -> bool:
        """True only for an ID on the list with list status ACTIVE (used by complimentary-Pro matching).

        A malformed ID returns False: it can never be on the list, so it never qualifies (fail closed).
        """
        try:
            normalised = normalise_client_id(client_id)
        except MalformedClientIdError:
            return False
        entry = self._repo.get(normalised)
        return entry is not None and entry.list_status is ListStatus.ACTIVE

    # ----- CSV import (AC-1, AC-2) ------------------------------------------------------------------------

    @staticmethod
    def _read_rows(request: ImportRequest) -> tuple[list[tuple[int, str]], int]:
        _require_text(request.file_name, "file_name")
        if not isinstance(request.csv_text, str):
            raise ValueError("csv_text must be a string")
        # Removes only a file-level byte-order mark before the header; data cells are never transformed here.
        records = list(csv.reader(io.StringIO(request.csv_text.lstrip("﻿"))))
        if not records:
            raise ValueError(f"{request.file_name!r} is empty")
        # Raw ASCII check before any strip()/lower(), so no non-ASCII header can become "client_id".
        header = [cell.strip(untrusted_text.ASCII_BLANKS).lower() if cell.isascii() else cell for cell in records[0]]
        if header.count(CLIENT_ID_COLUMN) != 1:
            raise ValueError(f"{request.file_name!r} must have exactly one '{CLIENT_ID_COLUMN}' header column")
        column = header.index(CLIENT_ID_COLUMN)
        rows: list[tuple[int, str]] = []
        blank = 0
        for n, rec in enumerate(records[1:], start=2):
            # Blank = only ASCII spaces/tabs; a cell of NBSP etc. is data (reported MALFORMED), never skipped.
            if all(not cell.strip(untrusted_text.ASCII_BLANKS) for cell in rec):
                blank += 1
                continue
            rows.append((n, rec[column] if column < len(rec) else ""))
        if not rows:
            raise ValueError(f"{request.file_name!r} has no data rows")
        known = {n for n, _ in rows}
        for n in set(request.edits) | set(request.excluded_rows) | set(request.reactivate_rows):
            if n not in known:
                raise ValueError(f"row {n} does not exist in {request.file_name!r}")
        both = set(request.edits) & set(request.excluded_rows)
        if both:
            raise ValueError(f"rows {sorted(both)} are both edited and excluded")
        both = set(request.reactivate_rows) & set(request.excluded_rows)
        if both:
            raise ValueError(f"rows {sorted(both)} are both reactivated and excluded")
        return rows, blank

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
                render_explanation("import_row_duplicate", client_id=client_id, row=seen[client_id]), edited,
            )
        seen[client_id] = row_number
        existing = self._repo.get(client_id)
        if existing is not None and existing.list_status is ListStatus.INACTIVE:
            return ImportRow(
                row_number, raw, client_id, RowCategory.INACTIVE_ON_LIST,
                render_explanation("import_row_inactive", client_id=client_id), edited,
            )
        if existing is not None:
            return ImportRow(
                row_number, raw, client_id, RowCategory.ALREADY_ON_LIST, render_explanation("import_row_already", client_id=client_id), edited
            )
        return ImportRow(row_number, raw, client_id, RowCategory.NEW, render_explanation("import_row_new", client_id=client_id), edited)

    def preview_import(self, request: ImportRequest) -> ImportReport:
        """Dry run: classify every data row; changes nothing."""
        seen: dict[str, int] = {}
        rows: list[ImportRow] = []
        data_rows, blank = self._read_rows(request)
        for row_number, raw in data_rows:
            if row_number in request.excluded_rows:
                rows.append(ImportRow(row_number, raw, None, RowCategory.EXCLUDED, render_explanation("import_row_excluded"), False))
                continue
            edited = row_number in request.edits
            value = request.edits[row_number] if edited else raw
            row = self._classify_one(row_number, value, seen, edited)
            if row_number in request.reactivate_rows:
                if row.category is not RowCategory.INACTIVE_ON_LIST:
                    raise ValueError(
                        f"row {row_number} cannot be reactivated: it is {row.category.value}, not INACTIVE_ON_LIST"
                    )
                row = replace(row, category=RowCategory.REACTIVATE, message=render_explanation("import_row_reactivated", client_id=row.client_id))
            rows.append(row)
        return ImportReport(request.file_name.strip(), tuple(rows), blank)

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
        reactivate_ids = [r.client_id for r in report.rows_in(RowCategory.REACTIVATE)]
        now = self._now()
        import_id = f"IMP-{len(self._repo.import_records()) + 1:04d}"
        for client_id in new_ids:
            entry = self._new_entry(client_id, actor, now)
            self._repo.insert(entry)
            self._audit(actor, now, "import_add", client_id, None, entry, import_id=import_id)
        for client_id in reactivate_ids:
            before = self._require_entry(client_id)
            after = replace(before, list_status=ListStatus.ACTIVE)
            self._repo.update(after)
            self._audit(actor, now, "reactivate", client_id, before, after, import_id=import_id)
        record = ImportRecord(
            import_id=import_id,
            actor_id=actor.actor_id,
            at=now,
            file_name=report.file_name,
            total_rows=len(report.rows),
            added=len(new_ids),
            already_on_list=len(report.rows_in(RowCategory.ALREADY_ON_LIST)),
            reactivated=len(reactivate_ids),
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
        list_status: ListStatus | None = None,
        verification_status: VerificationStatus | None = None,
        entitlement_status: EntitlementStatus | None = None,
        linked: bool | None = None,
    ) -> tuple[QualifyingEntry, ...]:
        """Entries matching every given filter, sorted by Client ID."""
        prefix = None
        if id_prefix is not None:
            prefix = untrusted_text.ascii_token(id_prefix, "id_prefix")
            if not prefix.isalnum():
                raise ValueError("id_prefix must be letters and digits only")
            prefix = prefix.upper()
        if list_status is not None and not isinstance(list_status, ListStatus):
            raise ValueError("list_status must be a ListStatus")
        if verification_status is not None and not isinstance(verification_status, VerificationStatus):
            raise ValueError("verification_status must be a VerificationStatus")
        if entitlement_status is not None and not isinstance(entitlement_status, EntitlementStatus):
            raise ValueError("entitlement_status must be an EntitlementStatus")
        return tuple(
            e
            for e in self._repo.all_entries()
            if (prefix is None or e.client_id.startswith(prefix))
            and (list_status is None or e.list_status is list_status)
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
