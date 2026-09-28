"""Registry of Zerodha rules encoded in code: every entry cites a source URL and a date.

REQ-053 AC-5: any Zerodha rule encoded in code (market-order limits, SL-M limits on index options,
freak-trade protection, OI and strike restrictions, basket execution, the instrument-list URL
itself) cites a current Zerodha source and date; a rule is never hard-coded without one. A test in
`tests/instruments/test_sources.py` asserts every registry entry carries both.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceRef:
    """One cited source for a Zerodha rule encoded in code."""

    rule: str
    url: str
    captured_on: str  # ISO date string, e.g. "2026-09-29" — the date the rule was verified.
    note: str = ""


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
    """Look up a cited source by rule name. Raises `KeyError` if the rule is not registered."""
    try:
        return SOURCES[rule]
    except KeyError as exc:
        raise KeyError(
            f"no cited source for rule {rule!r} — register one in ofo.instruments.sources "
            f"before encoding this Zerodha rule (REQ-053 AC-5)"
        ) from exc
