"""W-061 follow-ups (issues #138 gaps 2-3 / #167 items 1, 2, 4): the domain refuses, first and with its own fixed
refusal, every value the database validator would refuse, so a save never fails late with a bare 23514.

Spec basis: REQ-038 AC-5 ("live prices are never saved inside the strategy."); ADR-069 ("short identifiers or numbers
only - letters, digits, underscore, hyphen and dot, at most 64 characters"); ADR-008 (decimals are exact).

Expected bounds are the database validator's (migration 0008), read here as SOURCE TEXT (the migration needs alembic):
a bound changed on one side only turns the pinning test red. Standard library only.
"""
from __future__ import annotations

import ast
import datetime
import re
from decimal import Decimal
from pathlib import Path

import pytest

from ofo.engine.legs import Action, Instrument
from ofo.strategy import definition as definition_module
from ofo.strategy import settings_value
from ofo.strategy import stored_form as sf
from ofo.strategy.definition import DefinitionError, DefinitionLeg, StrategyDefinition, render_change_items

EXPIRY = datetime.date(2026, 10, 13)
VERSIONS = Path(__file__).resolve().parents[2] / "backend" / "ofo_app" / "alembic" / "versions"
MIGRATION_0008 = VERSIONS / "0008_strategy_store.py"


def _constants(path: Path) -> dict:
    out = {}
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                out[node.targets[0].id] = ast.literal_eval(node.value)
            except ValueError:
                pass
    return out


def _leg(strike: Decimal | None, instrument: Instrument = Instrument.CE, quantity: int = 65) -> DefinitionLeg:
    return DefinitionLeg(Action.SELL, instrument, strike, EXPIRY, quantity)


def _resolve(contract_id):
    return sf.CatalogueTerms("NIFTY", Instrument.CE, Decimal("22800"), EXPIRY, 65, True)


# ---- (a) a strike or contract id the database refuses is refused by the domain, with the domain's refusal ----

@pytest.mark.parametrize("strike", [Decimal("1000000000000000000"), Decimal("1E+2"), Decimal("1E+18"),
                                    Decimal("99999999999999999999.50")])
def test_a_strike_the_database_text_rule_refuses_is_refused_by_the_domain(strike):
    with pytest.raises(DefinitionError):
        _leg(strike)


@pytest.mark.parametrize("strike", [Decimal("999999999999999999"), Decimal("99999999999999999.99"),
                                    Decimal("22800"), Decimal("22800.50"), Decimal("0.05"), Decimal("22800.500")])
def test_a_strike_inside_the_bound_is_accepted(strike):
    assert _leg(strike).strike == strike


@pytest.mark.parametrize("contract_id, accepted", [(1, True), (10**18 - 1, True), (10**18, False), (10**19, False)])
def test_contract_id_bound_is_the_databases_in_every_door(contract_id, accepted):
    definition = StrategyDefinition("NIFTY", (_leg(Decimal("22800")),))
    doors = [lambda: sf.SavedDefinition(definition, (contract_id,)),
             lambda: sf.build_from_catalogue("NIFTY", [sf.LegChoice(contract_id, Action.SELL, 65)], _resolve),
             lambda: sf.from_document({**sf.to_document(sf.SavedDefinition(definition, (1,))),
                                       "legs": [{"contract_id": contract_id, "action": "SELL", "instrument": "CE",
                                                 "strike": "22800", "expiry": "2026-10-13", "quantity": 65}]},
                                      _resolve)]
    for door in doors:
        if accepted:
            door()
        else:
            with pytest.raises(sf.StoredFormError) as err:
                door()
            assert err.value.code == sf.MISSING_CONTRACT_ID


# ---- (#167 item 4) render_change_items holds the same 1..100 bound as the write path ----

@pytest.mark.parametrize("count, accepted", [(0, False), (1, True), (100, True), (101, False)])
def test_render_change_items_enforces_the_stored_item_bounds(count, accepted):
    items = [{"kind": "legs_reordered"}] * count
    if accepted:
        assert len(render_change_items(items)) == count
    else:
        with pytest.raises(DefinitionError):
            render_change_items(items)


# ---- one source: the domain constants equal the migration's ----

def test_the_domain_bounds_equal_the_migrations():
    const = _constants(MIGRATION_0008)
    assert definition_module.MAX_UNITS == const["MAX_UNITS"]
    assert definition_module.MAX_LEGS == const["MAX_LEGS"]
    assert definition_module.MAX_CHANGE_ITEMS == const["MAX_CHANGE_ITEMS"]
    assert definition_module.STRIKE_PATTERN == const["STRIKE_REGEX"].strip("^$")
    assert settings_value.IDENTIFIER_PATTERN == const["IDENTIFIER_REGEX"].strip("^$")
    assert settings_value.LIMIT_PATTERN == const["LIMIT_REGEX"].strip("^$")
    # the contract id regex in the migration's leg validator is ^[1-9][0-9]{0,17}$: ids 1 .. 10^18 - 1
    assert sf.MAX_CONTRACT_ID == 10**18 - 1
    assert re.search(r"\^\[1-9\]\[0-9\]\{\{0,17\}\}\$", MIGRATION_0008.read_text(encoding="utf-8"))
