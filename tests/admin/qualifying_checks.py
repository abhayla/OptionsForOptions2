"""Shared scenario + assertions for the qualifying-list tests (W-010).

The real tests and the mutation tests call the SAME check functions, so a mutation test proves that the real
test's assertions would go red if the code regressed that way.
"""
from __future__ import annotations

import datetime

import pytest

from ofo.admin.qualifying import (
    ImportRefusedError,
    ImportRequest,
    QualifyingListService,
    RowCategory,
)
from ofo.admin.qualifying_store import Actor, InMemoryQualifyingRepository, ListStatus

ADMIN = Actor("admin:priya")
T0 = datetime.datetime(2026, 9, 29, 10, 0, tzinfo=datetime.timezone.utc)

# 10 data rows: 7 distinct valid IDs, 2 in-file duplicates (rows 5 and 9), 1 malformed (row 8).
# Header is row 1, so data rows are 2..11.
PROOF_CSV = (
    "client_id\n"
    "AB1234\n"       # row 2
    "cd5678\n"       # row 3  (lower case, normalised)
    " EF9012 \n"     # row 4  (padded, normalised)
    "ab1234\n"       # row 5  duplicate of row 2 after normalisation
    "GHJ345\n"       # row 6
    "KLM678\n"       # row 7
    "12AB34\n"       # row 8  malformed
    "MN4321\n"       # row 9
    "CD5678\n"       # row 10 duplicate of row 3
    "PQ8765\n"       # row 11
)
VALID_IDS = ["AB1234", "CD5678", "EF9012", "GHJ345", "KLM678", "MN4321", "PQ8765"]


class StepClock:
    """Deterministic clock: each call returns T0 plus one more minute."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> datetime.datetime:
        self.calls += 1
        return T0 + datetime.timedelta(minutes=self.calls)


def new_service(service_cls: type = QualifyingListService, repo: object | None = None) -> QualifyingListService:
    return service_cls(repo if repo is not None else InMemoryQualifyingRepository(), clock=StepClock())


def check_problems_reported_and_apply_refused(svc: QualifyingListService) -> None:
    """AC-2 core: dry run lists exactly the 3 problems; apply is refused and changes nothing."""
    request = ImportRequest("direct-customers.csv", PROOF_CSV)
    report = svc.preview_import(request)
    assert [(r.row_number, r.category) for r in report.problems] == [
        (5, RowCategory.DUPLICATE_IN_FILE),
        (8, RowCategory.MALFORMED),
        (10, RowCategory.DUPLICATE_IN_FILE),
    ]
    assert [r.client_id for r in report.rows_in(RowCategory.NEW)] == VALID_IDS
    with pytest.raises(ImportRefusedError) as refused:
        svc.apply_import(request, ADMIN)
    assert [r.row_number for r in refused.value.report.problems] == [5, 8, 10]
    assert svc.search() == ()
    assert svc.audit_trail() == ()
    assert svc.import_history() == ()


def resolved_request() -> ImportRequest:
    """The admin's resolution: exclude the two duplicates, and exclude the malformed row."""
    return ImportRequest("direct-customers.csv", PROOF_CSV, excluded_rows=frozenset({5, 8, 10}))


def check_resolved_apply_adds_exactly_once(svc: QualifyingListService) -> None:
    """AC-2 core: after resolving, apply adds the 7 valid IDs; the same import again adds 0; one audit per change."""
    first = svc.apply_import(resolved_request(), ADMIN)
    assert (first.added, first.already_on_list, first.excluded_rows, first.total_rows) == (7, 0, 3, 10)
    assert [e.client_id for e in svc.search()] == sorted(VALID_IDS)
    second = svc.apply_import(resolved_request(), ADMIN)
    assert (second.added, second.already_on_list) == (0, 7)
    assert [e.client_id for e in svc.search()] == sorted(VALID_IDS)
    audit = svc.audit_trail()
    assert [(a.action, a.client_id, a.import_id) for a in audit] == [
        ("import_add", cid, "IMP-0001") for cid in VALID_IDS
    ]
    assert [(h.import_id, h.added) for h in svc.import_history()] == [("IMP-0001", 7), ("IMP-0002", 0)]


