"""AC-1: any combination of the six leg types, any number of legs, multiple expiries.
AC-4: a leg set matching no template is a valid Custom Strategy; one matching a template is named.
"""
from __future__ import annotations

import datetime
from decimal import Decimal

import pytest

from ofo.engine.legs import Action, Instrument, Leg
from ofo.engine.metrics import MultiExpiryError, strategy_metrics
from ofo.engine.strategy import Strategy
from ofo.strategy.loader import load_templates
from ofo.strategy.matching import CUSTOM_STRATEGY, match_template
from ofo.strategy.model import resolve_template

CATALOGUE = load_templates()
NEAR = datetime.date(2026, 10, 30)
NEXT = datetime.date(2026, 11, 27)


def test_strategy_holds_all_six_leg_types_across_two_expiries():
    """AC-1: the six leg types are Action(BUY/SELL) x Instrument(CE/PE/FUT); a strategy can hold all six,
    spread over two expiries, and is still valid."""
    legs = tuple(
        Leg(
            action=action,
            instrument=instrument,
            strike=Decimal("23000") if instrument is not Instrument.FUT else None,
            expiry=NEAR if instrument is not Instrument.FUT else NEXT,
            quantity=75,
            entry_price=Decimal("100"),
        )
        for action in (Action.BUY, Action.SELL)
        for instrument in (Instrument.CE, Instrument.PE, Instrument.FUT)
    )
    assert len(legs) == 6
    strategy = Strategy(legs=legs)
    assert len(strategy.legs) == 6
    assert not strategy.is_single_expiry  # FUT legs sit on NEXT, options on NEAR

    # The one engine prices it: expiry P&L computes at any level, exact metrics refuse (multi-expiry).
    assert isinstance(strategy.expiry_pnl_at(Decimal("23100")), Decimal)
    with pytest.raises(MultiExpiryError):
        strategy_metrics(strategy)


def test_custom_combination_matches_no_template():
    """AC-4: a leg set with no template counterpart in the catalogue is a valid Custom Strategy."""
    # Three calls bought at three different, unevenly-spaced strikes: no template in the catalogue
    # has this shape (every 3+ leg template here uses evenly-stepped or repeated strikes).
    legs = (
        Leg(Action.BUY, Instrument.CE, Decimal("23000"), NEAR, 75, Decimal("100")),
        Leg(Action.BUY, Instrument.CE, Decimal("23150"), NEAR, 75, Decimal("80")),
        Leg(Action.BUY, Instrument.CE, Decimal("23450"), NEAR, 75, Decimal("40")),
    )
    strategy = Strategy(legs=legs)
    matched = match_template(strategy, CATALOGUE, spot=Decimal("23200"), strike_gap=Decimal("50"))
    assert matched is None  # the caller reports this as "Custom Strategy"
    label = matched.name if matched is not None else CUSTOM_STRATEGY
    assert label == "Custom Strategy"


def test_resolved_iron_condor_matches_its_own_template():
    """AC-4: a leg set built FROM a template's resolver is recognised as that template."""
    iron_condor = next(t for t in CATALOGUE if t.id == "iron_condor")
    strategy = resolve_template(
        iron_condor,
        spot=Decimal("23200"),
        strike_gap=Decimal("50"),
        expiries={"near": NEAR},
        prices=[Decimal("10"), Decimal("30"), Decimal("30"), Decimal("10")],
        base_quantity=75,
    )
    matched = match_template(strategy, CATALOGUE, spot=Decimal("23200"), strike_gap=Decimal("50"))
    assert matched is not None
    assert matched.id == "iron_condor"


def test_every_catalogue_template_matches_itself_when_resolved():
    """AC-4, sweep: every template in the catalogue round-trips through resolve -> match."""
    for template in CATALOGUE:
        expiries = {"near": NEAR}
        if not template.is_single_expiry:
            expiries["next"] = NEXT
        strategy = resolve_template(
            template,
            spot=Decimal("23200"),
            strike_gap=Decimal("50"),
            expiries=expiries,
            prices=[Decimal("10.00") for _ in template.legs],
            base_quantity=75,
        )
        matched = match_template(strategy, CATALOGUE, spot=Decimal("23200"), strike_gap=Decimal("50"))
        assert matched is not None, template.id
        # cash_secured_put and wheel_strategy share one leg set (documented in matching.py); either
        # is an acceptable match for the other's resolved strategy.
        if template.id in ("cash_secured_put", "wheel_strategy"):
            assert matched.id in ("cash_secured_put", "wheel_strategy")
        else:
            assert matched.id == template.id


def test_a_single_leg_off_the_strike_grid_matches_nothing():
    """Red case: a strike that isn't on the strike-gap grid can't be expressed as offset steps."""
    legs = (Leg(Action.SELL, Instrument.PE, Decimal("23025"), NEAR, 75, Decimal("50")),)
    strategy = Strategy(legs=legs)
    matched = match_template(strategy, CATALOGUE, spot=Decimal("23200"), strike_gap=Decimal("50"))
    assert matched is None
