"""Input-domain guards of the partial-execution module (W-023): duplicates, absurd sizes, padded ids, and positions the
plan does not explain are refused or blocked, never silently used."""
from __future__ import annotations

from decimal import Decimal as D

import pytest
from partial_inputs import READ_AT, CONTRACTS, LOT, FakePlanner, book_with_three_filled, plan, statuses, three_positions

from execution_inputs import condor_legs
from ofo.execution.partial import (
    MAX_PLAN_LEGS,
    MAX_POSITION_LINES,
    BrokerOrderStatus,
    BrokerPositionLine,
    ExecutionPlan,
    ExecutionStatus,
    PlannedLeg,
    assess,
)
from ofo.orders import OrderState


def test_duplicate_plan_leg_or_contract_refused() -> None:
    leg = condor_legs()[0]
    with pytest.raises(ValueError, match="duplicate leg_ref"):
        ExecutionPlan("S-1", (PlannedLeg("a", "C1", leg), PlannedLeg("a", "C2", leg)))
    with pytest.raises(ValueError, match="duplicate contract"):
        ExecutionPlan("S-1", (PlannedLeg("a", "C1", leg), PlannedLeg("b", "C1", leg)))


def test_empty_or_oversized_plan_refused() -> None:
    leg = condor_legs()[0]
    with pytest.raises(ValueError):
        ExecutionPlan("S-1", ())
    with pytest.raises(ValueError):
        ExecutionPlan("S-1", tuple(PlannedLeg(f"l{i}", f"C{i}", leg) for i in range(MAX_PLAN_LEGS + 1)))


@pytest.mark.parametrize("bad", ["C1 ", " C1", ""])
def test_padded_or_blank_identifiers_refused(bad: str) -> None:
    with pytest.raises(ValueError):
        BrokerPositionLine(bad, 65, D("1.00"))
    with pytest.raises(ValueError):
        BrokerOrderStatus(bad, "C1", OrderState.REJECTED, 0)


def test_float_price_and_bool_quantity_refused() -> None:
    with pytest.raises(ValueError):
        BrokerPositionLine("C1", 65, 42.5)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        BrokerPositionLine("C1", True, D("42.50"))  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        BrokerOrderStatus("B", "C1", "Rejected", 0)  # type: ignore[arg-type]


def test_duplicate_broker_lines_refused() -> None:
    positions = three_positions() + [three_positions()[0]]
    with pytest.raises(ValueError, match="duplicate position contract"):
        assess(plan(), positions, statuses(), book_with_three_filled(), FakePlanner(), read_at=READ_AT)
    with pytest.raises(ValueError, match="duplicate broker order id"):
        assess(plan(), three_positions(), statuses() + [statuses()[0]], book_with_three_filled(), FakePlanner(), read_at=READ_AT)


def test_too_many_position_lines_refused() -> None:
    lines = [BrokerPositionLine(f"X{i}", 65, D("1.00")) for i in range(MAX_POSITION_LINES + 1)]
    with pytest.raises(ValueError, match="too many"):
        assess(plan(), lines, statuses(), book_with_three_filled(), FakePlanner(), read_at=READ_AT)


@pytest.mark.parametrize("line", [
    BrokerPositionLine("NIFTY26OCT24000CE", -65, D("10.00")),  # contract outside the plan
    BrokerPositionLine(CONTRACTS[2], 65, D("91.50")),  # planned short, broker shows long
    BrokerPositionLine(CONTRACTS[2], -2 * LOT, D("91.50")),  # more than planned
])
def test_positions_the_plan_cannot_explain_block(line: BrokerPositionLine) -> None:
    """Orchestrator default OD-f: never an exception with choices, always a reconciliation block."""
    positions = [p for p in three_positions() if p.contract != line.contract] + [line]
    a = assess(plan(), positions, statuses(), book_with_three_filled(), FakePlanner(), read_at=READ_AT)
    assert a.status is ExecutionStatus.RECONCILIATION_REQUIRED and a.choices == ()


def test_status_for_an_order_the_book_does_not_know_blocks() -> None:
    sts = statuses() + [BrokerOrderStatus("BRK-GHOST", CONTRACTS[3], OrderState.REJECTED, 0)]
    a = assess(plan(), three_positions(), sts, book_with_three_filled(), FakePlanner(), read_at=READ_AT)
    assert a.status is ExecutionStatus.RECONCILIATION_REQUIRED


def test_nothing_filled_is_not_a_partial_exception() -> None:
    """All four rejected, nothing held: NOT_EXECUTED, no choices (there is no partial position to protect)."""
    from ofo.orders import Order, OrderBook  # noqa: PLC0415

    book = OrderBook()
    for i, (c, leg) in enumerate(zip(CONTRACTS, condor_legs())):
        book.add(Order("S-1", f"leg-{i + 1}", c, leg.action, leg.quantity, leg.entry_price, broker_order_id=f"B{i}"))
        book.transition(f"B{i}", OrderState.SUBMITTED)
        book.transition(f"B{i}", OrderState.REJECTED)
    sts = [BrokerOrderStatus(f"B{i}", c, OrderState.REJECTED, 0, "rejected") for i, c in enumerate(CONTRACTS)]
    a = assess(plan(), [], sts, book, FakePlanner(), read_at=READ_AT)
    assert a.status is ExecutionStatus.NOT_EXECUTED and a.choices == () and len(a.failures) == 4
