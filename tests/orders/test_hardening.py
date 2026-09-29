"""Issue #29 items 1-3 (verifier findings on W-019), fixed in W-023 because partial execution depends on them.

1. A broker cumulative LOWER than the ledger blocks submission for that strategy, exactly as a higher one does
   (core invariant 6, ADR-018 "an unresolved mismatch blocks execution"); the block clears only through an explicit,
   audited call, and only when a fresh reconcile of EVERY order of that strategy agrees.
2. An identifier with surrounding whitespace is refused, so "T1 " can never become a second ledger key.
3. The transition table is read-only at runtime.
"""
from __future__ import annotations

import datetime
from decimal import Decimal as D

import pytest

from book_helpers import bound_book

from ofo.engine.legs import Action
from ofo.orders.model import (
    ALLOWED_TRANSITIONS,
    FillConflictError,
    FillEvent,
    Order,
    OrderBook,
    OrderState,
)

UTC = datetime.timezone.utc
AT = datetime.datetime(2026, 9, 29, 10, 0, tzinfo=UTC)
CONTRACT = "NIFTY26O0623200CE"
LATER = AT + datetime.timedelta(seconds=1)


#: Platform clock for these tests: well after every read used here, reads up to a day old accepted.
NOW = AT + datetime.timedelta(minutes=10)


def _book_with_fill(filled: int = 10) -> OrderBook:
    book = bound_book(clock=lambda: NOW, max_read_age=datetime.timedelta(days=1))
    book.add(Order("STRAT-9", "leg-0", CONTRACT, Action.BUY, 75, D("91.50"), broker_order_id="BRK-9", version_id="v1"))
    book.transition("BRK-9", OrderState.SUBMITTED)
    book.apply_fill(FillEvent("T-1", "BRK-9", CONTRACT, Action.BUY, filled, D("91.50"), AT))
    return book


def _second_order(book: OrderBook) -> None:
    book.add(Order("STRAT-9", "leg-1", CONTRACT, Action.BUY, 75, D("91.50"), broker_order_id="BRK-10", version_id="v1"))


# -- item 1 -------------------------------------------------------------------------------------------------------

def test_lower_broker_count_blocks_submit_for_the_strategy() -> None:
    """Item 1: broker 5 filled vs ledger 10 raises AND blocks the next Submitted transition for the strategy."""
    book = _book_with_fill(10)
    _second_order(book)
    with pytest.raises(FillConflictError):
        book.reconcile_cumulative("BRK-9", 5, read_at=AT)
    assert book.is_submit_blocked("STRAT-9") is True
    with pytest.raises(ValueError, match="reconciliation mismatch"):
        book.transition("BRK-10", OrderState.SUBMITTED)


def test_block_clears_only_after_a_fresh_reconcile_agrees_and_is_audited() -> None:
    """Item 1: clearing needs every order of the strategy re-read and equal; the clear is recorded with actor/reason."""
    book = _book_with_fill(10)
    _second_order(book)
    with pytest.raises(FillConflictError):
        book.reconcile_cumulative("BRK-9", 5, read_at=AT)

    # still disagreeing: refused, block stays, nothing audited as cleared
    with pytest.raises(FillConflictError):
        book.clear_reconciliation_block("STRAT-9", {"BRK-9": 5, "BRK-10": 0}, read_at=LATER, actor="user:U-1", reason="r", at=AT)
    assert book.is_submit_blocked("STRAT-9")
    # that disagreeing read at LATER renewed the block, so every later clear needs a read after LATER
    fresher = LATER + datetime.timedelta(seconds=1)
    # an order of the strategy missing from the fresh read: refused (a partial re-read is not agreement)
    with pytest.raises(ValueError, match="BRK-10"):
        book.clear_reconciliation_block("STRAT-9", {"BRK-9": 10}, read_at=fresher, actor="user:U-1", reason="r", at=AT)
    assert book.is_submit_blocked("STRAT-9")
    # an order of ANOTHER strategy in the read: refused (unknown keys are never ignored)
    with pytest.raises(ValueError, match="BRK-X"):
        book.clear_reconciliation_block(
            "STRAT-9", {"BRK-9": 10, "BRK-10": 0, "BRK-X": 0}, read_at=fresher, actor="user:U-1", reason="r", at=AT)
    assert book.is_submit_blocked("STRAT-9")

    book.clear_reconciliation_block(
        "STRAT-9", {"BRK-9": 10, "BRK-10": 0}, read_at=fresher, actor="user:U-1", reason="broker re-read agrees", at=AT)
    assert book.is_submit_blocked("STRAT-9") is False
    events = book.reconciliation_events("STRAT-9")
    # the first mismatch, the refused re-read that still disagreed (every disagreeing read is audited), the clear
    assert [e.kind for e in events] == ["blocked", "blocked", "cleared"]
    assert events[0].broker_order_id == "BRK-9" and events[0].broker_filled == 5 and events[0].local_filled == 10
    assert (events[2].actor, events[2].reason, events[2].at) == ("user:U-1", "broker re-read agrees", AT)
    book.transition("BRK-10", OrderState.SUBMITTED)  # submission works again


def test_clearing_an_unblocked_strategy_is_refused() -> None:
    """Item 1 negative: there is nothing to clear, so the call is refused rather than silently audited."""
    book = _book_with_fill(10)
    with pytest.raises(ValueError, match="not blocked"):
        book.clear_reconciliation_block("STRAT-9", {"BRK-9": 10}, read_at=LATER, actor="user:U-1", reason="r", at=AT)