def check_removal_deactivates_and_keeps_audit(svc: QualifyingListService) -> None:
    """AC-1/AC-4: removing an ID deactivates it (entry kept, no longer qualifying), keeps its full audit history,
    and is reversible with reactivate."""
    svc.add("AB1234", ADMIN)
    svc.remove("AB1234", ADMIN)
    entry = svc.get("AB1234")
    assert entry is not None and entry.list_status is ListStatus.INACTIVE
    assert svc.is_qualifying("AB1234") is False
    assert [e.client_id for e in svc.search(list_status=ListStatus.INACTIVE)] == ["AB1234"]
    trail = svc.audit_trail("AB1234")
    assert [a.action for a in trail] == ["add", "deactivate"]
    assert (trail[1].before["list_status"], trail[1].after["list_status"]) == ("ACTIVE", "INACTIVE")
    svc.reactivate("AB1234", ADMIN)
    assert svc.is_qualifying("AB1234") is True
    assert [a.action for a in svc.audit_trail("AB1234")] == ["add", "deactivate", "reactivate"]


# ----- class: untrusted text transformed before a strict-charset check (W-010 rounds 2-3) ----------------------
# Each contaminant is inserted BEFORE, INSIDE and AFTER "AB1234"; every entry path must treat the result as malformed.
CONTAMINANTS = {
    "NBSP": " ", "IDEOGRAPHIC_SPACE": "　", "EM_SPACE": " ", "EN_SPACE": " ",
    "THIN_SPACE": " ", "ZERO_WIDTH_SPACE": "​", "ZWJ": "‍", "LINE_SEP": " ",
    "PARA_SEP": " ", "NEL": "\u0085", "BOM": "﻿", "LRM": "‎", "RLM": "‏",
    "SOFT_HYPHEN": "­", "DOTLESS_I": "ı", "SHARP_S": "ß", "LONG_S": "ſ",
    "CYRILLIC_A": "А", "FULLWIDTH_1": "１",
}
CONTAMINATED = [
    (f"{name}-{where}", value)
    for name, c in CONTAMINANTS.items()
    for where, value in (("before", c + "AB1234"), ("inside", "AB1" + c + "234"), ("after", "AB1234" + c))
]
ASCII_PADDED = [" AB1234", "\tAB1234 ", "AB1234\t\t", "  ab1234  "]


def check_every_path_rejects(value: str) -> None:
    """add, edit(new_client_id), preview/apply import, search(id_prefix) and is_qualifying all refuse ``value``."""
    svc = new_service()
    with pytest.raises(ValueError):
        svc.add(value, ADMIN)
    assert svc.search() == ()

    svc.add("CD5678", ADMIN)
    with pytest.raises(ValueError):
        svc.edit("CD5678", ADMIN, new_client_id=value)
    assert [e.client_id for e in svc.search()] == ["CD5678"]

    request = ImportRequest("f.csv", f"client_id\n{value}\n")
    assert [(r.row_number, r.category) for r in svc.preview_import(request).problems] == [
        (2, RowCategory.MALFORMED)
    ]
    with pytest.raises(ImportRefusedError):
        svc.apply_import(request, ADMIN)

    svc.add("AB1234", ADMIN)
    with pytest.raises(ValueError):
        svc.search(id_prefix=value)
    assert svc.is_qualifying(value) is False
    assert [e.client_id for e in svc.search()] == ["AB1234", "CD5678"]


def check_class_rejected_everywhere() -> None:
    """Every contaminated value is refused on every entry path."""
    for _, value in CONTAMINATED:
        check_every_path_rejects(value)
