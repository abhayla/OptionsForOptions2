"""Decision-support wording check (ADR-003): a template's name/description is never advice.

Spec: CLAUDE.md "Wording is decision-support, never advice"; REQ-028 AC-5; ADR-003. Enforced at LOAD
time (``ofo.strategy.loader``), not just tested after the fact, so a banned phrase never reaches a
catalogue file silently.
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


def find_banned_phrases(text: str) -> list[str]:
    """Return every banned phrase (from ``BANNED_PHRASES``) found in ``text``, case-insensitive."""
    lowered = text.lower()
    return [phrase for phrase in BANNED_PHRASES if re.search(rf"\b{re.escape(phrase)}\b", lowered)]
