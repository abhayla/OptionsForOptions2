"""Issue 11 (ADR-238 (6), ADR-294): Take profit (A-24, A-25) through the route's ONE build path (``priced_approach``
after ``as_of_market``), one test per state of the trade. The profit test is BEFORE charges (row 294); an offered
approach carries the after-charges figure;
an after-charges loss is refused (ADR-326 (1)). Case 141: booked -32.50, charges paid 403.45, after charges -435.95."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal as D

import pytest
import t19_support as t
from ofo_app.routes.adjustment import as_of_market, priced_approach


def _whole_at_planned(sid: str) -> D:
    tr, mk, spot = t.inputs(t.load(sid))
    built, _ = priced_approach("A-24", as_of_market(tr, mk), mk, spot, t.RATES, t.PREFS.approach, roll_basis=t.BASIS)
    assert built is not None
    return sum(((c.exit - c.entry) * c.quantity * (1 if c.side == "BUY" else -1) for c in built.closed), D(0))


def _run(sid: str, *, whole: D | None, paid: D, a: str):
    """The scenario's legs and prices; booked chosen so the whole trade (booked + open legs at planned exit prices)
    is ``whole`` before charges (None: booked not known)."""
    tr, mk, spot = t.inputs(t.load(sid))
    open_part = _whole_at_planned(sid)
    booked = None if whole is None else whole - open_part
    tr = as_of_market(replace(tr, booked=booked, paid_charges=paid), mk)
    return priced_approach(a, tr, mk, spot, t.RATES, t.PREFS.approach, roll_basis=t.BASIS)


@pytest.mark.parametrize("a", ["A-24", "A-25"])
def test_case_141_loss_before_charges_is_refused(a):
    built, priced = _run("ADJ-10", whole=D("-32.50"), paid=D("403.45"), a=a)  # -32.50 before, -435.95 after charges
    assert built.refusal is not None and "would not be in profit" in built.refusal_message.what_happened
    assert priced is None and not built.trades


@pytest.mark.parametrize("a", ["A-24", "A-25"])
def test_zero_before_charges_is_refused(a):
    built, _ = _run("ADJ-10", whole=D(0), paid=D(0), a=a)
    assert built.refusal is not None


@pytest.mark.parametrize("a", ["A-24", "A-25"])
def test_booked_unknown_is_refused_with_its_reason(a):
    built, priced = _run("ADJ-10", whole=None, paid=D(0), a=a)
    assert "booked so far is not known" in built.refusal_message.what_happened and priced is None


@pytest.mark.parametrize("a", ["A-24", "A-25"])
def test_profit_before_charges_but_loss_after_is_refused_with_the_after_figure(a):
    """ADR-326 (1) (was: offered with the after-charges figure): case 143, +61.75 before and a loss after charges."""
    built, priced = _run("ADJ-10", whole=D("61.75"), paid=D("403.45"), a=a)
    assert built.refusal is not None and priced is None
    assert built.refusal_message.what_happened.startswith("Not in profit after charges: ")


def test_profit_before_and_after_charges_is_offered():
    built, priced = _run("ADJ-10", whole=D("5000"), paid=D("403.45"), a="A-24")
    assert built.refusal is None and priced.after.after_charges.max_profit > 0
