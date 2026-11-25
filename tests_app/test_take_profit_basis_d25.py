"""D-25 (ADR-238 (6), ADR-294 (4), ADR-320 point 4): the offer of Take profit (A-24, A-25) states its basis. The profit
test is BEFORE charges; the offer carries that figure and the whole-trade result AFTER charges beside it, each named,
so a
trader never reads an offered Take profit at a result of -223 as if it were a profit.

Real case 23 Nov, strategy 162: Take profit offered with the same numbers as Exit while the page showed P&L -223
(case 143 of 13 Nov is the same shape: +61.75 before charges, -218.85 after charges)."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal as D

import pytest
import t19_support as t
from ofo_app.api_models import AdjustApproachOut
from ofo_app.routes.adjustment import as_of_market, priced_approach, take_profit_block


def _run(a: str, whole: D, paid: D):
    tr, mk, spot = t.inputs(t.load("ADJ-10"))
    built0, _ = priced_approach("A-24", as_of_market(tr, mk), mk, spot, t.RATES, t.PREFS.approach, roll_basis=t.BASIS)
    open_part = sum(((c.exit - c.entry) * c.quantity * (1 if c.side == "BUY" else -1) for c in built0.closed), D(0))
    tr = as_of_market(replace(tr, booked=whole - open_part, paid_charges=paid), mk)
    return priced_approach(a, tr, mk, spot, t.RATES, t.PREFS.approach, roll_basis=t.BASIS)


@pytest.mark.parametrize("a", ["A-24", "A-25"])
def test_profit_before_charges_but_loss_after_is_no_longer_offered(a):
    """ADR-326 (1): the case this test once pinned as an offer (+61.75 before charges, a loss after) is now refused
    (tests_app/test_take_profit_after_charges_f1.py states the reason); no offer block exists beside the loss."""
    built, priced = _run(a, D("61.75"), D("403.45"))
    assert built.refusal is not None and priced is None and take_profit_block(built, priced) is None


def test_offer_in_profit_both_ways_carries_both_positive_figures():
    built, priced = _run("A-24", D("5000"), D("403.45"))
    block = take_profit_block(built, priced)
    assert block["before_charges"] == D("5000") and block["after_charges"] > 0


def test_refused_take_profit_and_other_approaches_carry_no_block():
    built, priced = _run("A-24", D("-32.50"), D("403.45"))
    assert built.refusal is not None and take_profit_block(built, priced) is None
    built, priced = _run("A-31", D("61.75"), D("403.45"))
    assert take_profit_block(built, priced) is None


def test_the_reply_model_has_the_block():
    assert "take_profit" in AdjustApproachOut.model_fields
