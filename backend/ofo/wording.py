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
#: A trailing `*` means the word stem: any token starting with it ("guaranteed", "recommendation").
#: A bare word is a whole TOKEN: "unsafe", "ensure" and "bestow" are other words, not these ones.
Q226_BARE_WORDS: tuple[str, ...] = ("best", "sure", "safe", "guarantee*", "recommend*")

#: Owner decision Q226: "Named exceptions, reviewed once: "best bid", "best ask", "best-case",
#: "make sure"; a new exception needs its own review." The ONE place exceptions live. Each is
#: tokenised the same way as the text, so "best-case", "best_case" and "best case" are one
#: exception, and an exception excuses only the words it covers, never a second bare occurrence.
Q226_NAMED_EXCEPTIONS: tuple[str, ...] = ("best bid", "best ask", "best-case", "make sure")

#: (regex, label) pairs run over the TOKENS joined by single spaces (so `_` and `-` are word
#: breaks). ADR-003's Forbidden phrases ("You should take this trade", "This is the best trade",
#: "Best adjustment", "Recommended trade", "Guaranteed", "Risk-free", "Certain profit") and "any
#: promise of returns or of reduced losses", generalised to the word stem; plus imperative variants
#: earlier verifier rounds found ("must", "ought to", "have to"). "best"/"recommend*"/"guarantee*"
#: are covered by the Q226 bare words above, so they are not repeated here.
ADVICE_WORDING_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bshould(n)?\b", "should"),
    (r"\bmust\b", "must"),
    (r"\bought to\b", "ought to"),
    (r"\bhave to\b", "have to"),
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
#: (brief item 3: "tokenised so `_` and `-` split words"; round-3 attack "you_should_buy").
_TOKEN = re.compile(r"[^\W_]+")


def tokenise(text: str) -> list[str]:
    """NFKC-normalise, drop zero-width/format characters, casefold, and split into letter/digit
    tokens. `_`, `-`, spaces and punctuation all separate words."""
    text = unicodedata.normalize("NFKC", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != _FORMAT_CATEGORY)
    return _TOKEN.findall(text.casefold())


_EXCEPTION_TOKENS: tuple[tuple[str, ...], ...] = tuple(tuple(tokenise(e)) for e in Q226_NAMED_EXCEPTIONS)


def _bare_word_matches(word: str, token: str) -> bool:
    if word.endswith("*"):
        return token.startswith(word[:-1])
    return token == word


def _covered_by_exception(tokens: list[str], index: int) -> bool:
    """True if the token at `index` is part of one of the Q226 named exceptions, in place."""
    for exception in _EXCEPTION_TOKENS:
        for offset, part in enumerate(exception):
            if part != tokens[index]:
                continue
            start = index - offset
            if start >= 0 and tuple(tokens[start:start + len(exception)]) == exception:
                return True
    return False


def find_q226_bare_words(text: str) -> list[str]:
    """Every Q226 bare word present in `text` and not covered by a named exception, as the Q226
    label (e.g. "guarantee*"), in `Q226_BARE_WORDS` order."""
    tokens = tokenise(text)
    found: list[str] = []
    for word in Q226_BARE_WORDS:
        for index, token in enumerate(tokens):
            if _bare_word_matches(word, token) and not _covered_by_exception(tokens, index):
                found.append(word)
                break
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
