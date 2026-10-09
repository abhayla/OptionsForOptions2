"""W-061 round 2 (issue #165, defect 3): a history summary is typed data rendered through the catalogue, never repr text.

Spec basis: REQ-038 AC-5 ("load back exactly as saved; live prices are never saved inside the strategy"); ADR-069 (a
free-text value is never stored or shown); ADR-064 (the closed name lists); ADR-003 Q226 (catalogue text only).
Expected lines are written from the spec and the real values of issue #165 (max_loss 9000.50), not from running the code.
Standard library only.
"""
from __future__ import annotations

import datetime
import json
from decimal import Decimal

import pytest

from ofo.engine.legs import Action, Instrument
from ofo.strategy import stored_form as sf

EXPIRY = datetime.date(2026, 10, 13)
SENTENCE = "LTP is 22950.35 buy now"


def _resolve(contract_id):
    return sf.CatalogueTerms("NIFTY", Instrument.CE, Decimal("22800"), EXPIRY, 65, True) if contract_id == 101 else None


def _build(**fields):
    return sf.build_from_catalogue("NIFTY", [sf.LegChoice(101, Action.SELL, 65)], _resolve, **fields)


def _summary(old, new) -> str:
    return sf.change_summary(old, new)


def test_the_real_issue_165_summary_renders_from_the_template_not_from_repr():
    """Today's text was `risk_limits "(('max_loss', Decimal('9000.50')),)" -> ...`."""
    old = _build(risk_limits={"max_loss": Decimal("9000.50")})
    new = _build(risk_limits={"max_loss": Decimal("12000")})
    text = _summary(old, new)
    assert json.loads(text) == [{"kind": "field", "map": "risk_limits", "name": "max_loss", "old": "9000.50",
                                 "new": "12000"}]
    shown = str(sf.render_summary(text))
    assert shown == "risk_limits max_loss: 9000.50 -> 12000"
    assert "Decimal" not in shown and "((" not in shown and "'" not in shown and '"' not in shown


def test_one_item_per_changed_name_and_an_absent_value_reads_as_not_set():
    old = _build(preferences={"objective": "income"}, rules_ref="rules-1")
    new = _build(preferences={"objective": "growth", "market_view": "range-bound"}, risk_limits={"max_loss": Decimal("5000")})
    shown = str(sf.render_summary(_summary(old, new)))
    assert shown == ("rules reference: rules-1 -> not set; risk_limits max_loss: not set -> 5000; "
                     "preferences market_view: not set -> range-bound; preferences objective: income -> growth")


@pytest.mark.parametrize("item", [
    {"kind": "field", "map": "preferences", "name": "objective", "old": SENTENCE, "new": "x"},
    {"kind": "field", "map": "preferences", "name": "objective", "old": "x", "new": SENTENCE},
    {"kind": "field", "map": "risk_limits", "name": "max_loss", "old": "5000 rupees", "new": "1"},
    {"kind": "field", "map": "risk_limits", "name": "max_loss", "old": "1E+3", "new": "1"},
    {"kind": "field", "map": "preferences", "name": "ltp", "old": "1", "new": "2"},
    {"kind": "field", "map": SENTENCE, "name": "objective", "old": "1", "new": "2"},
    {"kind": "field", "map": "preferences", "name": SENTENCE, "old": "1", "new": "2"},
    {"kind": "field", "map": "rules_ref", "name": "objective", "old": "1", "new": "2"},
    {"kind": "field", "label": "preferences", "old": "x", "new": "y"},  # the old repr-era shape
    {"kind": "field", "map": "preferences", "name": "objective", "old": "x", "new": "y", "extra": SENTENCE},
    {"kind": "field", "map": "preferences", "name": "objective", "old": 5, "new": "y"},
])
def test_a_field_item_with_free_text_in_any_slot_is_refused_on_write_and_shows_the_fixed_line_on_read(item):
    with pytest.raises(sf.StoredFormError) as err:
        sf.summary_text([item])
    assert SENTENCE not in str(err.value)
    stored = json.dumps([item])  # what an older or hand-written row would hold
    assert str(sf.render_summary(stored)) == "this change could not be shown"
    with pytest.raises(sf.StoredFormError):
        sf.check_summary_text(stored)


def test_every_name_on_the_closed_lists_renders():
    from ofo.strategy.definition import PREFERENCE_NAMES, RISK_LIMIT_NAMES
    for name in sorted(PREFERENCE_NAMES):
        assert str(sf.render_summary(sf.summary_text([{"kind": "field", "map": "preferences", "name": name,
                                                       "old": None, "new": "a-1"}]))) == f"preferences {name}: not set -> a-1"
    for name in sorted(RISK_LIMIT_NAMES):
        assert str(sf.render_summary(sf.summary_text([{"kind": "field", "map": "risk_limits", "name": name,
                                                       "old": "0", "new": None}]))) == f"risk_limits {name}: 0 -> not set"
