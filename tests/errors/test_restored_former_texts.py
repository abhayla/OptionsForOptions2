"""GC-IC1: a stored-and-restored explanation keeps reading back after its wording changes.

`restore_explanation` matches a stored line against a template's fixed words. A wording change used to orphan every
row stored before it (step 7 changed "Paper strategy - {name}" to an em dash; all stored paper alerts were left out).
`RESTORED_FORMER_TEXTS` lists the earlier texts; the pin below fails when a stored template changes without one.
"""
from __future__ import annotations

import re

import pytest
from ofo.errors import explanations as ex
from ofo.errors.explanations import EXPLANATIONS, RESTORED_FORMER_TEXTS, restore_explanation
from ofo.tracking.paper_alert import ALERT_BODY_TEMPLATES

STORED_TEMPLATE_TEXTS = {
    "paper_alert_title": "Paper strategy — {name}",
    "paper_alert_body_one": "{what}; exited at {price}. A paper exit only: no order was sent to Zerodha.",
    "paper_alert_body_one_named": "{what}; exited {leg}. A paper exit only: no order was sent to Zerodha.",
    "paper_alert_body": "{what}; exited {count} legs at {prices}. A paper exit only: no order was sent to Zerodha.",
}


def test_former_hyphen_title_restores():
    text = "Paper strategy - Iron condor 82"
    assert restore_explanation("paper_alert_title", text) == text


def test_current_title_and_body_restore():
    title = "Paper strategy — Iron condor 82"
    assert restore_explanation("paper_alert_title", title) == title
    body = "Stop hit; exited at 10. A paper exit only: no order was sent to Zerodha."
    assert restore_explanation("paper_alert_body_one", body) == body


def test_unfitting_text_still_refused():
    with pytest.raises(ValueError):
        restore_explanation("paper_alert_title", "Paper strategy ~ Iron condor 82")
    with pytest.raises(ValueError):
        restore_explanation("paper_alert_title", "Buy now - Iron condor 82")


def test_unknown_id_refused():
    with pytest.raises(ValueError):
        restore_explanation("no_such_template", "x")


def test_former_text_is_never_rendered():
    name = restore_explanation("paper_alert_title", "Paper strategy - A")
    assert ex.render_explanation("paper_alert_title", name=name) == "Paper strategy — Paper strategy - A"


def test_stored_template_wording_pinned():
    assert set(STORED_TEMPLATE_TEXTS) == {"paper_alert_title", *ALERT_BODY_TEMPLATES}
    for template_id, pinned in STORED_TEMPLATE_TEXTS.items():
        assert EXPLANATIONS[template_id].text == pinned, (
            f"a stored-and-restored template changed wording: add the old text to "
            f"RESTORED_FORMER_TEXTS[{template_id!r}] and update this pin")


def test_former_texts_have_known_ids_and_same_slots():
    def slots(text: str) -> list[str]:
        return re.findall(r"\{([a-z_]+)\}", text)

    for template_id, formers in RESTORED_FORMER_TEXTS.items():
        assert template_id in EXPLANATIONS
        for former in formers:
            assert slots(former) == slots(EXPLANATIONS[template_id].text)
