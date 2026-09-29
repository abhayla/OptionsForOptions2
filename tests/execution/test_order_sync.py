"""W-023 round 3 core and the independent reviewer's attacks 1-8 (REQ-058 AC-4; ADR-016, ADR-018 Q198; REQ-059).

Core: every Complete / Retry / Close first syncs the book's own orders with the fresh broker order-status read;
"in flight" means non-terminal in that reconciled book, and nothing else.
Class: the platform's view of its own orders not kept in step with the broker.

Golden Iron Condor, 65 units; legs 1-3 filled, the 23,600 CE buy (BRK-4) rejected; the platform then sends a
completing order (NEW-1) and the broker's later read decides what happened to it.
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
from ofo.orders import FillEvent, Order, OrderBook, OrderState

LTPS = (D("40.00"), D("80.00"), D("120.00"))
AFTER_SEND = READ_AT + datetime.timedelta(seconds=10)  # the platform clock (Clock default) when NEW-1 is sent
COMPLETE = PartialChoice.COMPLETE_STRATEGY


def _complete(book: OrderBook, broker: FakeBroker, catalogue, eligibility):  # noqa: ANN001, ANN202
    return complete_strategy(plan(), broker, book, FakePlanner(), entry_context(), catalogue, eligibility)


def _send_new1(book: OrderBook, catalogue, eligibility) -> FakeSubmitter:  # noqa: ANN001
    """Complete on the rejection and send it: NEW-1 (BUY 23,600 CE x 65) is now the platform's own order."""
    prep = _complete(book, FakeBroker(three_positions(LTPS), statuses()), catalogue, eligibility)
    submitter = FakeSubmitter()
    submit_confirmed(prep, choice=COMPLETE, confirmed_by="user:U-42", submitter=submitter)
    return submitter


def _read(state: OrderState, filled: int = 0, reason: str | None = None, *, extra=(), positions=None,  # noqa: ANN001
          read_at: datetime.datetime = AFTER_SEND) -> FakeBroker:
    sts = statuses() + [BrokerOrderStatus("NEW-1", CONTRACTS[3], state, filled, reason, "OFO000000001"), *extra]
    return FakeBroker(positions or three_positions(LTPS), sts, read_at=read_at)


def _prepared(prep) -> list[tuple[str, Action, int]]:  # noqa: ANN001
    return [(o.contract, o.side, o.quantity) for o in prep.orders]


# -- core -----------------------------------------------------------------------------------------------------------

def test_core_rejected_new1_mirrors_into_book_then_complete_and_close_work(catalogue, eligibility) -> None:  # noqa: ANN001
    """Core / attack 1: the broker read shows NEW-1 REJECTED -> the book shows Rejected; Complete prepares exactly the
    missing 65 units of 23,600 CE; Close is available (not locked as "in flight")."""
    book = book_with_three_filled()
    _send_new1(book, catalogue, eligibility)
    assert book.order_for("NEW-1").state is OrderState.SUBMITTED

    prep = _complete(book, _read(OrderState.REJECTED, reason="RMS:Margin Exceeds"), catalogue, eligibility)
    assert book.order_for("NEW-1").state is OrderState.REJECTED
    assert _prepared(prep) == [(CONTRACTS[3], Action.BUY, LOT)]
    assert "RMS:Margin Exceeds" in [f.reason for f in prep.assessment.failures]

    discard_preparation(prep)
    close = close_partial_strategy(plan(), _read(OrderState.REJECTED), book, FakePlanner(), entry_context(),
                                   catalogue, eligibility)
    assert close.ready and len(close.orders) == 3 and close.cancels == ()


# -- reviewer list ----------------------------------------------------------------------------------------------------

def test_cancelled_new1_mirrors_and_frees_complete(catalogue, eligibility) -> None:  # noqa: ANN001
    """Attack 1b: CANCELLED at the broker -> Cancelled in the book; the 65 units are missing again."""
    book = book_with_three_filled()
    _send_new1(book, catalogue, eligibility)
    prep = _complete(book, _read(OrderState.CANCELLED, reason="Cancelled by exchange"), catalogue, eligibility)
    assert book.order_for("NEW-1").state is OrderState.CANCELLED
    assert _prepared(prep) == [(CONTRACTS[3], Action.BUY, LOT)]


def test_pending_new1_mirrors_and_stays_in_flight(catalogue, eligibility) -> None:  # noqa: ANN001
    """Attack 1c: PENDING at the broker -> Pending in the book; still in flight, nothing prepared."""
    book = book_with_three_filled()
    _send_new1(book, catalogue, eligibility)
    prep = _complete(book, _read(OrderState.PENDING), catalogue, eligibility)
    assert book.order_for("NEW-1").state is OrderState.PENDING
    assert prep.orders == () and prep.assessment.status is ExecutionStatus.IN_PROGRESS


