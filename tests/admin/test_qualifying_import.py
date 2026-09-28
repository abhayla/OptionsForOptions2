"""W-010 core proof and REQ-020 AC-2: duplicates and malformed rows block an import until resolved."""
from __future__ import annotations

import pytest

from qualifying_checks import (
    ADMIN,
    PROOF_CSV,
    check_problems_reported_and_apply_refused,
    check_resolved_apply_adds_exactly_once,
    new_service,
)
from ofo.admin.qualifying import ImportRefusedError, ImportRequest, RowCategory


def test_core_import_refused_until_resolved_then_applied_exactly_once() -> None:
    """AC-2: 10-row CSV (7 valid, 2 duplicate, 1 malformed) -> 3 problems, apply refused; resolved -> adds 7 once."""
    svc = new_service()
    check_problems_reported_and_apply_refused(svc)
    check_resolved_apply_adds_exactly_once(svc)


def test_resolution_by_editing_rows() -> None:
    """AC-2: an admin may fix a problem row by editing its value; an edit to another bad value stays a problem."""
    svc = new_service()
    still_bad = ImportRequest("f.csv", PROOF_CSV, edits={8: "AB12"}, excluded_rows=frozenset({5, 10}))
    assert [(r.row_number, r.category) for r in svc.preview_import(still_bad).problems] == [
        (8, RowCategory.MALFORMED)
    ]
    with pytest.raises(ImportRefusedError):
        svc.apply_import(still_bad, ADMIN)
    fixed = ImportRequest("f.csv", PROOF_CSV, edits={8: "rs2468", 5: "TU1357"}, excluded_rows=frozenset({10}))
    record = svc.apply_import(fixed, ADMIN)
    assert (record.added, record.edited_rows, record.excluded_rows) == (9, 2, 1)
    assert svc.get("RS2468") is not None and svc.get("TU1357") is not None


def test_edit_that_creates_a_new_duplicate_is_still_refused() -> None:
    """AC-2: resolving one duplicate by editing it into another ID already in the file is still a duplicate."""
    svc = new_service()
    request = ImportRequest("f.csv", PROOF_CSV, edits={5: "PQ8765", 8: "XY1111"}, excluded_rows=frozenset({10}))
    problems = svc.preview_import(request).problems
    assert [(r.row_number, r.category, r.client_id) for r in problems] == [
        (11, RowCategory.DUPLICATE_IN_FILE, "PQ8765")
    ]
    assert "row 5" in problems[0].message


def test_apply_revalidates_against_the_list_at_apply_time() -> None:
    """AC-2: an ID added manually after the preview is skipped as already-on-list, never added twice."""
    svc = new_service()
    request = ImportRequest("f.csv", "client_id\nAB1234\nCD5678\n")
    assert [r.category for r in svc.preview_import(request).rows] == [RowCategory.NEW, RowCategory.NEW]
    svc.add("CD5678", ADMIN)
    record = svc.apply_import(request, ADMIN)
    assert (record.added, record.already_on_list) == (1, 1)
    assert [a.action for a in svc.audit_trail("CD5678")] == ["add"]


def test_already_on_list_is_not_a_problem_but_blank_rows_are() -> None:
    """AC-2: an ID already on the list is skipped (not a problem); an empty cell or blank line is malformed."""
    svc = new_service()
    svc.add("AB1234", ADMIN)
    report = svc.preview_import(ImportRequest("f.csv", "Client_ID,name\nAB1234,x\n,y\n\nCD5678,z\n"))
    assert [(r.row_number, r.category) for r in report.rows] == [
        (2, RowCategory.ALREADY_ON_LIST),
        (3, RowCategory.MALFORMED),
        (4, RowCategory.MALFORMED),
        (5, RowCategory.NEW),
    ]


