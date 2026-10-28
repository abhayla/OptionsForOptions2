"""ADR-193 PR-2d (walkthrough I-9): the Builder places no orders, so its margin lines say "planned entry prices";
the Execute-gate line (orders with limit prices) keeps "limit prices"."""
from __future__ import annotations

from ofo.errors import CATALOGUE
from ofo.errors.explanations import EXPLANATIONS


def test_builder_margin_lines_say_planned_entry_prices() -> None:
    """GC-UI D-A47: only the top-up wordings name the planned entry prices; none says "limit prices"."""
    for tid in ("outcome_margin_checked_top_up", "outcome_margin_short_top_up"):
        text = EXPLANATIONS[tid].text
        assert "planned entry prices" in text
        assert "limit prices" not in text
    for tid in ("outcome_margin_checked", "outcome_margin_short"):  # top-up 0: no addition is named
        text = EXPLANATIONS[tid].text
        assert "already includes the premium of the legs you buy" in text
        assert "limit prices" not in text and "adds" not in text and "{needed}" not in text


def test_execute_gate_margin_line_keeps_limit_prices() -> None:
    assert "limit prices" in CATALOGUE["margin_basket_insufficient"].what_happened
