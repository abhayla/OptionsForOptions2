"""W-024 round 9 part 6 fix round (review MAJOR-1; ADR-003 Q226): explanation slots take typed values only.

`Recorded` takes a typed value or one token (never a sentence, never an exception); the user's own words go in a quoted
`UserText`; a nested line is an `ExplanationText` that only `render_explanation()` mints. The old free-`str` slot
(`LegacyRecorded`) survives ONLY on the templates whose callers W-060 owns (engine, scenario): pinned below as a
ratchet, so the set can only shrink.
"""
from __future__ import annotations

import datetime
from decimal import Decimal

import pytest

from ofo.errors import explanations as ex
from ofo.errors.explanations import (
    EXPLANATIONS, LEGACY_SLOT_TEMPLATES, ExplanationText, Explained, LegacyRecorded, Recorded, UserText, Values,
    join_explanations, render_explanation, strike_text,
)

#: The pinned gap: W-060 (engine/display.py, scenario/views.py) callers still pass joined or formatted strings.
PINNED_LEGACY = frozenset({"estimate_line", "estimate_assume_iv", "estimate_assume_valued"})


def test_legacy_slot_set_is_pinned_and_can_only_shrink() -> None:
    using = {tid for tid, t in EXPLANATIONS.items() if LegacyRecorded in t.slots.values()}
    assert using == set(LEGACY_SLOT_TEMPLATES)
    assert set(LEGACY_SLOT_TEMPLATES) <= PINNED_LEGACY, "a new template on the free-str slot"
    assert PINNED_LEGACY <= using | set(), f"routed: remove from PINNED_LEGACY {sorted(PINNED_LEGACY - using)}"


@pytest.mark.parametrize("value", [
    "leg expired before execution, use strike 22,550", "two words", "", " 23600", "x" * 65,
    ValueError("leg expired"), True, 1.5,
])
def test_recorded_refuses_sentences_exceptions_and_untyped_values(value: object) -> None:
    with pytest.raises(TypeError):
        Recorded.validate(value)


@pytest.mark.parametrize("value", [3, Decimal("23600"), "NIFTY", "AB1234", datetime.date(2026, 10, 8)])
def test_recorded_takes_typed_values_and_tokens(value: object) -> None:
    Recorded.validate(value)


def test_explanation_text_is_minted_only_by_render_explanation() -> None:
    with pytest.raises(TypeError):
        ExplanationText("Your rule was triggered: anything at all")
    line = render_explanation("strike_part", strike="23600")
    assert type(line) is ExplanationText and line == " 23600"
    assert strike_text(None) == "" and type(strike_text(None)) is ExplanationText


def test_explained_and_join_refuse_plain_strings() -> None:
    with pytest.raises(TypeError):
        Explained.validate("no condition")
    with pytest.raises(TypeError):
        join_explanations(("plain text here",))
    with pytest.raises(ValueError):
        join_explanations((render_explanation("rule_no_condition_detail"),), " and ")
    joined = join_explanations((render_explanation("rule_no_condition_detail"),) * 2, "; ")
    assert type(joined) is ExplanationText and joined == "no condition; no condition"


def test_values_slot_joins_typed_items_only() -> None:
    assert Values.format(("L1", "L2")) == "L1, L2"
    with pytest.raises(TypeError):
        Values.validate(("L1", "leg two"))
    with pytest.raises(TypeError):
        Values.validate("L1, L2")


def test_user_text_is_quoted_word_for_word_and_never_an_exception() -> None:
    from ofo.errors.explanations import user_words  # noqa: F401 (minted through the request layer below)
    from ofo.rules.model import Always, Rule, RuleAction, RuleKind

    rule = Rule("r1", RuleKind.ENTRY, Always(), RuleAction.ALERT_ONLY, description="Max loss 3000")
    line = render_explanation("rule_alert", rule=rule.shown_name, detail=render_explanation("rule_no_condition_detail"))
    assert line == 'Your rule was triggered: "Max loss 3000" (no condition).'
    with pytest.raises(TypeError):
        UserText.validate(ValueError("Max loss 3000"))
    with pytest.raises(TypeError):  # round 10 item 3: a plain str (the shape of str(e)) is refused
        render_explanation("rule_alert", rule="Max loss 3000", detail=render_explanation("rule_no_condition_detail"))


def test_user_text_from_an_exception_outside_the_request_layer_raises() -> None:
    """W-024 round 10 item 3: UserText(str(e)), UserWords(str(e)) and user_words(str(e)) from this (non-request)
    module all raise; the slot refuses a plain str."""
    from ofo.errors.explanations import UserWords, user_words

    try:
        raise RuntimeError("kite failed: use strike 22,550")
    except RuntimeError as e:
        for make in (lambda: UserText(str(e)), lambda: UserWords(str(e)), lambda: user_words(str(e)),
                     lambda: UserText.validate(str(e))):
            with pytest.raises(TypeError):
                make()


def test_request_layer_is_pinned() -> None:
    """A new module allowed to mint user text fails here until reviewed."""
    assert set(ex.REQUEST_LAYER) == {"ofo.admin.client_id", "ofo.rules.model", "ofo.strategy.definition"}


def test_mutant_recorded_accepting_any_str_lets_a_sentence_through(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mutation: restore the old free-str Recorded -> an exception's sentence fills a slot (so the refusal is real)."""
    monkeypatch.setattr(ex.Recorded, "validate", staticmethod(lambda value: None))
    assert "use strike 22,550" in render_explanation(
        "change_leg_removed", leg="leg expired before execution, use strike 22,550")
