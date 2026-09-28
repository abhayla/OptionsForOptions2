"""Zerodha Client ID normalisation and validation for the qualifying list (REQ-020 AC-2, ADR-024).

ASSUMPTION (re-verify against a Zerodha source before launch): a Zerodha Client ID is 2 or 3 letters followed
by 3 to 6 digits, e.g. ``AB1234`` or ``ZXY12345``. No Zerodha document was checked when this pattern was
written; the spec (ADR-022, ADR-024) names the Client ID but never its format. If a real ID is rejected, widen
``CLIENT_ID_PATTERN`` here, in one place, and add that real ID to the tests.

Normalisation goes through ``untrusted_text.ascii_token``: refuse the RAW value unless it is plain ASCII, then trim
only ASCII spaces/tabs, then upper-case, then match the pattern. Any transformation before the ASCII check lets a
malformed value become a valid one: upper() folds 'ı'/'ß'/'ſ' into A-Z, and a bare strip() removes non-ASCII
whitespace such as NBSP. Anything that fails raises ``MalformedClientIdError``; nothing is silently repaired.
"""
from __future__ import annotations

import re

from ofo.admin import untrusted_text

CLIENT_ID_PATTERN = re.compile(r"[A-Z]{2,3}[0-9]{3,6}")
"""Assumed Zerodha Client ID shape: 2-3 letters then 3-6 digits (see module docstring)."""


class MalformedClientIdError(ValueError):
    """A value that is not a Zerodha Client ID under ``CLIENT_ID_PATTERN``."""


def normalise_client_id(raw: object) -> str:
    """Return the canonical (trimmed, upper-case) Client ID, or raise ``MalformedClientIdError``."""
    try:
        token = untrusted_text.ascii_token(raw, "Client ID")
    except ValueError as exc:
        raise MalformedClientIdError(str(exc)) from exc
    candidate = token.upper()
    if CLIENT_ID_PATTERN.fullmatch(candidate) is None:
        raise MalformedClientIdError(
            f"{token!r} is not a Client ID (expected 2-3 letters then 3-6 digits, e.g. AB1234)"
        )
    return candidate
