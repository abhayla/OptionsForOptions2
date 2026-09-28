"""Zerodha Client ID normalisation and validation for the qualifying list (REQ-020 AC-2, ADR-024).

ASSUMPTION (re-verify against a Zerodha source before launch): a Zerodha Client ID is 2 or 3 letters followed
by 3 to 6 digits, e.g. ``AB1234`` or ``ZXY12345``. No Zerodha document was checked when this pattern was
written; the spec (ADR-022, ADR-024) names the Client ID but never its format. If a real ID is rejected, widen
``CLIENT_ID_PATTERN`` here, in one place, and add that real ID to the tests.

Normalisation is: strip surrounding whitespace, refuse anything that is not plain ASCII, then upper-case, then
match the pattern. The ASCII check comes BEFORE upper() because upper() folds some non-ASCII letters into A-Z
(dotless 'ı' -> 'I', 'ß' -> 'SS', long 'ſ' -> 'S'), which would turn a malformed value into a different, valid-looking
ID. Anything that fails is malformed and raises ``MalformedClientIdError``; nothing is silently repaired.
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
    stripped = raw.strip()
    if not stripped:
        raise MalformedClientIdError("Client ID is empty")
    if not stripped.isascii():
        raise MalformedClientIdError(f"{stripped!r} is not a Client ID (contains non-ASCII characters)")
    candidate = stripped.upper()
    if CLIENT_ID_PATTERN.fullmatch(candidate) is None:
        raise MalformedClientIdError(
            f"{raw.strip()!r} is not a Client ID (expected 2-3 letters then 3-6 digits, e.g. AB1234)"
        )
    return candidate
