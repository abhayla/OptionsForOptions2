"""Issue #275 items 1-2 (W-083 minors): a duplicate (contract, product) row is shown, and the audit lists hidden rows.

Basis: REQ-061 AC-4 "every grouping decision recorded"; the grouping module's "one row per contract AND product".
Rows are Kite-shaped rows over real catalogue symbols (tests/reconciliation/grouping_inputs.py).
"""
from __future__ import annotations

import pytest

from grouping_inputs import (CONDOR_SYMBOLS, IN_STRATEGY, SPOTS, audit_log, catalogue, clock, row, seven_rows,
                             strategies, templates)
from ofo.errors import render
from ofo.reconciliation.grouping import STANDALONE, GroupingError, GroupingSession, suggest_groups

SHORT_PUT = CONDOR_SYMBOLS[1]  # -65 @ 86.00 MIS in seven_rows


def _suggest(rows):
    return suggest_groups(rows, strategies(), catalogue(), templates=templates(), spots=SPOTS)


def test_a_second_row_of_the_same_contract_and_product_is_listed_unresolved_not_dropped():
    s = _suggest(seven_rows() + [row(SHORT_PUT, -65, "99.00", "MIS")])
    assert [(u.tradingsymbol, u.reason) for u in s.unresolved] == [(SHORT_PUT, "duplicate_row")]
    legs = [p for g in s.groups for p in g.positions if p.tradingsymbol == SHORT_PUT]
    assert len(legs) == 1 and str(legs[0].average_price) == "86.00"  # the FIRST row is the one grouped


def test_the_same_contract_in_another_product_is_not_a_duplicate():
    s = _suggest(seven_rows() + [row(SHORT_PUT, -65, "99.00", "NRML")])
    assert not [u for u in s.unresolved if u.reason == "duplicate_row"]


def test_the_duplicate_row_is_refused_with_its_own_four_part_message_and_audited():
    log = audit_log()
    session = GroupingSession.start(_suggest(seven_rows() + [row(SHORT_PUT, -65, "99.00", "MIS")]), audit=log,
                                    clock=clock, actor="u", session_id="s", strategies=strategies())
    assert f"{SHORT_PUT}:duplicate_row" in log.events[0].payload["unresolved"]
    with pytest.raises(GroupingError) as exc:
        session.move_unresolved(SHORT_PUT, STANDALONE)
    assert exc.value.message == render("grouping_duplicate_row", contracts=1)
    assert len(log.events) == 1


def test_the_suggest_entry_lists_the_positions_hidden_by_a_strategy_with_its_id():
    log = audit_log()
    GroupingSession.start(_suggest(seven_rows()), audit=log, clock=clock, actor="u", session_id="s",
                          strategies=strategies())
    assert log.events[0].payload["hidden"] == [f"{IN_STRATEGY}:S-1"]


def test_nothing_hidden_means_an_empty_hidden_list():
    log = audit_log()
    GroupingSession.start(_suggest(seven_rows()[:6]), audit=log, clock=clock, actor="u", session_id="s",
                          strategies=strategies())
    assert log.events[0].payload["hidden"] == []
