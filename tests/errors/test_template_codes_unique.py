"""No two error templates share one user-facing code (class prefix + number).

Template ids were already checked for uniqueness; the CODE shown to the user (e.g. RECONCILIATION_MISMATCH_221) was not,
so two PRs that each took the next free number merged green with the same code (#275 vs #279, caught by review).
"""
from __future__ import annotations

from collections import defaultdict

from ofo.errors.templates import _TEMPLATES


def duplicate_codes(templates) -> dict[str, list[str]]:
    by_code: dict[str, list[str]] = defaultdict(list)
    for t in templates:
        by_code[t.code].append(t.id)
    return {code: ids for code, ids in by_code.items() if len(ids) > 1}


#: No known duplicates: every shipped code is unique. Do not add an exception; renumber the new template instead.
KNOWN_DUPLICATES: dict[str, list[str]] = {}


def test_no_two_templates_share_a_code() -> None:
    assert duplicate_codes(_TEMPLATES) == KNOWN_DUPLICATES


def test_the_guard_detects_a_duplicate_code() -> None:
    """Red case: a temporary copy of a real template under a new id but the same code is reported."""
    original = _TEMPLATES[0]
    clone = type(original)(**{**original.__dict__, "id": "temporary_duplicate_for_guard_test"})
    found = duplicate_codes([*_TEMPLATES, clone])
    assert found == {**KNOWN_DUPLICATES, original.code: [original.id, clone.id]}
