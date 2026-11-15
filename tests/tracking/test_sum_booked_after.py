"""ADR-311 (4), the all-strategies totals row: Booked after charges is the exact sum of every book's Booked after
ONLY when every book gives one (each after charges); if any book's is missing or fell back to before charges, the row
has none, with that book's reason - never a sum over some books, never a mix of bases. Total and Unbooked stay absent
while any book is paused (``sum_after_charges``)."""
from __future__ import annotations

from decimal import Decimal

from ofo.engine.extremes_charges import BookAfterCharges, sum_after_charges, sum_booked_after

D = Decimal


def test_every_book_gives_booked_after_the_row_is_their_exact_sum() -> None:
    assert sum_booked_after([(D("-36.09"), None), (D("613.91"), None), (D("-0.01"), None)]) == (D("577.81"), None)


def test_a_book_with_no_booked_after_makes_the_row_absent_with_its_reason_never_a_partial_sum() -> None:
    rows = [(D("-36.09"), None), (None, "rates_unavailable"), (D("5"), None)]
    assert sum_booked_after(rows) == (None, "rates_unavailable")


def test_a_book_on_the_before_charges_fallback_makes_the_row_absent_no_mixed_sum() -> None:
    assert sum_booked_after([(D("-36.09"), None), (None, "not_priced")]) == (None, "not_priced")
    assert sum_booked_after([(None, None)]) == (None, "rates_unavailable")  # a reason is never blank


def test_one_book_paused_for_a_price_total_stays_absent_while_booked_from_the_others_and_itself_can_sum() -> None:
    paused = BookAfterCharges(None, None, D("36.09"), None, "prices_not_live")
    fine = BookAfterCharges(D("100"), D("60"), D("30"), D("10"), None)
    got = sum_after_charges([paused, fine])
    assert (got.total_after, got.reason) == (None, "prices_not_live")
    assert sum_booked_after([(D("-36.09"), None), (D("70"), None)]) == (D("33.91"), None)  # booked - paid, each
