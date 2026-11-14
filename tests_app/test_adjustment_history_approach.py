"""GC-ICFIX issue 21 (ADR-273, REQ-163 AC-1): each adjustment row of the history is named by its approach, with the
Compare screen's own name (``approach_name_id`` -> ``render_explanation``); a row with no stored approach says so in
words, never blank or a raw id. No database: the naming function and the row model only."""
from __future__ import annotations

from ofo.errors.explanations import ADJUSTMENT_APPROACH_LABEL_TEXT, approach_name_id, render_explanation
from ofo_app.routes import adjustment_history as ah

NOT_RECORDED = "Approach not recorded"


def test_a_stored_approach_is_named_as_the_compare_screen_names_it() -> None:
    for key in ADJUSTMENT_APPROACH_LABEL_TEXT:
        assert ah.approach_text(key) == render_explanation(approach_name_id(key))


def test_no_stored_approach_is_said_plainly() -> None:
    assert ah.approach_text(None) == NOT_RECORDED


def test_an_unknown_approach_id_is_never_shown_raw() -> None:
    assert ah.approach_text("A-99-not-an-approach") == NOT_RECORDED


def test_the_row_model_carries_the_name() -> None:
    assert "approach_text" in ah.HistoryRowOut.model_fields
