"""REQ-020 AC-1 (import + manual add/edit/remove), AC-3 (search/filter, per-ID status), AC-5 (export)."""
from __future__ import annotations

import pytest

from qualifying_checks import ADMIN, T0, new_service
from ofo.admin.client_id import MalformedClientIdError, normalise_client_id
from ofo.admin.qualifying import ImportRequest
from ofo.admin.qualifying_store import Actor, EntitlementStatus, ListStatus, VerificationStatus

ENGINE = Actor("system:entitlement-engine")


# ----- AC-1 ---------------------------------------------------------------------------------------------------

def test_bulk_import_then_manual_add_edit_remove() -> None:
    """AC-1: bulk CSV import, then manual add, edit (verification, user link, ID typo fix) and remove."""
    svc = new_service()
    record = svc.apply_import(ImportRequest("batch1.csv", "client_id\nAB1234\nCD5678\n"), ADMIN)
    assert record.added == 2

    added = svc.add(" ef9012 ", ADMIN)
    assert (added.client_id, added.verification_status, added.entitlement_status, added.platform_user_id) == (
        "EF9012", VerificationStatus.UNVERIFIED, EntitlementStatus.NOT_EVALUATED, None,
    )
    assert added.added_by == "admin:priya"

    fixed = svc.edit("CD5678", ADMIN, new_client_id="CD5679")
    assert fixed.client_id == "CD5679" and svc.get("CD5678") is None

    verified = svc.edit("AB1234", ADMIN, verification_status=VerificationStatus.VERIFIED, platform_user_id="user-42")
    assert (verified.verification_status, verified.platform_user_id) == (VerificationStatus.VERIFIED, "user-42")
    assert verified.verified_at is not None and verified.verified_at > T0

    unlinked = svc.edit("AB1234", ADMIN, platform_user_id=None)
    assert unlinked.platform_user_id is None

    svc.remove("EF9012", ADMIN)
    assert [e.client_id for e in svc.search(list_status=ListStatus.ACTIVE)] == ["AB1234", "CD5679"]
    assert [e.client_id for e in svc.search(list_status=ListStatus.INACTIVE)] == ["EF9012"]
    assert (svc.is_qualifying("EF9012"), svc.is_qualifying("ab1234")) == (False, True)
    svc.reactivate("EF9012", ADMIN)
    assert svc.is_qualifying("EF9012") is True


@pytest.mark.parametrize("raw", ["AB12", "AB", "A1234", "ABCD1234", "AB1234567", "12AB34", "AB-1234", "", "  ", "AB 1234"])
def test_malformed_ids_rejected(raw: str) -> None:
    """AC-1: manual add refuses anything that is not 2-3 letters then 3-6 digits."""
    svc = new_service()
    with pytest.raises(MalformedClientIdError):
        svc.add(raw, ADMIN)
    assert svc.search() == ()


def test_normalisation_is_trim_and_upper_only() -> None:
    """AC-1: the only repair is trimming and upper-casing."""
    assert normalise_client_id("  ab1234\t") == "AB1234"
    assert normalise_client_id("xyz123456") == "XYZ123456"
    with pytest.raises(MalformedClientIdError):
        normalise_client_id(1234)  # type: ignore[arg-type]


@pytest.mark.parametrize("raw", ["\u0131b1234", "a\u00df123", "\u017ft12345", "AB\uff11\uff12\uff13\uff14"])
def test_non_ascii_rejected_before_upper(raw: str) -> None:
    """AC-1: non-ASCII input is malformed even when upper() would fold it into A-Z (IB1234, ASS123, ST12345)."""
    with pytest.raises(MalformedClientIdError):
        normalise_client_id(raw)
    svc = new_service()
    with pytest.raises(MalformedClientIdError):
        svc.add(raw, ADMIN)
    assert svc.search() == ()


