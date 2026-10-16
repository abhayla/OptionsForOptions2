"""W-091 domain rules on the fill ledger (kit CI runs tests/ only; the real-reply proof is in tests_app/).

ADR-103 (F-40 attack A1): a fill is never read as a side flip - an exit fill seen before the entry fill it closes, or
a fill carrying the position across zero, is refused (nothing recorded) and blocks the strategy until the missing fill
arrives. ADR-102: realised P&L from flat fills is exact Decimal, quantized to the paisa for output.
Values are the owner's real 2026-10-16 order (BUY 65 at 5.10, SELL 65 at 3.10), worked by hand: (3.10-5.10)x65 = -130.
"""
from __future__ import annotations

import datetime
from decimal import Decimal as D

import pytest

from ofo.engine import Action
from ofo.engine.product import Product
from ofo.orders.model import FillEvent, Order, OrderState, OutOfOrderFillError, realised_pnl
from tests.orders.book_helpers import bound_book

AT = datetime.datetime(2026, 1, 5, 4, 0, tzinfo=datetime.UTC)
C = "NIFTY26O0623200CE"  # a catalogue symbol (tests/test_fixture_symbols.py); the rule is contract-agnostic


def _clock() -> datetime.datetime:
    return AT


def _order(tag: str, side: Action, qty: int, boid: str) -> Order:
    return Order("STRAT-1", "L0", C, side, qty, D("5.45"), broker_order_id=boid, version_id="v1", client_tag=tag)


def _fill(tid: str, boid: str, side: Action, qty: int, price: str = "5.10") -> FillEvent:
    return FillEvent(tid, boid, C, side, qty, D(price), AT)


def _book(*orders: Order):
    book = bound_book(clock=_clock)
    for o in orders:
        book.add(o)
        book.mirror_broker_state(o.client_tag, OrderState.PENDING)
    return book


def test_exit_fill_before_its_entry_is_refused_blocked_then_accepted_after_the_entry():
    book = _book(_order("E", Action.BUY, 65, "B1"), _order("X", Action.SELL, 65, "S1"))
    with pytest.raises(OutOfOrderFillError):
        book.apply_fill(_fill("T2", "S1", Action.SELL, 65, "3.10"))
    assert book.position("STRAT-1", C) == 0 and book.raw_fills() == ()
    assert book.is_submit_blocked("STRAT-1")
    book.apply_fill(_fill("T1", "B1", Action.BUY, 65))
    book.apply_fill(_fill("T2", "S1", Action.SELL, 65, "3.10"))
    book.apply_fill(_fill("T2", "S1", Action.SELL, 65, "3.10"))  # replay: no-op
    assert book.position("STRAT-1", C) == 0 and len(book.raw_fills()) == 2


def test_a_fill_crossing_zero_is_refused():
    book = _book(_order("E", Action.BUY, 65, "B1"), _order("X", Action.SELL, 130, "S1"))
    book.apply_fill(_fill("T1", "B1", Action.BUY, 65))
    with pytest.raises(OutOfOrderFillError):
        book.apply_fill(_fill("T2", "S1", Action.SELL, 130, "3.10"))
    assert book.position("STRAT-1", C) == 65


def test_a_short_strategy_opens_with_a_sell_and_closes_with_a_buy():
    book = _book(_order("E", Action.SELL, 65, "S1"), _order("X", Action.BUY, 65, "B1"))
    book.apply_fill(_fill("T1", "S1", Action.SELL, 65))
    assert book.position("STRAT-1", C) == -65
    book.apply_fill(_fill("T2", "B1", Action.BUY, 65))
    assert book.position("STRAT-1", C) == 0 and not book.is_submit_blocked("STRAT-1")


def test_an_adopted_holding_sets_the_opening_side():
    book = bound_book(clock=_clock)
    book.record_adopted(book.check_adopted("STRAT-1", [(C, Action.BUY, 65, Product.NRML)], reference="adopt", at=AT))
    book.add(_order("X", Action.SELL, 65, "S1"))
    book.mirror_broker_state("X", OrderState.PENDING)
    book.apply_fill(_fill("T1", "S1", Action.SELL, 65, "3.10"))
    assert book.position("STRAT-1", C) == 0


def test_realised_pnl_is_exact_and_at_the_paisa():
    fills = [_fill("T1", "B1", Action.BUY, 65, "5.1"), _fill("T2", "S1", Action.SELL, 65, "3.1")]
    pnl = realised_pnl(fills)
    assert type(pnl) is D and str(pnl) == "-130.00"
    with pytest.raises(ValueError, match="still open"):
        realised_pnl(fills[:1])
    with pytest.raises(ValueError):
        realised_pnl([])
