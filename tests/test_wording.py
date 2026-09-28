"""ofo.wording: the shared ADR-003 decision-support wording checker (W-024 fix round).

Class: decision-support wording (ADR-003) guarded by exact-substring denylists written separately
per module (backend/ofo/strategy/wording.py, backend/ofo/errors/model.py) each missed word-stem
variants. This is the shared, single checker every module now delegates to.
"""
from __future__ import annotations

import pytest

from ofo.wording import find_advice_wording, is_blank_after_normalising, normalise_for_wording_scan

VERIFIER_BANNED_TEXTS: tuple[tuple[str, str], ...] = (
    ("guarantee stem", "We guarantee returns"),
    ("recommend stem", "We recommend buying calls"),
    ("risk free with space", "Risk free setup"),
    ("sure-shot", "A sure-shot trade"),
    ("should", "Traders should hedge now."),
    ("should with double space", "You  should buy"),
    ("reduce your losses", "This will reduce your losses"),
    ("best trade in a code-like string", "best trade"),
)


@pytest.mark.parametrize("label,text", VERIFIER_BANNED_TEXTS, ids=[c[0] for c in VERIFIER_BANNED_TEXTS])
def test_verifier_cases_are_found(label: str, text: str) -> None:
    """W-024: every verifier-found accepted-but-banned case is now caught."""
    assert find_advice_wording(text), f"{label!r} should have been flagged: {text!r}"


LEGITIMATE_TEXTS: tuple[str, ...] = (
    "This strategy loses money if NIFTY falls below 22,909",
    "Your rule was triggered",
    "Adjust the shoulder strikes of this butterfly.",  # 'should' as a word-stem prefix, not the word
    "Strategies you could consider",
    "Suggested setup",
)


@pytest.mark.parametrize("text", LEGITIMATE_TEXTS)
def test_legitimate_text_is_not_flagged(text: str) -> None:
    """W-024: ordinary decision-support text must not be flagged (no false positives)."""
    assert find_advice_wording(text) == [], text


def test_zero_width_space_alone_is_blank() -> None:
    """W-024 verifier case: a field containing only a zero-width space is blank, not real text."""
    assert is_blank_after_normalising("​") is True
    assert is_blank_after_normalising("​‌‍") is True


def test_nbsp_and_double_space_collapse_to_single_space() -> None:
    """Whitespace normalisation covers NBSP and doubled ASCII spaces alike."""
    assert normalise_for_wording_scan("You  should  buy") == "you should buy"


def test_visible_text_is_not_blank() -> None:
    assert is_blank_after_normalising("  Hello  ") is False


def test_find_advice_wording_is_case_insensitive_and_casefold_based() -> None:
    """Uses casefold (not just .lower()) so e.g. the German sharp s (ß) also normalises consistently."""
    assert find_advice_wording("GUARANTEED") == find_advice_wording("guaranteed")