def test_manual_changes_fail_closed() -> None:
    """AC-1: duplicate add, unknown ID, no-op edit, rename onto an existing or verified ID, and missing actor raise."""
    svc = new_service()
    svc.add("AB1234", ADMIN)
    svc.add("CD5678", ADMIN)
    with pytest.raises(ValueError):
        svc.add("ab1234", ADMIN)
    with pytest.raises(ValueError):
        svc.edit("ZZ9999", ADMIN, platform_user_id="u1")
    with pytest.raises(ValueError):
        svc.remove("ZZ9999", ADMIN)
    with pytest.raises(ValueError):
        svc.edit("AB1234", ADMIN)
    with pytest.raises(ValueError):
        svc.edit("AB1234", ADMIN, new_client_id="CD5678")
    with pytest.raises(ValueError):
        svc.edit("AB1234", ADMIN, platform_user_id="  ")
    svc.edit("AB1234", ADMIN, verification_status=VerificationStatus.VERIFIED)
    with pytest.raises(ValueError):
        svc.edit("AB1234", ADMIN, new_client_id="AB1235")
    with pytest.raises(ValueError):
        svc.add("EF9012", None)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        Actor("  ")
    assert [e.client_id for e in svc.search()] == ["AB1234", "CD5678"]
    assert len(svc.audit_trail()) == 3


# ----- AC-3 ---------------------------------------------------------------------------------------------------

def _populated():
    svc = new_service()
    for cid in ["AB1234", "AB5678", "ABC999", "CD1111"]:
        svc.add(cid, ADMIN)
    svc.edit("AB5678", ADMIN, verification_status=VerificationStatus.VERIFIED, platform_user_id="user-7")
    svc.record_entitlement_status("AB5678", EntitlementStatus.ACTIVE, ENGINE)
    svc.record_entitlement_status("CD1111", EntitlementStatus.INACTIVE, ENGINE)
    return svc


def test_search_filter_and_per_id_status() -> None:
    """AC-3: filter by ID prefix, verification, entitlement and user link; each entry shows all three statuses."""
    svc = _populated()
    ids = lambda entries: [e.client_id for e in entries]  # noqa: E731
    assert ids(svc.search(id_prefix="ab")) == ["AB1234", "AB5678", "ABC999"]
    assert ids(svc.search(id_prefix="ABC")) == ["ABC999"]
    assert ids(svc.search(id_prefix="ZZ")) == []
    assert ids(svc.search(verification_status=VerificationStatus.VERIFIED)) == ["AB5678"]
    assert ids(svc.search(verification_status=VerificationStatus.UNVERIFIED)) == ["AB1234", "ABC999", "CD1111"]
    assert ids(svc.search(entitlement_status=EntitlementStatus.ACTIVE)) == ["AB5678"]
    assert ids(svc.search(entitlement_status=EntitlementStatus.NOT_EVALUATED)) == ["AB1234", "ABC999"]
    assert ids(svc.search(linked=True)) == ["AB5678"]
    assert ids(svc.search(linked=False, id_prefix="AB")) == ["AB1234", "ABC999"]
    entry = svc.get("ab5678")
    assert entry is not None
    assert (entry.verification_status, entry.platform_user_id, entry.entitlement_status) == (
        VerificationStatus.VERIFIED, "user-7", EntitlementStatus.ACTIVE,
    )


@pytest.mark.parametrize("prefix", ["", "  ", "AB-", "AB%", "ÄB", "\u0131B", "\u017f"])
def test_bad_search_prefix_rejected(prefix: str) -> None:
    """AC-3: a prefix that is empty or not plain letters/digits is rejected, not treated as 'match all'."""
    svc = _populated()
    with pytest.raises(ValueError):
        svc.search(id_prefix=prefix)


def test_entitlement_status_is_recorded_not_computed() -> None:
    """AC-3: verifying an ID does not change its entitlement status; only the engine's input does."""
    svc = new_service()
    svc.add("AB1234", ADMIN)
    entry = svc.edit("AB1234", ADMIN, verification_status=VerificationStatus.VERIFIED, platform_user_id="u1")
    assert entry.entitlement_status is EntitlementStatus.NOT_EVALUATED
    with pytest.raises(ValueError):
        svc.record_entitlement_status("AB1234", EntitlementStatus.NOT_EVALUATED, ENGINE)
    with pytest.raises(ValueError):
        svc.record_entitlement_status("AB1234", "ACTIVE", ENGINE)  # type: ignore[arg-type]


