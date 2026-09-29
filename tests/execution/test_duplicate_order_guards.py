"""W-023 round 4 (PARKED #37, independent verifier): two duplicate-order guards had no test, and the 60 s/5 s
boundaries could move by one tick unnoticed. No production change; these tests only lock the guards already in
``backend/ofo/execution/partial.py`` and ``backend/ofo/orders/model.py``. REQ-058 AC-4.

Mutants named by the verifier, each with the test below that must turn red against it:
- M3: the ``submit_confirmed`` branch for a submit timeout / any outcome other than ``OrderRefused`` marks the order
  Rejected instead of leaving it non-terminal (OD-l) -> ``test_timeout_leaves_order_in_flight_not_rejected``.
- M2: the "nothing is prepared while an order is in flight" check in ``_prepare_missing`` (``if a.open_orders:``)
  is deleted -> ``test_open_exit_order_blocks_completion_after_a_fresh_close_read``.
- M1: the 60 s unconfirmed-grace comparison in ``_sync_book`` moves by one tick ->
  ``test_grace_boundary_exact_60s_still_in_flight_then_one_tick_over_is_mismatch``.
- M6: the 5 s clock-skew comparison in ``OrderBook.check_read`` moves by one tick ->
  ``test_skew_boundary_exact_5s_accepted_then_one_tick_over_is_refused``.
"""
from __future__ import annotations

import datetime
from decimal import Decimal as D

