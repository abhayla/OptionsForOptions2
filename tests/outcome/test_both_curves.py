"""GC-UI step 4 server, item 1 (REQ-083 AC-1/AC-2/AC-3; D-B06, D-B14; ADR-008, ADR-143): one outcome call carries the
At Expiry curve AND the Estimated Now curve over the SAME levels, both from the one engine, each point with its server
display text, so the chart draws both lines and a hover reads both values with no second request.

Answer states: flag off (today's reply byte-identical, tests/fixtures/outcome_both_curves/flag_off.json recorded on the
code before this change); flag on; Estimated Now unavailable (a leg without IV: that list absent with its reason, the
other unchanged); calendar (ADR-143: the At Expiry figures stay "can't be estimated"); from your prices (REQ-077 AC-9:
Estimated Now needs live prices)."""
from __future__ import annotations

import dataclasses
import json

import pytest
from ofo.engine.model import ModelInputs
from ofo.errors.explanations import render_explanation
from ofo.outcome.serialize import outcome_to_dict
from ofo.scenario.views import View
from outcome._both_curves_cases import (
    CALENDAR,
    GOLDEN,
    S54,
    as_json,
    entries_outcome,
    golden_text,
    market,
    outcome,
)


@pytest.fixture(scope="module")
def provider():
    return market()


def _single(provider, legs, view):
    return as_json(outcome_to_dict(outcome(provider, legs, view=view)))


def test_flag_off_replies_are_byte_identical_to_the_recorded_ones(provider):
    assert golden_text(provider) == GOLDEN.read_text(encoding="utf-8")


@pytest.mark.parametrize("view", list(View))
def test_core_both_curves_on_the_same_levels_equal_each_single_view_reply(provider, view):
    """The core: one call, both lists, the same levels, each byte-equal to today's single-view payoff points."""
    both = as_json(outcome_to_dict(outcome(provider, S54, view=view, both_views=True)))
    curves = both["curves"]
    assert set(curves) == {"at_expiry", "estimated_now"}
    for v in View:
        assert curves[v.value]["points"] == _single(provider, S54, v)["payoff"]["points"], v
        assert curves[v.value]["available"] is True and curves[v.value]["unavailable_reason"] is None
        assert curves[v.value]["view"] == v.value
    levels = [[p["level"] for p in curves[v.value]["points"]] for v in View]
    assert levels[0] == levels[1] and levels[0]
    # the asked view's own blocks are unchanged by the flag
    single = _single(provider, S54, view)
    for key in ("payoff", "table", "summary", "legs", "margin"):
        assert both[key] == single[key], key
    # the scenario block gains the other view's totals on the table's levels, from the same curve
    other = View.ESTIMATED_NOW if view is View.AT_EXPIRY else View.AT_EXPIRY
    o = both["scenario"].pop("other")
    assert both["scenario"] == single["scenario"]
    assert o["view"] == other.value and o["available"] is True
    assert o["totals"] == _single(provider, S54, other)["scenario"]["totals"]


def test_estimated_now_unavailable_keeps_at_expiry_and_says_why(provider, monkeypatch):
    """A leg without IV: the Estimated Now list is empty with the engine's reason; At Expiry is unchanged."""
    import ofo.outcome.service as service

    real = service.model_inputs

    def no_iv(strategy_input, forwards):
        legs = tuple(dataclasses.replace(leg, iv=None) if i == 0 else leg
                     for i, leg in enumerate(strategy_input.legs))
        return real(dataclasses.replace(strategy_input, legs=legs), forwards)

    monkeypatch.setattr(service, "model_inputs", no_iv)
    both = as_json(outcome_to_dict(outcome(provider, S54, both_views=True)))
    est, atx = both["curves"]["estimated_now"], both["curves"]["at_expiry"]
    assert est["available"] is False and est["points"] == []
    assert est["unavailable_reason"].startswith("Estimated Now is unavailable: no implied volatility for")
    monkeypatch.setattr(service, "model_inputs", real)
    assert atx["points"] == _single(provider, S54, View.AT_EXPIRY)["payoff"]["points"]
    assert isinstance(real, type(service.model_inputs)) and ModelInputs


def test_calendar_at_expiry_stays_cannot_be_estimated(provider):
    """ADR-143 / RD-088 not changed: the at-expiry curve of a calendar is unavailable with the worst-case line."""
    both = as_json(outcome_to_dict(outcome(provider, CALENDAR, view=View.ESTIMATED_NOW, both_views=True)))
    atx, est = both["curves"]["at_expiry"], both["curves"]["estimated_now"]
    assert atx["available"] is False and atx["points"] == []
    assert atx["unavailable_reason"] == render_explanation("mixed_expiry_worst_case")
    assert est["points"] == _single(provider, CALENDAR, View.ESTIMATED_NOW)["payoff"]["points"] != []


def test_from_your_prices_has_at_expiry_and_no_estimate(provider):
    both = as_json(outcome_to_dict(entries_outcome(provider, S54, both_views=True)))
    single = as_json(outcome_to_dict(entries_outcome(provider, S54)))
    assert both["curves"]["at_expiry"]["points"] == single["payoff"]["points"] != []
    est = both["curves"]["estimated_now"]
    assert est["available"] is False and est["points"] == []
    assert est["unavailable_reason"] == render_explanation("outcome_from_entries_no_estimate")


def test_flag_off_has_no_new_keys(provider):
    body = json.loads(json.dumps(outcome_to_dict(outcome(provider, S54)), default=str))
    assert "curves" not in body and "other" not in body["scenario"]
