"""Zerodha Client ID normalisation and validation for the qualifying list (REQ-020 AC-2, ADR-024).

ASSUMPTION (re-verify against a Zerodha source before launch): a Zerodha Client ID is 2 or 3 letters followed
by 3 to 6 digits, e.g. ``AB1234`` or ``ZXY12345``. No Zerodha document was checked when this pattern was
written; the spec (ADR-022, ADR-024) names the Client ID but never its format. If a real ID is rejected, widen
``CLIENT_ID_PATTERN`` here, in one place, and add that real ID to the tests.

Normalisation is: strip surrounding whitespace, then upper-case. Anything that does not then match the pattern
is malformed and raises ``MalformedClientIdError``; nothing is silently repaired beyond that.
"""
from __future__ import annotations

import re

CLIENT_ID_PATTERN = re.compile(r"[A-Z]{2,3}[0-9]{3,6}")
"""Assumed Zerodha Client ID shape: 2-3 letters then 3-6 digits (see module docstring)."""


class MalformedClientIdError(ValueError):
    """A value that is not a Zerodha Client ID under ``CLIENT_ID_PATTERN``."""


def normalise_client_id(raw: object) -> str:
    """Return the canonical (trimmed, upper-case) Client ID, or raise ``MalformedClientIdError``."""
    if not isinstance(raw, str):
        raise MalformedClientIdError(f"Client ID must be text, got {type(raw).__name__}")
    candidate = raw.strip().upper()
    if not candidate:
        raise MalformedClientIdError("Client ID is empty")
    if CLIENT_ID_PATTERN.fullmatch(candidate) is None:
        raise MalformedClientIdError(
            f"{raw.strip()!r} is not a Client ID (expected 2-3 letters then 3-6 digits, e.g. AB1234)"
        )
    return candidate
