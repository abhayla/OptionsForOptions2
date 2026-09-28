"""W-024 item 7: every execution safety-gate CheckCode maps to exactly one ErrorClass.

W-014 (backend/ofo/execution/safety.py) landed on main (2026-09-29, PR #24), so the mapping rounds
1-2 deferred is now buildable and testable against the real CheckCode enum on disk.
"""
from __future__ import annotations

import pytest

from ofo.errors import ErrorClass
from ofo.errors.checkcode_map import CHECKCODE_TO_ERROR_CLASS, error_class_for_check
from ofo.execution.safety import CheckCode


def test_mapping_is_total_every_checkcode_maps() -> None:
    """AC-1-adjacent core: every real CheckCode member has an entry."""
    missing = set(CheckCode) - set(CHECKCODE_TO_ERROR_CLASS)
    assert not missing, f"CheckCode members with no ErrorClass mapping: {sorted(m.value for m in missing)}"


def test_mapping_has_no_entries_beyond_real_checkcodes() -> None:
    """The mapping does not silently carry a stale/renamed CheckCode."""
    extra = set(CHECKCODE_TO_ERROR_CLASS) - set(CheckCode)
    assert not extra, f"mapping entries with no real CheckCode: {extra}"


def test_every_mapped_value_is_a_real_error_class() -> None:
    for code, error_class in CHECKCODE_TO_ERROR_CLASS.items():
        assert isinstance(error_class, ErrorClass), f"{code}: {error_class!r} is not an ErrorClass"


@pytest.mark.parametrize("code", list(CheckCode))
def test_error_class_for_check_resolves_every_checkcode(code: CheckCode) -> None:
    error_class = error_class_for_check(code)
    assert isinstance(error_class, ErrorClass)


def test_margin_insufficient_maps_to_margin_class() -> None:
    """Spot-check one mapping against the AC-1 class it obviously belongs to."""
    assert error_class_for_check(CheckCode.MARGIN_INSUFFICIENT) is ErrorClass.MARGIN


def test_internal_error_maps_to_internal_system_class() -> None:
    assert error_class_for_check(CheckCode.INTERNAL_ERROR) is ErrorClass.INTERNAL_SYSTEM
