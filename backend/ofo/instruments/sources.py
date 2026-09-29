"""Registry of Zerodha rules encoded in code: every entry cites a source URL and a date.

REQ-053 AC-5: any Zerodha rule encoded in code (market-order limits, SL-M limits on index options,
freak-trade protection, OI and strike restrictions, basket execution, the instrument-list URL
itself) cites a current Zerodha source and date; a rule is never hard-coded without one. A test in
`tests/instruments/test_sources.py` asserts every registry entry carries both.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from urllib.parse import urlsplit


@dataclass(frozen=True)
class SourceRef:
    """One cited source for a Zerodha rule encoded in code."""

    rule: str
    url: str
    captured_on: str  # ISO date string, e.g. "2026-09-29" — the date the rule was verified.
    note: str = ""


def validate_source(ref: SourceRef) -> None:
    """Validate one `SourceRef`: a real https URL (with a host) and a real ISO calendar date.

    Raises `ValueError` (fail closed) if either is missing or malformed — e.g. `"2026-99-99"`
    is shaped like a date but is not a real calendar date, and must be rejected, not accepted by
    a regex that only checks digit positions.
    """
    if not ref.url or not ref.url.startswith("https://") or not urlsplit(ref.url).hostname:
        raise ValueError(f"{ref.rule}: source url must be a real https url with a host, got {ref.url!r}")
    if not ref.captured_on:
        raise ValueError(f"{ref.rule}: captured_on must not be empty")
    try:
        date.fromisoformat(ref.captured_on)
    except ValueError as exc:
        raise ValueError(
            f"{ref.rule}: captured_on is not a real ISO calendar date: {ref.captured_on!r}"
        ) from exc


# Every rule this codebase encodes from Zerodha's public documentation/data. Add an entry here
# BEFORE encoding any new Zerodha-sourced rule (AC-5) — never hard-code one without a row.
SOURCES: dict[str, SourceRef] = {
    "instrument_list_url": SourceRef(
        rule="instrument_list_url",
        url="https://api.kite.trade/instruments",
        captured_on="2026-09-29",
        note=(
            "Kite Connect's public instrument dump (no login required); the source of every "
            "contract, lot size, tick size and strike in the catalogue."
        ),
    ),
}


def get(rule: str) -> SourceRef:
    """Look up a cited source by rule name.

    Raises `KeyError` if the rule is not registered, or `ValueError` (via `validate_source`) if
    the registered entry itself is malformed — a caller never gets back a bad source silently.
    """
    try:
        ref = SOURCES[rule]
    except KeyError as exc:
        raise KeyError(
            f"no cited source for rule {rule!r} — register one in ofo.instruments.sources "
            f"before encoding this Zerodha rule (REQ-053 AC-5)"
        ) from exc
    validate_source(ref)
    return ref
