"""GC-6 ORDERS-SCREEN (ADR-135, ADR-138 (1), ADR-079): the pure state rules, on the owner's REAL GC-3L replies
(``tests/fixtures/kite_replies/orders-gc3l-2026-10-19.json``: strategy 9, BUY 65 NIFTY26OCT24000CE filled 65 as
OFS9V1L0; SELL 65 filled 65 as OFS9V2L0). Expected states are written by hand from the four approved words.
"""
from __future__ import annotations

import datetime
import json
from decimal import Decimal as D

import pytest
from ofo_app import orders_view as ov
from ofo_app.execute_replay import REPLIES
from ofo_app.execution_plan_store import UNRESOLVED, PlanOrder, StoredPlan
from ofo_app.kite_replies import KiteReplyError
from ofo_app.routes import orders as route

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
TODAY = datetime.date(2026, 10, 19)
CREATED = datetime.datetime(2026, 10, 19, 10, 0, tzinfo=IST)
SYMBOL = "NIFTY26OCT24000CE"
ENTRY_TAG, EXIT_TAG = "OFS9V1L0", "OFS9V2L0"
PARTIAL_FILLED = 30


def _orders() -> list:
    return json.loads((REPLIES / "orders-gc3l-2026-10-19.json").read_text(encoding="utf-8"), parse_float=D)["data"]


def _plan(status="open", *, tag=ENTRY_TAG, filled=None, reason=None, created=CREATED) -> StoredPlan:
    side = "BUY" if tag == ENTRY_TAG else "SELL"
    order = PlanOrder(0, tag, "NSE_FO:1", SYMBOL, side, 65, D("7.00"), filled)
    return StoredPlan(9, 1, "ENTRY", status, (order,), created, None if status == "open" else created, reason)


def _resolve(plan, fresh=None, audit=None, today=TODAY):
    (order,) = plan.orders
    return ov.resolve(plan, order, fresh=fresh, audit=audit or {}, earlier_session=ov.earlier_session(plan, today))


def test_core_real_gc3l_rows_read_by_the_load_decide_both_orders_executed_65_of_65():
    tags = frozenset({ENTRY_TAG, EXIT_TAG})
    fresh = route._fresh(_orders(), tags)
    for tag in (ENTRY_TAG, EXIT_TAG):
        got = _resolve(_plan(tag=tag), fresh=fresh)
        assert (got.state, got.filled, got.unknown, got.reconciliation) == ("executed", 65, False, False)


def test_open_plan_with_no_prior_check_and_no_row_at_kite_is_not_sent_after_the_load_read():
    got = _resolve(_plan(), fresh=route._fresh(_orders(), frozenset({"OFS1V1L0"})))
    assert (got.state, got.unknown) == ("not_sent", False)


@pytest.mark.parametrize("status", ["OPEN", "TRIGGER PENDING", "AMO REQ RECEIVED", "VALIDATION PENDING", "complete",
                                    "SOMETHING NEW"])
def test_a_working_or_unknown_status_word_is_order_placed(status):
    row = {**_orders()[0], "status": status}
    got = _resolve(_plan(), fresh=route._fresh([row], frozenset({ENTRY_TAG})))
    assert (got.state, got.filled) == ("placed", None)


@pytest.mark.parametrize("status", ["REJECTED", "CANCELLED"])
def test_rejected_or_cancelled_is_not_executed(status):
    row = {**_orders()[0], "status": status, "filled_quantity": 0}
    got = _resolve(_plan(), fresh=route._fresh([row], frozenset({ENTRY_TAG})))
    assert (got.state, got.filled) == ("not_executed", None)


def test_a_tag_posted_twice_is_never_picked_between():
    rows = [_orders()[0], {**_orders()[0], "order_id": "261019170999999"}]
    got = _resolve(_plan(), fresh=route._fresh(rows, frozenset({ENTRY_TAG})))
    assert got == ov.UNKNOWN


def test_an_open_plan_from_an_earlier_session_is_not_called_not_sent_from_todays_book():
    earlier = CREATED - datetime.timedelta(days=1)
    got = _resolve(_plan(created=earlier), fresh={})
    assert got == ov.UNKNOWN
    audited = _resolve(_plan(created=earlier), fresh={}, audit={ENTRY_TAG: ov.Seen("OPEN", 0)})
    assert audited.state == "placed"


@pytest.mark.parametrize(("audit", "state", "unknown"), [
    (None, None, True), (ov.Seen("OPEN", 0), "placed", False), (ov.Seen("COMPLETE", 65), "executed", False),
    (ov.Seen("REJECTED", 0), "not_executed", False), (ov.Seen("COMPLETE", 66), None, True)])
def test_a_failed_read_falls_back_to_the_audit_row_else_could_not_confirm(audit, state, unknown):
    got = _resolve(_plan(), fresh=None, audit={ENTRY_TAG: audit} if audit else {})
    assert (got.state, got.unknown) == (state, unknown)


def test_closed_plans_answer_from_the_audit_row_then_the_stored_fill():
    partial = _resolve(_plan("closed", filled=PARTIAL_FILLED, reason="partial"))  # Executed 30 of 65
    assert (partial.state, partial.filled) == ("executed", PARTIAL_FILLED)
    assert _resolve(_plan("closed", filled=0, reason="nothing_placed")).state == "not_sent"
    ended = {ENTRY_TAG: ov.Seen("REJECTED", 0)}
    rejected = _resolve(_plan("closed", filled=0, reason="nothing_placed"), audit=ended)
    assert rejected.state == "not_executed"
    unresolved = _resolve(_plan("closed", filled=0, reason=UNRESOLVED))
    assert (unresolved.state, unresolved.reconciliation, unresolved.unknown) == (None, True, False)


def test_every_resolved_state_is_one_of_the_four_words_or_a_flag():
    states = {_resolve(_plan(), fresh=route._fresh([{**_orders()[0], "status": s}], frozenset({ENTRY_TAG}))).state
              for s in ("COMPLETE", "OPEN", "REJECTED", "CANCELLED", "X")}
    assert states == {"executed", "placed", "not_executed"}
    assert set(ov.State.__args__) == {"not_sent", "placed", "executed", "not_executed"}


def test_an_unreadable_row_fails_the_whole_read_not_one_line():
    with pytest.raises((KiteReplyError, ValueError)):
        route._fresh([{**_orders()[0], "filled_quantity": 70}], frozenset({ENTRY_TAG}))
    with pytest.raises(ValueError, match="mapping"):
        route._fresh(["not a row"], frozenset({ENTRY_TAG}))


def test_audit_rows_keep_the_latest_per_tag_and_skip_unreadable_ones():
    class Row:
        def __init__(self, tag, status, filled):
            self.tag, self.status, self.filled = tag, status, filled

    seen = route._audit_seen([Row("A", "COMPLETE", "65"), Row("A", "OPEN", "0"), Row("B", None, "0"),
                              Row("C", "OPEN", "x")])
    assert seen == {"A": ov.Seen("COMPLETE", 65)}
