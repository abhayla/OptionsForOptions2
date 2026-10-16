"""ADR-058: a delisted contract held by a live strategy raises that strategy's reconciliation (ADR-018/ADR-019).

Core proof: an OrderBook with S1 holding 65 of a contract and S2 flat in it; the delisting of that contract blocks S1
(reason code ``delisted_held``) and leaves S2 unblocked. No recorded case exists: the ADR-058 case (NIFTY Dec-2029
23000 CE, token 61746) was never held, so the positions are built by hand on the real book (fills and an adopted
holding), the delisting is the function's input.
"""
from __future__ import annotations

import datetime
from decimal import Decimal as D

import pytest
from book_helpers import bound_book

from ofo.engine.legs import Action
from ofo.instruments.models import NSE_FO, InstrumentId
from ofo.orders.model import AdoptedHolding, FillEvent, Order, OrderState, Product
from ofo.reconciliation.delisted import DELISTED_HELD, DelistedContract, DelistedMappingError, block_delisted_held

AT = datetime.datetime(2026, 10, 7, 10, 0, tzinfo=datetime.UTC)
HELD = "NIFTY26O0623200CE"  # real catalogue symbols (tests/test_fixture_symbols.py)
OTHER = "NIFTY26O0623400CE"
HELD_ID = InstrumentId(NSE_FO, 61746)
OTHER_ID = InstrumentId(NSE_FO, 61747)


def _hold(book, strategy: str, symbol: str, boid: str, side: Action = Action.BUY, qty: int = 65) -> None:
    book.add(Order(strategy, "leg-0", symbol, side, qty, D("91.50"), broker_order_id=boid, version_id="v1"))
    book.transition(boid, OrderState.SUBMITTED)
    book.apply_fill(FillEvent(f"T-{boid}", boid, symbol, side, qty, D("91.50"), AT))


def _book():
    book = bound_book(clock=lambda: AT)
    _hold(book, "STRAT-1", HELD, "B-1")  # S1 holds 65
    _hold(book, "STRAT-2", OTHER, "B-2")  # S2 holds a different contract, flat in HELD
    return book


def test_held_strategy_is_blocked_with_the_code_and_a_flat_one_is_not():
    book = _book()
    blocked = block_delisted_held(book, [DelistedContract(HELD_ID, (HELD,))])
    assert blocked == ("STRAT-1",)
    assert book.is_submit_blocked("STRAT-1") and not book.is_submit_blocked("STRAT-2")
    assert not book.is_submit_blocked("STRAT-5")
    assert book.reconciliation_events("STRAT-1")[-1].reason == DELISTED_HELD == "delisted_held"
    assert book.reconciliation_events("STRAT-2") == ()


def test_a_short_position_is_blocked_too():
    book = bound_book(clock=lambda: AT)
    book.record_adopted([AdoptedHolding("STRAT-1", HELD, Action.SELL, 65, Product.NRML, "ref-1", AT)])
    assert book.position("STRAT-1", HELD) == -65
    assert block_delisted_held(book, [DelistedContract(HELD_ID, (HELD,))]) == ("STRAT-1",)
    assert book.is_submit_blocked("STRAT-1")


def test_a_flat_position_after_an_exit_is_not_blocked():
    book = _book()
    _hold(book, "STRAT-1", HELD, "B-3", Action.SELL)  # S1 sold its 65: flat (order history alone holds nothing)
    assert book.position("STRAT-1", HELD) == 0
    assert block_delisted_held(book, [DelistedContract(HELD_ID, (HELD,))]) == ()
    assert not book.is_submit_blocked("STRAT-1")


def test_a_delisted_contract_matching_no_book_key_blocks_nothing():
    book = _book()
    assert block_delisted_held(book, [DelistedContract(InstrumentId(NSE_FO, 99999), ("NO-SUCH-SYMBOL",))]) == ()
    assert not any(book.is_submit_blocked(s) for s in book.strategy_ids())


def test_one_delisted_contract_matching_two_held_keys_raises_and_blocks_nothing():
    book = _book()
    with pytest.raises(DelistedMappingError, match="matches 2"):
        block_delisted_held(book, [DelistedContract(HELD_ID, (HELD, OTHER))])
    assert not any(book.is_submit_blocked(s) for s in book.strategy_ids())


def test_two_delisted_contracts_naming_one_symbol_raise_and_block_nothing():
    book = _book()
    with pytest.raises(DelistedMappingError, match="named by delisted"):
        block_delisted_held(book, [DelistedContract(OTHER_ID, (OTHER,)),
                                   DelistedContract(HELD_ID, ("NO-SUCH-OTHER", OTHER))])
    assert not any(book.is_submit_blocked(s) for s in book.strategy_ids())


def test_an_unusable_delisted_entry_is_refused():
    with pytest.raises(ValueError, match="InstrumentId"):
        DelistedContract((NSE_FO, 61746), (HELD,))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="tradingsymbols"):
        DelistedContract(HELD_ID, ())
