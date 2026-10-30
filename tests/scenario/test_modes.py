"""REQ-034 AC-6: At Expiry (default, exact) and Estimated Now (model-based, labelled estimate) (Q33A = C)."""
import dataclasses
from decimal import Decimal as D

import ofo.outcome.service as service_module
import pytest
from marketdata._kite_fixture import all_instrument_ids, new_provider, replay
from ofo.engine.estimate import MODEL, estimate_now
from ofo.engine.legs import Action, Instrument
from ofo.outcome import OutcomeState
from ofo.scenario.config import ScenarioConfig
from ofo.scenario.levels import build_level_set
from ofo.scenario.views import DEFAULT_VIEW, View, scenario_values
from outcome.test_same_engine import formula_pnl, outcome_of
from scenario_fixtures import nifty_input, nifty_leg

LEGS = 4  # the condor's legs


def test_ac6_at_expiry_is_default_and_exact(golden, settings):
    """AC-6: the default view is At Expiry, kind exact, with the §6 values at the inserted columns."""
    assert DEFAULT_VIEW is View.AT_EXPIRY
    values = scenario_values(build_level_set(golden, settings.for_index("NIFTY")), golden, DEFAULT_VIEW)
    assert (values.view, values.label, values.kind, values.available) == (View.AT_EXPIRY, "At Expiry", "exact", True)
    by_level = dict(zip(values.levels, values.totals))
    assert by_level[D("22909")] == D("0") and by_level[D("23491")] == D("0")
    assert by_level[D("23047")] == D("6825") and by_level[D("22900")] == D("-675")
    assert by_level[D("22000")] == D("-8175") and by_level[D("24000")] == D("-8175")
    # Per-leg rows filled for every leg at every level (§1); leg 1 at 22,000 = +56,812.50 (§6 sample).
    assert len(values.leg_rows) == 4 and all(len(row) == len(values.levels) for row in values.leg_rows)
    assert values.leg_rows[0][values.levels.index(D("22000"))] == D("56812.50")
    assert values.assumptions is None


def test_ac6_estimated_now_labelled_estimate_from_engine(golden, settings):
    """AC-6: Estimated Now is labelled an estimate, states its assumptions, and every value is the engine's estimate."""
    ls = build_level_set(golden, settings.for_index("NIFTY"))
    values = scenario_values(ls, golden, View.ESTIMATED_NOW)
    assert (values.kind, values.available) == ("estimate", True)
    assert "estimate" in values.label.lower()
    assert values.assumptions.model == MODEL
    assert values.assumptions.ivs == tuple(leg.iv for leg in golden.legs)
    for level, total in zip(values.levels, values.totals):
        assert total == estimate_now(golden.inputs, level).total, level
    # An estimate before expiry is not the expiry number (time value remains 10 days out).
    exact = scenario_values(ls, golden, View.AT_EXPIRY)
    at = values.levels.index(D("23047"))
    assert values.totals[at] != exact.totals[at]


def test_ac6_missing_iv_makes_estimated_now_unavailable_never_zero(settings):
    """AC-6 negative: an option leg without IV -> Estimated Now unavailable with a reason; At Expiry unaffected."""
    legs = [nifty_leg(Action.SELL, Instrument.PE, "23000", "86.00", iv="0.108838"),
            nifty_leg(Action.BUY, Instrument.PE, "22800", "42.50")]
    inputs = nifty_input(legs)
    ls = build_level_set(inputs, settings.for_index("NIFTY"))
    values = scenario_values(ls, inputs, View.ESTIMATED_NOW)
    assert values.available is False
    assert values.totals is None and values.leg_rows is None
    assert values.unavailable_reason == "Estimated Now is unavailable: no implied volatility for NIFTY26OCT22800PE"
    assert scenario_values(ls, inputs, View.AT_EXPIRY).available is True


