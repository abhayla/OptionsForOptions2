"""Shared decision-support wording checker (ADR-003): ONE denylist for every module that shows text
to a user, so a word-stem variant only has to be added in one place.

Class (W-024 fix round, 2026-09-29): exact-substring denylists written separately per module
(``backend/ofo/strategy/wording.py`` for templates, a first cut of ``backend/ofo/errors/model.py``
for user-facing errors) each missed word-stem variants a verifier found in the other's blind spot
(hyphenation, pluralisation, double spaces, NBSP/zero-width characters, casefold vs lower). This
module is the fix at class level: one normaliser, one pattern list, used everywhere text reaches a
user.

Round 5 (issue #30) implements owner decision Q226 exactly: the bare words in `Q226_BARE_WORDS`,
minus the four reviewed exceptions in `Q226_NAMED_EXCEPTIONS`, matched on TOKENS (so `_` and `-`
split words: "you_should_buy", "RISK-FREE"), plus the ADR-003 phrase families below. The error
catalogue's `render()` runs it on every finished message at runtime; the strategy template loader
runs it on top of its own list (`ofo.strategy.wording`), so neither is narrower than before.

ADR-003 forbidden wording (quoted): "You should take this trade", "This is the best trade",
"Best adjustment", "Recommended trade", "Guaranteed", "Risk-free", "Certain profit", and any promise
of returns or of reduced losses.
"""
from __future__ import annotations

import re
import unicodedata

#: Unicode category "Cf" = "Format": zero-width space/joiner/non-joiner, byte-order mark, bidi
#: control marks, etc. Never visible, never meaningful text — and the verifier's red case ("a part
#: containing only a zero-width space") is exactly a Cf character alone, which a plain ``.strip()``
#: would not remove.
_FORMAT_CATEGORY = "Cf"

#: Owner decision Q226 (2026-09-29, ADR-003): "Templates may not contain the bare words "best",
#: "sure", "safe", "guarantee*" or "recommend*" (in addition to the Forbidden phrases above)."
#: Owner decision Q230 (2026-09-29, ADR-003): "the ban covers every word form of the five words
#: (e.g. "best", "safest", "safely", "safer", "surely", "guaranteed", "recommended",
#: "recommendation")." So every one of the five is matched as a word START: any token that begins
#: with it ("safest", "surely", "bests", and, as a consequence, "bestow"/"safeguard"). A token that
#: merely contains the letters later ("unsafe", "ensure", "insurer") is another word.
Q226_BARE_WORDS: tuple[str, ...] = ("best", "sure", "safe", "guarantee*", "recommend*")

#: Owner decision Q226: "Named exceptions, reviewed once: "best bid", "best ask", "best-case",
#: "make sure"; a new exception needs its own review." Q230: "The four exceptions match only as
#: spelled ... "best case" with a space is not an exception." The ONE place exceptions live. An
#: exception matches only its exact characters (letter case aside: "Best bid" opens a sentence),
#: as a whole word, and excuses only the words it covers.
Q226_NAMED_EXCEPTIONS: tuple[str, ...] = ("best bid", "best ask", "best-case", "make sure")

#: (regex, label) pairs run over the TOKENS joined by single spaces (so `_` and `-` are word
#: breaks). ADR-003's Forbidden phrases ("You should take this trade", "This is the best trade",
#: "Best adjustment", "Recommended trade", "Guaranteed", "Risk-free", "Certain profit") and "any
#: promise of returns or of reduced losses", generalised to the word stem. "best"/"recommend*"/
#: "guarantee*" are covered by the Q226 words above, so they are not repeated here. Q230: "must",
#: "have to" and "ought to" are NOT banned, so no pattern for them exists.
ADVICE_WORDING_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bshould(n)?\b", "should"),
    (r"\brisk ?free\b", "risk-free"),
    (r"\bcertain (profit|return)s?\b", "certain profit/return"),
    (r"\bno risk\b", "no risk"),
    (r"\breduc\w* (your )?loss(es)?\b", "reduce loss(es)"),
    (r"\bavoid\w* (a )?loss(es)?\b", "avoid loss(es)"),
    (r"\bnever los\w*\b", "never lose"),
)

_COMPILED_PATTERNS: tuple[tuple["re.Pattern[str]", str], ...] = tuple(
    (re.compile(pattern), label) for pattern, label in ADVICE_WORDING_PATTERNS
)

#: A token is a run of letters/digits; everything else, INCLUDING `_` and `-`, separates tokens
#: (round-3 attack "you_should_buy").
_TOKEN = re.compile(r"[^\W_]+")


def _prepare(text: str) -> str:
    """NFKC-normalise (fullwidth letters fold to ASCII), drop zero-width/format characters, casefold."""
    text = unicodedata.normalize("NFKC", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != _FORMAT_CATEGORY)
    return text.casefold()


def tokenise(text: str) -> list[str]:
    """`_prepare`, then split into letter/digit tokens. `_`, `-`, spaces and punctuation all
    separate words."""
    return _TOKEN.findall(_prepare(text))


#: Each exception as a regex over `_prepare`d text: its exact characters (one ASCII space stays one
#: ASCII space, the hyphen stays a hyphen), not preceded or followed by a letter/digit.
_EXCEPTION_PATTERNS: tuple["re.Pattern[str]", ...] = tuple(
    re.compile(r"(?<![^\W_])" + re.escape(e.casefold()) + r"(?![^\W_])") for e in Q226_NAMED_EXCEPTIONS
)


def _without_exceptions(prepared: str) -> str:
    """`prepared` with every exact named exception blanked out, so only the words it covers are
    excused and a second, bare occurrence is still seen."""
    for pattern in _EXCEPTION_PATTERNS:
        prepared = pattern.sub(" ", prepared)
    return prepared


