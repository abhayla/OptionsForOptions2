"""AC-2 (REQ-025, via W-046): ofo.wording, the shared ADR-003 decision-support wording checker.

Class: decision-support wording (ADR-003) guarded by exact-substring denylists written separately
per module (backend/ofo/strategy/wording.py on main; a first cut of the parked W-024 error
catalogue) each missed word-stem variants. This is the shared, single checker; on main the
strategy template loader and ofo.timeline.why run it on top of their own list.
Expected values below come from ADR-003's text (Forbidden list, Q226, Q230, Q231, Q235), not from
running the checker.
"""
from __future__ import annotations

import pytest

from ofo.wording import (
    check_platform_text,
    find_advice_wording,
    find_q226_bare_words,
    is_blank_after_normalising,
    is_nfkc_clean_latin,
    normalise_for_duplicate_check,
    normalise_for_wording_scan,
)

# ---------------------------------------------------------------------------------------------
# check_platform_text: THE check (W-046 core). Each case quotes the ADR-003 line it rests on.
# ---------------------------------------------------------------------------------------------

#: (text, ADR-003 basis) -- must be REFUSED.
REFUSED_PLATFORM_TEXTS: tuple[tuple[str, str], ...] = (
    ("the best guaranteed setup", 'Q226: bare words "best", "guarantee*"'),
    ("best case", 'Q230: "\\"best case\\" with a space is not an exception"'),
    ("safest", 'Q230: every word form, e.g. "safest"'),
    ("safer", 'Q231: still banned "safer"'),
    ("safely", 'Q231: still banned "safely"'),
    ("safeguard", 'Q231: still banned "safeguard"'),
    ("surely", 'Q230: "surely"'),
    ("recommendation", 'Q230: "recommendation"'),
    ("Recommended trade", 'Forbidden: "Recommended trade"'),
    ("assured returns", 'Q235: "assured return(s)"'),
    ("You should take this trade", 'Forbidden: "You should take this trade"'),
    ("This is the best trade", 'Forbidden: "This is the best trade"'),
    ("Best adjustment", 'Forbidden: "Best adjustment"'),
    ("Risk-free", 'Forbidden: "Risk-free"'),
    ("Certain profit", 'Forbidden: "Certain profit"'),
    ("best bid, and the best price", 'Q226: an exception excuses only the words it covers'),
    ("unsafe", 'Q230 word form: negated "un" + word'),
)


@pytest.mark.parametrize("text,basis", REFUSED_PLATFORM_TEXTS, ids=[c[0] for c in REFUSED_PLATFORM_TEXTS])
def test_check_platform_text_refuses_adr003_wording(text: str, basis: str) -> None:
    """AC-2: platform text carrying ADR-003/Q226/Q230/Q231/Q235 wording is refused (never 'the trade to take')."""
    with pytest.raises(ValueError, match="banned wording"):
        check_platform_text(text, "test")


#: (text, ADR-003 basis) -- must PASS.
ALLOWED_PLATFORM_TEXTS: tuple[tuple[str, str], ...] = (
    ("best bid", 'Q226 named exception "best bid"'),
    ("Best ask", 'Q226 named exception "best ask" (sentence case)'),
    ("best-case", 'Q226 named exception "best-case"'),
    ("make sure", 'Q226 named exception "make sure"'),
    ("safety check", 'Q231: "safety check"'),
    ("safety checks", 'Q231: "safety checks"'),
    ("safety gate", 'Q231: "safety gate"'),
    ("You must reconnect Zerodha", 'Q230: "\\"You must reconnect Zerodha\\" is allowed"'),
    ("You have to confirm this order", 'Q230: "have to" is NOT banned'),
    ("Strategies you could consider", "ADR-003 Preferred"),
    ("Suggested setup", "ADR-003 Preferred"),
    ("Adjustment opportunity detected", "ADR-003 Preferred"),
    ("Your rule was triggered", "ADR-003 Preferred"),
    ("no loss of data", 'Q235 note: "no loss of data" is a technical phrase'),
    ("Prices shown may be stale — confirm to continue.", "em dash is punctuation"),
    ("Max loss: ₹2,500", "rupee sign is allowed"),
)


