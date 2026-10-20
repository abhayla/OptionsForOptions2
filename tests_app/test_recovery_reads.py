"""#380-3 item 1: Zerodha's raw replies -> the recovery domain's read, on the real GC-3L round trip of 2026-10-19
(strategy 9: plan 1 BUY 65 NIFTY26OCT24000CE filled, plan 2 SELL 65 filled; the positions net row is flat).

No database: the converter is pure; the route tests that use it run in CI.
"""
from __future__ import annotations

import copy
import datetime
import json
from decimal import Decimal as D
from pathlib import Path

import pytest
from ofo.engine import Action, Instrument, Leg
from ofo.execution.planned import ExecutionPlan, PlannedLeg
from ofo.execution.recovery import Refusal, Scope, close_filled_legs, missing_legs
from ofo.reconciliation.positions import position_line_from_kite_row
from ofo_app.kite_replies import PositionsRead
from ofo_app.recovery_reads import zerodha_read

REPLIES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "kite_replies"
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
AT = datetime.datetime(2026, 10, 19, 11, 0, tzinfo=IST)
ORDERS = json.loads((REPLIES / "orders-2026-10-19-roundtrip.json").read_text(encoding="utf-8"))["data"]
POSITIONS = json.loads((REPLIES / "positions-2026-10-19-roundtrip.json").read_text(encoding="utf-8"))["data"]
CONTRACT = ORDERS[0]["tradingsymbol"]


def _line(quantity: int) -> object:
    row = {**copy.deepcopy(POSITIONS["net"][0]), "quantity": quantity, "average_price": D("3.30"),
           "last_price": D("6.50")}
    return position_line_from_kite_row(row)


def test_real_order_book_reads_as_two_settled_rows_and_flat_net() -> None:
    read = zerodha_read(ORDERS, PositionsRead({}, ()), AT)
    assert [(o.contract, o.side, o.status, o.filled_quantity, o.tag) for o in read.orders] == [
        (CONTRACT, Action.BUY, "COMPLETE", 65, "OFS9V1L0"), (CONTRACT, Action.SELL, "COMPLETE", 65, "OFS9V2L0")]
    assert (dict(read.net), read.read_at) == ({}, AT)


def test_real_round_trip_is_neither_partial_nor_closable() -> None:
    """Plan 1 filled in full and plan 2 closed it: Place missing legs has nothing to do; Close has nothing held."""
    plan = ExecutionPlan("9", (PlannedLeg("L0", CONTRACT, Leg(Action.BUY, Instrument.CE, D("24000"),
                                                                datetime.date(2026, 10, 27), 65, D("3.30"))),))
    read = zerodha_read(ORDERS, PositionsRead({}, ()), AT)
    scope = Scope(9, 1, {CONTRACT: 65}, AT, False)
    assert missing_legs(plan, read, scope).refusal is Refusal.NOT_PARTIAL
    assert close_filled_legs(plan, read, scope).refusal is Refusal.NOTHING_TO_CLOSE


def test_position_lines_are_summed_per_contract_and_flat_dropped() -> None:
    read = zerodha_read([], PositionsRead({}, (_line(-65), _line(-65))), AT)
    assert (read.orders, dict(read.net)) == ((), {CONTRACT: -130})
    assert dict(zerodha_read([], PositionsRead({}, (_line(65), _line(-65))), AT).net) == {}


@pytest.mark.parametrize("rows", [None, {"data": []}, [{**ORDERS[0], "filled_quantity": "sixty"}],
                                  [{k: v for k, v in ORDERS[0].items() if k != "status"}]])
def test_an_unreadable_order_book_is_a_failed_read(rows: object) -> None:
    """Failed answer state: the whole book is unread (None), never decided on the rows that parsed."""
    assert zerodha_read(rows, PositionsRead({}, ()), AT).orders is None


def test_unread_positions_and_naive_clock() -> None:
    assert zerodha_read(ORDERS, None, AT).net is None
    with pytest.raises(ValueError, match="timezone-aware"):
        zerodha_read(ORDERS, None, AT.replace(tzinfo=None))
