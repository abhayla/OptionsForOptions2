"""GC-SET step 5a (REQ-167 AC-2, AC-5): a "time" setting is an IST time of day stored as the whole number HHMM.

Spec basis: REQ-167 AC-5 "Exchange and broker facts (... paper settlement window, ... contract-list publish time), each
with its source in the note"; AC-2 "a value outside the allowed range or of the wrong unit is refused with the reason".
Threat model: a malformed time is refused at save and never turned into a time by the reader (fail closed).
"""

from __future__ import annotations

import datetime
import json
from decimal import Decimal

import pytest
from ofo import settings
from ofo.settings import RegistryError, SettingRefused, calc, parse_registry, time_of, validate

TIME_ROW = {"key": "facts.x", "group": "Exchange and broker facts", "label": "X", "unit": "time", "type": "integer",
            "min": "0", "max": "2359", "default": "1545", "what_it_changes": "x", "source": "y"}


def _text(**over: str) -> str:
    return json.dumps({"schema": 1, "settings": [{**TIME_ROW, **over}]})


@pytest.mark.parametrize(("raw", "expected"), [("1545", datetime.time(15, 45)), ("0", datetime.time(0, 0)),
                                               ("600", datetime.time(6, 0)), ("2359", datetime.time(23, 59))])
def test_a_valid_hhmm_is_accepted_and_read_as_that_time(raw, expected):
    s = parse_registry(_text())["facts.x"]
    assert time_of(settings.check_value(s, Decimal(raw))) == expected


@pytest.mark.parametrize(("raw", "code"), [("1575", "setting_not_a_time"), ("1560", "setting_not_a_time"),
                                           ("99", "setting_not_a_time"), ("2400", "setting_out_of_range"),
                                           ("1545.5", "setting_not_whole"), ("-1", "setting_out_of_range")])
def test_a_value_that_is_not_a_time_of_day_is_refused_with_the_reason(raw, code):
    s = parse_registry(_text())["facts.x"]
    with pytest.raises(SettingRefused) as err:
        settings.check_value(s, Decimal(raw))
    assert err.value.code == code


def test_the_not_a_time_reason_names_the_format_and_an_example():
    with pytest.raises(SettingRefused, match="HHMM, for example 1545"):
        validate(calc.PAPER_SETTLE_FROM, "1575")


def test_a_typed_clock_text_is_refused_not_coerced():
    with pytest.raises(SettingRefused, match="number"):
        validate(calc.PAPER_SETTLE_FROM, "15:45")


@pytest.mark.parametrize("bad", [Decimal("1575"), Decimal("1545.5"), Decimal("NaN"), 1545])
def test_time_of_refuses_a_malformed_value_rather_than_guessing(bad):
    with pytest.raises(ValueError, match="HHMM"):
        time_of(bad)


def test_a_registry_time_default_that_is_not_a_time_refuses_the_whole_file():
    with pytest.raises(RegistryError, match="default"):
        parse_registry(_text(default="1575"))
    with pytest.raises(RegistryError, match="HHMM"):
        parse_registry(_text(type="decimal"))


def test_each_time_key_default_is_exactly_the_old_literal():
    """One test per key (standing item): each default equals the literal it replaced."""
    values = settings.defaults()
    assert calc.paper_settle_from(values) == datetime.time(15, 45)  # was paper_settlement.SETTLE_FROM
    assert calc.paper_retry_until(values) == datetime.time(18, 0)  # was paper_settlement.RETRY_UNTIL


def test_every_time_setting_is_an_exchange_or_broker_fact_naming_its_source():
    times = [s for s in settings.registry().values() if s.unit == "time"]
    assert times
    assert all(s.group == "Exchange and broker facts" and s.source.strip() for s in times)
