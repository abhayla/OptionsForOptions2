"""W-061 round 2 (issue #165, defect 1): ADR-069's value type is enforced on EVERY path that builds or loads a definition.

Spec basis: ADR-069 ("short identifiers or numbers only - letters, digits, underscore, hyphen and dot, at most 64
characters"; a longer or free-text value "is refused on save with the fixed input error (HTTP 422) and is never echoed
back."); ADR-064 ("Any other name is refused on every path that builds or loads a definition"); REQ-038 AC-5.

Expected values come from the ADR text, never from running the code. Standard library only (tests/ never imports app
packages); the migration's copy of the rule is read as source text, not imported (it needs alembic).
"""
from __future__ import annotations

import ast
import datetime
import re
from decimal import Decimal
from pathlib import Path

import pytest

from ofo.engine.legs import Action, Instrument
from ofo.strategy import settings_value
from ofo.strategy import stored_form as sf
from ofo.strategy.definition import (DefinitionLeg, PREFERENCE_NAMES, RISK_LIMIT_NAMES, StrategyDefinition,
                                     ValueRefusedError)

SENTENCE = "LTP is 22950.35 buy now"
EXPIRY = datetime.date(2026, 10, 13)
LEG = DefinitionLeg(Action.SELL, Instrument.CE, Decimal("22800"), EXPIRY, 65)
MIGRATION = Path(__file__).resolve().parents[2] / "backend" / "ofo_app" / "alembic" / "versions" / "0008_strategy_store.py"

BAD_IDENTIFIERS = [SENTENCE, "", " ", "a b", " a", "a ", "a\n", "a\tb", "x" * 65, "a/b", "a,b", "a;b", "a:b", "café",
                   "١٢", "a+b", "1E+3 "]
GOOD_IDENTIFIERS = ["neutral", "range-bound", "rules_set.v2", "22950.35", "A", "x" * 64, "0", "a-b_c.d"]


def _resolve(contract_id):
    return sf.CatalogueTerms("NIFTY", Instrument.CE, Decimal("22800"), EXPIRY, 65, True) if contract_id == 101 else None


def _build(**fields):
    return sf.build_from_catalogue("NIFTY", [sf.LegChoice(101, Action.SELL, 65)], _resolve, **fields)


def _document(**fields) -> dict:
    doc = sf.to_document(_build())
    doc.update(fields)
    return doc


def _refused(call):
    with pytest.raises((ValueRefusedError, sf.StoredFormError)) as err:
        call()
    return err.value


# ---- the type itself ----

@pytest.mark.parametrize("value", BAD_IDENTIFIERS)
def test_adr069_identifier_refuses_free_text_and_never_echoes_it(value):
    with pytest.raises(settings_value.SettingsValueError) as err:
        settings_value.identifier(value, "preference 'objective'")
    assert value.strip() == "" or value not in str(err.value)


@pytest.mark.parametrize("value", [5, 5.5, None, True, Decimal("5"), b"neutral", ["a"], {"a": "b"}])
def test_adr069_identifier_takes_only_a_str(value):
    with pytest.raises(settings_value.SettingsValueError):
        settings_value.identifier(value, "preference 'objective'")


@pytest.mark.parametrize("value", GOOD_IDENTIFIERS)
def test_adr069_identifier_accepts_the_allowed_characters_up_to_64(value):
    assert settings_value.identifier(value, "k") == value


@pytest.mark.parametrize("value", [Decimal("-1"), Decimal("1E+3"), Decimal("NaN"), Decimal("Infinity"), 5.5, 5, "5000",
                                   None, True, Decimal("1") * Decimal("10") ** 40])
def test_adr069_limit_takes_only_a_finite_plain_digit_decimal(value):
    with pytest.raises(settings_value.SettingsValueError):
        settings_value.limit(value, "risk limit 'max_loss'")


@pytest.mark.parametrize("value", [Decimal("0"), Decimal("9000.50"), Decimal("250000"), Decimal("0.0001")])
def test_adr069_limit_accepts_plain_digit_decimals(value):
    assert settings_value.limit(value, "k") == value


# ---- every path that builds or loads a definition ----

PATHS = {
    "preference": lambda v: {"preferences": {"objective": v}},
    "rules_ref": lambda v: {"rules_ref": v},
}


@pytest.mark.parametrize("value", [SENTENCE, "a b", "x" * 65, ""])
@pytest.mark.parametrize("kind", sorted(PATHS))
def test_adr069_build_from_catalogue_refuses_a_sentence(kind, value):
    err = _refused(lambda: _build(**PATHS[kind](value)))
    assert isinstance(err, sf.StoredFormError) and err.code == sf.VALUE_NOT_ALLOWED
    assert SENTENCE not in str(err) and "22950" not in str(err)


