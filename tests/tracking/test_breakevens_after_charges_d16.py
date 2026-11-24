"""D-16 (ADR-263 one basis, GC-ICLIVE-B): the book's breakevens carry the charges the Max Profit / Max Loss beside
them carry. ``book_breakevens(view, terms, charges=C)`` = the levels where booked - C + open payoff = 0; charges 0 /
absent is the old answer. Real book: strategy 63 roll (tests/fixtures/paper/strategy-63-roll.json), booked +962.00."""
from __future__ import annotations

from decimal import Decimal

from ofo.engine.extremes import book_breakevens
from ofo.engine.orderbook import net_positions
from test_extremes import _real

D = Decimal
TWO_LEVELS = 2  # an iron condor has a lower and an upper breakeven


def test_charges_move_both_breakevens_inward_by_the_same_rule():
    orders, terms, _ = _real()
    view = net_positions(orders, {})
    before = book_breakevens(view, terms).levels
    same = book_breakevens(view, terms, charges=D(0)).levels
    after = book_breakevens(view, terms, charges=D("500")).levels
    assert before is not None and after is not None and same == before
    assert len(after) == len(before) == TWO_LEVELS
    assert after[0] > before[0] and after[1] < before[1]  # a charge paid narrows the profit range from both sides
    # hand check: each level moves by the charge divided by the slope at its leg of the condor, so both move
    assert (after[0] - before[0]) > 0 and (before[1] - after[1]) > 0