def test_executed_new1_with_ledger_fill_is_complete(catalogue, eligibility) -> None:  # noqa: ANN001
    """Attack 1d: EXECUTED at the broker and the fill in the ledger -> Executed, COMPLETE, nothing prepared."""
    book = book_with_three_filled()
    _send_new1(book, catalogue, eligibility)
    book.apply_fill(FillEvent("T-9", "NEW-1", CONTRACTS[3], Action.BUY, LOT, D("44.00"), AFTER_SEND))
    four = three_positions(LTPS) + [BrokerPositionLine(CONTRACTS[3], LOT, D("44.00"))]
    prep = _complete(book, _read(OrderState.EXECUTED, LOT, positions=four), catalogue, eligibility)
    assert book.order_for("NEW-1").state is OrderState.EXECUTED
    assert prep.orders == () and prep.assessment.status is ExecutionStatus.COMPLETE


def test_executed_at_broker_without_ledger_fill_is_a_mismatch(catalogue, eligibility) -> None:  # noqa: ANN001
    """Attack 1e: the broker says NEW-1 filled 65 but no fill reached the ledger -> reconciliation, nothing."""
    book = book_with_three_filled()
    _send_new1(book, catalogue, eligibility)
    prep = _complete(book, _read(OrderState.EXECUTED, LOT), catalogue, eligibility)
    assert prep.orders == () and prep.assessment.status is ExecutionStatus.RECONCILIATION_REQUIRED


def test_missing_from_read_is_unconfirmed_then_mismatch_after_grace(catalogue, eligibility) -> None:  # noqa: ANN001
    """Attack 2: NEW-1 missing from the broker's read -> unconfirmed, in flight, nothing prepared; 61 s after it was
    sent (grace 60 s) the same absence is a reconciliation mismatch."""
    clock = Clock()
    book = book_with_three_filled(clock=clock)
    _send_new1(book, catalogue, eligibility)
    lagging = FakeBroker(three_positions(LTPS), statuses(), read_at=AFTER_SEND)
    first = _complete(book, lagging, catalogue, eligibility)
    assert first.orders == () and first.assessment.status is ExecutionStatus.IN_PROGRESS
    clock.advance(61)
    later = _complete(book, FakeBroker(three_positions(LTPS), statuses(), read_at=clock.t), catalogue, eligibility)
    assert later.orders == () and later.assessment.status is ExecutionStatus.RECONCILIATION_REQUIRED
    assert any("not in Zerodha's order list" in m for m in later.assessment.mismatches)


def test_unknown_broker_order_is_a_mismatch(catalogue, eligibility) -> None:  # noqa: ANN001
    """Attack 3: the broker shows an order the platform never sent -> reconciliation required, nothing prepared,
    and Close is not offered."""
    ghost = BrokerOrderStatus("GHOST-1", CONTRACTS[3], OrderState.PENDING, 0)
    book = book_with_three_filled()
    broker = FakeBroker(three_positions(LTPS), statuses() + [ghost])
    prep = _complete(book, broker, catalogue, eligibility)
    close = close_partial_strategy(plan(), broker, book, FakePlanner(), entry_context(), catalogue, eligibility)
    assert prep.orders == () and prep.assessment.status is ExecutionStatus.RECONCILIATION_REQUIRED
    assert close.orders == ()


class _IdSubmitter(FakeSubmitter):
    def __init__(self, broker_id: object) -> None:
        super().__init__()
        self.broker_id = broker_id

    def submit(self, order) -> str:
        self.sent.append(order)
        return self.broker_id  # type: ignore[return-value]


def test_unusable_id_after_acceptance_is_reconciliation_not_failure(catalogue, eligibility) -> None:  # noqa: ANN001
    """Attack 4: the broker accepts but returns a padded, duplicate or empty id -> not "failed"; the order stays
    tracked (non-terminal) under its client tag, the strategy needs reconciliation, the next Complete sends nothing."""
    for bad in (" NEW-1", "BRK-1", ""):
        book = book_with_three_filled()
        prep = _complete(book, FakeBroker(three_positions(LTPS), statuses()), catalogue, eligibility)
        submitter = _IdSubmitter(bad)
        result = submit_confirmed(prep, choice=COMPLETE, confirmed_by="user:U-42", submitter=submitter)
        assert result.failed is None and result.needs_reconciliation == ("OFO000000001",), bad
        assert book.order_for_key("OFO000000001").state not in (OrderState.REJECTED, OrderState.CANCELLED)
        assert book.is_submit_blocked("S-1")
        again = _complete(book, FakeBroker(three_positions(LTPS), statuses(), read_at=AFTER_SEND), catalogue,
                          eligibility)
        assert again.orders == () and len(submitter.sent) == 1


class _BlockingSubmitter(FakeSubmitter):
    """Accepts, but a reconciliation block lands while the order is on the wire (so Submitted is refused)."""

    def __init__(self, book: OrderBook) -> None:
        super().__init__()
        self.book = book

    def submit(self, order) -> str:
        self.book.block_strategy("S-1", "mismatch found by another read while sending")
        return self._send(order)


