"""D-10 (ADR-207 (2), REQ-109 AC-4): a contract's order history splits into lifecycles (open -> flat). A closed
lifecycle keeps its own booked P&L, entry and exit price; a reopening of the same contract is a separate open row
with booked 0.
Real case: C1 155, short 25400 PE closed for +643.50, then a new long 25400 PE."""
import datetime
from decimal import Decimal as D

import pytest
from ofo.engine.orderbook import PaperOrder, lifecycles, net_positions

T0 = datetime.datetime(2026, 11, 23, 9, 30, tzinfo=datetime.UTC)
PE = "25400PE"


def order(n, side, qty, price, kind="open"):
    return PaperOrder(PE, side, qty, D(price), kind, T0 + datetime.timedelta(minutes=n))


# SELL 150 at 120.00, BUY back 150 at 115.71: (120.00 - 115.71) x 150 = 4.29 x 150 = 643.50; then a NEW long at 90.00
C1 = [order(0, "SELL", 150, "120.00"), order(1, "BUY", 150, "115.71", "exit"), order(2, "BUY", 150, "90.00")]


def test_closed_short_keeps_its_booked_and_the_new_long_starts_at_zero():
    view = lifecycles(C1, {PE: D("95.00")})
    assert len(view.closed) == 1 and len(view.positions) == 1
    closed, new = view.closed[0], view.positions[0]
    assert (closed.instrument_id, closed.side, closed.quantity) == (PE, "SELL", 150)
    assert (closed.average_entry, closed.average_exit, closed.booked) == (D("120"), D("115.71"), D("643.50"))
    assert (new.net_quantity, new.average, new.booked) == (150, D("90"), D(0))
    assert new.unbooked == D("750") and new.total == D("750")  # (95.00 - 90.00) x 150, own lifecycle only
    assert closed.booked + new.booked == net_positions(C1, {PE: D("95.00")}).booked  # the strategy's booked total


def test_every_total_is_unchanged_and_rows_reconcile():
    old = net_positions(C1, {PE: D("95.00")})
    new = lifecycles(C1, {PE: D("95.00")})
    assert (new.booked, new.unbooked, new.total) == (old.booked, old.unbooked, old.total)


def test_partial_exit_stays_open_with_its_booked_so_far():
    book = [order(0, "SELL", 150, "120.00"), order(1, "BUY", 75, "110.00", "exit")]
    view = lifecycles(book, {PE: D("100.00")})
    assert view.closed == ()
    only = view.positions[0]
    assert (only.net_quantity, only.booked) == (-75, D("750"))  # (120 - 110) x 75


def test_reversal_in_one_order_splits_at_flat():
    book = [order(0, "BUY", 75, "100.00"), order(1, "SELL", 150, "110.00", "exit")]  # closes 75 long, opens 75 short
    view = lifecycles(book, {PE: D("105.00")})
    assert [(c.side, c.quantity, c.average_exit, c.booked) for c in view.closed] == [("BUY", 75, D("110"), D("750"))]
    row = view.positions[0]
    assert (row.net_quantity, row.average, row.booked) == (-75, D("110"), D(0))


def test_settlement_at_zero_closes_a_lifecycle_with_exit_price_zero():
    book = [order(0, "SELL", 75, "12.00"), order(1, "BUY", 75, "0.00", "settle")]
    view = lifecycles(book, {})
    assert view.closed[0].average_exit == D(0) and view.closed[0].booked == D("900")
    assert view.positions[0].net_quantity == 0 and view.positions[0].booked == D("900")


def test_never_reopened_contract_is_one_closed_and_one_flat_row_with_the_same_booked():
    book = [order(0, "BUY", 75, "10.00"), order(1, "SELL", 75, "12.00", "exit")]
    view = lifecycles(book, {})
    assert view.closed[0].booked == D("150") == view.positions[0].booked


def test_non_terminating_booked_reconciles_exactly_per_contract():
    book = [order(0, "BUY", 25, "10.00"), order(1, "BUY", 50, "10.01"), order(2, "SELL", 75, "10.50", "exit"),
            order(3, "SELL", 3, "9.00"), order(4, "BUY", 1, "8.33", "exit"), order(5, "BUY", 2, "8.34", "exit"),
            order(6, "BUY", 7, "8.00")]
    view = lifecycles(book, {PE: D("8.00")})
    total = net_positions(book, {PE: D("8.00")}).booked
    assert sum((c.booked for c in view.closed), D(0)) + view.positions[0].booked == total


def test_no_orders_is_refused_like_net_positions():
    with pytest.raises(ValueError):
        lifecycles([], {})