def test_ac6_estimate_at_exact_breakeven_uses_quoted_level():
    """AC-6: a breakeven whose exact value has 3 decimals (23,100.625) is estimated at 23,100.62 (half-even to 0.01).
    Since REQ-155 AC-4 (F-75) the engine rounds every derived level at its one producer, so the level set already
    carries 23,100.62 (was the exact 23,100.625) and Estimated Now is taken at that same quoted level."""
    legs = [
        nifty_leg(Action.BUY, Instrument.CE, "23000", "100.00", iv="0.12"),
        nifty_leg(Action.BUY, Instrument.CE, "23100", "1.00", iv="0.12"),
    ]
    legs = [dataclasses.replace(legs[0], quantity=3), dataclasses.replace(legs[1], quantity=5)]
    inputs = nifty_input(legs)
    config = ScenarioConfig("NIFTY", D("100"), D("100"), D("1000"), 2, 200)
    ls = build_level_set(inputs, config)
    assert ls.breakevens == (D("23100.62"),)
    values = scenario_values(ls, inputs, View.ESTIMATED_NOW)
    at = values.levels.index(D("23100.62"))
    assert values.estimated_levels[at] == D("23100.62")
    assert values.totals[at] == estimate_now(inputs.inputs, D("23100.62")).total


def test_views_fail_closed(golden, settings):
    """Negative: an unknown view or a level set from another strategy input is refused."""
    ls = build_level_set(golden, settings.for_index("NIFTY"))
    with pytest.raises(ValueError, match="view must be a View"):
        scenario_values(ls, golden, "estimated_now")
    other = nifty_input(golden.legs, spot=D("23100"))
    with pytest.raises(ValueError, match="different strategy input"):
        scenario_values(ls, other, View.AT_EXPIRY)


@pytest.fixture(scope="module")
def replayed():
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    replay(provider, clock)
    return provider


# ---- the same two modes on the product's path: build_outcome (the outcome route and the live push call it) -----------
def test_ac6_build_outcome_default_is_at_expiry_exact(replayed):
    """AC-6 on build_outcome, real 2026-10-08 frames: the default is At Expiry, exact, every cell the formula."""
    out = outcome_of(replayed)
    assert out.state is OutcomeState.COMPUTED, out.reason
    values = out.scenario
    assert (values.view, values.label, values.kind, values.available) == (View.AT_EXPIRY, "At Expiry", "exact", True)
    assert values.assumptions is None
    assert len(values.leg_rows) == LEGS and all(len(row) == len(values.levels) for row in values.leg_rows)
    for level, total in zip(values.levels, values.totals, strict=True):
        assert total == formula_pnl(level, replayed), level


def test_ac6_build_outcome_estimated_now_is_labelled_estimate(replayed):
    """AC-6 on build_outcome: Estimated Now is an estimate from the engine with the legs' solved IVs, and differs from
    the expiry number 5 days out."""
    out = outcome_of(replayed, view=View.ESTIMATED_NOW)
    values = out.scenario
    assert (values.view, values.kind, values.available) == (View.ESTIMATED_NOW, "estimate", True)
    assert "estimate" in values.label.lower()
    assert values.assumptions.model == MODEL
    assert values.assumptions.ivs == tuple(leg.iv for leg in out.legs) and None not in values.assumptions.ivs
    exact = outcome_of(replayed).scenario
    assert exact.levels == values.levels
    at = values.levels.index(D("22500"))
    assert values.totals[at] != exact.totals[at]


def test_ac6_build_outcome_without_iv_estimated_now_unavailable_never_zero(replayed, monkeypatch):
    """AC-6 negative on build_outcome: no solved IV -> Estimated Now unavailable with its reason; At Expiry kept."""
    monkeypatch.setattr(service_module, "_leg_iv", lambda *a, **k: None)
    out = outcome_of(replayed, view=View.ESTIMATED_NOW)
    values = out.scenario
    assert values.available is False
    assert values.totals is None and values.leg_rows is None and out.payoff_points == ()
    names = ", ".join(leg.symbol for leg in out.legs)
    assert values.unavailable_reason == f"Estimated Now is unavailable: no implied volatility for {names}"
    assert outcome_of(replayed).scenario.available is True