def test_transition_refused_after_send_still_counts_as_in_flight(catalogue, eligibility) -> None:  # noqa: ANN001
    """Attack 5: marking Submitted raises after the broker accepted -> the order stays Prepared, which is
    non-terminal: it is in the reconciled book's open orders and nothing more is prepared."""
    book = book_with_three_filled()
    prep = _complete(book, FakeBroker(three_positions(LTPS), statuses()), catalogue, eligibility)
    submit_confirmed(prep, choice=COMPLETE, confirmed_by="user:U-42", submitter=_BlockingSubmitter(book))
    assert book.order_for("NEW-1").state is OrderState.PREPARED
    again = _complete(book, FakeBroker(three_positions(LTPS), statuses(), read_at=AFTER_SEND), catalogue,
                      eligibility)
    assert again.orders == ()
    assert "OFO000000001" in [v.key for v in again.assessment.open_orders]


class _ConcurrentSubmitter(FakeSubmitter):
    """While the order is on the wire, the user presses Complete again (the broker's read does not show it yet)."""

    def __init__(self, book: OrderBook, catalogue, eligibility) -> None:  # noqa: ANN001
        super().__init__()
        self.args = (book, catalogue, eligibility)
        self.during = None

    def submit(self, order) -> str:
        book, catalogue, eligibility = self.args
        self.during = _complete(book, FakeBroker(three_positions(LTPS), statuses()), catalogue, eligibility)
        return self._send(order)


def test_order_is_in_flight_from_before_the_broker_sees_it(catalogue, eligibility) -> None:  # noqa: ANN001
    """Attack 6: registered BEFORE sending, the order (Prepared) is in flight during submit() itself: a second
    Complete pressed meanwhile prepares nothing. Exactly one 65-unit order ever goes out."""
    book = book_with_three_filled()
    prep = _complete(book, FakeBroker(three_positions(LTPS), statuses()), catalogue, eligibility)
    submitter = _ConcurrentSubmitter(book, catalogue, eligibility)
    submit_confirmed(prep, choice=COMPLETE, confirmed_by="user:U-42", submitter=submitter)
    assert submitter.during.orders == ()
    assert [(o.contract, o.quantity) for o in submitter.sent] == [(CONTRACTS[3], LOT)]


def test_future_read_refused_within_skew_accepted_stale_refused(catalogue, eligibility) -> None:  # noqa: ANN001
    """Attack 7: a read stamped a year ahead, or 61 s old, prepares nothing; a read 4 s ahead (inside the 5 s skew)
    is accepted."""
    now = AFTER_SEND
    for bad in (now + datetime.timedelta(days=365), now - datetime.timedelta(seconds=61)):
        prep = _complete(book_with_three_filled(), FakeBroker(three_positions(LTPS), statuses(), read_at=bad),
                         catalogue, eligibility)
        assert prep.orders == () and "could not re-read" in prep.reason
    ok = _complete(book_with_three_filled(),
                   FakeBroker(three_positions(LTPS), statuses(), read_at=now + datetime.timedelta(seconds=4)),
                   catalogue, eligibility)
    assert _prepared(ok) == [(CONTRACTS[3], Action.BUY, LOT)]


def test_double_complete_on_lagging_read_sends_exactly_one(catalogue, eligibility) -> None:  # noqa: ANN001
    """Attack 8: Complete, send, Complete again on a read that still lags (NEW-1 absent) -> one order in total."""
    book = book_with_three_filled()
    submitter = _send_new1(book, catalogue, eligibility)
    again = _complete(book, FakeBroker(three_positions(LTPS), statuses(), read_at=AFTER_SEND), catalogue,
                      eligibility)
    assert again.orders == ()
    assert [(o.contract, o.quantity) for o in submitter.sent] == [(CONTRACTS[3], LOT)]


def test_close_lists_cancel_requests_for_own_open_entry_orders(catalogue, eligibility) -> None:  # noqa: ANN001
    """OD-m (owner question Q223): BRK-4 (BUY 23,600 CE) is still PENDING at the broker, so the strategy is in
    progress; Close is available, prepares exits for the three filled legs, and LISTS BRK-4 for cancellation."""
    book = book_with_three_filled(fourth=OrderState.SUBMITTED)
    broker = FakeBroker(three_positions(LTPS), statuses(OrderState.PENDING, None))
    close = close_partial_strategy(plan(), broker, book, FakePlanner(), entry_context(), catalogue, eligibility)
    assert close.assessment.status is ExecutionStatus.IN_PROGRESS
    assert close.ready and close.cancels == ("BRK-4",)
    assert sorted((o.contract, o.side) for o in close.orders) == sorted(
        [(CONTRACTS[0], Action.SELL), (CONTRACTS[1], Action.BUY), (CONTRACTS[2], Action.BUY)])
