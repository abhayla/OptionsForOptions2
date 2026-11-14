"""ADR-307 (2)/(3): a compare reply that draws a nearer-expiry estimate curve (legs on two expiries) carries the one
sentence saying it is not a limit, and its Max loss / Max profit cells are the ADR-143 text, never a number read off the
estimate. A one-expiry reply carries neither."""
from __future__ import annotations

from decimal import Decimal as D
from types import SimpleNamespace

import pytest
from ofo.adjustment.compare import _Rows
from ofo.errors.explanations import render_explanation
from ofo_app.routes.adjustment import _compare_block

NOTE = ("This curve is an estimate at the nearer expiry only. The later leg stays open after that date, so the loss "
        "shown is not a limit, and the maximum loss cannot be estimated.")


def _cmp(estimated: tuple[str, ...]):
    return SimpleNamespace(criteria=[], leads={}, curves={"A-1": [(D(100), D(-5))]}, estimated=estimated)


def test_two_expiry_reply_carries_the_sentence():
    block = _compare_block(_cmp(("A-1",)))
    assert block["curves_estimate_note"] == NOTE == render_explanation("adjust_cmp_curve_estimate_note")


def test_one_expiry_reply_carries_no_sentence():
    assert _compare_block(_cmp(()))["curves_estimate_note"] is None


@pytest.mark.parametrize("cell", ["max_loss", "max_profit"])
def test_two_expiry_column_shows_the_cannot_be_estimated_text_not_a_number(cell):
    col = SimpleNamespace(whole=None, near=object(), charges_known=True, no_whole_reason="x")
    rows = _Rows.__new__(_Rows)
    rows.col = col
    out = getattr(rows, cell)()
    key = "mixed_expiry_worst_case" if cell == "max_loss" else "summary_make_mixed_expiry"
    assert out.value is None
    assert render_explanation(key) in repr(out)
