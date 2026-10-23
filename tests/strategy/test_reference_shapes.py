"""REQ-028 AC-3 (RD-090, RD-095; W-143): the 20 ready-made shapes added as catalogue data, and the display renames.

Spec: REQ-028 AC-3 (templates are data; a shape that fits two templates is refused; ADR-003 wording). Each leg set below
is the reference study's preset for NIFTY (preset-matrix, spot about 22,810, ATM 22,800, gap 50, lot 65), written out by
hand: its legs are NOT read from the catalogue. No engine or matching code changed for these templates.
"""
from __future__ import annotations

import datetime
from decimal import Decimal
from pathlib import Path

import pytest
from ofo import wording as shared_wording
from ofo.engine.legs import Action, Instrument, Leg
from ofo.strategy.loader import DEFAULT_CATALOGUE_PATH, check_wording, load_templates
from ofo.strategy.matching import MatchResult, match, match_shape, shape_of
from ofo.strategy.model import TemplateError

CATALOGUE = load_templates()
BY_ID = {t.id: t for t in CATALOGUE}
NEAR = datetime.date(2026, 10, 27)
NEXT = datetime.date(2026, 11, 23)
SPOT, GAP, LOT = Decimal("22810"), Decimal("50"), 65
CATALOGUE_SIZE, NEW_SHAPES = 41, 20  # the 21 before plus the 20 of RD-090
B, S = Action.BUY, Action.SELL
CE, PE, FUT = Instrument.CE, Instrument.PE, Instrument.FUT


def leg(action: Action, instrument: Instrument, strike: str | None, lots: int = 1, expiry: datetime.date = NEAR) -> Leg:
    return Leg(action, instrument, None if strike is None else Decimal(strike), expiry, LOT * lots, Decimal("10"))


# template id -> the reference preset's legs (study preset-matrix, NIFTY block)
PRESETS: dict[str, list[Leg]] = {
    "buy_call": [leg(B, CE, "22800")],
    "sell_call": [leg(S, CE, "22800")],
    "buy_put": [leg(B, PE, "22800")],
    "sell_put_atm": [leg(S, PE, "22800")],
    "buy_future": [leg(B, FUT, None)],
    "sell_future": [leg(S, FUT, None)],
    "bull_condor": [leg(B, CE, "23050"), leg(S, CE, "23300"), leg(S, CE, "23550"), leg(B, CE, "23800")],
    "bear_condor": [leg(B, PE, "22600"), leg(S, PE, "22350"), leg(S, PE, "22100"), leg(B, PE, "21850")],
    "bear_butterfly": [leg(B, PE, "22600"), leg(S, PE, "22350", 2), leg(B, PE, "22100")],
    "long_calendar_puts": [leg(S, PE, "22600"), leg(B, PE, "22600", expiry=NEXT)],
    "range_forward": [leg(B, CE, "23050"), leg(S, PE, "22600")],
    "risk_reversal": [leg(S, CE, "23050"), leg(B, PE, "22600")],
    "batman": [leg(B, CE, "23000"), leg(S, CE, "23050", 2), leg(B, PE, "22600"), leg(S, PE, "22550", 2)],
    "double_plateau": [leg(B, CE, "23050"), leg(S, CE, "23300"), leg(S, CE, "23550"), leg(B, CE, "23800"),
                       leg(B, PE, "22600"), leg(S, PE, "22350"), leg(S, PE, "22100"), leg(B, PE, "21850")],
    "reverse_jade_lizard": [leg(S, CE, "23000"), leg(S, PE, "22400"), leg(B, PE, "22250")],
    "call_ratio_spread": [leg(B, CE, "22800"), leg(S, CE, "23000", 2)],
    "put_ratio_spread": [leg(B, PE, "22800"), leg(S, PE, "22600", 2)],
    "long_iron_butterfly": [leg(B, PE, "22800"), leg(S, PE, "22600"), leg(S, CE, "23000"), leg(B, CE, "22800")],
    "strap": [leg(B, CE, "22800", 2), leg(B, PE, "22800")],
    "strip": [leg(B, PE, "22800", 2), leg(B, CE, "22800")],
}
NEW_IDS = set(PRESETS)
# RD-095: template id -> the name users read (ids stay as they were)
RENAMES = {
    "short_straddle": "Short Straddle", "short_strangle": "Short Strangle", "long_straddle": "Long Straddle",
    "long_strangle": "Long Strangle", "iron_condor": "Short Iron Condor", "reverse_iron_condor": "Long Iron Condor",
    "calendar_spread": "Long Calendar with Calls", "butterfly_spread": "Bull Butterfly",
    "synthetic_long": "Long Synthetic Future", "synthetic_short": "Short Synthetic Future",
}


