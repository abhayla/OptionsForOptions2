"""GC-UI step 2 (D-A47, D-A46): the CHECKED margin sentence and the breakeven sentence.

D-A47: needed = Zerodha's final.total (which already includes each BUY leg's option_premium) + the ADR-094 top-up
max(0, qty x planned price - option_premium) (``margin_gate.basket_requirement``). The sentence names the top-up only
when there is one; with a top-up of 0 it says what Zerodha's figure already includes and never claims an addition.
Strategy 54 (measured 2026-10-28): Zerodha 32,029.59, needed 32,029.59, top-up 0. The funds figure here is made up.

D-A46: the breakeven sentence says it is before charges when the charges are known; the breakeven NUMBER is the
pre-charges payoff's (spec sections 1 and 3) and does not move.
"""
import datetime
from decimal import Decimal as D

import pytest
from ofo.errors.explanations import MARGIN_SHORTFALL_NEXT_ACTION
from ofo.outcome.service import MARGIN_CHECKED, margin_checked
from outcome.test_charges_in_sentences import RATES, outcome_of, replayed  # noqa: F401 - the replay fixture

AT = datetime.datetime(2026, 10, 28, 10, 0, tzinfo=datetime.UTC)
FUNDS = D("100000.00")  # made up: never the owner's real funds
OLD = "With the premium at your planned entry prices"


def test_core_strategy_54_top_up_0_says_zerodhas_figure_already_includes_the_premium() -> None:
    m = margin_checked(D("32029.59"), FUNDS, AT, D("32029.59"), D("0"))
    assert m.state == MARGIN_CHECKED and m.shortfall is False and m.shortfall_reason is None
    assert str(m.reason) == ("Zerodha's own margin figure is ₹32,029.59, which already includes the premium of the "
                             "legs you buy; ₹1,00,000.00 is available in your Zerodha account.")
    assert OLD not in str(m.reason) and "adds" not in str(m.reason)


def test_checked_with_a_top_up_names_it_and_the_estimate() -> None:
    m = margin_checked(D("7065.50"), FUNDS, AT, D("6409"), D("656.50"))
    assert str(m.reason) == ("Zerodha's own margin figure is ₹6,409.00; your planned entry prices are above Zerodha's, "
                             "which adds about ₹656.50, so about ₹7,065.50 is needed (an estimate); ₹1,00,000.00 is "
                             "available in your Zerodha account.")


def test_short_top_up_0_keeps_its_tail_and_next_action() -> None:
    m = margin_checked(D("32029.59"), D("671.50"), AT, D("32029.59"), D("0"))
    assert m.shortfall is True
    assert str(m.shortfall_reason) == ("Zerodha's own margin figure is ₹32,029.59, which already includes the premium "
                                       "of the legs you buy; ₹671.50 is available in your account. "
                                       + MARGIN_SHORTFALL_NEXT_ACTION)


def test_short_with_a_top_up_names_it() -> None:
    m = margin_checked(D("7065.50"), D("671.50"), AT, D("6409"), D("656.50"))
    assert str(m.shortfall_reason) == ("Zerodha's own margin figure is ₹6,409.00; your planned entry prices are above "
                                       "Zerodha's, which adds about ₹656.50, so about ₹7,065.50 is needed (an "
                                       "estimate); ₹671.50 is available in your account. "
                                       + MARGIN_SHORTFALL_NEXT_ACTION)


@pytest.mark.parametrize("bad", [D("-0.01"), D("NaN"), 1, None])
def test_a_top_up_that_is_not_a_finite_decimal_of_0_or_more_is_refused(bad) -> None:
    with pytest.raises(ValueError):
        margin_checked(D("100.00"), FUNDS, AT, D("100.00"), bad)


def test_breakeven_sentence_with_known_charges_says_before_charges(replayed) -> None:  # noqa: F811
    _, out = outcome_of(replayed, RATES)
    s = out.summary
    assert s.charges is not None
    text = str(s.where_do_i_start_losing)
    assert text.startswith("If NIFTY ends below ") and " or above " in text
    charges = f"₹{s.charges:,}"
    assert text.endswith(f" at expiry, before about {charges} of charges and taxes."), text


def test_breakeven_sentence_without_charges_is_unchanged_and_the_breakevens_do_not_move(replayed) -> None:  # noqa: F811
    _, with_rates = outcome_of(replayed, RATES)
    _, without = outcome_of(replayed, None)
    assert without.summary.charges is None
    text = str(without.summary.where_do_i_start_losing)
    assert text.startswith("If NIFTY ends below ") and text.endswith(" at expiry.") and "charges" not in text
    assert with_rates.summary.breakevens == without.summary.breakevens
    assert str(with_rates.summary.where_do_i_start_losing).startswith(text[:-1])  # the same levels, then the clause