def test_clear_needs_actor_reason_and_aware_time() -> None:
    """Item 1 input domain: blank actor/reason and a naive time are refused; the block stays."""
    book = _book_with_fill(10)
    book.reconcile_cumulative("BRK-9", 12, read_at=AT)
    for kwargs in (
        {"actor": " ", "reason": "r", "at": AT},
        {"actor": "user:U-1", "reason": "", "at": AT},
        {"actor": "user:U-1", "reason": "r", "at": datetime.datetime(2026, 9, 29, 10, 0)},
    ):
        with pytest.raises(ValueError):
            book.clear_reconciliation_block("STRAT-9", {"BRK-9": 10}, read_at=LATER, **kwargs)
    assert book.is_submit_blocked("STRAT-9")


def test_clearing_with_a_stale_read_is_refused() -> None:
    """Item 1 / W-023 fix (e), verifier attack 3: a broker read taken BEFORE (or at) the read that set the block
    cannot clear it, even when its counts agree; a read taken after it can."""
    t_block = AT + datetime.timedelta(minutes=5)
    book = _book_with_fill(10)
    book.reconcile_cumulative("BRK-9", 12, read_at=t_block)
    for stale in (AT, t_block):
        with pytest.raises(ValueError, match="stale"):
            book.clear_reconciliation_block("STRAT-9", {"BRK-9": 10}, read_at=stale, actor="user:U-1", reason="r",
                                            at=t_block)
        assert book.is_submit_blocked("STRAT-9")
    book.clear_reconciliation_block("STRAT-9", {"BRK-9": 10}, read_at=t_block + datetime.timedelta(seconds=1),
                                    actor="user:U-1", reason="r", at=t_block)
    assert not book.is_submit_blocked("STRAT-9")


def test_future_stamped_read_neither_clears_nor_sets_a_block() -> None:
    """W-023 round 3 red (c): a read stamped a year ahead is refused by clear (block kept) and by reconcile (no
    block, no block time pushed forward); a read within the 5 s skew is accepted."""
    year_ahead = NOW + datetime.timedelta(days=365)
    book = _book_with_fill(10)
    book.reconcile_cumulative("BRK-9", 12, read_at=AT)
    with pytest.raises(ValueError, match="future"):
        book.clear_reconciliation_block("STRAT-9", {"BRK-9": 10}, read_at=year_ahead, actor="user:U-1", reason="r",
                                        at=NOW)
    assert book.is_submit_blocked("STRAT-9")
    with pytest.raises(ValueError, match="future"):
        book.reconcile_cumulative("BRK-9", 13, read_at=year_ahead)
    # the refused read did not push the block time forward: an honest later read still clears it
    book.clear_reconciliation_block("STRAT-9", {"BRK-9": 10}, read_at=NOW + datetime.timedelta(seconds=4),
                                    actor="user:U-1", reason="r", at=NOW)
    assert not book.is_submit_blocked("STRAT-9")


def test_stale_read_older_than_age_limit_refused() -> None:
    """W-023 round 3: a read older than the book's age limit (default 60 s) is refused."""
    book = bound_book(clock=lambda: NOW)
    book.add(Order("STRAT-9", "leg-0", CONTRACT, Action.BUY, 75, D("91.50"), broker_order_id="BRK-9", version_id="v1"))
    with pytest.raises(ValueError, match="stale"):
        book.reconcile_cumulative("BRK-9", 0, read_at=NOW - datetime.timedelta(seconds=61))
    assert book.reconcile_cumulative("BRK-9", 0, read_at=NOW - datetime.timedelta(seconds=59)) == "ok"


def test_reconcile_needs_an_aware_read_time() -> None:
    """Item 1 input domain: a naive read_at is refused and nothing is blocked."""
    book = _book_with_fill(10)
    with pytest.raises(ValueError):
        book.reconcile_cumulative("BRK-9", 12, read_at=datetime.datetime(2026, 9, 29, 10, 0))
    assert not book.is_submit_blocked("STRAT-9")


# -- item 2 -------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("trade_id", ["T-1 ", " T-1", "T-1\t", "\nT-1"])
def test_trade_id_with_surrounding_whitespace_is_refused(trade_id: str) -> None:
    """Item 2: "T-1 " is refused at construction, so a padded replay cannot double the filled quantity."""
    book = _book_with_fill(3)
    with pytest.raises(ValueError, match="whitespace"):
        FillEvent(trade_id, "BRK-9", CONTRACT, Action.BUY, 3, D("91.50"), AT)
    assert book.order_for("BRK-9").filled_quantity == 3


@pytest.mark.parametrize("field", ["broker_order_id", "strategy_id", "leg_ref", "contract"])
def test_other_identifiers_with_whitespace_are_refused(field: str) -> None:
    """Item 2, swept to the class: every identifier on Order refuses surrounding whitespace."""
    values = {"strategy_id": "S", "leg_ref": "L", "contract": CONTRACT, "broker_order_id": "B"}
    values[field] = values[field] + " "
    with pytest.raises(ValueError, match="whitespace"):
        Order(values["strategy_id"], values["leg_ref"], values["contract"], Action.BUY, 75, D("1.00"),
              broker_order_id=values["broker_order_id"], version_id="v1")


# -- item 3 -------------------------------------------------------------------------------------------------------

def test_transition_table_cannot_be_changed_at_runtime() -> None:
    """Item 3: neither the table nor any of its rows can be mutated."""
    with pytest.raises(TypeError):
        ALLOWED_TRANSITIONS[OrderState.REJECTED] = frozenset({OrderState.SUBMITTED})  # type: ignore[index]
    with pytest.raises(TypeError):
        del ALLOWED_TRANSITIONS[OrderState.PREPARED]  # type: ignore[attr-defined]
    for row in ALLOWED_TRANSITIONS.values():
        assert isinstance(row, frozenset)
    assert ALLOWED_TRANSITIONS[OrderState.REJECTED] == frozenset()