@pytest.mark.parametrize(
    "request_",
    [
        ImportRequest("f.csv", ""),
        ImportRequest("f.csv", "client_id\n"),
        ImportRequest("f.csv", "id\nAB1234\n"),
        ImportRequest("f.csv", "client_id,client_id\nAB1234,AB1234\n"),
        ImportRequest("", "client_id\nAB1234\n"),
        ImportRequest("f.csv", "client_id\nAB1234\n", excluded_rows=frozenset({9})),
        ImportRequest("f.csv", "client_id\nAB1234\n", edits={7: "CD5678"}),
        ImportRequest("f.csv", "client_id\nAB1234\n", edits={2: "CD5678"}, excluded_rows=frozenset({2})),
    ],
)
def test_unusable_files_and_resolutions_fail_closed(request_: ImportRequest) -> None:
    """AC-2: empty file, no data rows, missing/doubled header, unknown or contradictory resolutions raise."""
    svc = new_service()
    with pytest.raises(ValueError):
        svc.preview_import(request_)
    with pytest.raises(ValueError):
        svc.apply_import(request_, ADMIN)
    assert svc.search() == () and svc.import_history() == ()


def test_apply_requires_explicit_actor() -> None:
    """AC-2: apply without an Actor is refused; there is no ambient admin."""
    svc = new_service()
    with pytest.raises(ValueError):
        svc.apply_import(ImportRequest("f.csv", "client_id\nAB1234\n"), "admin:priya")  # type: ignore[arg-type]
    assert svc.search() == ()


def test_inactive_id_in_import_is_a_problem_until_admin_chooses() -> None:
    """AC-2: an INACTIVE ID in a CSV is reported as INACTIVE_ON_LIST and blocks apply; it is never silently
    reactivated. The admin either excludes the row or asks for reactivation, which is audited with the import id."""
    svc = new_service()
    svc.add("AB1234", ADMIN)
    svc.remove("AB1234", ADMIN)
    request = ImportRequest("f.csv", "client_id\nAB1234\nCD5678\n")
    assert [(r.row_number, r.category) for r in svc.preview_import(request).problems] == [
        (2, RowCategory.INACTIVE_ON_LIST)
    ]
    with pytest.raises(ImportRefusedError):
        svc.apply_import(request, ADMIN)
    assert svc.is_qualifying("AB1234") is False and svc.get("CD5678") is None

    excluded = svc.apply_import(ImportRequest("f.csv", request.csv_text, excluded_rows=frozenset({2})), ADMIN)
    assert (excluded.added, excluded.reactivated, excluded.excluded_rows) == (1, 0, 1)
    assert svc.is_qualifying("AB1234") is False

    chosen = ImportRequest("f.csv", request.csv_text, reactivate_rows=frozenset({2}))
    assert [r.category for r in svc.preview_import(chosen).rows] == [
        RowCategory.REACTIVATE, RowCategory.ALREADY_ON_LIST,
    ]
    record = svc.apply_import(chosen, ADMIN)
    assert (record.import_id, record.added, record.reactivated, record.already_on_list) == ("IMP-0002", 0, 1, 1)
    assert svc.is_qualifying("AB1234") is True
    last = svc.audit_trail("AB1234")[-1]
    assert (last.action, last.import_id, last.before["list_status"], last.after["list_status"]) == (
        "reactivate", "IMP-0002", "INACTIVE", "ACTIVE",
    )
    again = svc.apply_import(ImportRequest("f.csv", request.csv_text), ADMIN)
    assert (again.added, again.reactivated, again.already_on_list) == (0, 0, 2)


def test_reactivate_rows_fail_closed() -> None:
    """AC-2: asking to reactivate a row that is not an INACTIVE ID, or both reactivating and excluding it, raises."""
    svc = new_service()
    svc.add("AB1234", ADMIN)
    svc.remove("AB1234", ADMIN)
    text = "client_id\nAB1234\nCD5678\n"
    with pytest.raises(ValueError):
        svc.preview_import(ImportRequest("f.csv", text, reactivate_rows=frozenset({3})))
    with pytest.raises(ValueError):
        svc.preview_import(
            ImportRequest("f.csv", text, reactivate_rows=frozenset({2}), excluded_rows=frozenset({2}))
        )
    with pytest.raises(ValueError):
        svc.apply_import(ImportRequest("f.csv", text, reactivate_rows=frozenset({9})), ADMIN)
    assert svc.is_qualifying("AB1234") is False and svc.get("CD5678") is None
