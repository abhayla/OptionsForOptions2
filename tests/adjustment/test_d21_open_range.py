"""D-21 round 3: the profit-range cell of a single breakeven, from the engine's own loss regions (ADR-089).

First loss region open below (lower end None) -> profit above the breakeven; last region open above -> profit below;
loss at both ends with one touching point -> not an open range: the old width wording and a finite rank stand.
An open side ranks above every finite width and below "profit at every level" (``compare.OPEN_SIDE_RANK``).
"""
from __future__ import annotations

from decimal import Decimal as D
from types import SimpleNamespace

from ofo.adjustment import compare, what_changes


def cell_of(breakevens, regions):
    figures = SimpleNamespace(breakevens=breakevens, loss_regions=regions)
    col = SimpleNamespace(built=SimpleNamespace(after=()), whole=SimpleNamespace(after_charges=figures), near=None,
                          charges_known=True, no_whole_reason=None)
    ctx = SimpleNamespace(position=SimpleNamespace(lot=1), chain=(), spot=D(120))
    return compare.Rows(col, ctx).breakevens()


def test_loss_below_one_breakeven_means_profit_above_and_ranks_open_not_infinite():
    cell = cell_of((D(100),), ((None, D(100)),))
    assert cell.text == "Profit above 100.00, no upper end" and cell.value is None
    assert D(1000) < cell.rank < D("Infinity")
    assert what_changes._of_cell(cell).number == cell.rank


def test_loss_above_one_breakeven_means_profit_below():
    cell = cell_of((D(100),), ((D(100), None),))
    assert cell.text == "Profit below 100.00, no lower end" and D(1000) < cell.rank < D("Infinity")


def test_a_single_touching_point_is_not_an_open_range():
    cell = cell_of((D(100),), ((None, D(100)), (D(100), None)))  # loses on both sides, breaks even at one level
    assert cell.text == "100 (profit range 20 points)" and cell.value == D(20) and cell.rank == D(20)


def test_profit_at_every_level_outranks_an_open_side():
    cell = cell_of((), ())
    assert cell.rank == D("Infinity") and cell.rank > compare.OPEN_SIDE_RANK
