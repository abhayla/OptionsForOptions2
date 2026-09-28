"""AC-5 tests: every Zerodha rule encoded in code cites a source URL and a capture date."""
from __future__ import annotations

import re

import pytest

from ofo.instruments.sources import SOURCES, get


def test_every_source_entry_has_url_and_date() -> None:
    """AC-5: any Zerodha rule encoded in code cites a current Zerodha source and date."""
    assert SOURCES, "the source registry must not be empty"
    date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    for rule_name, ref in SOURCES.items():
        assert ref.url, f"{rule_name} has no source url"
        assert ref.url.startswith("https://"), f"{rule_name} url must be a real https source"
        assert ref.captured_on, f"{rule_name} has no captured_on date"
        assert date_pattern.match(ref.captured_on), f"{rule_name} captured_on is not an ISO date"
        assert ref.rule == rule_name, f"{rule_name} key/rule mismatch: {ref.rule}"


def test_get_returns_registered_source() -> None:
    """AC-5: the instrument-list source used by the parser/catalogue is registered and lookup-able."""
    ref = get("instrument_list_url")
    assert ref.url == "https://api.kite.trade/instruments"
    assert ref.captured_on == "2026-09-29"


def test_get_raises_for_unregistered_rule() -> None:
    """AC-5 negative case: an unregistered rule must fail closed, not silently return nothing."""
    with pytest.raises(KeyError):
        get("some_rule_nobody_registered")
