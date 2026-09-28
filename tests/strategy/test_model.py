"""AC-1: any combination of the six leg types, any number of legs, multiple expiries.
AC-4: a leg set matching no template is a valid Custom Strategy; one matching a template is named.

Matching is structural (translation-invariant on the strike ladder, merge-invariant on quantity) --
see ``ofo.strategy.matching`` -- so it never takes a ``spot``.
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
GAP = Decimal("50")
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
    matched = match_template(strategy, CATALOGUE, strike_gap=GAP)
    assert matched is None  # the caller reports this as "Custom Strategy"
    label = matched.name if matched is not None else CUSTOM_STRATEGY
    assert label == "Custom Strategy"


def test_resolved_iron_condor_matches_its_own_template():
    """AC-4: a leg set built FROM a template's resolver is recognised as that template."""
    iron_condor = next(t for t in CATALOGUE if t.id == "iron_condor")
    strategy = resolve_template(
        iron_condor,
        spot=Decimal("23200"),
        strike_gap=GAP,
        expiries={"near": NEAR},
        prices=[Decimal("10"), Decimal("30"), Decimal("30"), Decimal("10")],
        base_quantity=75,
    )
    matched = match_template(strategy, CATALOGUE, strike_gap=GAP)
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
            strike_gap=GAP,
            expiries=expiries,
            prices=[Decimal("10.00") for _ in template.legs],
            base_quantity=75,
        )
        matched = match_template(strategy, CATALOGUE, strike_gap=GAP)
        assert matched is not None, template.id
        assert matched.id == template.id


def test_a_single_leg_off_the_strike_grid_matches_nothing():
    """Red case: a strike that isn't on the strike-gap grid can't be expressed as offset steps."""
    legs = (Leg(Action.SELL, Instrument.PE, Decimal("23025"), NEAR, 75, Decimal("50")),)
    strategy = Strategy(legs=legs)
    matched = match_template(strategy, CATALOGUE, strike_gap=GAP)
    assert matched is None


# ---------------------------------------------------------------------------
# AC-4 fix round: structural (translation-invariant) matching, and leg-merging.
# ---------------------------------------------------------------------------


def test_iron_condor_shifted_away_from_atm_still_matches():
    """A same-shape Iron Condor entered several strikes away from any particular ATM is still an Iron
    Condor -- matching never anchors to a spot/ATM."""
    iron_condor = next(t for t in CATALOGUE if t.id == "iron_condor")
    # Resolved once "at" spot 23,200 (ATM 23,200)...
    near_atm = resolve_template(
        iron_condor,
        spot=Decimal("23200"),
        strike_gap=GAP,
        expiries={"near": NEAR},
        prices=[Decimal("10"), Decimal("30"), Decimal("30"), Decimal("10")],
        base_quantity=75,
    )
    # ...and again shifted 6 strikes (300 points) away, same shape, different absolute strikes.
    shifted = resolve_template(
        iron_condor,
        spot=Decimal("23500"),
        strike_gap=GAP,
        expiries={"near": NEAR},
        prices=[Decimal("10"), Decimal("30"), Decimal("30"), Decimal("10")],
        base_quantity=75,
    )
    assert [leg.strike for leg in near_atm.legs] != [leg.strike for leg in shifted.legs]
    assert match_template(shifted, CATALOGUE, strike_gap=GAP).id == "iron_condor"
    assert match_template(near_atm, CATALOGUE, strike_gap=GAP).id == "iron_condor"


def test_butterfly_with_one_merged_double_quantity_leg_matches():
    """A butterfly entered as one SELL leg of quantity 2 (instead of two SELL legs of quantity 1) is
    the same shape and must match Butterfly Spread -- legs are merged by (action, instrument, strike,
    expiry) before comparing."""
    legs = (
        Leg(Action.BUY, Instrument.CE, Decimal("23100"), NEAR, 75, Decimal("40")),
        Leg(Action.SELL, Instrument.CE, Decimal("23200"), NEAR, 150, Decimal("70")),  # merged x2
        Leg(Action.BUY, Instrument.CE, Decimal("23300"), NEAR, 75, Decimal("15")),
    )
    strategy = Strategy(legs=legs)
    matched = match_template(strategy, CATALOGUE, strike_gap=GAP)
    assert matched is not None
    assert matched.id == "butterfly_spread"


def test_unequal_wings_stay_custom_strategy():
    """A near-butterfly with unequal wing widths is a DIFFERENT shape -- must stay Custom, not match."""
    legs = (
        Leg(Action.BUY, Instrument.CE, Decimal("23050"), NEAR, 75, Decimal("60")),  # 1 step below
        Leg(Action.SELL, Instrument.CE, Decimal("23200"), NEAR, 150, Decimal("70")),
        Leg(Action.BUY, Instrument.CE, Decimal("23400"), NEAR, 75, Decimal("10")),  # 4 steps above
    )
    strategy = Strategy(legs=legs)
    assert match_template(strategy, CATALOGUE, strike_gap=GAP) is None


def test_mismatched_quantity_ratio_stays_custom_strategy():
    """Same strikes as a bull call spread, but the ratio between legs is 1:3, not 1:1 -- not the same
    shape, so stays Custom."""
    legs = (
        Leg(Action.BUY, Instrument.CE, Decimal("23200"), NEAR, 75, Decimal("100")),
        Leg(Action.SELL, Instrument.CE, Decimal("23300"), NEAR, 225, Decimal("40")),  # 3x quantity
    )
    strategy = Strategy(legs=legs)
    assert match_template(strategy, CATALOGUE, strike_gap=GAP) is None


def test_reverse_calendar_does_not_match_calendar_spread():
    """AC-4 fix round: Calendar Spread is SELL near / BUY next; its reverse (BUY near / SELL next) is a
    different position and must not be labelled Calendar Spread."""
    reverse_calendar = (
        Leg(Action.BUY, Instrument.CE, Decimal("23200"), NEAR, 75, Decimal("40")),
        Leg(Action.SELL, Instrument.CE, Decimal("23200"), NEXT, 75, Decimal("70")),
    )
    strategy = Strategy(legs=reverse_calendar)
    matched = match_template(strategy, CATALOGUE, strike_gap=GAP)
    assert matched is None or matched.id != "calendar_spread"


def test_calendar_resolved_and_matched_is_not_mislabelled_by_file_order():
    """AC-4 fix round: the real Calendar Spread (SELL near, BUY next, as resolved from the template)
    must still match itself -- expiry slots are ranked by EXPIRY_SLOTS' canonical order, not by the
    order legs happen to appear."""
    calendar = next(t for t in CATALOGUE if t.id == "calendar_spread")
    strategy = resolve_template(
        calendar,
        spot=Decimal("23200"),
        strike_gap=GAP,
        expiries={"near": NEAR, "next": NEXT},
        prices=[Decimal("40"), Decimal("70")],
        base_quantity=75,
    )
    matched = match_template(strategy, CATALOGUE, strike_gap=GAP)
    assert matched is not None
    assert matched.id == "calendar_spread"
