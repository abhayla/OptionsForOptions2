"""D-30 (ADR-320): the outcome counters count CONDITIONS (records) while the list counts ROWS (groups); the reply states
both units next to each other. Real case 23 Nov: Open 23 + Dismissed 0 + Acted 0 + Completed 19 + Lapsed 47 = 89 conditions
against "Showing 1-25 of 52 rows" (one row can hold 4 conditions)."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from ofo_app import playbook_store
from ofo_app.routes.adjustment_opportunities import InboxOut, inbox_body

SHOWN = dt.datetime(2026, 11, 23, 9, 1, 20, tzinfo=dt.UTC)


def _row(sid: int, strategy: int, group: str, outcome: str) -> playbook_store.InboxRow:
    s = playbook_store.Suggestion(sid, strategy, f"R-{sid}", "T-01", "Last day", Decimal("0.7293"), Decimal("0.7500"), SHOWN,
                                  outcome, None, [{"cmp": "le", "label": "Spot distance", "unit": "%", "group": group}])
    return playbook_store.InboxRow(s, "C6", True)


def test_the_reply_states_conditions_and_rows_on_their_own_units():
    rows = [_row(1, 160, "g1", "open"), _row(2, 160, "g1", "open"), _row(3, 160, "g1", "lapsed"), _row(4, 160, "g1", "lapsed"),
            _row(5, 161, "g2", "lapsed")]
    body = inbox_body(rows)
    assert body["totals"]["conditions"] == 5 and body["totals"]["rows"] == 2
    assert sum(c["count"] for c in body["counts"]) == body["totals"]["conditions"]
    assert len(body["groups"]) == body["totals"]["rows"]
    text = str(body["totals"]["text"])
    assert "conditions" in text and "rows" in text and "Conditions: 5" in text and "Rows: 2" in text
    assert "totals" in InboxOut.model_fields


def test_an_empty_inbox_has_zero_of_each():
    body = inbox_body([])
    assert body["totals"]["conditions"] == 0 and body["totals"]["rows"] == 0
