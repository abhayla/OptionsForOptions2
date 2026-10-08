"""Zerodha Client ID normalisation and validation for the qualifying list (REQ-020 AC-2, ADR-024).

OWNER DECISION Q234 (2026-09-29, REQ-020): a Zerodha Client ID is 6 characters, 2-3 letters followed by digits
(owner, as the Zerodha AP: "2-3 letter at the beginning + 3-5 digits. Total length 6"). With a total of 6 this
admits exactly two shapes: 2 letters + 4 digits (e.g. ``AB1234``) or 3 letters + 3 digits (e.g. ``ABC123``).
Letters are case-insensitive on input and stored upper-case. This replaces the unverified W-010 guess
(2-3 letters + 3-6 digits). If a real ID is ever rejected, change ``CLIENT_ID_PATTERN`` here, in one place, and
record it as a new owner decision.

Normalisation goes through ``untrusted_text.ascii_token``: refuse the RAW value unless it is plain ASCII, then trim
only ASCII spaces/tabs, then upper-case, then match the pattern. Any transformation before the ASCII check lets a
malformed value become a valid one: upper() folds 'ı'/'ß'/'ſ' into A-Z, and a bare strip() removes non-ASCII
whitespace such as NBSP. Anything that fails raises ``MalformedClientIdError``; nothing is silently repaired.
"""
from __future__ import annotations
from ofo.errors.explanations import render_explanation

import re

from ofo.admin import untrusted_text

CLIENT_ID_PATTERN = re.compile(r"(?:[A-Z]{2}[0-9]{4}|[A-Z]{3}[0-9]{3})")
"""Zerodha Client ID: 6 characters, 2 letters + 4 digits or 3 letters + 3 digits (Q234, see module docstring)."""


class MalformedClientIdError(ValueError):
    """A value that is not a Zerodha Client ID under ``CLIENT_ID_PATTERN``."""


def normalise_client_id(raw: object) -> str:
    """Return the canonical (trimmed, upper-case) Client ID, or raise ``MalformedClientIdError``."""
    try:
        token = untrusted_text.ascii_token(raw, render_explanation("label_client_id"))
    except ValueError as exc:
        raise MalformedClientIdError(str(exc)) from exc
    candidate = token.upper()
    if CLIENT_ID_PATTERN.fullmatch(candidate) is None:
        raise MalformedClientIdError(render_explanation("client_id_not_valid", value=token))
    return candidate
