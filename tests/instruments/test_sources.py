"""AC-5 tests: every Zerodha rule encoded in code cites a source URL and a capture date."""
from __future__ import annotations

import pytest

from ofo.instruments.sources import SOURCES, SourceRef, get, validate_source


def test_every_source_entry_has_url_and_date() -> None:
    """AC-5: any Zerodha rule encoded in code cites a current Zerodha source and date."""
    assert SOURCES, "the source registry must not be empty"
    for rule_name, ref in SOURCES.items():
        validate_source(ref)  # our own registry validation, not just a stdlib call inline
        assert ref.rule == rule_name, f"{rule_name} key/rule mismatch: {ref.rule}"


def test_invalid_captured_on_date_is_rejected() -> None:
    """AC-5 negative case: a captured_on that is not a real calendar date must fail OUR OWN
    registry validation (`validate_source`), not just the stdlib's `date.fromisoformat` in the
    test itself — a regex-based check would wrongly accept "2026-99-99"."""
    bad_ref = SourceRef(rule="bad_rule", url="https://example.com", captured_on="2026-99-99")
    with pytest.raises(ValueError):
        validate_source(bad_ref)


def test_invalid_url_is_rejected_by_registry_validation() -> None:
    """AC-5 negative case: a non-https or empty url must fail our own `validate_source`."""
    bad_ref = SourceRef(rule="bad_rule", url="http://not-https.example.com", captured_on="2026-09-29")
    with pytest.raises(ValueError):
        validate_source(bad_ref)


@pytest.mark.parametrize("url", ["https://", "https:///instruments", "https://:443/x", "https://?a=b"])
def test_url_without_a_host_is_rejected(url: str) -> None:
    """AC-5 negative case (issue #10 item 1): a bare `https://` has the scheme but no host and must be refused."""
    with pytest.raises(ValueError, match="host"):
        validate_source(SourceRef(rule="bad_rule", url=url, captured_on="2026-09-29"))


def test_real_instrument_list_url_still_passes_validation() -> None:
    """AC-5: the real Zerodha URL used by the downloader still validates after the host check."""
    validate_source(SourceRef(rule="r", url="https://api.kite.trade/instruments", captured_on="2026-09-29"))


def test_get_returns_registered_source() -> None:
    """AC-5: the instrument-list source used by the parser/catalogue is registered and lookup-able."""
    ref = get("instrument_list_url")
    assert ref.url == "https://api.kite.trade/instruments"
    assert ref.captured_on == "2026-09-29"


def test_get_raises_for_unregistered_rule() -> None:
    """AC-5 negative case: an unregistered rule must fail closed, not silently return nothing."""
    with pytest.raises(KeyError):
        get("some_rule_nobody_registered")
