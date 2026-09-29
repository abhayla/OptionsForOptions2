"""AC-2: every strategy template carries one level, at least one market view and at least one objective.

Spec: REQ-068 AC-2; owner decision Q251 (2026-09-29). The expected levels below are derived from the Q251 rule
text (each rule names strategies; a template is placed by matching its shape to a rule), NOT read from the YAML.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from ofo.strategy.loader import DEFAULT_CATALOGUE_PATH, load_templates
from ofo.strategy.model import TemplateError
from ofo.strategy.wording import find_banned_phrases

# Q251: "Beginner: long call, long put, bull call / bull put / bear call / bear put vertical spreads."
BEGINNER_RULE = {"bull_call_spread", "bull_put_spread", "bear_call_spread", "bear_put_spread"}
# Q251: "Intermediate: Iron Condor, Iron Butterfly, short strangle, short straddle, covered call, cash-secured put."
INTERMEDIATE_RULE = {"iron_condor", "iron_butterfly", "short_strangle", "short_straddle", "covered_call",
                     "cash_secured_put"}
# Q251: "Advanced: calendars, diagonals, ratio spreads, Jade Lizard, broken-wing butterfly, and any strategy with
# naked short legs beyond a short straddle/strangle."
ADVANCED_RULE = {"calendar_spread", "diagonal_spread", "ratio_backspread_call", "ratio_backspread_put", "jade_lizard"}
# Not clearly placed by the rules: labelled by the nearest rule (Q251: "listed ... for the owner to see").
UNPLACED = {
    "synthetic_long": "Advanced",       # naked short put leg, not a straddle/strangle
    "synthetic_short": "Advanced",      # naked short call leg, not a straddle/strangle
    "long_straddle": "Intermediate",    # mirror of short straddle; long-only, defined risk
    "long_strangle": "Intermediate",    # mirror of short strangle
    "reverse_iron_condor": "Intermediate",  # mirror of Iron Condor
    "butterfly_spread": "Intermediate",  # symmetric butterfly; nearest is Iron Butterfly
}
EXPECTED = {
    **{t: "Beginner" for t in BEGINNER_RULE},
    **{t: "Intermediate" for t in INTERMEDIATE_RULE},
    **{t: "Advanced" for t in ADVANCED_RULE},
    **UNPLACED,
}
VIEWS = {"bullish", "bearish", "range-bound", "volatile"}
OBJECTIVES = {"income", "directional", "hedge", "volatility"}

CATALOGUE = load_templates()


def test_ac2_every_real_template_level_matches_the_q251_rules() -> None:
    """AC-2: all 21 real templates load; each level equals the level the Q251 rule text gives it."""
    assert {t.id for t in CATALOGUE} == set(EXPECTED)
    assert len(CATALOGUE) == 21
    for template in CATALOGUE:
        assert template.level == EXPECTED[template.id], template.id


def test_ac2_every_template_has_views_and_objectives_from_the_closed_lists() -> None:
    """AC-2: at least one view and one objective each, all from the Q251 lists, no repeats."""
    for template in CATALOGUE:
        assert template.views and set(template.views) <= VIEWS, template.id
        assert template.objectives and set(template.objectives) <= OBJECTIVES, template.id
        assert len(set(template.views)) == len(template.views)
        assert len(set(template.objectives)) == len(template.objectives)


def test_ac2_views_match_payoff_direction_for_the_vertical_spreads() -> None:
    """AC-2: independent check: bull spreads are bullish, bear spreads bearish, condor/straddle/strangle range-bound."""
    by_id = {t.id: t for t in CATALOGUE}
    assert by_id["bull_call_spread"].views == ("bullish",)
    assert by_id["bear_put_spread"].views == ("bearish",)
    for tid in ("iron_condor", "short_straddle", "short_strangle"):
        assert by_id[tid].views == ("range-bound",)
    assert by_id["long_straddle"].views == ("volatile",)


def test_ac2_names_and_descriptions_still_pass_the_wording_checks() -> None:
    """AC-2: ADR-003 wording still holds for every template after the change."""
    for template in CATALOGUE:
        assert find_banned_phrases(f"{template.name} {template.description}") == [], template.id


def _catalogue_with(tmp_path: Path, transform) -> Path:
    text = DEFAULT_CATALOGUE_PATH.read_text(encoding="utf-8")
    path = tmp_path / "catalogue.yaml"
    path.write_text(transform(text), encoding="utf-8")
    return path


def _drop_first(key: str):
    return lambda text: re.sub(rf"^    {key}: .*\n", "", text, count=1, flags=re.M)


@pytest.mark.parametrize("key", ["level", "views", "objectives"])
def test_ac2_loader_refuses_a_template_missing_a_label(tmp_path: Path, key: str) -> None:
    """AC-2: deleting the level, views or objectives of one template makes the loader raise."""
    path = _catalogue_with(tmp_path, _drop_first(key))
    with pytest.raises(TemplateError, match=key):
        load_templates(path)


@pytest.mark.parametrize(
    "old, new",
    [
        ("    level: Beginner", "    level: Expert"),
        ("    level: Beginner", "    level: beginner"),
        ("    views: [bullish]", "    views: [sideways]"),
        ("    views: [bullish]", "    views: []"),
        ("    views: [bullish]", "    views: [bullish, bullish]"),
        ("    objectives: [directional]", "    objectives: [speculation]"),
        ("    objectives: [directional]", "    objectives: []"),
    ],
)
def test_ac2_loader_refuses_unknown_empty_or_repeated_values(tmp_path: Path, old: str, new: str) -> None:
    """AC-2: closed enums: an unknown, wrong-case, empty or repeated value is refused."""
    path = _catalogue_with(tmp_path, lambda text: text.replace(old, new, 1))
    with pytest.raises(TemplateError):
        load_templates(path)


def test_ac2_loader_refuses_two_levels(tmp_path: Path) -> None:
    """AC-2: exactly one level: a list of levels is refused."""
    path = _catalogue_with(tmp_path, lambda text: text.replace("    level: Beginner", "    level: [Beginner, Advanced]", 1))
    with pytest.raises(TemplateError):
        load_templates(path)


@pytest.mark.parametrize("field, value", [("level", "Expert"), ("views", ()), ("views", "bullish"),
                                          ("objectives", ("income", "income")), ("objectives", ("speculation",))])
def test_ac2_template_model_refuses_bad_labels_built_directly(field: str, value: object) -> None:
    """AC-2: the model itself refuses bad labels, even when the schema is bypassed."""
    import dataclasses
    with pytest.raises(TemplateError, match=field):
        dataclasses.replace(CATALOGUE[0], **{field: value})
