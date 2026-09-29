"""REQ-020 AC-2 (over the AC-1/AC-3 entry paths): untrusted text is never transformed before its ASCII check.

Class: any strip()/upper()/lower() of untrusted text before a strict character-set check turns a malformed value
into a valid ID (round 2: upper() folded 'ı' into 'I'; round 3: strip() removed NBSP). One helper,
``untrusted_text.ascii_token``, is the gate on every path; these tests run the whole contaminant list over every path.
"""
from __future__ import annotations

import pytest

from qualifying_checks import (
    ADMIN,
    ASCII_PADDED,
    CONTAMINATED,
    check_class_rejected_everywhere,
    check_every_path_rejects,
    new_service,
)
from ofo.admin import untrusted_text
from ofo.admin.qualifying import ImportRequest, RowCategory

CHECK_FAILED = (AssertionError, pytest.fail.Exception)


@pytest.mark.parametrize("value", [v for _, v in CONTAMINATED], ids=[i for i, _ in CONTAMINATED])
def test_contaminated_value_is_malformed_on_every_path(value: str) -> None:
    """AC-2: each non-ASCII contaminant before/inside/after 'AB1234' is rejected by add, edit, import, search and
    is_qualifying."""
    check_every_path_rejects(value)


@pytest.mark.parametrize("value", ASCII_PADDED)
def test_ascii_space_and_tab_padding_still_accepted(value: str) -> None:
    """AC-2: plain ASCII spaces and tabs around a Client ID are trimmed and accepted on every path."""
    svc = new_service()
    assert svc.add(value, ADMIN).client_id == "AB1234"
    assert svc.is_qualifying(value) is True
    assert [e.client_id for e in svc.search(id_prefix=value)] == ["AB1234"]
    svc.add("CD5678", ADMIN)
    assert svc.edit("CD5678", ADMIN, new_client_id=value.replace("1234", "9999")).client_id == "AB9999"
    report = new_service().preview_import(ImportRequest("f.csv", f"client_id\n{value}\n"))
    assert [(r.category, r.client_id) for r in report.rows] == [(RowCategory.NEW, "AB1234")]


def test_nbsp_only_row_is_reported_not_skipped_as_blank() -> None:
    """AC-2: a row holding only non-ASCII whitespace is data (MALFORMED), not a silently ignored blank line."""
    report = new_service().preview_import(ImportRequest("f.csv", "client_id\n \nAB1234\n\t \n"))
    assert [(r.row_number, r.category) for r in report.rows] == [(2, RowCategory.MALFORMED), (3, RowCategory.NEW)]
    assert report.blank_lines_ignored == 1


def test_ascii_token_rules() -> None:
    """AC-2: the gate checks the RAW value, trims only ASCII space/tab, and refuses empty or non-text input."""
    assert untrusted_text.ascii_token(" \tAB1234\t ", "f") == "AB1234"
    for bad in (" AB1234", "AB1234\u0085", "", " \t ", None, 1234):
        with pytest.raises(ValueError):
            untrusted_text.ascii_token(bad, "f")  # type: ignore[arg-type]
    assert untrusted_text.ascii_token("AB1234\r", "f") == "AB1234\r"  # only space/tab trimmed; the pattern rejects \r


def _round2_strip_then_check(raw: object, field: str) -> str:
    """Mutant: the round-2 code shape, a bare strip() BEFORE the ASCII check."""
    if not isinstance(raw, str):
        raise ValueError(field)
    token = raw.strip()
    if not token or not token.isascii():
        raise ValueError(field)
    return token


def test_mutant_strip_before_ascii_check_is_caught(monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-2 mutation: swapping the gate back to a bare strip() makes the class check fail (NBSP etc. accepted)."""
    monkeypatch.setattr(untrusted_text, "ascii_token", _round2_strip_then_check)
    with pytest.raises(CHECK_FAILED):
        check_every_path_rejects(" AB1234 ")
    with pytest.raises(CHECK_FAILED):
        check_class_rejected_everywhere()


def test_real_gate_passes_the_whole_class() -> None:
    """AC-2 control: the unmutated gate rejects every contaminated value on every path."""
    check_class_rejected_everywhere()
