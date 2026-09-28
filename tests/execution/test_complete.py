"""REQ-058 AC-4 (completing re-fetches, recomputes, re-checks margin, verifies the missing leg, prepares only it) and
AC-5 (never complete because every intended order was submitted). Golden Iron Condor, 23,600 CE buy rejected."""
from __future__ import annotations

from decimal import Decimal as D

import pytest
from partial_inputs import (
    CONTRACTS,
    LOT,
    FakeBroker,
    FakePlanner,
    FakeSubmitter,
    book_with_three_filled,
    entry_context,
    plan,
    statuses,
    three_positions,
)

from ofo.engine import Action
from ofo.execution import CheckCode
from ofo.execution.partial import (
    BrokerOrderStatus,
    BrokerPositionLine,
    ExecutionStatus,
    PartialChoice,
    assess,
    complete_strategy,
    submit_confirmed,
)
from ofo.orders import FillEvent, OrderState
from partial_inputs import FILL_AT


def _complete(broker: FakeBroker, planner: FakePlanner | None = None, book=None, ctx=None, cat=None, elig=None):  # noqa: ANN001, ANN202
    return complete_strategy(plan(), broker, book or book_with_three_filled(), planner or FakePlanner(),
                             ctx or entry_context(), cat, elig)


def test_ac4_both_reads_happen_before_anything_is_prepared(catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-4: positions and order status are each read exactly once, then margin, before the single order exists."""
    broker = FakeBroker(three_positions(), statuses())
    prep = _complete(broker, cat=catalogue, elig=eligibility)
    assert broker.calls == ["positions", "order_statuses", "margin"]
    assert [(o.contract, o.side, o.quantity) for o in prep.orders] == [(CONTRACTS[3], Action.BUY, LOT)]


@pytest.mark.parametrize("failing", ["positions", "order_statuses", "margin"])
def test_ac4_a_failed_read_prepares_nothing(failing: str, catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-4 fail closed: if any re-read fails, nothing is prepared and the reason says so."""
    broker = FakeBroker(three_positions(), statuses(), fail=failing)
    prep = _complete(broker, cat=catalogue, elig=eligibility)
    assert prep.orders == () and not prep.ready
    assert "could not re-read" in prep.reason
    if failing == "positions":
        assert broker.calls == ["positions"]


def test_ac4_uses_the_fresh_read_not_the_earlier_state(catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-4: the earlier assessment saw the 23,600 CE missing; by the time the user presses Complete, Zerodha shows it
    filled (a late fill). The fresh read wins: the strategy is complete and NOTHING is prepared."""
    book = book_with_three_filled(fourth=OrderState.SUBMITTED)
    before = assess(plan(), three_positions(), statuses(OrderState.SUBMITTED, None), book, FakePlanner())
    assert before.status is ExecutionStatus.IN_PROGRESS
    book.apply_fill(FillEvent("T-4", "BRK-4", CONTRACTS[3], Action.BUY, LOT, D("44.00"), FILL_AT))
    positions = three_positions() + [BrokerPositionLine(CONTRACTS[3], LOT, D("44.00"))]
    sts = statuses()[:3] + [BrokerOrderStatus("BRK-4", CONTRACTS[3], OrderState.EXECUTED, LOT)]
    prep = _complete(FakeBroker(positions, sts), book=book, cat=catalogue, elig=eligibility)
    assert prep.orders == ()
    assert prep.assessment.status is ExecutionStatus.COMPLETE
    assert "complete" in prep.reason


def test_ac4_still_open_missing_leg_prepares_nothing(catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-4 verify the missing leg: while its order is still pending at the broker it may yet fill, so no second
    order is prepared (orchestrator default OD-b)."""
    book = book_with_three_filled(fourth=OrderState.SUBMITTED)
    prep = _complete(FakeBroker(three_positions(), statuses(OrderState.PENDING, None)), book=book,
                     cat=catalogue, elig=eligibility)
    assert prep.orders == () and prep.assessment.status is ExecutionStatus.IN_PROGRESS


def test_ac4_margin_rechecked_with_fresh_broker_figure(catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-4 re-check margin: fresh available 1,200.00 < planner's 4,400.00 for the missing order -> the gate blocks
    with MARGIN_INSUFFICIENT and nothing is prepared; the planner was asked about the ONE missing leg only."""
    planner = FakePlanner(D("4400.00"))
    prep = _complete(FakeBroker(three_positions(), statuses(), margin=D("1200.00")), planner=planner,
                     ctx=entry_context(margin_available=D("999999.00")), cat=catalogue, elig=eligibility)
    assert prep.orders == ()
    assert CheckCode.MARGIN_INSUFFICIENT in prep.gate.failed_codes
    assert [(leg.strike, leg.quantity) for leg in planner.asked[-1].legs] == [(D("23600"), LOT)]


def test_ac4_gate_blocks_completion_when_market_closed(catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-4: completion passes the W-014 gate; a closed market blocks it."""
    prep = _complete(FakeBroker(three_positions(), statuses()), ctx=entry_context(market_open=False),
                     cat=catalogue, elig=eligibility)
    assert prep.orders == () and CheckCode.MARKET_CLOSED in prep.gate.failed_codes


def test_ac4_reconciliation_block_on_the_book_blocks_completion(catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-4 / ADR-018: a broker count lower than the ledger blocks; nothing prepared, no choices."""
    sts = statuses()
    sts[0] = BrokerOrderStatus("BRK-1", CONTRACTS[0], OrderState.EXECUTED, 30)
    prep = _complete(FakeBroker(three_positions(), sts), cat=catalogue, elig=eligibility)
    assert prep.orders == () and prep.assessment.status is ExecutionStatus.RECONCILIATION_REQUIRED


def test_ac4_only_the_missing_part_of_a_partly_filled_leg(catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-4: 2 lots planned on every leg; the 23,600 CE order filled 1 lot (65) then was cancelled -> exactly one
    order for the remaining 65 units, not 130."""
    from execution_inputs import condor_legs  # noqa: PLC0415
    from ofo.execution.partial import ExecutionPlan, PlannedLeg  # noqa: PLC0415
    from ofo.orders import Order, OrderBook  # noqa: PLC0415

    legs = condor_legs(quantity=2 * LOT)
    two_lot = ExecutionPlan("S-1", tuple(PlannedLeg(f"leg-{i + 1}", c, leg) for i, (c, leg) in
                                         enumerate(zip(CONTRACTS, legs))))
    book = OrderBook()
    positions, sts = [], []
    for i, (c, leg) in enumerate(zip(CONTRACTS, legs)):
        boid = f"BRK-{i + 1}"
        book.add(Order("S-1", f"leg-{i + 1}", c, leg.action, leg.quantity, leg.entry_price, broker_order_id=boid))
        book.transition(boid, OrderState.SUBMITTED)
        filled = leg.quantity if i < 3 else LOT
        book.apply_fill(FillEvent(f"T-{i}", boid, c, leg.action, filled, leg.entry_price, FILL_AT))
        sign = 1 if leg.action is Action.BUY else -1
        positions.append(BrokerPositionLine(c, sign * filled, leg.entry_price))
        sts.append(BrokerOrderStatus(boid, c, OrderState.EXECUTED if i < 3 else OrderState.CANCELLED, filled,
                                     None if i < 3 else "Cancelled by exchange: IOC unfilled"))
    book.transition("BRK-4", OrderState.CANCELLED)
    prep = complete_strategy(two_lot, FakeBroker(positions, sts), book, FakePlanner(), entry_context(), catalogue,
                             eligibility)
    assert [(o.contract, o.side, o.quantity) for o in prep.orders] == [(CONTRACTS[3], Action.BUY, LOT)]


def test_ac5_all_orders_submitted_is_not_complete(catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-5: every intended order was sent (four Submitted; the completing order sent and accepted) but the broker's
    positions still show three legs -> not complete. Sending never changes the status; only positions do."""
    book = book_with_three_filled()
    broker = FakeBroker(three_positions(), statuses())
    prep = complete_strategy(plan(), broker, book, FakePlanner(), entry_context(), catalogue, eligibility)
    result = submit_confirmed(prep, choice=PartialChoice.COMPLETE_STRATEGY, confirmed_by="user:U-42",
                              submitter=FakeSubmitter())
    assert result.submitted == (("leg-4", "NEW-1"),)
    sts = statuses()[:3] + [BrokerOrderStatus("BRK-4", CONTRACTS[3], OrderState.REJECTED, 0, "x"),
                            BrokerOrderStatus("NEW-1", CONTRACTS[3], OrderState.SUBMITTED, 0)]
    book.add(prep.orders[0].__class__("S-1", "leg-4", CONTRACTS[3], Action.BUY, LOT, D("44.00"),
                                      broker_order_id="NEW-1"))
    book.transition("NEW-1", OrderState.SUBMITTED)
    after = assess(plan(), three_positions(), sts, book, FakePlanner())
    assert after.status is not ExecutionStatus.COMPLETE
    assert after.status is ExecutionStatus.IN_PROGRESS


def test_ac5_broker_says_executed_but_positions_disagree_is_not_complete() -> None:
    """AC-5: all four order statuses read Executed, but the broker's positions show only three legs -> the ledger
    and broker disagree; the result is RECONCILIATION_REQUIRED, never COMPLETE."""
    sts = statuses()[:3] + [BrokerOrderStatus("BRK-4", CONTRACTS[3], OrderState.EXECUTED, LOT)]
    a = assess(plan(), three_positions(), sts, book_with_three_filled(fourth=OrderState.SUBMITTED), FakePlanner())
    assert a.status is ExecutionStatus.RECONCILIATION_REQUIRED


def test_ac5_complete_only_when_positions_equal_plan() -> None:
    """AC-5 positive: four broker positions equal the plan and the ledger agrees -> COMPLETE, no choices."""
    book = book_with_three_filled(fourth=OrderState.SUBMITTED)
    book.apply_fill(FillEvent("T-4", "BRK-4", CONTRACTS[3], Action.BUY, LOT, D("44.00"), FILL_AT))
    positions = three_positions() + [BrokerPositionLine(CONTRACTS[3], LOT, D("44.00"))]
    sts = statuses()[:3] + [BrokerOrderStatus("BRK-4", CONTRACTS[3], OrderState.EXECUTED, LOT)]
    a = assess(plan(), positions, sts, book, FakePlanner())
    assert a.status is ExecutionStatus.COMPLETE and a.choices == () and a.remaining == ()
