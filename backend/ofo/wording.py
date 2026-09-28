"""Shared decision-support wording checker (ADR-003): ONE denylist for every module that shows text
to a user, so a word-stem variant only has to be added in one place.

Class (W-024 fix round, 2026-09-29): exact-substring denylists written separately per module
(``backend/ofo/strategy/wording.py`` for templates, a first cut of ``backend/ofo/errors/model.py``
for user-facing errors) each missed word-stem variants a verifier found in the other's blind spot
(hyphenation, pluralisation, double spaces, NBSP/zero-width characters, casefold vs lower). This
module is the fix at class level: one normaliser, one pattern list, used everywhere text reaches a
user.

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

#: (regex, label) pairs. `label` names the phrase family for messages; the compiled `regex` is the
#: enforced rule. Each pattern generalises one ADR-003 phrase, or a variant of it the W-024 verifier
#: found, to its word stem/boundary so re-wording cannot dodge the ban by pluralising, hyphenating,
#: inserting extra whitespace or adding a different following noun.
ADVICE_WORDING_PATTERNS: tuple[tuple[str, str], ...] = (
    # ADR-003: "You should take this trade" -> generalised to the imperative word itself.
    (r"\bshould\b", "should"),
    # W-024 round-3 verifier finding: "you must buy more lots" makes the same imperative claim.
    (r"\bmust\b", "must"),
    # W-024 round-3 verifier finding: "you ought to close this leg" makes the same imperative claim.
    (r"\bought\s+to\b", "ought to"),
    # ADR-003: "This is the best trade" / "Best adjustment" -> best + a trade-like noun. Deliberately
    # NOT a bare \bbest\b (round-3 design constraint: that would block "best-case", an ordinary word).
    (r"\bbest\s+(trade|strategy|option|choice|adjustment|strike|entry|time|pick|level)s?\b",
     "best <trade/strategy/option/choice/adjustment/strike/entry/time/pick/level>"),
    # ADR-003: "Recommended trade" -> any recommend* stem.
    (r"\brecommend\w*\b", "recommend*"),
    # ADR-003: "Guaranteed" -> any guarantee* stem.
    (r"\bguarantee\w*\b", "guarantee*"),
    # ADR-003: "Risk-free" -> hyphen, space or no separator.
    (r"\brisk[- ]?free\b", "risk-free"),
    # ADR-003: "Certain profit" -> certain profit(s)/return(s).
    (r"\bcertain\s+(profit|return)s?\b", "certain profit/return"),
    # W-024 verifier finding: "sure-shot" makes the same claim as "guaranteed".
    (r"\bsure[- ]?shot\b", "sure-shot"),
    # W-024 verifier finding: "no risk" makes the same claim as "risk-free".
    (r"\bno\s+risk\b", "no risk"),
    # W-024 verifier finding: "safe trade/bet/profit" makes the same claim as "risk-free"/"guaranteed".
    (r"\bsafe\s+(trade|bet|profit)s?\b", "safe <trade/bet/profit>"),
    # ADR-003: "any promise ... of reduced losses" -> reduce/avoid/never-lose phrasing.
    (r"\breduc\w*\s+(your\s+)?loss(es)?\b", "reduce loss(es)"),
    (r"\bavoid\w*\s+(a\s+)?loss(es)?\b", "avoid loss(es)"),
    (r"\bnever\s+los\w*\b", "never lose"),
)

_COMPILED_PATTERNS: tuple[tuple["re.Pattern[str]", str], ...] = tuple(
    (re.compile(pattern, re.IGNORECASE), label) for pattern, label in ADVICE_WORDING_PATTERNS
)


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
    text = re.sub(r" {2,}", " ", text).strip()
    return text


def find_advice_wording(text: str) -> list[str]:
    """Return every ADR-003 advice-wording family found in `text` (normalised first), by label,
    in `ADVICE_WORDING_PATTERNS` order. Empty list means the text is clean."""
    normalised = normalise_for_wording_scan(text)
    return [label for pattern, label in _COMPILED_PATTERNS if pattern.search(normalised)]


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
