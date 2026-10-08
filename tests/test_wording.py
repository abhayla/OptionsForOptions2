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


#: Owner decision Q235 (ADR-003): promise phrases are Forbidden, "in every word form".
PROMISE_TEXTS: tuple[str, ...] = (
    "assured returns",
    "Assured return on every trade",
    "Get assured returns",
    "You cannot lose here",
    "Cannot  lose",
    "You can't lose",
    "you can’t lose",
    "You cant lose",
    "You can not lose",
    "There is no loss",
    "No losses",
    "no_loss",
    "minimise losses",
    "minimize your losses",
    "Minimising the losses",
    "Minimized loss",
    "reduces your losses",
    "reduce losses",
    "reduce the losses",
    "Zero risk",
    "zero-risk trade",
    "ZERO  RISK",
    "no risk",
    "certain profit",
    "guaranteed profit",
)


@pytest.mark.parametrize("text", PROMISE_TEXTS)
def test_promise_phrases_are_flagged_in_every_word_form(text: str) -> None:
    """Q235: each promise phrase and its word-form variants is found by the ONE shared check."""
    assert find_advice_wording(text), f"promise phrase not flagged: {text!r}"


ALLOWED_NEAR_MISSES: tuple[str, ...] = (
    "no loss of data",
    "Loss",
    "risk",
    "Risk of loss is shown for every level",
    "reduce the quantity",
    "You can lose money",
    "maximum loss",
    "The loss is limited to the premium paid",
    "We were assured of the timing",
    "Zero quantity is not allowed",
    "no risky legs",
)


#: W-024 round 8 (ADR-056 item 1): the round-7 residual promise phrases from issue 30, each in
#: several word forms. Spec: ADR-003 Forbidden "any promise of returns or of reduced losses";
#: Q235 "in every word form". Keyed by the phrase, so removing one pattern turns its cases red.
ROUND7_RESIDUAL_PROMISES: dict[str, tuple[str, ...]] = {
    "returns are assured": ("Returns are assured", "your return is assured", "Profits are assured",
                            "gains assured", "returns will be assured"),
    "losses are minimised": ("Losses are minimised", "losses are minimized", "Your loss is minimised",
                             "losses get minimised", "loss minimized"),
    "riskless": ("Riskless", "a riskless trade", "RISKLESS setup", "trade risklessly"),
    "won't lose": ("You won't lose", "you won’t lose", "you wont lose", "You will not lose",
                   "won t lose money", "will not lose money"),
    "loss-free": ("loss-free", "Loss free trade", "LOSS_FREE", "a lossfree setup"),
    "profit is certain": ("Profit is certain", "profits are certain", "returns are certain",
                          "the gain is certain", "profit will be certain", "profit certainly"),
}


@pytest.mark.parametrize(
    "phrase,text",
    [(p, t) for p, texts in ROUND7_RESIDUAL_PROMISES.items() for t in texts],
    ids=[f"{p}: {t}" for p, texts in ROUND7_RESIDUAL_PROMISES.items() for t in texts],
)
def test_round7_residual_promises_are_flagged_under_their_own_label(phrase: str, text: str) -> None:
    """Each residual is caught by ITS OWN pattern (the label), so no other pattern hides a mutant."""
    assert phrase in find_advice_wording(text), (phrase, text, find_advice_wording(text))


ROUND8_NEAR_MISSES: tuple[str, ...] = (
    "risk",
    "loss",
    "Losses are shown at every level",
    "Returns are shown before charges",
    "profit at expiry",
    "The maximum loss is the premium paid",
    "You will lose money below 22,909",
    "a certain strike",
    "Risk is shown for every leg",
    "Loss at this level",
    "free margin",
)


@pytest.mark.parametrize("text", ROUND8_NEAR_MISSES)
def test_round8_promise_patterns_leave_ordinary_risk_and_loss_text_clean(text: str) -> None:
    assert find_advice_wording(text) == [], text


@pytest.mark.parametrize("text", ALLOWED_NEAR_MISSES)
def test_promise_phrase_patterns_do_not_catch_normal_text(text: str) -> None:
    """Q235: ordinary words near a promise phrase ("no loss of data", "Loss", "risk", "reduce the
    quantity") stay allowed."""
    assert find_advice_wording(text) == [], text
