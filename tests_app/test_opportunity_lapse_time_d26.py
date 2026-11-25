"""D-26 (ADR-320 / REQ-112 AC-2): a record that lapsed says WHEN it lapsed. The store writes the time of every outcome
change into the record's timeline entry ('at'); the inbox reply carries it as ``closed_at`` (None while open).
Real case 23 Nov, condor C7 (strategy 161): delta 0.3675 -> 0.3311 and the row went Lapsed within 3 minutes."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from ofo_app import playbook_store
from ofo_app.routes.adjustment_opportunities import OpportunityOut, _record

SHOWN = dt.datetime(2026, 11, 23, 9, 1, 20, tzinfo=dt.UTC)


def _suggestion(outcome: str, timeline: list) -> playbook_store.Suggestion:
    return playbook_store.Suggestion(901, 161, "R-delta", "T-04", "Last day", Decimal("0.3311"),
                                     Decimal("0.3500"), SHOWN,
                                     outcome, None, timeline)


OPENED = {"cmp": "le", "label": "Net delta", "group": "g"}


def test_a_lapsed_record_carries_the_time_it_lapsed():
    lapsed = {"at": "2026-11-23T09:04:11.250000+00:00", "outcome": "lapsed", "suggestion_id": 901,
              "reason": "condition_stopped"}
    record = _record(_suggestion("lapsed", [OPENED, lapsed]), True)
    assert record["closed_at"] == dt.datetime(2026, 11, 23, 9, 4, 11, 250000, tzinfo=dt.UTC)
    assert record["outcome_text"] is not None and "closed_at" in OpportunityOut.model_fields


def test_an_open_record_has_no_closed_time():
    assert _record(_suggestion("open", [OPENED]), True)["closed_at"] is None


def test_an_unreadable_time_is_none_never_a_guess():
    bad = {"at": "yesterday", "outcome": "lapsed", "reason": "condition_stopped"}
    assert _record(_suggestion("lapsed", [OPENED, bad]), True)["closed_at"] is None
    assert _record(_suggestion("lapsed", [OPENED, {"outcome": "lapsed"}]), True)["closed_at"] is None


def test_a_dismissed_record_keeps_its_dismiss_time_after_condition_cleared_is_appended():
    dismissed = {"at": "2026-11-23T09:04:11+00:00", "outcome": "dismissed", "suggestion_id": 901, "reason": None}
    cleared = {"at": "2026-11-23T11:00:00+00:00", "event": "condition_cleared"}
    record = _record(_suggestion("dismissed", [OPENED, dismissed, cleared]), True)
    assert record["closed_at"] == dt.datetime(2026, 11, 23, 9, 4, 11, tzinfo=dt.UTC)


def test_an_acted_on_record_keeps_its_acted_on_time_after_orders_placed_is_appended():
    acted = {"at": "2026-11-23T09:04:11+00:00", "outcome": "acted_on", "suggestion_id": 901, "reason": None}
    placed = {"at": "2026-11-23T09:20:00+00:00", "event": "orders_placed", "order_ids": [5], "basket_legs": 1}
    record = _record(_suggestion("acted_on", [OPENED, acted, placed]), True)
    assert record["closed_at"] == dt.datetime(2026, 11, 23, 9, 4, 11, tzinfo=dt.UTC)
