"""AC-1: any combination of the six leg types, any number of legs, multiple expiries.
AC-4: a leg set fitting no template is a valid Custom Strategy; one fitting a template is named, with params.

Spec: REQ-028 AC-1, AC-4; ADR-006 Q52. The reviewer's reproductions R1-R14 and the resolve->match property
sweep live in ``test_param_templates.py``; this file keeps the AC-1 model tests and the AC-4 basics.
"""
from __future__ import annotations

import datetime
from decimal import Decimal

import pytest

from ofo.engine.legs import Action, Instrument, Leg
from ofo.engine.metrics import MultiExpiryError, strategy_metrics
from ofo.engine.strategy import Strategy
from ofo.strategy.loader import load_templates
from ofo.strategy.matching import CUSTOM_STRATEGY, Custom, MatchResult, match
from ofo.strategy.model import TemplateError, resolve_template

CATALOGUE = load_templates()
BY_ID = {t.id: t for t in CATALOGUE}
SPOT, GAP = Decimal("23200"), Decimal("50")
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
    strategy = Strategy(legs=legs)
    assert len(strategy.legs) == 6
    assert not strategy.is_single_expiry
    assert strategy.expiry_pnl_at(Decimal("23100")) == Decimal("0")  # every pair nets to zero
    with pytest.raises(MultiExpiryError):
        strategy_metrics(strategy)


def test_multi_expiry_templates_resolve_and_refuse_exact_metrics():
    """AC-1: calendar and diagonal resolve onto two expiries; exact metrics still raise MultiExpiryError."""
    for template_id in ("calendar_spread", "diagonal_spread"):
        strategy = resolve_template(
            BY_ID[template_id], spot=SPOT, strike_gap=GAP, expiries={"near": NEAR, "next": NEXT},
            prices=[Decimal("40"), Decimal("70")], base_quantity=75,
        )
        assert {leg.expiry for leg in strategy.legs} == {NEAR, NEXT}
        with pytest.raises(MultiExpiryError):
            strategy_metrics(strategy)
        result = match(strategy, spot=SPOT, strike_gap=GAP, templates=CATALOGUE)
        assert isinstance(result, MatchResult) and result.template.id == template_id


def test_custom_combination_matches_no_template():
    """AC-4: three calls bought at three unevenly spaced strikes fit no template: a valid Custom Strategy."""
    legs = (
        Leg(Action.BUY, Instrument.CE, Decimal("23000"), NEAR, 75, Decimal("100")),
        Leg(Action.BUY, Instrument.CE, Decimal("23150"), NEAR, 75, Decimal("80")),
        Leg(Action.BUY, Instrument.CE, Decimal("23450"), NEAR, 75, Decimal("40")),
    )
    result = match(Strategy(legs=legs), spot=SPOT, strike_gap=GAP, templates=CATALOGUE)
    assert isinstance(result, Custom)
    assert result.label == CUSTOM_STRATEGY == "Custom Strategy"
    assert result.nearest == ()  # no template has three bought calls


def test_match_returns_template_and_parameters():
    """AC-4 (review F5): matching returns the parameters, not only a name."""
    strategy = resolve_template(
        BY_ID["iron_condor"], spot=SPOT, strike_gap=GAP, expiries={"near": NEAR},
        prices=[Decimal("10"), Decimal("30"), Decimal("30"), Decimal("10")], base_quantity=75,
        overrides={"p": 3, "q": 4, "w_put": 5, "w_call": 5},
    )
    result = match(strategy, spot=SPOT, strike_gap=GAP, templates=CATALOGUE)
    assert result.label == "Iron Condor"
    assert dict(result.params) == {"p": 3, "q": 4, "w_put": 5, "w_call": 5}
    assert result.base_quantity == 75


def test_butterfly_entered_as_two_separate_middle_legs_matches():
    """AC-4: two SELL legs of 75 at one strike merge into the template's single x2 middle leg."""
    legs = (
        Leg(Action.BUY, Instrument.CE, Decimal("23100"), NEAR, 75, Decimal("40")),
        Leg(Action.SELL, Instrument.CE, Decimal("23200"), NEAR, 75, Decimal("70")),
        Leg(Action.SELL, Instrument.CE, Decimal("23200"), NEAR, 75, Decimal("70")),
        Leg(Action.BUY, Instrument.CE, Decimal("23300"), NEAR, 75, Decimal("15")),
    )
    result = match(legs, spot=SPOT, strike_gap=GAP, templates=CATALOGUE)
    assert result.template.id == "butterfly_spread" and dict(result.params) == {"m": 0, "w": 2}


def test_atm_is_measured_from_spot_with_half_up_tie():
    """AC-4: the same legs read differently from different spots; spot 23,225 is a tie and rounds up to 23,250,
    so a straddle at 23,250 is Straddle (Short) there and Custom from spot 23,224 (ATM 23,200)."""
    legs = (
        Leg(Action.SELL, Instrument.CE, Decimal("23250"), NEAR, 75, Decimal("90")),
        Leg(Action.SELL, Instrument.PE, Decimal("23250"), NEAR, 75, Decimal("95")),
    )
    assert match(legs, spot=Decimal("23225"), strike_gap=GAP, templates=CATALOGUE).template.id == "short_straddle"
    assert isinstance(match(legs, spot=Decimal("23224"), strike_gap=GAP, templates=CATALOGUE), Custom)


def test_three_expiries_is_custom_and_empty_input_is_refused():
    """AC-4 red cases: legs over three expiries fit no template (only two slots exist); no legs is an error."""
    legs = tuple(
        Leg(Action.BUY, Instrument.CE, Decimal("23200"), expiry, 75, Decimal("50"))
        for expiry in (NEAR, NEXT, datetime.date(2026, 12, 31))
    )
    assert isinstance(match(legs, spot=SPOT, strike_gap=GAP, templates=CATALOGUE), Custom)
    with pytest.raises(TemplateError):
        match((), spot=SPOT, strike_gap=GAP, templates=CATALOGUE)
