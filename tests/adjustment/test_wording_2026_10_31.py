"""Owner wording decisions of 2026-10-31 (18 items): exact new strings, the {stage} slot, the fail-closed stage name.

Expected strings are typed here from the owner's decision list, not read back from the catalogue.
"""
from __future__ import annotations

import pytest
from ofo.adjustment.playbook_eval import _stage_words
from ofo.errors import CATALOGUE, render
from ofo.errors.explanations import (
    EXPLANATIONS,
    LABEL_TABLES,
    PLAYBOOK_SUMMARY_TEXT,
    render_explanation,
)


def test_no_stage_value_names_the_stage_and_says_how_to_fix_it():
    t = render("adjust_trigger_no_stage_value", stage="Early")
    assert t.what_happened == "No value is set for this rule in the Early stage."
    assert t.impact == "This rule is not checked in this stage."
    assert t.what_is_blocked == "This rule."
    assert t.next_action == "To check it in this stage, enter a value in the playbook."


@pytest.mark.parametrize("bad", [None, "", "   ", 5, 'say "x"', "{stage}", "x" * 81])
def test_missing_or_unusable_stage_name_never_shows_a_brace_or_a_gap(bad):
    word = _stage_words(bad)
    assert word == "current"
    text = render("adjust_trigger_no_stage_value", stage=word).what_happened
    assert text == "No value is set for this rule in the current stage."
    assert "{" not in text and "  " not in text


def test_a_real_stage_name_is_kept_trimmed():
    assert _stage_words(" Late ") == "Late"


def test_no_stage_and_no_expiry_values_tell_the_user_what_to_enter():
    assert render("adjust_trigger_no_stage", days=-1).next_action == \
        "Add a stage that covers this point of the trade in the playbook."
    assert render("adjust_trigger_no_expiry_values").next_action == "Enter a value for expiry day in the playbook."


def test_switched_off_greyed_unknown_not_evaluated_next_actions():
    assert render("adjust_trigger_switched_off").next_action == "Switch it on in the playbook to have it checked."
    for code in ("greyed", "unknown", "not_evaluated"):
        assert render(f"adjust_trigger_{code}").next_action == \
            "Nothing to do; this rule is not checked for this strategy."
    # a missing-data reason still says it is checked again
    assert render("adjust_trigger_missing_spot").next_action == "Nothing to do; it is checked again at the next check."
    assert render("adjust_trigger_missing_max_adjustments").next_action == \
        "Set a maximum number of adjustments in the playbook to have this rule checked."


def test_trigger_and_refusal_sentences():
    assert render("adjust_trigger_t14_pending").what_happened == \
        "The loss-from-a-1%-move rule is not checked yet in this version."
    for code, tail in (("stale", "prices stale or missing."), ("fresh_unknown", "price freshness not available."),
                       ("no_spot", "spot not available.")):
        assert render(f"adjust_trigger_withheld_{code}").what_happened == \
            f"No adjustment opportunity checked: {tail}"


def test_reduce_refusal_has_no_lot_count():
    assert "lots" not in CATALOGUE["adjust_reduce_needs_two_lots"].slots
    assert "{lots}" not in CATALOGUE["adjust_reduce_needs_two_lots"].what_happened


def test_catalogue_words_of_the_owner_list():
    app = LABEL_TABLES["playbook_approach"]
    adj = LABEL_TABLES["adjustment_approach"]
    assert app["A-13"] == "Convert to a jade lizard: sell a put and a call spread"
    assert adj["A-11"] == "Convert to an iron butterfly: move both shorts to the money"
    assert EXPLANATIONS["adjust_approach_name_a_11"].text == adj["A-11"]
    assert app["A-09"] == "Add wings (buy far options on each side)"
    assert app["A-10"] == "Inverted strangle (short call strike below short put strike)"
    assert app["A-18"] == "Gamma scalp with futures (trade futures as spot moves to stay delta-neutral)"
    assert LABEL_TABLES["playbook_guard"]["entry_guide"] == "Entry this playbook assumes"
    assert LABEL_TABLES["adjustment_leader"]["gamma"] == "Gamma closest to zero"
    assert LABEL_TABLES["adjustment_leader"]["vega"] == "Vega closest to zero"
    assert EXPLANATIONS["adjust_cmp_lead_gamma"].text == "Gamma closest to zero"
    assert EXPLANATIONS["adjust_spot_from_rest_quote"].text == "Spot from a one-time price request"
    assert EXPLANATIONS["adjust_history_fill_failed"].text == (
        "Could not read Zerodha's answer; check this order in Kite")
    for key in ("A-01", "A-05", "A-28", "A-29"):
        assert "side that spot is" in LABEL_TABLES["adjustment_approach_about"][key]


def test_summary_stop_words_are_the_plan_stop_words():
    s = PLAYBOOK_SUMMARY_TEXT
    assert s["stop_loss"].replace("{{", "{").replace("}}", "}") == EXPLANATIONS["plan_stop_words_loss"].text
    assert s["stop_margin"].replace("{{", "{").replace("}}", "}") == EXPLANATIONS["plan_stop_words_margin"].text
    assert s["stop_either"].replace("{{", "{").replace("}}", "}") == EXPLANATIONS["plan_stop_words_either"].text
    assert render_explanation("plan_stop_words_either", pct="50", margin="20") is not None