@pytest.mark.parametrize("value", [SENTENCE, "a b", "x" * 65, ""])
@pytest.mark.parametrize("kind", sorted(PATHS))
def test_adr069_a_definition_built_directly_refuses_a_sentence(kind, value):
    err = _refused(lambda: StrategyDefinition("NIFTY", (LEG,), **PATHS[kind](value)))
    assert isinstance(err, ValueRefusedError)
    assert SENTENCE not in str(err)


@pytest.mark.parametrize("value", [Decimal("-1"), Decimal("1E+3"), Decimal("NaN"), 5.5, "5000 rupees"])
def test_adr069_a_risk_limit_outside_the_number_form_is_refused_on_every_door(value):
    assert isinstance(_refused(lambda: StrategyDefinition("NIFTY", (LEG,), risk_limits={"max_loss": value})),
                      ValueRefusedError)
    assert _refused(lambda: _build(risk_limits={"max_loss": value})).code in (sf.VALUE_NOT_ALLOWED, sf.INVALID_DEFINITION)


@pytest.mark.parametrize("fields", [{"preferences": {"objective": SENTENCE}}, {"rules_ref": SENTENCE}],
                         ids=["preference", "rules_ref"])
def test_adr069_loading_a_stored_sentence_is_refused(fields):
    """A row written before the rule (or by hand) is refused on load, never returned."""
    err = _refused(lambda: sf.from_document(_document(**fields), _resolve))
    assert err.code == sf.VALUE_NOT_ALLOWED and SENTENCE not in str(err)


def test_adr069_loading_a_stored_risk_limit_with_an_exponent_is_refused():
    err = _refused(lambda: sf.from_document(_document(risk_limits={"max_loss": "1E+3"}), _resolve))
    assert err.code == sf.VALUE_NOT_ALLOWED


def test_adr069_the_allowed_values_round_trip_exactly():
    saved = _build(rules_ref="rules-set_1.v2", risk_limits={"max_loss": Decimal("9000.50")},
                   preferences={"objective": "income", "market_view": "range-bound"})
    back = sf.loads(sf.dumps(saved), _resolve)
    assert back == saved and str(dict(back.definition.risk_limits)["max_loss"]) == "9000.50"


@pytest.mark.parametrize("call", [
    lambda: sf.check_setting_values(preferences={"objective": SENTENCE}),
    lambda: sf.check_setting_values(rules_ref=SENTENCE),
    lambda: sf.limit_from_text(SENTENCE, "risk_limit"),
    lambda: sf.limit_from_text("1E+3", "risk_limit"),
    lambda: sf.limit_from_text("-5", "risk_limit"),
])
def test_adr069_the_request_helpers_use_the_same_type_and_refuse_before_any_query(call):
    err = _refused(call)
    assert err.code == sf.VALUE_NOT_ALLOWED and SENTENCE not in str(err)


def test_adr069_the_request_helpers_accept_what_the_type_accepts():
    sf.check_setting_values(rules_ref="rules-1", preferences={"objective": "income"})
    assert sf.limit_from_text("9000.50", "risk_limit") == Decimal("9000.50")


# ---- the database CHECK is the same rule (migration 0008 copies the patterns; pinned equal here) ----

def _migration_constants() -> dict:
    out = {}
    for node in ast.parse(MIGRATION.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                out[node.targets[0].id] = ast.literal_eval(node.value)
            except ValueError:
                pass
    return out


def test_the_migration_check_uses_the_domain_patterns_and_name_lists():
    const = _migration_constants()
    assert const["IDENTIFIER_REGEX"] == "^" + settings_value.IDENTIFIER_PATTERN + "$"
    assert const["LIMIT_REGEX"] == "^" + settings_value.LIMIT_PATTERN + "$"
    assert set(const["DOCUMENT_KEYS"]) == sf.DOCUMENT_KEYS and set(const["LEG_KEYS"]) == sf.LEG_KEYS
    assert set(const["RISK_LIMIT_NAMES"]) == RISK_LIMIT_NAMES and set(const["PREFERENCE_NAMES"]) == PREFERENCE_NAMES


@pytest.mark.parametrize("value", BAD_IDENTIFIERS + GOOD_IDENTIFIERS)
def test_the_migration_identifier_regex_agrees_with_the_domain_on_every_sample(value):
    """PostgreSQL's regex and Python's differ in detail (``$`` and a trailing newline); the shared samples must agree
    under Python's ``fullmatch`` of the domain pattern and a ``re.search`` of the migration's anchored text, with the
    newline case refused by both."""
    migration = re.compile(_migration_constants()["IDENTIFIER_REGEX"].replace("$", r"\Z"))
    assert bool(migration.search(value)) == (re.fullmatch(settings_value.IDENTIFIER_PATTERN, value) is not None)

