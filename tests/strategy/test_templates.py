"""AC-3, AC-5: templates are data, no per-strategy engine code, and wording stays decision-support.

Core proof (W-005): the Iron Condor template, resolved at NIFTY spot 23,200 with strike gap 50, yields
four legs the engine prices -- see ``test_iron_condor_core_proof_at_nifty``.
"""
from __future__ import annotations

import datetime
import re
from decimal import Decimal

import pytest

from ofo.engine.metrics import MultiExpiryError, strategy_metrics
from ofo.engine.legs import Instrument
from ofo.strategy.loader import DEFAULT_CATALOGUE_PATH, load_templates
from ofo.strategy.model import Template, TemplateError, TemplateLeg, resolve_template

CATALOGUE = load_templates()
NEAR_EXPIRY = datetime.date(2026, 10, 30)
NEXT_EXPIRY = datetime.date(2026, 11, 27)

# Sample entry prices, clearly labelled: round rupee figures that are never mistaken for a real quote.
SAMPLE_PRICE_CYCLE = [Decimal("10.00"), Decimal("25.00"), Decimal("40.00"), Decimal("55.00")]


def _sample_prices(n: int) -> list[Decimal]:
    return [SAMPLE_PRICE_CYCLE[i % len(SAMPLE_PRICE_CYCLE)] for i in range(n)]


def test_catalogue_has_22_templates_adapted_from_algochanakya():
    """AC-3: the catalogue loads as data; count matches spec/technical-design/legacy-reuse.md row 7."""
    assert len(CATALOGUE) == 22
    assert len({t.id for t in CATALOGUE}) == 22


def test_iron_condor_core_proof_at_nifty():
    """Core: Iron Condor resolved at NIFTY spot 23,200, strike gap 50, prices through the engine."""
    iron_condor = next(t for t in CATALOGUE if t.id == "iron_condor")
    strategy = resolve_template(
        iron_condor,
        spot=Decimal("23200"),
        strike_gap=Decimal("50"),
        expiries={"near": NEAR_EXPIRY},
        prices=[Decimal("10"), Decimal("30"), Decimal("30"), Decimal("10")],
        base_quantity=75,
    )
    assert [leg.strike for leg in strategy.legs] == [
        Decimal("23000"),
        Decimal("23100"),
        Decimal("23300"),
        Decimal("23400"),
    ]
    metrics = strategy_metrics(strategy)
    assert metrics.max_profit == Decimal("3000")
    assert metrics.max_loss == Decimal("4500")
    assert metrics.min_pnl == Decimal("-4500")
    assert metrics.breakevens == (Decimal("23060"), Decimal("23340"))


@pytest.mark.parametrize(
    "index,spot,strike_gap",
    [
        ("NIFTY", Decimal("23200"), Decimal("50")),
        ("SENSEX", Decimal("79800"), Decimal("100")),
    ],
)
def test_every_template_resolves_and_prices_through_the_engine(index, spot, strike_gap):
    """AC-3: every catalogue template resolves at a real index/gap and prices through the one engine."""
    for template in CATALOGUE:
        expiries = {"near": NEAR_EXPIRY}
        if not template.is_single_expiry:
            expiries["next"] = NEXT_EXPIRY
        strategy = resolve_template(
            template,
            spot=spot,
            strike_gap=strike_gap,
            expiries=expiries,
            prices=_sample_prices(len(template.legs)),
            base_quantity=75,
        )
        assert len(strategy.legs) == len(template.legs)

        # Expiry P&L at three levels always computes -- it's a per-leg formula, independent of dates.
        for level in (spot - strike_gap * 10, spot, spot + strike_gap * 10):
            value = strategy.expiry_pnl_at(level)
            assert isinstance(value, Decimal), (template.id, index)

        if template.is_single_expiry:
            metrics = strategy_metrics(strategy)
            assert metrics.max_loss is not None, (template.id, index)
        else:
            with pytest.raises(MultiExpiryError):
                strategy_metrics(strategy)


