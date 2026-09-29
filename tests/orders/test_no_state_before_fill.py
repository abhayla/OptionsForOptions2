"""AC-2: a submitted order never changes strategy state or positions until the broker confirms
execution (Q195). Plus the round-3 fix (`knowledge/findings/fill-not-exactly-once.json`): a fill
is applied exactly once, keyed by (broker_order_id, trade_id), and validated against the exact
order it claims to fill -- unknown order, wrong contract/side, over-fill, a closed order, and a
reused trade_id across two different orders are all refused with nothing appended; an identical
replay is an idempotent no-op; a genuinely conflicting replay raises FillConflictError.
"""
from __future__ import annotations

import datetime
from decimal import Decimal as D

import pytest

from ofo.engine.legs import Action
from ofo.orders.model import FillConflictError, FillEvent, Order, OrderBook, OrderState


UTC = datetime.timezone.utc
CONTRACT = "NIFTY26OCT23000PE"
READ_AT = datetime.datetime(2026, 9, 29, 10, 5, tzinfo=UTC)


def make_order(**overrides: object) -> Order:
    fields = dict(
        strategy_id="STRAT-9", leg_ref="leg-0", contract=CONTRACT,
        side=Action.SELL, quantity=75, price=D("86.00"), broker_order_id="BRK-9",
    )
    fields.update(overrides)
    return Order(**fields)  # type: ignore[arg-type]


def fill(trade_id: str, quantity: int, *, broker_order_id: str = "BRK-9", contract: str = CONTRACT,
         side: Action = Action.SELL, price: D = D("86.00")) -> FillEvent:
    return FillEvent(
        trade_id, broker_order_id, contract, side, quantity, price,
        datetime.datetime(2026, 9, 29, 10, 0, tzinfo=UTC),
    )


def test_submitted_and_pending_change_nothing() -> None:
    """AC-2: moving to Submitted, then Pending, leaves the ledger untouched."""
    book = OrderBook()
    book.add(make_order())
    book.transition("BRK-9", OrderState.SUBMITTED)
    assert book.position("STRAT-9", CONTRACT) == 0
    book.transition("BRK-9", OrderState.PENDING)
    assert book.position("STRAT-9", CONTRACT) == 0
    assert book.raw_fills() == ()


def test_rejected_and_cancelled_never_touch_the_ledger() -> None:
    """AC-2 negative case: a rejected/cancelled order never moves the ledger, and cannot be
    resubmitted (ADR-017: no automatic or manual retry)."""
    book = OrderBook()
    book.add(make_order())
    book.transition("BRK-9", OrderState.SUBMITTED)
    book.transition("BRK-9", OrderState.REJECTED)
    assert book.position("STRAT-9", CONTRACT) == 0
    with pytest.raises(ValueError):
        book.transition("BRK-9", OrderState.SUBMITTED)  # no resubmission transition exists

    book.add(make_order(leg_ref="leg-1", quantity=20, broker_order_id="BRK-9B"))
    book.transition("BRK-9B", OrderState.CANCELLED)
    assert book.position("STRAT-9", CONTRACT) == 0


def test_a_completing_fill_always_moves_to_executed() -> None:
    """AC-2/Core positive case: a fill that fully covers the order drives it straight to
    Executed, and the position moves by exactly the confirmed quantity."""
    book = OrderBook()
    book.add(make_order(quantity=75))
    book.transition("BRK-9", OrderState.SUBMITTED)
    view = book.apply_fill(fill("T-1", 75))
    assert view.state is OrderState.EXECUTED
    assert book.position("STRAT-9", CONTRACT) == -75  # SELL reduces net position


def test_fill_for_an_unknown_broker_order_id_is_refused() -> None:
    """Round-3 (b): a fill naming a broker_order_id that was never registered is refused."""
    book = OrderBook()
    book.add(make_order())
    book.transition("BRK-9", OrderState.SUBMITTED)
    with pytest.raises(ValueError):
        book.apply_fill(fill("T-1", 10, broker_order_id="BRK-DOES-NOT-EXIST"))
    assert book.raw_fills() == ()


