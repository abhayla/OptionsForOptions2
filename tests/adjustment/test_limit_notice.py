"""ADR-297 (D4): at the adjustment limit the offer screen says so ("Adjustment limit reached (2 of 2)") and lists every
withheld approach as not offered with the limit reason. The sentence and the reason come from the explanation catalogue;
``offered.limit_notice`` is the one place that decides there is a notice (same test as the S-11 filter)."""
from __future__ import annotations

import pytest
from ofo.adjustment import offered
from ofo.errors.explanations import render_explanation

SENTENCE = "Adjustment limit reached (2 of 2)"


def test_the_sentence_is_row_297s_wording_with_the_trades_own_numbers():
    assert render_explanation("adjust_limit_reached", used=2, max=2) == SENTENCE
    assert render_explanation("adjust_limit_reached", used=3, max=2) == "Adjustment limit reached (3 of 2)"
    assert render_explanation("adjust_limit_reason") == "Adjustment limit reached"


def test_at_the_limit_there_is_a_notice_with_the_numbers_and_the_sentence():
    assert offered.limit_notice({"max_adjustments": 2}, 2) == {"used": 2, "max": 2, "text": SENTENCE}


def test_above_the_limit_by_old_data_the_notice_is_still_there_with_the_trades_own_count():
    n = offered.limit_notice({"max_adjustments": 2}, 3)
    assert n == {"used": 3, "max": 2, "text": "Adjustment limit reached (3 of 2)"}


@pytest.mark.parametrize(("guards", "used"), [({"max_adjustments": 2}, 1), ({"max_adjustments": 2}, 0),
                                              ({"max_adjustments": 2}, None), ({}, 2), (None, 2),
                                              ({"max_adjustments": True}, 2)])
def test_below_the_limit_or_no_limit_known_there_is_no_notice(guards, used):
    assert offered.limit_notice(guards, used) is None


def test_the_notice_agrees_with_the_s11_filter_for_every_count():
    ids = ("A-01", "A-26", "A-36")
    for used in (None, 0, 1, 2, 3, 4):
        g = {"max_adjustments": 2}
        assert (offered.limit_notice(g, used) is not None) == (offered.limit_filter(ids, g, used) != ids)
