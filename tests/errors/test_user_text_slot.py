"""GC-ADJ2 1A (REQ-158 AC-3): a `user_text` slot (the playbook name) is the user's own words. The builder masks
exactly its quoted span for the wording scan; the template around it is still scanned, on build and on every read.

Spec basis (quoted): REQ-158 AC-3 "a duplicate name is refused with "A playbook named <name> already exists for
<type>""; Q226 (the user's own words are never judged as our wording).
"""
from __future__ import annotations

import pytest
from ofo.errors import ErrorClass, render
from ofo.errors.model import _checked


def _fields(what: str, user_text: tuple[str, ...]) -> dict:
    return {"error_class": ErrorClass.USER_INPUT, "code": "USER_INPUT_114", "what_happened": what,
            "impact": "Nothing was saved.", "what_is_blocked": "Saving this playbook.",
            "next_action": "Type another name.", "external": None, "user_text": user_text}


def test_a_user_name_containing_a_banned_word_renders_the_ac_sentence_exactly():
    shown = render("playbook_name_taken", name="Iron Condor Safe", type="Iron condor")
    assert shown.what_happened == 'A playbook named Iron Condor Safe already exists for Iron condor.'


def test_the_template_text_around_a_user_name_is_still_scanned():
    with pytest.raises(ValueError, match="banned wording"):
        _checked(_fields('A playbook named "Mine" is safe to use.', ("Mine",)))
    _checked(_fields('A playbook named "Safe Mine" already exists.', ("Safe Mine",)))


def test_without_the_user_text_field_the_same_name_is_refused():
    with pytest.raises(ValueError, match="banned wording"):
        _checked(_fields('A playbook named "Safe Mine" already exists.', ()))


@pytest.mark.parametrize("value", ["", "   ", 'a"b', "x" * 81, "line\nbreak", "not in the text"])
def test_a_user_text_value_that_is_not_a_short_quoted_span_of_a_part_is_refused(value):
    with pytest.raises((ValueError, TypeError)):
        _checked(_fields('A playbook named "Mine" already exists.', (value,)))


def test_a_user_name_with_a_double_quote_is_refused_by_the_slot():
    with pytest.raises(ValueError, match="double quote"):
        render("playbook_name_taken", name='Mine" is safe "x', type="Iron condor")
