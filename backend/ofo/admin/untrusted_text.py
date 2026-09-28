"""The one gate for untrusted text that feeds a strict (ASCII) character-set check.

Class guarded (W-010 rounds 2-3): ANY transformation of untrusted text before it is checked against a strict
character set lets a malformed value become a valid one. ``str.upper()`` folds 'ı'/'ß'/'ſ' into A-Z, and
``str.strip()`` with no argument removes about 20 non-ASCII whitespace characters (NBSP, ideographic space, NEL,
line/paragraph separators, ...), so '\\xa0AB1234\\xa0' became 'AB1234'.

Rule: check the RAW value is ASCII first, and only then transform it, and then only by removing ASCII space and
tab. Every caller must reach this function through the module attribute (``untrusted_text.ascii_token``), never a
``from`` import, so there is exactly one implementation to test and to mutate.
"""
from __future__ import annotations

ASCII_BLANKS = " \t"
"""The only characters trimmed from untrusted text: ASCII space and tab."""


def ascii_token(raw: object, field: str) -> str:
    """Return ``raw`` with ASCII spaces/tabs trimmed, or raise ``ValueError``.

    Raises when ``raw`` is not a string, contains any non-ASCII character (checked on the RAW value, before any
    transformation), or is empty after trimming.
    """
    if not isinstance(raw, str):
        raise ValueError(f"{field} must be text, got {type(raw).__name__}")
    if not raw.isascii():
        raise ValueError(f"{field} {raw!r} contains non-ASCII characters")
    token = raw.strip(ASCII_BLANKS)
    if not token:
        raise ValueError(f"{field} is empty")
    return token
