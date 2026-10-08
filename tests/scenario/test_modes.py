"""REQ-034 AC-6: At Expiry (default, exact) and Estimated Now (model-based, labelled estimate) (Q33A = C)."""
import dataclasses
from decimal import Decimal as D

import pytest

from ofo.engine.estimate import MODEL, estimate_now
from ofo.engine.legs import Action, Instrument
from ofo.scenario.config import ScenarioConfig
from ofo.scenario.levels import build_level_set
from ofo.scenario.outcome import scenario_table
from ofo.scenario.views import DEFAULT_VIEW, View, scenario_values
from scenario_fixtures import nifty_input, nifty_leg


def test_ac6_at_expiry_is_default_and_exact(golden, settings):
    """AC-6: the default view is At Expiry, kind exact, with the §6 values at the inserted columns."""
    assert DEFAULT_VIEW is View.AT_EXPIRY
    table = scenario_table(golden, settings.for_index("NIFTY"))
    values = table.values
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
        assert total == estimate_now(golden, level).total, level
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
    """AC-6: a breakeven with 3 decimals (23,100.625) is estimated at 23,100.62 (half-even to 0.01) and recorded."""
    legs = [
        nifty_leg(Action.BUY, Instrument.CE, "23000", "100.00", iv="0.12"),
        nifty_leg(Action.BUY, Instrument.CE, "23100", "1.00", iv="0.12"),
    ]
    legs = [dataclasses.replace(legs[0], quantity=3), dataclasses.replace(legs[1], quantity=5)]
    inputs = nifty_input(legs)
    config = ScenarioConfig("NIFTY", D("100"), D("100"), D("1000"), 2, 200)
    ls = build_level_set(inputs, config)
    assert ls.breakevens == (D("23100.625"),)
    values = scenario_values(ls, inputs, View.ESTIMATED_NOW)
    at = values.levels.index(D("23100.625"))
    assert values.estimated_levels[at] == D("23100.62")
    assert values.totals[at] == estimate_now(inputs, D("23100.62")).total
    assert scenario_values(ls, inputs, View.AT_EXPIRY).totals[at] == D("0")


def test_views_fail_closed(golden, settings):
    """Negative: an unknown view or a level set from another strategy input is refused."""
    ls = build_level_set(golden, settings.for_index("NIFTY"))
    with pytest.raises(ValueError, match="view must be a View"):
        scenario_values(ls, golden, "estimated_now")
    other = dataclasses.replace(golden, underlying_level=D("23100"), spot=dataclasses.replace(golden.spot, level=D("23100")))
    with pytest.raises(ValueError, match="different strategy input"):
        scenario_values(ls, other, View.AT_EXPIRY)
