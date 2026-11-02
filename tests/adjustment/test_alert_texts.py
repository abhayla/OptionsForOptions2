"""GC-ALERT1 item 7: the alert gate's shown words have ONE home, the explanation catalogue (REQ-170 AC-4, ADR-236 (2)).

Spec basis: ADR-236 (2) a new record says "Worse than the one you dismissed"; REQ-170 AC-4 "held: daily limit" /
"held: quiet time". The gate keeps its record constants (the pure layer compares them); this test fails the suite
when a constant and its catalogue entry drift apart, and when a reason the gate can give has no catalogue text.
"""
from __future__ import annotations

from ofo.adjustment import alert_gate
from ofo.errors.explanations import EXPLANATIONS, render_explanation


def test_each_gate_text_id_names_a_catalogue_entry():
    assert [i for i in alert_gate.TEXT_IDS.values() if i not in EXPLANATIONS] == []
    assert len(alert_gate.TEXT_IDS) == 4  # noqa: PLR2004 - the two record texts and the two held reasons


def test_the_record_constants_equal_their_catalogue_text():
    assert render_explanation(alert_gate.TEXT_IDS[alert_gate.WORSE_THAN_LAST]) == "Worse than the last one"
    assert render_explanation(alert_gate.TEXT_IDS[alert_gate.WORSE_THAN_DISMISSED]) == \
        "Worse than the one you dismissed"
    for constant in (alert_gate.WORSE_THAN_LAST, alert_gate.WORSE_THAN_DISMISSED):
        assert render_explanation(alert_gate.TEXT_IDS[constant]) == constant


def test_the_held_reasons_read_exactly():
    assert render_explanation(alert_gate.TEXT_IDS[alert_gate.HELD_DAILY_LIMIT]) == "held: daily limit"
    assert render_explanation(alert_gate.TEXT_IDS[alert_gate.HELD_QUIET_TIME]) == "held: quiet time"


def test_the_style_names_cover_every_resolver_style():
    from ofo.adjustment import alert_presets  # noqa: PLC0415
    assert [render_explanation(f"alert_style_name_{s}") for s in alert_presets.STYLES] == \
        ["Intraday", "Weekly", "Monthly"]
    assert render_explanation("alert_style_automatic_now", style=render_explanation("alert_style_name_weekly")) == \
        "Automatic (now Weekly)"
