"""ADR-258 starting point of the F-71 rule memory (issue 65): a check reads and writes the memory of "adjustments made
so far", and after an adjustment basket the entry is no longer the baseline (the first check after it is). Pure: no DB.
"""
from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from ofo.adjustment.approaches import EntryFacts
from ofo_app import adjustment_check as check

STORED = {0: {"T-01": (True, False)}, 2: {"T-01": (False, False)}}


@pytest.mark.parametrize(("used", "marker"), [(0, 0), (1, 1), (3, 3), (None, 2), (True, 2), (-1, 2)])
def test_marker_is_the_adjustment_count_and_an_unread_count_keeps_the_newest(used, marker):
    assert check.rule_marker(used, STORED) == marker


def test_no_stored_memory_and_an_unread_count_is_the_entry():
    assert check.rule_marker(None, {}) == 0


def test_after_a_basket_the_entry_is_never_the_baseline():
    """marker > 0 -> None (the caller then takes this check's state): never the first fill's spot again."""
    facts = EntryFacts(Decimal("23460"), None, None, at=datetime.datetime(2026, 11, 6, 9, 20, tzinfo=datetime.UTC))
    assert check.entry_baseline(None, None, None, facts, 1) is None
    assert check.entry_baseline(object(), None, None, facts, 2) is None  # a scenario entry too
