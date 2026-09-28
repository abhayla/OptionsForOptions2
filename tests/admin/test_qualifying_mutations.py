"""Tier A mutation tests for W-010: each seeded defect must turn the real tests' checks red.

Each mutant is the real service/repository with ONE behaviour broken. The check functions are the same ones the
AC tests call (``qualifying_checks``), so if a mutant survived, the AC tests would not catch that regression.
"""
from __future__ import annotations

import pytest

from qualifying_checks import (
    ADMIN,
    check_problems_reported_and_apply_refused,
    check_removal_keeps_audit,
    check_resolved_apply_adds_exactly_once,
    new_service,
)
from ofo.admin.qualifying import ImportReport, ImportRow, QualifyingListService
from ofo.admin.qualifying_store import InMemoryQualifyingRepository

# A check "goes red" by a failed assert or a failed pytest.raises (pytest.fail.Exception).
CHECK_FAILED = (AssertionError, pytest.fail.Exception)


class ApplyIgnoresProblems(QualifyingListService):
    """Mutant (a): apply goes ahead even when the report still has unresolved problems."""

    @staticmethod
    def _refuse_if_problems(report: ImportReport) -> None:
        return None


class ForgetsEarlierRows(QualifyingListService):
    """Mutant (b): in-file duplicate detection forgets earlier rows, so a duplicate is treated as new."""

    def _classify_one(self, row_number: int, raw: str, seen: dict[str, int], edited: bool) -> ImportRow:
        return super()._classify_one(row_number, raw, {}, edited)


class OverwritingRepository(InMemoryQualifyingRepository):
    """Mutant (b'): the store silently accepts a second insert of the same ID (upsert)."""

    def insert(self, entry) -> None:  # type: ignore[no-untyped-def]
        self._entries[entry.client_id] = entry


class ApplyBlindToList(QualifyingListService):
    """Mutant (b''): apply does not look at the current list, over a store that overwrites, so a re-import
    re-adds every ID (the idempotency the exactly-once check guards)."""

    def apply_import(self, request, actor):  # type: ignore[no-untyped-def]
        original = self._repo.get
        self._repo.get = lambda cid: None  # type: ignore[method-assign]
        try:
            return super().apply_import(request, actor)
        finally:
            self._repo.get = original  # type: ignore[method-assign]


class PurgingRepository(InMemoryQualifyingRepository):
    """Mutant (c): removing an ID also deletes its audit history."""

    def delete(self, client_id: str) -> None:
        super().delete(client_id)
        self._audit = [a for a in self._audit if a.client_id != client_id]


def test_real_code_passes_every_check() -> None:
    """AC-2/AC-4 control: the unmutated service passes all three checks."""
    svc = new_service()
    check_problems_reported_and_apply_refused(svc)
    check_resolved_apply_adds_exactly_once(svc)
    check_removal_keeps_audit(new_service())


def test_mutant_apply_ignores_unresolved_problems_is_caught() -> None:
    """AC-2 mutation (a): if apply ignored unresolved problems, the refusal check fails."""
    with pytest.raises(CHECK_FAILED):
        check_problems_reported_and_apply_refused(new_service(ApplyIgnoresProblems))


def test_mutant_duplicate_in_file_applied_twice_is_caught() -> None:
    """AC-2 mutation (b): if in-file duplicates were not detected, the 3-problem check fails."""
    with pytest.raises(CHECK_FAILED):
        check_problems_reported_and_apply_refused(new_service(ForgetsEarlierRows))


def test_mutant_reimport_applies_again_is_caught() -> None:
    """AC-2 mutation (b): if a re-import added already-listed IDs again, the exactly-once check fails."""
    svc = new_service(ApplyBlindToList, OverwritingRepository())
    with pytest.raises(CHECK_FAILED):
        check_resolved_apply_adds_exactly_once(svc)


def test_mutant_removal_deletes_audit_history_is_caught() -> None:
    """AC-4 mutation (c): if removal deleted audit history, the audit-kept check fails."""
    with pytest.raises(CHECK_FAILED):
        check_removal_keeps_audit(new_service(repo=PurgingRepository()))


def test_mutant_upserting_store_alone_is_still_blocked_by_service() -> None:
    """AC-2: even over a store that would overwrite, the real service never adds an ID twice."""
    svc = new_service(repo=OverwritingRepository())
    check_resolved_apply_adds_exactly_once(svc)
    with pytest.raises(ValueError):
        svc.add("AB1234", ADMIN)
