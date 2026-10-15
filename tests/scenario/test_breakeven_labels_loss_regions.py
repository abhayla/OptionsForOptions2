"""W-082 / ADR-089 (#171) AC-6: Lower BE / Upper BE follow the computed loss regions, not the P&L next to a breakeven.

Expected labels are hand-derived (lot 75, NIFTY, expiry payoff):
- zero-cost bull put spread, sell 22400 PE @100 + buy 22200 PE @100: P&L is exactly 0 at and above 22,400 and negative
  below it -> the one breakeven 22,400 is the LOWER BE (loss lies below it).
- long call 23000 @100: loss below 23,100 -> Lower BE 23,100.   short call: loss above 23,100 -> Upper BE.
- long put 23000 @100: loss above 22,900 -> Upper BE 22,900.    short put: loss below 22,900 -> Lower BE.
- iron condor: two breakevens -> lowest / highest (unchanged).
"""
from decimal import Decimal as D

from ofo.engine.legs import Action, Instrument
from ofo.scenario.levels import build_level_set

from scenario_fixtures import GOLDEN_LEGS, nifty_input, nifty_leg  # noqa: F401  (fixtures: settings)
from scenario_fixtures import settings  # noqa: F401

BUY, SELL, CE, PE = Action.BUY, Action.SELL, Instrument.CE, Instrument.PE


def _labels(legs, settings):
    ls = build_level_set(nifty_input(legs), settings.for_index("NIFTY"))
    return ls.breakevens, ls.lower_be, ls.upper_be


def test_zero_cost_bull_put_spread_is_lower_be(settings):
    legs = [nifty_leg(SELL, PE, "22400", "100.00"), nifty_leg(BUY, PE, "22200", "100.00")]
    assert _labels(legs, settings) == ((D("22400"),), D("22400"), None)


def test_long_call_lower(settings):
    assert _labels([nifty_leg(BUY, CE, "23000", "100.00")], settings) == ((D("23100"),), D("23100"), None)


def test_short_call_upper(settings):
    assert _labels([nifty_leg(SELL, CE, "23000", "100.00")], settings) == ((D("23100"),), None, D("23100"))


def test_long_put_upper(settings):
    assert _labels([nifty_leg(BUY, PE, "23000", "100.00")], settings) == ((D("22900"),), None, D("22900"))


def test_short_put_lower(settings):
    assert _labels([nifty_leg(SELL, PE, "23000", "100.00")], settings) == ((D("22900"),), D("22900"), None)


def test_iron_condor_two_breakevens_unchanged(settings):
    legs = [nifty_leg(*row) for row in GOLDEN_LEGS]
    assert _labels(legs, settings) == ((D("22909"), D("23491")), D("22909"), D("23491"))


def test_no_loss_region_touching_breakeven_shows_neither(settings, monkeypatch):
    """If the metrics cannot say which side the loss is on, show neither label: no guess, no exception."""
    import ofo.scenario.levels as levels

    real = levels.strategy_metrics

    def no_regions(strategy):
        from dataclasses import replace
        return replace(real(strategy), loss_regions=())

    monkeypatch.setattr(levels, "strategy_metrics", no_regions)
    assert _labels([nifty_leg(BUY, CE, "23000", "100.00")], settings) == ((D("23100"),), None, None)