def test_fill_for_the_wrong_contract_is_refused() -> None:
    """Round-3 (c): a fill's contract must match the order it claims to fill."""
    book = OrderBook()
    book.add(make_order())
    book.transition("BRK-9", OrderState.SUBMITTED)
    with pytest.raises(ValueError):
        book.apply_fill(fill("T-1", 10, contract="NIFTY26OCT23400CE"))
    assert book.raw_fills() == ()


def test_fill_for_the_wrong_side_is_refused() -> None:
    """Round-3 (c): a fill's side must match the order it claims to fill."""
    book = OrderBook()
    book.add(make_order(side=Action.SELL))
    book.transition("BRK-9", OrderState.SUBMITTED)
    with pytest.raises(ValueError):
        book.apply_fill(fill("T-1", 10, side=Action.BUY))
    assert book.raw_fills() == ()


def test_fill_for_a_closed_order_is_refused() -> None:
    """Round-3: a fill against an order that is not open (Rejected here) is refused."""
    book = OrderBook()
    book.add(make_order())
    book.transition("BRK-9", OrderState.SUBMITTED)
    book.transition("BRK-9", OrderState.REJECTED)
    with pytest.raises(ValueError):
        book.apply_fill(fill("T-1", 10))
    assert book.raw_fills() == ()


def test_over_fill_is_refused_and_nothing_is_appended() -> None:
    """Round-3: a cumulative fill above the ordered quantity is refused, and the ledger gains no
    row for the refused attempt."""
    book = OrderBook()
    book.add(make_order(quantity=10))
    book.transition("BRK-9", OrderState.SUBMITTED)
    book.apply_fill(fill("T-1", 8))
    with pytest.raises(ValueError):
        book.apply_fill(fill("T-2", 5))  # 8 + 5 > 10
    assert book.order_for("BRK-9").filled_quantity == 8
    assert len(book.raw_fills()) == 1


def test_two_orders_can_independently_reuse_the_same_trade_id() -> None:
    """Round-3 item 1 / finding fill-not-exactly-once: Kite trade ids are only unique per order.
    A trade_id reused across two different orders must fill BOTH independently -- the ledger key
    is (broker_order_id, trade_id), not trade_id alone.
    """
    book = OrderBook()
    book.add(make_order(broker_order_id="BRK-A", quantity=10))
    book.add(make_order(leg_ref="leg-1", broker_order_id="BRK-B", quantity=20))
    book.transition("BRK-A", OrderState.SUBMITTED)
    book.transition("BRK-B", OrderState.SUBMITTED)

    view_a = book.apply_fill(fill("t1", 10, broker_order_id="BRK-A"))
    view_b = book.apply_fill(fill("t1", 20, broker_order_id="BRK-B"))

    assert view_a.filled_quantity == 10
    assert view_a.state is OrderState.EXECUTED
    assert view_b.filled_quantity == 20  # order B's fill was NOT dropped
    assert view_b.state is OrderState.EXECUTED
    assert len(book.raw_fills()) == 2


def test_a_replayed_identical_fill_is_a_no_op_even_after_completion() -> None:
    """Round-3 (a): the exact same fill message (same key, same copy) applied twice is a no-op
    the second time, EVEN once the order has become Executed (proves validation-before-replay-
    lookup does not re-run the "must be open" check on a genuine replay)."""
    book = OrderBook()
    book.add(make_order(quantity=30))
    book.transition("BRK-9", OrderState.SUBMITTED)
    completing = fill("T-1", 30)
    first = book.apply_fill(completing)
    assert first.state is OrderState.EXECUTED
    replayed = book.apply_fill(completing)  # identical FillEvent, same key
    assert replayed.state is OrderState.EXECUTED
    assert replayed.filled_quantity == 30  # not doubled
    assert book.position("STRAT-9", CONTRACT) == -30  # moved once
    assert len(book.raw_fills()) == 1


