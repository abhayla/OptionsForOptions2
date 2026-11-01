"""REQ-167 AC-1, AC-2: the settings registry loader and value checks (``ofo.settings``), no database.

Spec basis: REQ-167 AC-1 (key, group, label, unit, type, range, default, what it changes); AC-2 refusal with the reason
("Enter 0.065 for 6.5%"); ADR-222 (1); ADR-008 (exact Decimal, never float).
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest
from ofo import settings
from ofo.settings import RegistryError, SettingRefused, parse_registry, validate

ROW = {"key": "pricing.risk_free_rate", "group": "Pricing", "label": "Risk-free interest rate", "unit": "fraction",
       "type": "decimal", "min": "0", "max": "0.5", "default": "0.065", "what_it_changes": "x", "source": "y"}


def _text(*rows) -> str:
    return json.dumps({"schema": 1, "settings": list(rows)})


def test_the_checked_in_registry_loads_with_the_rate_at_its_default():
    s = settings.registry()["pricing.risk_free_rate"]
    assert s.default == Decimal("0.065") and isinstance(s.default, Decimal)
    assert (s.group, s.unit, s.min, s.max) == ("Pricing", "fraction", Decimal("0"), Decimal("0.5"))
    assert settings.defaults()["pricing.risk_free_rate"] == Decimal("0.065")


def test_a_json_float_anywhere_is_refused():
    with pytest.raises(RegistryError, match="float"):
        parse_registry(_text(ROW).replace('"0.065"', "0.065"))


def test_a_duplicated_key_is_refused():
    with pytest.raises(RegistryError, match="duplicated"):
        parse_registry(_text(ROW, ROW))


@pytest.mark.parametrize("default", ["0.6", "-0.1"])
def test_a_default_outside_its_range_is_refused(default):
    with pytest.raises(RegistryError, match="outside"):
        parse_registry(_text({**ROW, "default": default}))


def test_min_above_max_and_unknown_unit_are_refused():
    with pytest.raises(RegistryError, match="outside"):
        parse_registry(_text({**ROW, "min": "0.6"}))
    with pytest.raises(RegistryError, match="unknown unit"):
        parse_registry(_text({**ROW, "unit": "bananas"}))


def test_a_missing_text_field_is_refused():
    with pytest.raises(RegistryError, match="required text"):
        parse_registry(_text({**ROW, "what_it_changes": " "}))


@pytest.mark.parametrize(("raw", "code"), [
    ("51", "setting_out_of_range"), ("-0.01", "setting_out_of_range"), ("60", "setting_out_of_range"),
    ("6.5", "setting_fraction_unit"), ("NaN", "setting_not_a_number"), ("Infinity", "setting_not_a_number"),
    ("", "setting_not_a_number"), (0.07, "setting_not_a_number"), (True, "setting_not_a_number"),
])
def test_validate_refuses_with_a_code(raw, code):
    with pytest.raises(SettingRefused) as info:
        validate("pricing.risk_free_rate", raw)
    assert info.value.code == code


def test_a_value_above_max_whose_hundredth_fits_gets_the_fraction_hint():
    """0.9 is above 0.5; read as 0.9% it is 0.009, so the hint names that (the unit, not only the range, is wrong)."""
    with pytest.raises(SettingRefused) as info:
        validate("pricing.risk_free_rate", "0.9")
    assert info.value.code == "setting_fraction_unit" and "enter 0.009 for 0.9%" in info.value.reason


def test_a_percent_typed_for_a_fraction_names_the_fraction():
    with pytest.raises(SettingRefused) as info:
        validate("pricing.risk_free_rate", "6.5")
    assert "enter 0.065 for 6.5%" in info.value.reason


def test_the_bounds_are_accepted_exactly():
    assert validate("pricing.risk_free_rate", "0") == Decimal("0")
    assert validate("pricing.risk_free_rate", " 0.5 ") == Decimal("0.5")


def test_value_of_refuses_an_unknown_key_and_a_float():
    with pytest.raises(KeyError):
        settings.value_of({}, "pricing.no_such")
    with pytest.raises(TypeError):
        settings.value_of({"pricing.risk_free_rate": 0.065}, "pricing.risk_free_rate")


def test_a_repeated_field_in_one_object_is_refused():
    text = '{"schema": 1, "settings": [' + json.dumps(ROW)[:-1] + ', "default": "0.07"}]}'
    with pytest.raises(RegistryError, match="repeats the field 'default'"):
        parse_registry(text)


def test_a_repeated_field_at_the_file_level_is_refused():
    with pytest.raises(RegistryError, match="repeats the field 'schema'"):
        parse_registry('{"schema": 1, "schema": 1, "settings": []}')


def test_a_misspelt_entry_field_is_refused():
    row = {k: v for k, v in ROW.items() if k != "default"} | {"defualt": "0.065"}
    with pytest.raises(RegistryError, match="unknown field"):
        parse_registry(_text(row))


def test_an_extra_field_beside_a_good_entry_and_at_the_file_level_is_refused():
    with pytest.raises(RegistryError, match="unknown field"):
        parse_registry(_text(ROW | {"note": "x"}))
    with pytest.raises(RegistryError, match="unknown field"):
        parse_registry(json.dumps({"schema": 1, "settings": [ROW], "extra": 1}))
