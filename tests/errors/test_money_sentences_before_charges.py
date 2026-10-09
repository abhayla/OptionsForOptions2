"""ADR-071: every maximum-loss / maximum-profit sentence with a fixed amount says it is before charges and taxes.

Expected strings are written literally. The "no fixed limit", "cannot make money" and breakeven sentences stay as they were.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from ofo.errors.explanations import EXPLANATIONS, render_explanation

PHRASE = "before charges and taxes"


def test_max_loss_sentence_for_the_w063_condor() -> None:
    assert (render_explanation("summary_lose_at_most", amount=Decimal("8245.25"))
            == "At most ₹8,245.25 at expiry, before charges and taxes.")


def test_max_profit_sentence_for_the_w063_condor() -> None:
    assert (render_explanation("summary_make_at_most", amount=Decimal("4754.75"))
            == "At most ₹4,754.75 at expiry, before charges and taxes.")


def test_zero_amounts_read_the_same_way_never_as_no_risk() -> None:
    assert (render_explanation("summary_lose_at_most", amount=Decimal("0"))
            == "At most ₹0.00 at expiry, before charges and taxes.")
    assert (render_explanation("summary_make_at_most", amount=Decimal("0"))
            == "At most ₹0.00 at expiry, before charges and taxes.")


def test_unlimited_none_and_breakeven_sentences_are_unchanged() -> None:
    assert (render_explanation("summary_lose_unlimited", index="NIFTY")
            == "Your loss has no fixed limit if NIFTY rises far enough by expiry.")
    assert (render_explanation("summary_make_unlimited", index="NIFTY")
            == "Your profit has no fixed limit if NIFTY rises far enough by expiry.")
    assert render_explanation("summary_make_none") == "This strategy cannot make money at expiry."
    assert (render_explanation("summary_start_between", index="NIFTY", lower=Decimal("22400"), upper=Decimal("22800"))
            .startswith("If NIFTY ends between "))
    for tid in ("summary_lose_unlimited", "summary_make_unlimited", "summary_make_none", "summary_start_outside",
                "summary_start_between", "summary_start_below"):
        assert PHRASE not in EXPLANATIONS[tid].text, tid


@pytest.mark.parametrize("tid", ["summary_lose_at_most", "summary_make_at_most"])
def test_every_fixed_amount_summary_template_carries_the_phrase(tid: str) -> None:
    assert PHRASE in EXPLANATIONS[tid].text
