"""The value of a strategy setting (a risk limit, a preference, a rules reference): one type, one door (ADR-069).

Spec: ADR-069 ("short identifiers or numbers only - letters, digits, underscore, hyphen and dot, at most 64
characters"; a longer or free-text value "is refused on save with the fixed input error (HTTP 422) and is never echoed
back"); ADR-064 (the names); REQ-038 AC-5 ("live prices are never saved inside the strategy"). Issue #165 defect 1:
the rule used to be checked only at the API body, so ``build_from_catalogue`` / ``save_draft`` / ``update`` accepted
a sentence. Now ``StrategyDefinition`` builds every risk limit, preference and rules reference through these functions,
so the API, ``build_from_catalogue``, the store and a load all inherit the rule; the database CHECK in migration 0008
is the same rule once more (tests/strategy/test_settings_value.py pins the two patterns equal).

A refusal never carries the offending value: only the setting's kind and the value's type name.
"""
from __future__ import annotations

import re
from decimal import Decimal

#: ADR-069: letters, digits, underscore, hyphen, dot; 1 to 64 characters. Matched with ``fullmatch`` (no trailing
#: newline slips through ``$``).
IDENTIFIER_PATTERN = r"[A-Za-z0-9_.-]{1,64}"
#: A risk limit as stored text: a finite, non-negative decimal as plain digits (no sign, no exponent, no spaces).
LIMIT_PATTERN = r"[0-9]{1,30}([.][0-9]{1,30})?"

_IDENTIFIER = re.compile(IDENTIFIER_PATTERN)
_LIMIT = re.compile(LIMIT_PATTERN)


class SettingsValueError(ValueError):
    """A setting's value is outside ADR-069's type. Its text holds no part of the value."""

    def __init__(self, kind: str, got: str) -> None:
        self.kind = kind  # a token such as "preference.objective" or "rules_ref"
        self.got = got  # the value's TYPE name
        super().__init__(kind)


def identifier(value: object, kind: str) -> str:
    """``value`` if it is an ADR-069 identifier (a string of letters, digits, ``_ - .``; 1 to 64 characters)."""
    if type(value) is not str or _IDENTIFIER.fullmatch(value) is None:
        raise SettingsValueError(kind, type(value).__name__)
    return value


def limit(value: object, kind: str) -> Decimal:
    """``value`` if it is a finite, non-negative ``Decimal`` whose text is plain digits (so it round-trips through the
    stored text exactly and fits ADR-069's number form)."""
    if type(value) is not Decimal or not value.is_finite() or _LIMIT.fullmatch(str(value)) is None:
        raise SettingsValueError(kind, type(value).__name__)
    return value