def test_ac3_twenty_new_shapes_are_data_only() -> None:
    """AC-3: the catalogue holds 41 templates: the 21 before plus the 20 reference shapes; all load as data."""
    assert len(CATALOGUE) == CATALOGUE_SIZE
    assert len(NEW_IDS) == NEW_SHAPES and set(BY_ID) >= NEW_IDS


@pytest.mark.parametrize("template_id", sorted(PRESETS))
def test_ac3_each_new_shape_matches_its_own_template_and_no_other(template_id: str) -> None:
    """AC-3: the reference preset's legs match exactly their own template (base quantity one lot), and fit no other."""
    result = match(PRESETS[template_id], spot=SPOT, strike_gap=GAP, templates=CATALOGUE)
    assert isinstance(result, MatchResult), template_id
    assert result.template.id == template_id
    assert result.base_quantity == LOT
    shape = shape_of(PRESETS[template_id], spot=SPOT, strike_gap=GAP)
    fitting = [t.id for t in CATALOGUE if isinstance(match_shape(shape, [t]), MatchResult)]
    assert fitting == [template_id]  # not two


def test_ac3_a_one_to_one_straddle_is_still_a_straddle_not_a_strap() -> None:
    """AC-3 (red case): 1 call + 1 put at the ATM strike is Long Straddle; the 2:1 mix is Strap; neither steals
    the other."""
    plain = match([leg(B, CE, "22800"), leg(B, PE, "22800")], spot=SPOT, strike_gap=GAP, templates=CATALOGUE)
    assert plain.label == "Long Straddle"
    assert match(PRESETS["strap"], spot=SPOT, strike_gap=GAP, templates=CATALOGUE).label == "Strap"


def test_ac3_a_put_sold_off_the_money_is_still_the_cash_secured_put() -> None:
    """AC-3: the overlap with the reference's Sell Put is resolved by keeping both:
    out of the money = cash_secured_put."""
    otm = match([leg(S, PE, "22700")], spot=SPOT, strike_gap=GAP, templates=CATALOGUE)
    assert otm.template.id == "cash_secured_put"
    assert match(PRESETS["sell_put_atm"], spot=SPOT, strike_gap=GAP, templates=CATALOGUE).template.id == "sell_put_atm"


def test_ac3_loader_still_refuses_a_duplicate_shape(tmp_path: Path) -> None:
    """AC-3: a template with the same legs as buy_call under another id and name is refused as a shared shape."""
    text = DEFAULT_CATALOGUE_PATH.read_text(encoding="utf-8")
    start = text.index("  - id: buy_call\n")
    block = text[start:text.index("  - id: sell_call\n")]
    clone = block.replace("id: buy_call", "id: buy_call_twin").replace('name: "Buy Call"', 'name: "Buy Call Twin"')
    path = tmp_path / "catalogue.yaml"
    path.write_text(text + "\n" + clone, encoding="utf-8")
    with pytest.raises(TemplateError, match="share a shape"):
        load_templates(path)


def test_ac3_renamed_templates_keep_their_ids_and_show_the_new_names() -> None:
    """AC-3 (RD-095): ten display names changed; every id is the one stored strategies and tests already use."""
    assert {tid: BY_ID[tid].name for tid in RENAMES} == RENAMES
    names = [t.name for t in CATALOGUE]
    assert len(set(names)) == len(names)


def test_ac3_new_names_and_descriptions_pass_the_adr003_wording_check() -> None:
    """AC-3 (ADR-003): every new and renamed name and description passes the loader's wording check and the
    shared one."""
    for template_id in NEW_IDS | set(RENAMES):
        template = BY_ID[template_id]
        check_wording(template)
        assert shared_wording.find_advice_wording(f"{template.name} {template.description}") == [], template_id


def test_ac3_wording_check_would_refuse_advice_in_a_new_shape(tmp_path: Path) -> None:
    """AC-3 (red case, ADR-003): the same check refuses a new shape described as the best choice."""
    text = DEFAULT_CATALOGUE_PATH.read_text(encoding="utf-8")
    bad = text.replace("description: Buy a single call, one expiry.", "description: The best call to buy, guaranteed.")
    path = tmp_path / "catalogue.yaml"
    path.write_text(bad, encoding="utf-8")
    with pytest.raises(TemplateError, match="banned wording"):
        load_templates(path)