@pytest.mark.parametrize("text,basis", ALLOWED_PLATFORM_TEXTS, ids=[c[0] for c in ALLOWED_PLATFORM_TEXTS])
def test_check_platform_text_allows_reviewed_wording(text: str, basis: str) -> None:
    """AC-2: ADR-003 preferred wording and the reviewed Q226/Q230/Q231 exceptions pass unchanged."""
    assert check_platform_text(text, "test") is None


@pytest.mark.parametrize("value", [None, b"Suggested setup", 3, ["Suggested setup"]])
def test_check_platform_text_refuses_non_str(value: object) -> None:
    """AC-2: platform text must be exactly str (fail closed: bytes/None/list never reach the user)."""
    with pytest.raises(TypeError, match="exactly str"):
        check_platform_text(value, "test")


def test_check_platform_text_refuses_str_subclass() -> None:
    """AC-2: a str subclass (which could override methods the check relies on) is refused."""

    class Sneaky(str):
        pass

    with pytest.raises(TypeError, match="exactly str"):
        check_platform_text(Sneaky("Suggested setup"), "test")


@pytest.mark.parametrize("value", ["", "   ", "​", " ‍\t"])
def test_check_platform_text_refuses_blank(value: str) -> None:
    """AC-2: blank text (incl. only zero-width / NBSP characters) is refused."""
    with pytest.raises(ValueError, match="blank"):
        check_platform_text(value, "test")


@pytest.mark.parametrize("value", ["bеst trade", "Suggested ѕetup", "βest"])
def test_check_platform_text_refuses_confusable_letters(value: str) -> None:
    """AC-2: a Cyrillic/Greek look-alike letter (which dodges the ASCII word scan) is refused outright."""
    with pytest.raises(ValueError, match="non-Latin"):
        check_platform_text(value, "test")


def test_fullwidth_letters_fold_and_are_scanned() -> None:
    """AC-2: fullwidth 'ｂｅｓｔ' folds to 'best' under NFKC and is caught by the word scan."""
    assert is_nfkc_clean_latin("ｂｅｓｔ") is True
    assert find_q226_bare_words("ｂｅｓｔ") == ["best"]
    with pytest.raises(ValueError, match="banned wording"):
        check_platform_text("ｂｅｓｔ", "test")


def test_zero_width_inside_a_word_does_not_hide_it() -> None:
    """AC-2: a zero-width space inside 'be​st' is dropped before scanning, so the word is found."""
    assert find_q226_bare_words("be​st trade") == ["best"]


def test_error_message_names_where() -> None:
    """AC-2: the refusal names the caller-given location so a failing template is findable."""
    with pytest.raises(ValueError, match="template 'x' name"):
        check_platform_text("best", "template 'x' name")


def test_q226_labels_are_reported_in_q226_order() -> None:
    """AC-2: every one of the five Q226 words is found, labelled as Q226 spells it."""
    assert find_q226_bare_words("recommended guarantee safe sure best") == [
        "best", "sure", "safe", "guarantee*", "recommend*",
    ]
    assert find_q226_bare_words("ensure the insurer is assured") == []  # other words that contain the letters


def test_duplicate_check_ignores_punctuation_and_spacing() -> None:
    """AC-2: two texts differing only by punctuation/spacing normalise equal."""
    assert normalise_for_duplicate_check("Same  text.") == normalise_for_duplicate_check("same text")

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


@pytest.mark.parametrize("text", ALLOWED_NEAR_MISSES)
def test_promise_phrase_patterns_do_not_catch_normal_text(text: str) -> None:
    """Q235: ordinary words near a promise phrase ("no loss of data", "Loss", "risk", "reduce the
    quantity") stay allowed."""
    assert find_advice_wording(text) == [], text


def test_real_strategy_catalogue_passes_the_shared_check() -> None:
    """AC-2 (real data): all 21 strategy templates in backend/ofo/strategy/catalogue.yaml load through the wired
    loader, and each name and description passes check_platform_text."""
    from ofo.strategy.loader import DEFAULT_CATALOGUE_PATH, load_templates

    templates = load_templates(DEFAULT_CATALOGUE_PATH)
    assert len(templates) == 21
    for template in templates:
        check_platform_text(template.name, f"{template.id} name")
        check_platform_text(template.description, f"{template.id} description")