def find_q226_bare_words(text: str) -> list[str]:
    """Every Q226/Q230 banned word present in `text` (any word form: a token starting with it) and
    not inside an exact named exception, as its Q226 label (e.g. "guarantee*"), in
    `Q226_BARE_WORDS` order."""
    tokens = _TOKEN.findall(_without_exceptions(_prepare(text)))
    found: list[str] = []
    for word in Q226_BARE_WORDS:
        stem = word.rstrip("*")
        if any(token.startswith(stem) for token in tokens):
            found.append(word)
    return found


def normalise_for_wording_scan(text: str) -> str:
    """NFKC-normalise (round 3: folds fullwidth/compatibility variants, e.g. fullwidth "ｂｅｓｔ" ->
    "best", to their ordinary form so they cannot bypass the scan); casefold; drop zero-width/format
    characters; collapse all Unicode whitespace (incl. NBSP, thin space, tabs, double spaces) to
    single ASCII spaces; strip leading/trailing space.

    This is the normalisation step every wording/blank check in the project runs text through
    before matching, so a word-stem pattern (or an emptiness check) cannot be dodged by whitespace,
    invisible-character or compatibility-character tricks.
    """
    text = unicodedata.normalize("NFKC", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != _FORMAT_CATEGORY)
    text = text.casefold()
    text = "".join(" " if ch.isspace() else ch for ch in text)
    # W-024 round-4 verifier finding: "_" is a `\w` character, so "you_should_buy" was ONE
    # contiguous word to a `\bshould\b` pattern (no boundary appears around an underscore) and
    # the imperative slipped through. Folding underscores to spaces first gives the boundary back.
    text = text.replace("_", " ")
    text = re.sub(r" {2,}", " ", text).strip()
    return text


def find_advice_wording(text: str) -> list[str]:
    """Return every ADR-003/Q226 advice-wording hit in `text`: first the Q226 bare words (by their
    Q226 label), then the phrase families (by label). Empty list means the text is clean."""
    joined = " ".join(tokenise(text))
    phrases = [label for pattern, label in _COMPILED_PATTERNS if pattern.search(joined)]
    return find_q226_bare_words(text) + phrases


def is_blank_after_normalising(text: str) -> bool:
    """True if `text` has no visible content once zero-width/format characters are stripped and
    whitespace is collapsed (catches e.g. a field that is only a zero-width space)."""
    return normalise_for_wording_scan(text) == ""


def normalise_for_duplicate_check(text: str) -> str:
    """As `normalise_for_wording_scan`, plus strips all punctuation — so 'Same.' and 'Same' (or two
    template parts differing only by a full stop) compare equal. W-024 round-3 verifier finding:
    parts differing only by punctuation were not flagged as duplicates."""
    base = normalise_for_wording_scan(text)
    return re.sub(r"[^\w\s]", "", base, flags=re.UNICODE)


#: Characters allowed in platform-authored (our own) user-facing text: ASCII Latin letters, digits,
#: the rupee sign, common whitespace and punctuation. Anything else — most importantly a confusable
#: non-Latin letter such as Cyrillic "о" (U+043E, which LOOKS like Latin "o" but is a different
#: character and a different Unicode script) — fails this check. `ExternalText` (round-3 slot type)
#: is exempt: it is someone else's text, shown quoted and labelled, never scanned or restyled.
#: `{}` are included because this check also runs over un-rendered `MessageTemplate` text
#: (`{slot_name}` placeholders), not only final display strings — a slot's own formatted value is
#: substituted in before anything is shown to a user.
_ALLOWED_PLATFORM_TEXT = re.compile(
    r"^[A-Za-z0-9₹\s.,;:!?()'\"‘’“”%/&@#+=<>*«»_{}-]*$"
)


def is_nfkc_clean_latin(text: str) -> bool:
    """True if `text`, after NFKC normalisation, is entirely Latin letters/digits/₹/punctuation —
    no confusable non-Latin letters (e.g. Cyrillic look-alikes) that could carry an unscanned claim.

    W-024 round-3 verifier finding: Cyrillic and fullwidth letters bypassed the wording scan (a
    lookalike letter from a different Unicode script never matches an ASCII-anchored `\\w`/`\\b`
    pattern). NFKC handles the fullwidth case (folds to ASCII, so the wording scan sees it); this
    check refuses the Cyrillic/other-script case outright rather than trying to transliterate it.
    """
    normalised = unicodedata.normalize("NFKC", text)
    return bool(_ALLOWED_PLATFORM_TEXT.match(normalised))


def check_platform_text(text: object, where: str) -> None:
    """THE check every piece of the platform's own user-visible text passes (ADR-003, Q226, Q230):
    exactly a `str`; not blank once invisible characters are removed; only Latin letters, digits,
    ₹ and punctuation (no confusable other-script letters); and no ADR-003/Q226/Q230 wording.
    Raises TypeError / ValueError naming `where`. Zerodha's or the user's own words never go
    through this: they are quoted in a labelled field (Q226)."""
    if type(text) is not str:
        raise TypeError(f"{where}: platform text must be exactly str, got {type(text).__name__}")
    if is_blank_after_normalising(text):
        raise ValueError(f"{where}: platform text is blank: {text!r}")
    if not is_nfkc_clean_latin(text):
        raise ValueError(f"{where}: platform text has non-Latin/confusable characters: {text!r}")
    hits = find_advice_wording(text)
    if hits:
        raise ValueError(f"{where}: platform text contains banned wording {hits}: {text!r}")
