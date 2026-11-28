"""I-44 (test plan 28 Nov 2026): the Home Total P&L with ONE settled or ONE unpriced trade in it follows the rules:
a settled (expired, all legs closed at the settlement) trade adds its booked figure and nothing unbooked; an unpriced
one makes the unbooked part and the total ABSENT with its reason (never a partial sum) unless it is left out and
counted in the one "left out" line. Exact Decimal.
Real case: S-21 books of 28 Nov: one live book (booked 100.00, unbooked 50.00) beside one settled book (booked
-1,250.50, unbooked 0.00) or one unpriced book.
Spec basis: REQ-109 AC-5 (never a partial sum), ADR-008, ADR-330 (15) (closed trades kept in the whole-paper total).
"""
from __future__ import annotations

from decimal import Decimal as D

from ofo.tracking import paper, paper_decay
from ofo_app.routes.paper import _totals
from test_paper_totals_rules import _strategy

LIVE = paper_decay.Decay(D("-10.00"), None)
SETTLED = paper_decay.Decay(D("0"), None)


def test_one_settled_trade_adds_its_booked_figure_and_no_unbooked_part():
    got = _totals([_strategy("100.00", "50.00"), _strategy("-1250.50", "0.00")], [LIVE, SETTLED], closed=1)
    assert (got["booked"], got["unbooked"], got["total"]) == (D("-1150.50"), D("50.00"), D("-1100.50"))
    assert got["totals_reason"] is None and got["totals_as_of"] is None
    assert got["closed_count"] == 1 and got["decay"] == D("-10.00")


def test_only_a_settled_trade_is_its_booked_figure_exactly():
    got = _totals([_strategy("-1250.50", "0.00")], [SETTLED], closed=1)
    assert (got["booked"], got["unbooked"], got["total"]) == (D("-1250.50"), D("0.00"), D("-1250.50"))
    assert got["totals_reason"] is None


def test_one_unpriced_trade_in_the_sum_makes_the_total_absent_with_its_reason_never_a_partial_sum():
    got = _totals([_strategy("100.00", "50.00"), _strategy("-20.50", None, "not_priced")],
                  [LIVE, paper_decay.Decay(None, "not_priced")])
    assert got["booked"] == D("79.50") and got["unbooked"] is None and got["total"] is None
    assert got["totals_reason"] == "not_priced" and got["total_text"] is None
    assert got["decay"] is None and got["decay_reason"] == "not_priced"


def test_an_unpriced_trade_without_a_reason_gets_the_prices_not_live_reason():
    got = _totals([_strategy("-20.50", None)], [paper_decay.Decay(None, "no_iv")])
    assert got["total"] is None and got["totals_reason"] == paper.PRICES_NOT_LIVE


def test_an_unpriced_trade_left_out_is_counted_in_one_line_and_the_rest_still_sums():
    got = _totals([_strategy("100.00", "50.00")], [LIVE], unpriced=1)
    assert got["total"] == D("150.00") and got["totals_reason"] is None
    assert got["left_out_count"] == 1 and got["left_out_text"], got["left_out_text"]