from partial_inputs import (
    CONTRACTS,
    LOT,
    READ_AT,
    Clock,
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
from ofo.execution.partial import (
    BrokerOrderStatus,
    BrokerPositionLine,
    ExecutionStatus,
    PartialChoice,
    close_partial_strategy,
    complete_strategy,
    discard_preparation,
    submit_confirmed,
)
from ofo.orders import FillEvent, OrderState

COMPLETE = PartialChoice.COMPLETE_STRATEGY
LTPS = (D("40.00"), D("80.00"), D("120.00"))


class _TimeoutSubmitter(FakeSubmitter):
    """Accepts the order onto the wire, then the broker call itself times out (outcome unknown, OD-l)."""

    def submit(self, order):  # noqa: ANN001, ANN201
        self.sent.append(order)
        raise TimeoutError("broker did not respond in time")


def test_timeout_leaves_order_in_flight_not_rejected(catalogue, eligibility) -> None:  # noqa: ANN001
    """M3: a submit timeout must leave the order non-terminal ("outcome unknown"), never Rejected. If it were marked
    Rejected, a second Complete would prepare another BUY 23,600 CE x65 -- the double-order class of rounds 1-2."""
    book = book_with_three_filled()
    first_read = FakeBroker(three_positions(), statuses())
    prep = complete_strategy(plan(), first_read, book, FakePlanner(), entry_context(), catalogue, eligibility)
    assert [(o.contract, o.side, o.quantity) for o in prep.orders] == [(CONTRACTS[3], Action.BUY, LOT)]

    result = submit_confirmed(prep, choice=COMPLETE, confirmed_by="user:U-42", submitter=_TimeoutSubmitter())
    assert result.submitted == ()
    assert result.failed == ("leg-4", "outcome unknown: broker did not respond in time")

    view = book.order_for_key("OFO000000001")
    assert view.state not in (OrderState.REJECTED, OrderState.CANCELLED)  # locks OD-l: unknown != refused
    assert view.state is OrderState.SUBMITTED

    # a second Complete on a read that still does not show the timed-out order prepares NOTHING: it is in flight
    lagging = FakeBroker(three_positions(), statuses(), read_at=READ_AT + datetime.timedelta(seconds=5))
    second = complete_strategy(plan(), lagging, book, FakePlanner(), entry_context(), catalogue, eligibility)
    assert second.orders == () and second.assessment.status is ExecutionStatus.IN_PROGRESS

    # later Zerodha confirms the timed-out order actually filled: attach its real id, then the ledger fill
    book.attach_broker_id("OFO000000001", "NEW-9")
    book.apply_fill(FillEvent("T-9", "NEW-9", CONTRACTS[3], Action.BUY, LOT, D("44.00"), READ_AT))
    positions = three_positions() + [BrokerPositionLine(CONTRACTS[3], LOT, D("44.00"))]
    sts = statuses() + [BrokerOrderStatus("NEW-9", CONTRACTS[3], OrderState.EXECUTED, LOT, None, "OFO000000001")]
    final = complete_strategy(plan(), FakeBroker(positions, sts, read_at=READ_AT + datetime.timedelta(seconds=6)),
                              book, FakePlanner(), entry_context(), catalogue, eligibility)
    assert final.orders == () and final.assessment.status is ExecutionStatus.COMPLETE  # no duplicate, ever


def test_open_exit_order_blocks_completion_after_a_fresh_close_read(catalogue, eligibility) -> None:  # noqa: ANN001
    """M2: an open exit order on a filled leg must block Complete, even on a read taken AFTER the Close read (so the
    separate "needs a fresh read after Close" guard does not also explain the block). Three Close exit orders are
    sent and stay non-terminal (no status read yet); a later, fresher read still must prepare nothing for the
    missing 23,600 CE leg while those exits are in flight."""
    book = book_with_three_filled()
    stale = FakeBroker(three_positions(LTPS), statuses(), read_at=READ_AT)
    close = close_partial_strategy(plan(), stale, book, FakePlanner(), entry_context(), catalogue, eligibility)
    assert close.ready and len(close.orders) == 3
    submit_confirmed(close, choice=PartialChoice.CLOSE_PARTIAL_STRATEGY, confirmed_by="user:U-42",
                     submitter=FakeSubmitter())

    fresh = FakeBroker(three_positions(LTPS), statuses(), read_at=READ_AT + datetime.timedelta(seconds=5))
    after = complete_strategy(plan(), fresh, book, FakePlanner(), entry_context(), catalogue, eligibility)
    assert after.orders == ()
    assert "in flight" in after.reason  # not "needs a fresh read": the read IS fresher than the Close read
    assert fresh.read_at > stale.read_at  # confirms the read used here really is newer than the Close read


def test_grace_boundary_exact_60s_still_in_flight_then_one_tick_over_is_mismatch(catalogue, eligibility) -> None:  # noqa: ANN001
    """M1: at exactly the 60 s unconfirmed grace the missing order is still IN_PROGRESS; one tick (1 ms) later it is
    a reconciliation mismatch. Locks the ``>`` (not ``>=``) in ``_sync_book``'s grace comparison."""
    clock = Clock(t=READ_AT + datetime.timedelta(seconds=10))
    book = book_with_three_filled(clock=clock)
    prep = complete_strategy(plan(), FakeBroker(three_positions(), statuses(), read_at=clock.t), book,
                             FakePlanner(), entry_context(), catalogue, eligibility)
    submit_confirmed(prep, choice=COMPLETE, confirmed_by="user:U-42", submitter=FakeSubmitter())

    clock.advance(60)  # exactly the grace window since registration
    at_60 = complete_strategy(plan(), FakeBroker(three_positions(), statuses(), read_at=clock.t), book,
                              FakePlanner(), entry_context(), catalogue, eligibility)
    assert at_60.orders == () and at_60.assessment.status is ExecutionStatus.IN_PROGRESS
    assert not any("not in Zerodha's order list" in m for m in at_60.assessment.mismatches)

    clock.t += datetime.timedelta(milliseconds=1)  # one tick past the grace window
    over = complete_strategy(plan(), FakeBroker(three_positions(), statuses(), read_at=clock.t), book,
                             FakePlanner(), entry_context(), catalogue, eligibility)
    assert over.orders == () and over.assessment.status is ExecutionStatus.RECONCILIATION_REQUIRED
    assert any("not in Zerodha's order list" in m for m in over.assessment.mismatches)


def test_skew_boundary_exact_5s_accepted_then_one_tick_over_is_refused(catalogue, eligibility) -> None:  # noqa: ANN001
    """M6: a broker read stamped exactly 5 s ahead of the platform clock is accepted; one tick (1 ms) further ahead
    is refused. Locks the ``>`` (not ``>=``) in ``OrderBook.check_read``'s future-skew comparison."""
    clock = Clock(t=READ_AT + datetime.timedelta(seconds=10))
    book = book_with_three_filled(clock=clock)

    exact = FakeBroker(three_positions(), statuses(), read_at=clock.t + datetime.timedelta(seconds=5))
    ok = complete_strategy(plan(), exact, book, FakePlanner(), entry_context(), catalogue, eligibility)
    assert [(o.contract, o.side, o.quantity) for o in ok.orders] == [(CONTRACTS[3], Action.BUY, LOT)]
    discard_preparation(ok)

    over = FakeBroker(three_positions(), statuses(),
                      read_at=clock.t + datetime.timedelta(seconds=5, milliseconds=1))
    refused = complete_strategy(plan(), over, book, FakePlanner(), entry_context(), catalogue, eligibility)
    assert refused.orders == () and "could not re-read" in refused.reason
