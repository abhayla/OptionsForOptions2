"""GC-IC1 (REQ-076 AC-8, ADR-186 (4)): a template's build range never hides a shape from the matcher.

Owner's position (strategy 82): NIFTY 2026-12-29, +21000 PE / -21500 PE / -24000 CE / +24500 CE, 65 each, spot 23674.
Before the fix: Custom, "param 'p'=43 outside its bounds [-20, 20]".
"""
from __future__ import annotations

import datetime
from decimal import Decimal as D

import pytest
from ofo.adjustment.strategy_type import type_of
from ofo.engine.legs import Action, Instrument, Leg
from ofo.strategy.loader import load_templates
from ofo.strategy.matching import MatchResult, match, match_shape, template_shape
from ofo.strategy.model import Param, TemplateError, resolve_template

CATALOGUE = load_templates()
BY_ID = {t.id: t for t in CATALOGUE}
EXP = datetime.date(2026, 12, 29)
SPOT, GAP = D("23674"), D("50")
FAR_P = 43
B, S, CE, PE = Action.BUY, Action.SELL, Instrument.CE, Instrument.PE


def _leg(action, inst, strike):
    return Leg(action, inst, D(strike), EXP, 65, D("10"))


def _owner(put_long="21000", put_short="21500"):
    return [_leg(B, PE, put_long), _leg(S, PE, put_short), _leg(S, CE, "24000"), _leg(B, CE, "24500")]


def test_owner_far_condor_is_an_iron_condor_and_typed_ic():
    result = match(_owner(), spot=SPOT, strike_gap=GAP, templates=CATALOGUE)
    assert isinstance(result, MatchResult) and result.template.id == "iron_condor"
    assert result.params["p"] == FAR_P
    assert type_of(_owner(), SPOT, GAP) == "ic"


def test_long_put_above_short_put_is_not_a_condor():
    legs = _owner(put_long="21700", put_short="21500")
    result = match(legs, spot=SPOT, strike_gap=GAP, templates=CATALOGUE)
    assert not (isinstance(result, MatchResult) and result.template.id == "iron_condor")
    assert type_of(legs, SPOT, GAP) != "ic"


def test_shorts_at_different_strikes_stay_a_condor_not_a_butterfly():
    result = match(_owner(), spot=SPOT, strike_gap=GAP, templates=CATALOGUE)
    assert result.template.id == "iron_condor"


def test_building_still_refuses_p_43():
    condor = BY_ID["iron_condor"]
    kwargs = {"spot": SPOT, "strike_gap": GAP, "expiries": {"near": EXP}, "prices": [D("10")] * 4}
    with pytest.raises(TemplateError):
        resolve_template(condor, overrides={"p": FAR_P}, **kwargs)
    assert condor.violations({**condor.defaults(), "p": FAR_P})
    assert not condor.violations({**condor.defaults(), "p": FAR_P}, matching=True)


def test_param_states_in_both_modes():
    inside = Param(name="x", default=1, min=1, max=5)
    pos = Param(name="x", default=1, min=1, max=5, must_be_positive=True)
    assert inside.violation(3) is None and inside.violation(3, matching=True) is None
    assert inside.violation(9) and inside.violation(9, matching=True) is None  # outside range
    assert pos.violation(0) and pos.violation(0, matching=True)  # not positive: both modes refuse
    assert pos.violation(-4) and pos.violation(-4, matching=True)
    assert inside.violation(True) and inside.violation(True, matching=True)  # int check kept
    assert inside.violation(2.5) and inside.violation(2.5, matching=True)


def test_every_template_still_matches_3x_its_max_range_away():
    """Detection: a future range cannot hide a shape again."""
    checked = 0
    for t in CATALOGUE:
        defaults = t.defaults()
        for p in t.params:
            for far in (p.max * 3, p.min * 3):
                if far == 0 or far == defaults[p.name]:
                    continue
                values = {**defaults, p.name: far}
                if t.violations(values, matching=True):
                    continue  # moving this param alone breaks an order / sign / positive rule: not a range case
                result = match_shape(template_shape(t, values), [t])
                assert isinstance(result, MatchResult) and result.template.id == t.id, (t.id, p.name, far)
                checked += 1
    assert checked >= len(CATALOGUE)