# ---------------------------------------------------------------------------------------------
# W-046 round 2: sentence-level promise rules. ADR-003: "never ... promises that losses will be
# reduced"; Forbidden: "any promise of returns or of reduced losses (T1 #74)"; "Adjustments are never
# described as reducing risk by default; they can increase it (T1 #176)"; Q235 "in every word form".
# Round 1 matched only the listed word ORDER; the verifier's reworded phrases below passed it.
# ---------------------------------------------------------------------------------------------

#: The W-046 round-1 verifier's exact failing phrases (each passed check_platform_text on f6cac29).
VERIFIER_ROUND1_PROMISES: tuple[str, ...] = (
    "Your losses will be reduced",
    "returns are assured",
    "won't lose",
    "lower your losses",
    "Adjustments reduce risk",
)


@pytest.mark.parametrize("text", VERIFIER_ROUND1_PROMISES)
def test_verifier_reworded_promises_are_refused(text: str) -> None:
    """AC-2: the W-046 verifier's reworded promises (any word order) are refused by check_platform_text."""
    with pytest.raises(ValueError, match="banned wording"):
        check_platform_text(text, "test")


#: Builder's own paraphrases, loss/risk side: each is a promise of reduced loss or risk.
LOSS_PROMISE_PARAPHRASES: tuple[str, ...] = (
    "This adjustment will cut your losses.",          # cut
    "Losses are minimised with this setup.",          # minimi[sz]*, passive
    "Your downside is protected.",                    # protect*, downside
    "The hedge shields your position from risk.",     # shield*
    "Risk is eliminated once the put is bought.",     # eliminat*
    "Drawdowns are prevented by this rule.",          # prevent*, drawdown
    "Rolling the call lowers the risk.",              # lowers
    "Your risk is limited with this adjustment.",     # limited (not "limited to <amount>")
    "Adjusting now helps you avoid further losses.",  # avoid*
    "Risk decreases after the roll.",                 # decreas*
    "The spread mitigates losses.",                   # mitigat*
    "This curbs your losses.",                        # curb*
    "Loss reduction built in.",                       # reduc* (noun form)
    "This adjustment lowers your maximum loss.",      # no blanket metric-label exemption (T1 #176)
)


@pytest.mark.parametrize("text", LOSS_PROMISE_PARAPHRASES)
def test_loss_reduction_paraphrases_are_refused(text: str) -> None:
    """AC-2: a loss/risk word with a reduction word anywhere in one sentence is a promise of reduced loss."""
    assert "promise of reduced loss/risk" in find_advice_wording(text), text
    with pytest.raises(ValueError, match="banned wording"):
        check_platform_text(text, "test")


NO_LOSS_PROMISES: tuple[str, ...] = (
    "You won't ever lose money here.",
    "You will not lose on this spread.",
    "This trade has never lost.",
    "There is no chance of a loss.",
    "Exit without losses.",
    "No downside at all.",
    "zero drawdown",
    "You do not lose if NIFTY stays in range.",
)


@pytest.mark.parametrize("text", NO_LOSS_PROMISES)
def test_negated_loss_promises_are_refused(text: str) -> None:
    """AC-2: "won't/will not/never lose", "no chance of loss", "without losses", "no downside" are promises of
    no loss."""
    assert "promise of no loss" in find_advice_wording(text), text


#: Builder's own paraphrases, return side: each promises a return or profit.
RETURN_PROMISE_PARAPHRASES: tuple[str, ...] = (
    "Profit is certain if held to expiry.",
    "This setup gives a fixed monthly income.",
    "Gains are assured.",
    "You will certainly make a profit.",
    "Assured income every week.",
    "The profit is definite at expiry.",
    "We promise steady returns.",
    "Earnings are sure with this spread.",
    "Returns: assured.",
    "A yield you can be certain of.",
    "Riskless profits.",
)


