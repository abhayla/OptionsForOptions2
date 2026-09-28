"""AC-5 tests: every Zerodha rule encoded in code cites a source URL and a capture date."""
from __future__ import annotations

from datetime import date

import pytest

from ofo.instruments.sources import SOURCES, SourceRef, get


def test_every_source_entry_has_url_and_date() -> None:
    """AC-5: any Zerodha rule encoded in code cites a current Zerodha source and date."""
    assert SOURCES, "the source registry must not be empty"
    for rule_name, ref in SOURCES.items():
        assert ref.url, f"{rule_name} has no source url"
        assert ref.url.startswith("https://"), f"{rule_name} url must be a real https source"
        assert ref.captured_on, f"{rule_name} has no captured_on date"
        # A real ISO date, not just a string shaped like one: date.fromisoformat rejects
        # out-of-range values like "2026-99-99" that a regex ^\d{4}-\d{2}-\d{2}$ would accept.
        date.fromisoformat(ref.captured_on)
        assert ref.rule == rule_name, f"{rule_name} key/rule mismatch: {ref.rule}"


def test_invalid_captured_on_date_is_rejected() -> None:
    """AC-5 negative case: a captured_on that is not a real calendar date must fail validation."""
    bad_ref = SourceRef(rule="bad_rule", url="https://example.com", captured_on="2026-99-99")
    with pytest.raises(ValueError):
        date.fromisoformat(bad_ref.captured_on)


def test_get_returns_registered_source() -> None:
    """AC-5: the instrument-list source used by the parser/catalogue is registered and lookup-able."""
    ref = get("instrument_list_url")
    assert ref.url == "https://api.kite.trade/instruments"
    assert ref.captured_on == "2026-09-29"


def test_get_raises_for_unregistered_rule() -> None:
    """AC-5 negative case: an unregistered rule must fail closed, not silently return nothing."""
    with pytest.raises(KeyError):
        get("some_rule_nobody_registered")