# ----- AC-5 ---------------------------------------------------------------------------------------------------

def test_export_whole_list_and_filtered() -> None:
    """AC-5: export writes one CSV row per ID with every status column; a filtered export writes only matches."""
    svc = _populated()
    lines = svc.export_csv().splitlines()
    assert lines[0] == (
        "client_id,list_status,verification_status,verified_at,platform_user_id,entitlement_status,added_by,added_at"
    )
    assert [line.split(",")[0] for line in lines[1:]] == ["AB1234", "AB5678", "ABC999", "CD1111"]
    ab5678 = lines[2].split(",")
    assert ab5678[1:6] == ["ACTIVE", "VERIFIED", svc.get("AB5678").verified_at.isoformat(), "user-7", "ACTIVE"]
    assert lines[1].split(",")[1:6] == ["ACTIVE", "UNVERIFIED", "", "", "NOT_EVALUATED"]
    svc.remove("ABC999", ADMIN)
    assert svc.export_csv().splitlines()[3].split(",")[:2] == ["ABC999", "INACTIVE"]
    filtered = svc.export_csv(svc.search(entitlement_status=EntitlementStatus.INACTIVE)).splitlines()
    assert [line.split(",")[0] for line in filtered[1:]] == ["CD1111"]


def test_export_neutralises_formula_cells() -> None:
    """AC-5: a user id starting with '=' cannot become a spreadsheet formula in the export."""
    svc = new_service()
    svc.add("AB1234", ADMIN)
    svc.edit("AB1234", ADMIN, platform_user_id="=HYPERLINK(1)")
    row = svc.export_csv().splitlines()[1]
    assert "'=HYPERLINK(1)" in row


# ----- deactivate / reactivate (AC-1, AC-3; ADR-024 Q70 "deactivate") --------------------------------------------

def test_remove_deactivates_and_is_reversible() -> None:
    """AC-1: remove keeps the entry as INACTIVE (not qualifying); reactivate restores it; both fail closed when
    repeated, on an unknown ID, or without an actor."""
    svc = new_service()
    svc.add("AB1234", ADMIN)
    removed = svc.remove("AB1234", ADMIN)
    assert (removed.client_id, removed.list_status) == ("AB1234", ListStatus.INACTIVE)
    assert svc.is_qualifying("AB1234") is False
    with pytest.raises(ValueError):
        svc.remove("AB1234", ADMIN)
    restored = svc.reactivate("AB1234", ADMIN)
    assert restored.list_status is ListStatus.ACTIVE and svc.is_qualifying("AB1234") is True
    with pytest.raises(ValueError):
        svc.reactivate("AB1234", ADMIN)
    with pytest.raises(ValueError):
        svc.reactivate("ZZ9999", ADMIN)
    with pytest.raises(ValueError):
        svc.remove("AB1234", None)  # type: ignore[arg-type]
    assert [a.action for a in svc.audit_trail("AB1234")] == ["add", "deactivate", "reactivate"]


def test_is_qualifying_only_for_active_listed_ids() -> None:
    """AC-3: an unknown ID does not qualify, an INACTIVE one does not, an ACTIVE one does; malformed input raises."""
    svc = new_service()
    svc.add("AB1234", ADMIN)
    svc.add("CD5678", ADMIN)
    svc.remove("CD5678", ADMIN)
    assert (svc.is_qualifying("AB1234"), svc.is_qualifying("CD5678"), svc.is_qualifying("EF9012")) == (
        True, False, False,
    )
    for malformed in ("not-an-id", "\u0131b1234", "", "AB\uff11\uff12\uff13\uff14"):
        assert svc.is_qualifying(malformed) is False
    with pytest.raises(ValueError):
        svc.search(list_status="INACTIVE")  # type: ignore[arg-type]