@pytest.mark.parametrize("text", RETURN_PROMISE_PARAPHRASES)
def test_return_promise_paraphrases_are_refused(text: str) -> None:
    """AC-2: a return/profit word with an assurance word anywhere in one sentence is a promise of returns."""
    assert "promise of returns" in find_advice_wording(text), text
    with pytest.raises(ValueError, match="banned wording"):
        check_platform_text(text, "test")


#: Factual risk/return text that must pass: the brief's four near-misses, real platform text that puts
#: a loss next to a reduction word's noun sense, and metric labels.
FACTUAL_RISK_TEXTS: tuple[str, ...] = (
    "maximum loss",
    "You can lose money",
    "no loss of data",
    "reduce the quantity",
    "Maximum loss ₹8,175",
    "Max loss: ₹2,500 at the lower breakeven.",
    "Loss at 22,000: ₹1,200.",
    "P&L at expiry",
    # Real platform text, backend/ofo/execution/safety.py:
    "This strategy's possible loss has no upper limit if the market moves far enough.",
    "The loss is limited to the premium paid",
    "Sell a put and buy a put at a lower strike; the loss is shown for every level.",
    "Risk limit reached: ₹5,000.",
    "Your loss limit was triggered.",
    "Loss at the lower limit is shown.",
    "Place a limit order and see the loss at expiry.",
    "Adjustments can increase risk.",
    "Losses are shown per leg. Reduce the quantity to see a smaller position.",  # two sentences
    "In certain cases the profit shown may change.",
    "Make sure the profit target is set.",
    "If Zerodha disconnects, you will not lose your plan.",
    "Maximum profit ₹3,000 at the upper breakeven.",
    "Protective put",
)


@pytest.mark.parametrize("text", FACTUAL_RISK_TEXTS)
def test_factual_risk_text_passes(text: str) -> None:
    """AC-2: factual risk/return text (metric labels, noun senses of "lower"/"limit", separate sentences, the
    Q226 "make sure" exception) is not a promise and passes check_platform_text."""
    assert find_advice_wording(text) == [], text
    assert check_platform_text(text, "test") is None


def test_noun_sense_exemption_does_not_hide_a_real_verb() -> None:
    """AC-2: blanking "lower strike" / "limited to the premium" removes only that word; a real reduction verb in
    the same sentence is still seen."""
    assert "promise of reduced loss/risk" in find_advice_wording("Buy at a lower strike to cut your loss.")
    assert "promise of reduced loss/risk" in find_advice_wording(
        "The loss is limited to the premium paid, so this reduces risk.")
    assert "promise of reduced loss/risk" in find_advice_wording("Losses are limited to what you can afford.")


def test_certain_as_determiner_does_not_hide_a_real_assurance() -> None:
    """AC-2: "certain cases" is exempt, but "certain" as an assurance in the same sentence is still seen."""
    assert "promise of returns" in find_advice_wording("In certain cases the profit is certain.")


def test_data_exemption_is_only_for_app_data() -> None:
    """AC-2: "you will not lose your plan" passes, "you will not lose your money" is refused."""
    assert find_advice_wording("You will not lose your plan.") == []
    assert "promise of no loss" in find_advice_wording("You will not lose your money.")


def test_de_risk_is_refused() -> None:
    """AC-2 / T1 #176: "de-risk" describes an adjustment as removing risk."""
    assert "de-risk" in find_advice_wording("De-risk your position with this adjustment")
    assert "de-risk" in find_advice_wording("Derisking made easy")


def test_sentences_split_on_line_breaks() -> None:
    """AC-2: a line break ends a sentence, so a loss word on one line and "reduce" on the next are separate."""
    assert find_advice_wording("Loss shown per level\nReduce the quantity") == []
    assert "promise of reduced loss/risk" in find_advice_wording("Loss shown per level, reduce it")


def test_decimal_point_does_not_split_a_sentence() -> None:
    """AC-2: "8.5" is not a sentence end, so the promise around it is still one sentence."""
    assert "promise of reduced loss/risk" in find_advice_wording("Cuts the loss by 8.5 percent")
    assert "promise of returns" in find_advice_wording("Returns of 1.5 percent assured")
