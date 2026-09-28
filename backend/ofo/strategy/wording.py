"""Wording checks on template text, enforced at load time (``ofo.strategy.loader``).

Spec: ADR-003 (decision-support wording, never advice); REQ-028 AC-3. Two checks:
- banned advice phrases never appear (delegates to the shared ``ofo.wording`` checker, W-024 fix
  round: this module used to carry its own exact-substring denylist, which missed word-stem variants
  a verifier found; the class-level fix put one checker in ``ofo.wording`` for every module);
- a position word (at-the-money, in-the-money, out-of-the-money, protective) appears only when the template
  carries the constraint that makes it true for every allowed parameter value.
"""
from __future__ import annotations

import re

from ofo.wording import ADVICE_WORDING_PATTERNS, find_advice_wording

#: Kept for backward compatibility (label names of the shared checker's pattern families). Extend
#: ``ofo.wording.ADVICE_WORDING_PATTERNS`` rather than this module — this is a derived view, not a
#: second source of truth.
BANNED_PHRASES: tuple[str, ...] = tuple(label for _pattern, label in ADVICE_WORDING_PATTERNS)

#: Words that claim where a strike sits relative to the at-the-money strike, or what a leg does for the
#: position. Each class is allowed only with its matching constraint (see ``loader``).
POSITION_WORDS: dict[str, tuple[str, ...]] = {
    "atm": ("at-the-money", "at the money", "atm"),
    "itm": ("in-the-money", "in the money", "itm"),
    "otm": ("out-of-the-money", "out of the money", "otm"),
    "protective": ("protective", "protection", "protects"),
}


def find_banned_phrases(text: str) -> list[str]:
    """Return every ADR-003 advice-wording family found in ``text`` (delegates to
    ``ofo.wording.find_advice_wording``); empty list means clean."""
    return find_advice_wording(text)


def find_position_words(text: str) -> set[str]:
    """Return the classes of ``POSITION_WORDS`` whose words appear in ``text``, case-insensitive."""
    lowered = text.lower()
    return {
        kind
        for kind, words in POSITION_WORDS.items()
        if any(re.search(rf"(?<![a-z]){re.escape(word)}(?![a-z])", lowered) for word in words)
    }
