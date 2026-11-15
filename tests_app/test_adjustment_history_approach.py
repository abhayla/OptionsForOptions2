"""GC-ICFIX issue 21 (ADR-273, REQ-163 AC-1): an adjustment row is named by its approach, with the Compare screen's own
name (``approach_name_id`` -> ``render_explanation``), only when the server has one stored; otherwise the field is None
and the row shows no approach line (never a filler sentence, never a raw id). No database."""
from __future__ import annotations

from ofo.errors.explanations import ADJUSTMENT_APPROACH_LABEL_TEXT, approach_name_id, render_explanation
from ofo_app.routes import adjustment_history as ah


def test_a_stored_approach_is_named_as_the_compare_screen_names_it() -> None:
    for key in ADJUSTMENT_APPROACH_LABEL_TEXT:
        assert ah.approach_text(key) == render_explanation(approach_name_id(key))


def test_no_stored_approach_gives_no_text() -> None:
    assert ah.approach_text(None) is None


def test_an_unknown_approach_id_is_never_shown_raw() -> None:
    assert ah.approach_text("A-99-not-an-approach") is None


def test_the_row_model_carries_the_field_null_by_default() -> None:
    assert ah.HistoryRowOut.model_fields["approach_text"].default is None