def test_multi_expiry_templates_are_exactly_calendar_and_diagonal():
    """AC-3: the only multi-expiry templates in this catalogue are the two that name a later expiry."""
    multi = {t.id for t in CATALOGUE if not t.is_single_expiry}
    assert multi == {"calendar_spread", "diagonal_spread"}


def test_adding_a_template_file_needs_zero_code_changes(tmp_path):
    """AC-3 core proof: a brand-new template, added purely as data, resolves with no code change."""
    new_catalogue = tmp_path / "extra.yaml"
    new_catalogue.write_text(
        """
        templates:
          - id: naked_call
            name: "Naked Call"
            description: "Sell a single out-of-the-money call."
            legs:
              - {action: SELL, instrument: CE, offset_steps: 2, expiry_slot: near, quantity_multiplier: 1}
        """,
        encoding="utf-8",
    )
    (loaded,) = load_templates(new_catalogue)
    assert loaded.id == "naked_call"
    strategy = resolve_template(
        loaded,
        spot=Decimal("23200"),
        strike_gap=Decimal("50"),
        expiries={"near": NEAR_EXPIRY},
        prices=[Decimal("15")],
        base_quantity=75,
    )
    metrics = strategy_metrics(strategy)
    assert metrics.max_profit == Decimal("1125")  # premium 15 x 75


BANNED_PHRASES = ("best", "you should", "guaranteed", "sure", "risk-free", "risk free")


def test_no_template_text_uses_banned_advice_wording():
    """AC-5 (ADR-003): template names/descriptions never say 'best', 'you should', 'guaranteed', ...

    Red case: a text string carrying a banned phrase is caught by the same scan.
    """
    for template in CATALOGUE:
        text = f"{template.name} {template.description}".lower()
        for phrase in BANNED_PHRASES:
            assert not re.search(rf"\b{re.escape(phrase)}\b", text), (template.id, phrase)

    with pytest.raises(AssertionError):
        text = "this is the best strategy, you should always use it".lower()
        for phrase in BANNED_PHRASES:
            assert not re.search(rf"\b{re.escape(phrase)}\b", text)


def test_default_catalogue_path_points_at_the_real_file():
    assert DEFAULT_CATALOGUE_PATH.name == "catalogue.yaml"
    assert DEFAULT_CATALOGUE_PATH.is_file()


def test_resolve_template_rejects_wrong_price_count():
    """Red case: fewer prices than legs raises TemplateError, never a silent default price."""
    iron_condor = next(t for t in CATALOGUE if t.id == "iron_condor")
    with pytest.raises(TemplateError):
        resolve_template(
            iron_condor,
            spot=Decimal("23200"),
            strike_gap=Decimal("50"),
            expiries={"near": NEAR_EXPIRY},
            prices=[Decimal("10"), Decimal("30")],
            base_quantity=75,
        )


def test_resolve_template_rejects_missing_expiry_slot():
    """Red case: a multi-expiry template with no 'next' expiry supplied raises, never a silent default."""
    calendar = next(t for t in CATALOGUE if t.id == "calendar_spread")
    with pytest.raises(TemplateError):
        resolve_template(
            calendar,
            spot=Decimal("23200"),
            strike_gap=Decimal("50"),
            expiries={"near": NEAR_EXPIRY},
            prices=_sample_prices(len(calendar.legs)),
            base_quantity=75,
        )


def test_futures_leg_has_no_strike_offset():
    """Covered call's futures leg carries no strike, matching Leg's own futures rule (ADR-041)."""
    covered_call = next(t for t in CATALOGUE if t.id == "covered_call")
    strategy = resolve_template(
        covered_call,
        spot=Decimal("23200"),
        strike_gap=Decimal("50"),
        expiries={"near": NEAR_EXPIRY},
        prices=_sample_prices(len(covered_call.legs)),
        base_quantity=75,
    )
    fut_legs = [leg for leg in strategy.legs if leg.instrument is Instrument.FUT]
    assert len(fut_legs) == 1
    assert fut_legs[0].strike is None