@pytest.mark.parametrize(
    "conflicting",
    [
        dict(quantity=6),
        dict(contract="NIFTY26OCT23400CE"),
        dict(side=Action.BUY),
        dict(price=D("99.99")),
    ],
)
def test_same_key_different_copy_conflicts(conflicting: dict) -> None:
    """Round-3 (a): the same (broker_order_id, trade_id) key with a DIFFERENT fill (a different
    quantity, contract, side or price) raises FillConflictError, and nothing moves."""
    book = OrderBook()
    book.add(make_order(quantity=30))
    book.transition("BRK-9", OrderState.SUBMITTED)
    book.apply_fill(fill("T-1", 5))
    before = book.position("STRAT-9", CONTRACT)
    base = dict(trade_id="T-1", quantity=5, broker_order_id="BRK-9", contract=CONTRACT, side=Action.SELL,
                price=D("86.00"))
    base.update(conflicting)
    with pytest.raises(FillConflictError):
        book.apply_fill(fill(base["trade_id"], base["quantity"], broker_order_id=base["broker_order_id"],
                              contract=base["contract"], side=base["side"], price=base["price"]))
    assert book.position("STRAT-9", CONTRACT) == before  # unchanged
    assert len(book.raw_fills()) == 1


def test_fill_needs_a_timezone_aware_timestamp() -> None:
    """FillEvent construction refuses a naive datetime."""
    with pytest.raises(ValueError):
        FillEvent("T-1", "BRK-9", CONTRACT, Action.SELL, 10, D("86.00"), datetime.datetime(2026, 9, 29, 10, 0))


def test_fill_needs_a_trade_id() -> None:
    """FillEvent construction refuses a missing/blank trade_id (broker trade id)."""
    with pytest.raises(ValueError):
        FillEvent("", "BRK-9", CONTRACT, Action.SELL, 10, D("86.00"),
                  datetime.datetime(2026, 9, 29, 10, 0, tzinfo=UTC))


@pytest.mark.parametrize(
    "seed_state",
    [OrderState.SUBMITTED, OrderState.PENDING, OrderState.REJECTED, OrderState.CANCELLED],
)
def test_add_refuses_every_non_prepared_state(seed_state: OrderState) -> None:
    """Round-3 item 3: OrderBook.add() only accepts a freshly Prepared order."""
    seeded = make_order()._copy_with(state=seed_state)  # test-only seed
    book = OrderBook()
    with pytest.raises(ValueError):
        book.add(seeded)


def test_reconcile_cumulative_equal_passes() -> None:
    """ADR-016/018: broker's cumulative equals ours -- reconciliation passes cleanly."""
    book = OrderBook()
    book.add(make_order(quantity=30))
    book.transition("BRK-9", OrderState.SUBMITTED)
    book.apply_fill(fill("T-1", 10))
    assert book.reconcile_cumulative("BRK-9", 10, read_at=datetime.datetime.now(UTC)) == "ok"
    assert not book.is_submit_blocked("STRAT-9")


def test_reconcile_cumulative_higher_blocks_next_submit() -> None:
    """ADR-018: broker reports MORE filled than we have -- trades are missing locally; this
    blocks the strategy's next Submitted transition until resolved."""
    book = OrderBook()
    book.add(make_order(quantity=30))
    book.transition("BRK-9", OrderState.SUBMITTED)
    book.apply_fill(fill("T-1", 10))
    assert book.reconcile_cumulative("BRK-9", 25, read_at=datetime.datetime.now(UTC)) == "missing_trades"
    assert book.is_submit_blocked("STRAT-9")

    book.add(make_order(leg_ref="leg-1", broker_order_id="BRK-9C", quantity=5))
    with pytest.raises(ValueError):
        book.transition("BRK-9C", OrderState.SUBMITTED)


def test_reconcile_cumulative_lower_is_a_conflict() -> None:
    """ADR-016: broker reports FEWER filled than we already recorded -- irreconcilable."""
    book = OrderBook()
    book.add(make_order(quantity=30))
    book.transition("BRK-9", OrderState.SUBMITTED)
    book.apply_fill(fill("T-1", 10))
    with pytest.raises(FillConflictError):
        book.reconcile_cumulative("BRK-9", 5, read_at=datetime.datetime.now(UTC))
