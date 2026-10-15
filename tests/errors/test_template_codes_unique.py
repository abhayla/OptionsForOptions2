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


#: Found by this guard on main (not introduced here): two MARKET_DATA templates already share code 120. Renumbering a
#: shipped code is an owner/orchestrator call (issue to file); the entry must be removed when it is fixed.
KNOWN_DUPLICATES = {"MARKET_DATA_120": ["gate_price_outside_circuit", "marketdata_disconnected"]}


def test_no_two_templates_share_a_code() -> None:
    assert duplicate_codes(_TEMPLATES) == KNOWN_DUPLICATES


def test_the_guard_detects_a_duplicate_code() -> None:
    """Red case: a temporary copy of a real template under a new id but the same code is reported."""
    original = _TEMPLATES[0]
    clone = type(original)(**{**original.__dict__, "id": "temporary_duplicate_for_guard_test"})
    found = duplicate_codes([*_TEMPLATES, clone])
    assert found == {**KNOWN_DUPLICATES, original.code: [original.id, clone.id]}
