"""REQ-020 AC-4: import history and a full, append-only audit trail (REQ-064 AC-2)."""
from __future__ import annotations

import dataclasses

import pytest

from qualifying_checks import ADMIN, check_removal_deactivates_and_keeps_audit, new_service
from ofo.admin.qualifying import ImportRequest
from ofo.admin.qualifying_store import Actor, EntitlementStatus, InMemoryQualifyingRepository, VerificationStatus


def test_every_change_audited_with_who_when_what_before_after() -> None:
    """AC-4: add, import, edit, rename, entitlement input and remove each write one audit entry, in order."""
    svc = new_service()
    other = Actor("admin:ravi")
    svc.add("AB1234", ADMIN)
    svc.apply_import(ImportRequest("june.csv", "client_id\nCD5678\n"), other)
    svc.edit("AB1234", ADMIN, verification_status=VerificationStatus.VERIFIED)
    svc.edit("CD5678", other, new_client_id="CD5679")
    svc.record_entitlement_status("AB1234", EntitlementStatus.ACTIVE, Actor("system:entitlement-engine"))
    svc.remove("CD5679", ADMIN)

    trail = svc.audit_trail()
    assert [(a.sequence, a.actor_id, a.action, a.client_id) for a in trail] == [
        (1, "admin:priya", "add", "AB1234"),
        (2, "admin:ravi", "import_add", "CD5678"),
        (3, "admin:priya", "edit", "AB1234"),
        (4, "admin:ravi", "edit", "CD5679"),
        (5, "system:entitlement-engine", "entitlement_status", "AB1234"),
        (6, "admin:priya", "deactivate", "CD5679"),
    ]
    times = [a.at for a in trail]
    assert times == sorted(times) and len(set(times)) == 6
    assert trail[0].before is None and trail[0].after["verification_status"] == "UNVERIFIED"
    assert (trail[2].before["verification_status"], trail[2].after["verification_status"]) == (
        "UNVERIFIED", "VERIFIED",
    )
    assert (trail[3].before["client_id"], trail[3].after["client_id"]) == ("CD5678", "CD5679")
    assert (trail[4].before["entitlement_status"], trail[4].after["entitlement_status"]) == (
        "NOT_EVALUATED", "ACTIVE",
    )
    assert trail[1].import_id == "IMP-0001" and trail[0].import_id is None
    # The renamed ID's history is reachable from both its old and its new ID.
    assert [a.action for a in svc.audit_trail("CD5678")] == ["import_add", "edit"]
    assert [a.action for a in svc.audit_trail("CD5679")] == ["edit", "deactivate"]


def test_import_history_records_who_when_file_and_counts() -> None:
    """AC-4: each applied import is kept with actor, time, file name and counts; a refused one records nothing."""
    svc = new_service()
    svc.apply_import(ImportRequest("june.csv", "client_id\nAB1234\nCD5678\n"), ADMIN)
    with pytest.raises(ValueError):
        svc.apply_import(ImportRequest("bad.csv", "client_id\nAB1234\nab1234\n"), ADMIN)
    svc.apply_import(
        ImportRequest("july.csv", "client_id\nAB1234\nEF9012\nxx\n", edits={4: "GH3456"}), Actor("admin:ravi")
    )
    history = svc.import_history()
    assert [
        (h.import_id, h.actor_id, h.file_name, h.total_rows, h.added, h.already_on_list, h.edited_rows,
         h.excluded_rows)
        for h in history
    ] == [
        ("IMP-0001", "admin:priya", "june.csv", 2, 2, 0, 0, 0),
        ("IMP-0002", "admin:ravi", "july.csv", 3, 2, 1, 1, 0),
    ]
    assert history[0].at < history[1].at


def test_removal_keeps_audit_history() -> None:
    """AC-4: removing an ID never deletes its audit history."""
    check_removal_deactivates_and_keeps_audit(new_service())


def test_audit_records_are_immutable() -> None:
    """AC-4: an audit entry and its before/after snapshots cannot be changed, and the repository has no delete."""
    svc = new_service()
    svc.add("AB1234", ADMIN)
    entry = svc.audit_trail()[0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        entry.action = "tampered"  # type: ignore[misc]
    with pytest.raises(TypeError):
        entry.after["client_id"] = "ZZ0000"  # type: ignore[index]
    assert not any(hasattr(InMemoryQualifyingRepository, name) for name in ("delete_audit", "update_audit"))
    returned = svc.audit_trail()
    assert isinstance(returned, tuple)
