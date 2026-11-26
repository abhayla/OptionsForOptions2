"""ADR-330 (5): both figures of one level come from one pure place. Real case: Rs 1,000 on a 3,900 max-profit trade is
25.64 % (owner example); 25.64 % of 3,900 is Rs 999.96, so a typed pair 25.64 % / Rs 1,000 agrees through the rupee side.
Spec basis: ADR-330 (5) and its Q3 answer (whole trade, before charges, per-lot beside it)."""
from decimal import Decimal as D

from ofo.checks import rupee_figures as rf


def test_rupees_to_percent_and_per_lot():
    f = rf.from_rupees(D("1000"), D("3900"), 2)
    assert (f.percent, f.rupees, f.per_lot) == (D("25.64"), D("1000"), D("500.00"))


def test_percent_to_rupees_to_the_paisa():
    f = rf.from_percent(D("25.7"), D("3900"), 4)
    assert (f.percent, f.rupees, f.per_lot) == (D("25.7"), D("1002.30"), D("250.58"))


def test_no_base_gives_only_the_typed_figure():
    assert rf.from_percent(D("50"), None, 2) == rf.Figures(D("50"), None, None)
    assert rf.from_rupees(D("400"), None, 2) == rf.Figures(None, D("400"), D("200.00"))
    assert rf.from_rupees(D("400"), D("0"), 2).percent is None


def test_rupees_above_the_base_have_no_percent():
    assert rf.from_rupees(D("5000"), D("3900"), 1).percent is None


def test_agree_and_disagree():
    assert rf.agree(D("25.64"), D("1000"), D("3900"), 1)
    assert not rf.agree(D("30"), D("1000"), D("3900"), 1)
    assert not rf.agree(D("25.64"), D("1000"), None, 1)  # cannot be judged: never "agrees"
