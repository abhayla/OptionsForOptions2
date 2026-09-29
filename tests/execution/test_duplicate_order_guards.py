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

W-023 round 5 (issue #37 follow-up), three more mutants with no killing test:
- M10: the ``submit_confirmed`` branch for a definite ``OrderRefused`` stops marking the order Rejected and instead
  leaves it non-terminal -> ``test_refused_retry_frees_the_strategy_for_a_second_retry`` (the round-2 lockout class:
  Retry would see IN_PROGRESS with 0 orders forever instead of PARTIAL_EXCEPTION with 1).
- M13: ``_sync_book`` silently ignores a broker status line for another strategy's order instead of raising a
  mismatch -> ``test_broker_status_for_another_strategys_order_is_a_mismatch``.
- M16: the 60 s stale-read comparison in ``OrderBook.check_read`` moves by one tick ->
  ``test_stale_read_boundary_exact_60s_accepted_then_one_tick_older_is_refused``.

W-023 round 6 (issue #37 last gap): the ``is_submit_blocked`` re-check at the top of ``submit_confirmed`` had no
killing test -> ``test_blocked_strategy_refuses_submit_confirmed_and_sends_nothing``.
"""
from __future__ import annotations

import datetime
from decimal import Decimal as D

from partial_inputs import (
    condor_record,
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
    retry_failed_leg,
    submit_confirmed,
)
from ofo.orders import FillEvent, Order, OrderState

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
                     acknowledgement=close.guard.acknowledgement,  # W-026: a close changes the risk profile
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


def test_refused_retry_frees_the_strategy_for_a_second_retry(catalogue, eligibility) -> None:  # noqa: ANN001
    """M10: a definite OrderRefused must mark the order Rejected (terminal) immediately -- never left non-terminal,
    which would lock the strategy at IN_PROGRESS with 0 orders forever (the round-2 lockout class). A Retry right
    after the refusal must show PARTIAL_EXCEPTION and prepare exactly 1 order for the same leg."""
    book = book_with_three_filled()
    broker = FakeBroker(three_positions(), statuses())
    prep = complete_strategy(plan(), broker, book, FakePlanner(), entry_context(), catalogue, eligibility)
    result = submit_confirmed(prep, choice=COMPLETE, confirmed_by="user:U-42", submitter=FakeSubmitter(refuse=1))
    assert result.submitted == () and result.failed is not None and "Margin Exceeds" in result.failed[1]

    view = book.order_for_key("OFO000000001")
    assert view.state is OrderState.REJECTED  # a definite refusal is terminal at once, not left in flight

    retry = retry_failed_leg(plan(), "leg-4", broker, book, FakePlanner(), entry_context(), catalogue, eligibility)
    assert retry.assessment.status is ExecutionStatus.PARTIAL_EXCEPTION
    assert [(o.contract, o.side, o.quantity) for o in retry.orders] == [(CONTRACTS[3], Action.BUY, LOT)]


def test_broker_status_for_another_strategys_order_is_a_mismatch(catalogue, eligibility) -> None:  # noqa: ANN001
    """M13: ``_sync_book`` -- a broker order-status line whose id belongs to ANOTHER strategy's order in this same
    book is flagged ("belongs to another strategy") and blocks with RECONCILIATION_REQUIRED, never silently
    ignored (which would let this strategy's assessment go on as if that line never arrived)."""
    book = book_with_three_filled()
    book.bind_strategy("S-9", condor_record())  # REQ-036 AC-1: every order's strategy has a record
    other = Order("S-9", "other-leg", CONTRACTS[3], Action.BUY, LOT, D("44.00"), broker_order_id="BRK-OTHER", version_id="v1")
    book.add(other)
    book.transition("BRK-OTHER", OrderState.SUBMITTED)

    foreign_status = BrokerOrderStatus("BRK-OTHER", CONTRACTS[3], OrderState.EXECUTED, LOT)
    prep = complete_strategy(plan(), FakeBroker(three_positions(), statuses() + [foreign_status]), book,
                             FakePlanner(), entry_context(), catalogue, eligibility)
    assert prep.orders == ()
    assert prep.assessment.status is ExecutionStatus.RECONCILIATION_REQUIRED
    assert any("belongs to another strategy" in m for m in prep.assessment.mismatches)


def test_stale_read_boundary_exact_60s_accepted_then_one_tick_older_is_refused(catalogue, eligibility) -> None:  # noqa: ANN001
    """M16: a broker read stamped exactly 60 s old is accepted; one tick (1 ms) older is refused. Locks the ``<``
    (not ``<=``) in ``OrderBook.check_read``'s stale-read comparison ("older than the age limit" is refused)."""
    clock = Clock(t=READ_AT + datetime.timedelta(seconds=10))
    book = book_with_three_filled(clock=clock)

    exact = FakeBroker(three_positions(), statuses(), read_at=clock.t - datetime.timedelta(seconds=60))
    ok = complete_strategy(plan(), exact, book, FakePlanner(), entry_context(), catalogue, eligibility)
    assert [(o.contract, o.side, o.quantity) for o in ok.orders] == [(CONTRACTS[3], Action.BUY, LOT)]
    discard_preparation(ok)

    stale = FakeBroker(three_positions(), statuses(),
                       read_at=clock.t - datetime.timedelta(seconds=60, milliseconds=1))
    refused = complete_strategy(plan(), stale, book, FakePlanner(), entry_context(), catalogue, eligibility)
    assert refused.orders == () and "could not re-read" in refused.reason


def test_blocked_strategy_refuses_submit_confirmed_and_sends_nothing(catalogue, eligibility) -> None:  # noqa: ANN001
    """The ``is_submit_blocked`` re-check at the top of ``submit_confirmed``: a strategy is prepared (Complete,
    ready), then a reconciliation mismatch lands on it (a broker cumulative count higher than the ledger) AFTER the
    preparation was made but BEFORE the user confirms. ``submit_confirmed`` must refuse, and the fake broker/
    submitter must receive ZERO orders -- nothing goes out for a strategy under an unresolved mismatch."""
    book = book_with_three_filled()
    prep = complete_strategy(plan(), FakeBroker(three_positions(), statuses()), book, FakePlanner(),
                             entry_context(), catalogue, eligibility)
    assert prep.ready and len(prep.orders) == 1

    # a reconciliation mismatch lands on the strategy after preparation, before confirmation: the broker now reports
    # more filled on BRK-1 than the ledger has recorded -- reconcile_cumulative blocks the strategy for this reason.
    book.reconcile_cumulative("BRK-1", LOT + 1, read_at=READ_AT + datetime.timedelta(seconds=1))
    assert book.is_submit_blocked("S-1")

    submitter = FakeSubmitter()
    try:
        submit_confirmed(prep, choice=COMPLETE, confirmed_by="user:U-42", submitter=submitter)
        raised = False
    except ValueError as exc:
        raised = True
        assert "unresolved reconciliation mismatch" in str(exc)
    assert raised, "submit_confirmed must refuse a strategy that became blocked after preparation"
    assert submitter.sent == []  # the broker/submitter must see ZERO orders
