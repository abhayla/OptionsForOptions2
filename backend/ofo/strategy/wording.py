"""Wording checks on template text, enforced at load time (``ofo.strategy.loader``).

Spec: ADR-003 (decision-support wording, never advice); REQ-028 AC-3. Two checks:
- banned advice phrases never appear;
- a position word (at-the-money, in-the-money, out-of-the-money, protective) appears only when the template
  carries the constraint that makes it true for every allowed parameter value.
"""
from __future__ import annotations

import re

#: Case-insensitive, whole-word/phrase match. Extend this list rather than special-casing a template.
BANNED_PHRASES: tuple[str, ...] = (
    "best",
    "you should",
    "guaranteed",
    "sure",
    "risk-free",
    "risk free",
    "recommended trade",
    "certain profit",
    "safe",
    "no risk",
)

#: Words that claim where a strike sits relative to the at-the-money strike, or what a leg does for the
#: position. Each class is allowed only with its matching constraint (see ``loader``).
POSITION_WORDS: dict[str, tuple[str, ...]] = {
    "atm": ("at-the-money", "at the money", "atm"),
    "itm": ("in-the-money", "in the money", "itm"),
    "otm": ("out-of-the-money", "out of the money", "otm"),
    "protective": ("protective", "protection", "protects"),
}


def find_banned_phrases(text: str) -> list[str]:
    """Return every banned phrase (from ``BANNED_PHRASES``) found in ``text``, case-insensitive."""
    lowered = text.lower()
    return [phrase for phrase in BANNED_PHRASES if re.search(rf"\b{re.escape(phrase)}\b", lowered)]


def find_position_words(text: str) -> set[str]:
    """Return the classes of ``POSITION_WORDS`` whose words appear in ``text``, case-insensitive."""
    lowered = text.lower()
    return {
        kind
        for kind, words in POSITION_WORDS.items()
        if any(re.search(rf"(?<![a-z]){re.escape(word)}(?![a-z])", lowered) for word in words)
    }
