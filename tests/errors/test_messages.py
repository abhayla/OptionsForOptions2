"""AC-2: every user-facing error states what happened, the impact, what is blocked, next action.

Covers construction of UserFacingError (all four parts required, fail-closed on missing/blank
fields and on ADR-003 banned wording), plus negative/red cases per the input-domain checklist.
"""
from __future__ import annotations

import pytest

from ofo.errors import CATALOGUE, ErrorClass, UserFacingError, scan_for_banned_phrases


def test_valid_construction_round_trips_all_four_parts() -> None:
    """AC-2: a well-formed error carries what happened, impact, what is blocked, next action."""
    error = UserFacingError(
        error_class=ErrorClass.MARGIN,
        code="MARGIN_002",
        what_happened="Margin available is below what this strategy needs.",
        impact="Zerodha would reject this order for insufficient margin.",
        what_is_blocked="Execution of this strategy.",
        next_action="Add funds in Zerodha or reduce the quantity, then retry.",
    )
    as_dict = error.as_dict()
    assert as_dict["error_class"] == "MARGIN"
    assert as_dict["what_happened"]
    assert as_dict["impact"]
    assert as_dict["what_is_blocked"]
    assert as_dict["next_action"]


@pytest.mark.parametrize(
    "field",
    ["what_happened", "impact", "what_is_blocked", "next_action"],
)
def test_missing_any_of_the_four_parts_raises(field: str) -> None:
    """AC-2 negative: each of the four required parts is required on its own; blank fails closed."""
    kwargs = {
        "error_class": ErrorClass.USER_INPUT,
        "code": "USER_INPUT_002",
        "what_happened": "The value entered was not a whole number.",
        "impact": "The form cannot be submitted.",
        "what_is_blocked": "Saving this form.",
        "next_action": "Enter a whole number and try again.",
    }
    kwargs[field] = "   "
    with pytest.raises(ValueError):
        UserFacingError(**kwargs)


def test_missing_code_raises() -> None:
    """Negative: a blank code fails closed rather than defaulting to an empty string."""
    with pytest.raises(ValueError):
        UserFacingError(
            error_class=ErrorClass.INTERNAL_SYSTEM,
            code="",
            what_happened="An unexpected error occurred.",
            impact="Your changes were not saved.",
            what_is_blocked="Saving.",
            next_action="Try again in a few minutes.",
        )


def test_wrong_type_for_error_class_raises() -> None:
    """Negative: a raw string in place of an ErrorClass member fails closed, never coerced."""
    with pytest.raises(ValueError):
        UserFacingError(
            error_class="margin",  # type: ignore[arg-type]
            code="MARGIN_003",
            what_happened="Margin available is below what this strategy needs.",
            impact="The order would be rejected.",
            what_is_blocked="Execution.",
            next_action="Add funds and retry.",
        )


@pytest.mark.parametrize(
    "banned_text",
    [
        "You should take this trade now.",
        "This is the best adjustment for you.",
        "This is a guaranteed outcome.",
        "This is a recommended trade.",
        "A risk-free way to proceed.",
        "Certain profit awaits.",
    ],
)
def test_banned_adr_003_wording_is_rejected_at_construction(banned_text: str) -> None:
    """AC-2 + ADR-003 negative: advice wording in any of the four parts fails closed at construction."""
    with pytest.raises(ValueError):
        UserFacingError(
            error_class=ErrorClass.STRATEGY_VALIDATION,
            code="STRATEGY_VALIDATION_002",
            what_happened=banned_text,
            impact="This strategy cannot be saved as configured.",
            what_is_blocked="Saving this strategy version.",
            next_action="Adjust the strategy and save again.",
        )


def test_banned_wording_is_rejected_wherever_it_appears_across_all_four_parts() -> None:
    """AC-2 negative: the scan covers every one of the four parts, not only what_happened."""
    base = {
        "error_class": ErrorClass.MARGIN,
        "code": "MARGIN_004",
        "what_happened": "Margin available is below what this strategy needs.",
        "impact": "The order would be rejected.",
        "what_is_blocked": "Execution of this strategy.",
        "next_action": "Add funds in Zerodha or reduce the quantity, then retry.",
    }
    for field in ("impact", "what_is_blocked", "next_action"):
        kwargs = dict(base)
        kwargs[field] = "Guaranteed to work if you proceed."
        with pytest.raises(ValueError):
            UserFacingError(**kwargs)


def test_is_frozen_no_bypass_of_the_constructor() -> None:
    """Input-domain checklist: no raw state change bypassing validated construction."""
    error = CATALOGUE[ErrorClass.MARGIN]
    with pytest.raises(Exception):
        error.what_happened = "Guaranteed profit."  # type: ignore[misc]


def test_catalogue_example_text_carries_no_pan_shaped_identifiers() -> None:
    """No real personal data: catalogue text must not contain a PAN-shaped identifier."""
    import re

    pan_pattern = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")
    for error in CATALOGUE.values():
        for text in (error.what_happened, error.impact, error.what_is_blocked, error.next_action):
            assert not pan_pattern.search(text), f"looks like a PAN: {text!r}"


def test_scan_for_banned_phrases_is_case_insensitive() -> None:
    """AC-2/ADR-003: the scan is case-insensitive, since a UI string may be re-cased."""
    assert scan_for_banned_phrases("GUARANTEED returns") == ["guaranteed"]
    assert scan_for_banned_phrases("You Should proceed") == ["you should"]


# --- CheckCode -> ErrorClass mapping -----------------------------------------------------------
#
# W-024 also asks to map the merged execution gate's CheckCode values
# (backend/ofo/execution/safety.py on main) to an ErrorClass. As of this build there is no
# backend/ofo/execution/ directory and no safety.py anywhere in the repo (checked with
# `find backend -iname "safety*.py"` and `find backend/ofo -maxdepth 1`, both empty/absent for
# execution) — the merged safety-checks work item has not landed on main yet. Per the work item's
# own instruction ("otherwise skip and say so"), this mapping is skipped; there is no CheckCode
# enum on disk in this worktree to map or to test.
def test_no_execution_safety_module_present_to_map_yet() -> None:
    """Documents the skip above: backend/ofo/execution/safety.py does not exist on this branch."""
    import importlib.util

    try:
        spec = importlib.util.find_spec("ofo.execution.safety")
    except ModuleNotFoundError:
        spec = None
    assert spec is None, (
        "ofo.execution.safety now exists — W-024's CheckCode mapping is no longer skippable; "
        "add ofo/errors/checkcode_map.py mapping every CheckCode to an ErrorClass and a test that "
        "every CheckCode maps."
    )
