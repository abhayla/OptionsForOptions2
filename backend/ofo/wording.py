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
split words: "you_should_buy", "RISK-FREE"), plus the ADR-003 phrase families below.

Wired on main (W-046, extracted from the W-024 branch with the owner's OK; the error catalogue
itself stays parked, issue #30): the strategy template loader (`ofo.strategy.loader.check_wording`)
and the rule-trigger explanation (`ofo.timeline.why`) each run it ON TOP of their own older list
(`ofo.strategy.wording.find_banned_phrases`), so neither is narrower than before.

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
#: merely contains the letters later ("ensure", "insurer", "assured") is another word, EXCEPT the
#: negated form: "un" + the word ("unsafe", "unsure") is a word form of it and is banned too
#: (coordinator ruling with Q231, 2026-09-29).
Q226_BARE_WORDS: tuple[str, ...] = ("best", "sure", "safe", "guarantee*", "recommend*")

#: Owner decision Q226: "Named exceptions, reviewed once: "best bid", "best ask", "best-case",
#: "make sure"; a new exception needs its own review." Q230: "The four exceptions match only as
#: spelled ... "best case" with a space is not an exception." The ONE place exceptions live. An
#: exception matches only its exact characters (letter case aside: "Best bid" opens a sentence),
#: as a whole word, and excuses only the words it covers.
#: Owner decision Q231 (2026-09-29, ADR-003): ""safety" is a reviewed exception to the Q230
#: word-form ban, because it names a check the platform runs (REQ-059 "Pre-execution safety
#: gate"), not a promise about a trade. Allowed: "safety", "safety check", "safety checks",
#: "safety gate"." "safeguard", "safer", "safest", "safely" stay banned.
Q226_NAMED_EXCEPTIONS: tuple[str, ...] = (
    "best bid", "best ask", "best-case", "make sure",
    "safety", "safety check", "safety checks", "safety gate",
)

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
    (r"\breduc\w* (your |the |any |all )?loss(es)?\b", "reduce loss(es)"),
    # Owner decision Q235 (ADR-003): promise phrases, "in every word form". Tokens are letters and
    # digits only, so "can't" arrives as "can t". "no loss of data" is a technical phrase: allowed.
    # ("guaranteed profit" is already covered by the Q226 word "guarantee*".)
    (r"\bassured (return|profit|gain)s?\b", "assured return(s)"),
    (r"\bcan ?(not|never|t) lose\b", "cannot lose"),
    (r"\bno loss(es)?\b(?! of data\b)", "no loss"),
    (r"\bminimi[sz]\w* (your |the |my |all |any )?loss(es)?\b", "minimise loss(es)"),
    (r"\bzero risk\b", "zero risk"),
    (r"\bavoid\w* (a )?loss(es)?\b", "avoid loss(es)"),
    (r"\bnever los\w*\b", "never lose"),
    # W-046 round 2: "de-risk" is a promise that risk is removed ("Adjustments are never described
    # as reducing risk by default", T1 #176).
    (r"\bde ?risk\w*\b", "de-risk"),
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


#: A negated word form ("unsafe", "unsure") is a word form of the word it negates.
_NEGATION = "un"


def find_q226_bare_words(text: str) -> list[str]:
    """Every Q226/Q230 banned word present in `text` (any word form: a token starting with it) and
    not inside an exact named exception, as its Q226 label (e.g. "guarantee*"), in
    `Q226_BARE_WORDS` order."""
    tokens = _TOKEN.findall(_without_exceptions(_prepare(text)))
    found: list[str] = []
    for word in Q226_BARE_WORDS:
        stem = word.rstrip("*")
        if any(token.startswith(stem) or token.startswith(_NEGATION + stem) for token in tokens):
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


#: ---- Sentence-level promise rules (W-046 round 2) ------------------------------------------------
#: ADR-003: "never ... promises that losses will be reduced"; Forbidden: "any promise of returns or of
#: reduced losses (T1 #74)"; "Adjustments are never described as reducing risk by default; they can
#: increase it (T1 #176)"; Q235: "in every word form". The phrase patterns above match one word ORDER
#: ("reduce your losses"), so "Your losses will be reduced" or "returns are assured" passed. These rules
#: look at a whole SENTENCE instead: a loss/risk word together with a reduction word, or a return/profit
#: word together with an assurance word, anywhere in the same sentence, is a promise.
#:
#: There is deliberately NO blanket exemption for metric labels ("maximum loss", "max loss", "loss at",
#: "P&L"): a label with no reduction/assurance word next to it already passes ("Maximum loss 8,175"),
#: and exempting the label would let "This adjustment lowers your maximum loss" through, which is the
#: exact promise T1 #176 forbids.

#: Loss/risk terms (whole tokens).
_LOSS_TERM = re.compile(r"\b(?:loss|losses|risk|risks|drawdown|drawdowns|downside|downsides)\b")

#: Reduction words, every word form (a token-start match where the stem is unambiguous).
_REDUCTION_TERM = re.compile(
    r"\b(?:reduc\w*|lower|lowers|lowered|lowering|cut|cuts|cutting|limit|limits|limited|limiting"
    r"|minimi[sz]\w*|protect\w*|shield\w*|prevent\w*|avoid\w*|eliminat\w*|decreas\w*|mitigat\w*"
    r"|curb\w*)\b"
)

#: Non-promise senses of a reduction word, blanked before the co-occurrence test. Each is a noun or
#: adjective use naming a thing (a strike, an order type, a cap on the size of a loss), never a verb
#: acting on a loss. Narrow on purpose: only the reduction word itself is blanked, so a real verb in
#: the same sentence ("buy at a lower strike to cut your loss") is still seen.
_REDUCTION_NOUN_SENSES: tuple["re.Pattern[str]", ...] = tuple(re.compile(p) for p in (
    # "lower" as a position adjective: "a lower strike", "the lower breakeven".
    r"\blower(?= (?:strike|strikes|breakeven|breakevens|leg|legs|wing|wings|bound|band|call|put|limit|limits)\b)",
    # "limit" as a noun: "no upper limit", "risk limit", "loss limit", "a limit order", "limit price".
    r"(?<=\bupper )limits?\b",
    r"(?<=\blower )limits?\b",
    r"(?<=\bloss )limits?\b",
    r"(?<=\brisk )limits?\b",
    r"\blimit(?= (?:order|orders|price|prices)\b)",
    # A stated cap, which is a factual quantity: "the loss is limited to the premium paid", "to 5 000".
    r"\blimited(?= to (?:the )?(?:premium|net debit|debit|spread width|width|\d))",
))

#: A negated loss: "won't lose", "will not lose", "can't lose", "never lose", "cannot possibly lose".
#: Tokens are letters/digits only, so "won't" arrives as "won t". Exempt only when what is not lost is
#: the user's own data/work in the app ("you will not lose your plan"), never money.
_NEGATED_LOSS = re.compile(
    r"\b(?:not|t|never|cannot)(?: \w+)? (?:lose|loses|losing|lost)\b"
    r"(?! (?:your |the |any )?(?:data|plan|plans|changes|settings)\b)"
)
_NO_CHANCE_OF_LOSS = re.compile(
    r"\b(?:(?:no|zero) (?:chance|possibility|way|danger|risk) of (?:a |any )?|without (?:a |any )?)"
    r"(?:loss|losses|losing)\b"
)
_NO_DOWNSIDE = re.compile(r"\b(?:no|zero|without) (?:any )?(?:downside|downsides|drawdown|drawdowns)\b")

#: Return/profit terms (whole tokens).
_RETURN_TERM = re.compile(r"\b(?:return|returns|profit|profits|income|incomes|gain|gains|earnings|yield|yields)\b")

#: Assurance words, every word form.
_ASSURANCE_TERM = re.compile(
    r"\b(?:assur\w*|guarantee\w*|certain|certainly|certainty|sure|surely|fixed|risk free|riskless"
    r"|definite\w*|promis\w*)\b"
)

#: "certain" as a determiner ("in certain cases") is not an assurance.
_ASSURANCE_NON_SENSES: tuple["re.Pattern[str]", ...] = (
    re.compile(r"\bcertain(?= (?:cases|conditions|situations|circumstances|scenarios|events|legs|strikes"
               r"|orders|instruments)\b)"),
)

#: A sentence ends at . ! ? ; or a line break followed by whitespace/end (so "8.5" stays one sentence).
_SENTENCE_BREAK = re.compile(r"[.!?;]+(?=\s|$)|[\r\n]+")

PROMISE_REDUCED_LOSS = "promise of reduced loss/risk"
PROMISE_NO_LOSS = "promise of no loss"
PROMISE_RETURNS = "promise of returns"


def _blank(joined: str, patterns: tuple["re.Pattern[str]", ...]) -> str:
    """`joined` with every match of every pattern (each found on the ORIGINAL text, so one blank never
    hides another's context: "lower limit" blanks both words) replaced by spaces."""
    chars = list(joined)
    for pattern in patterns:
        for match in pattern.finditer(joined):
            chars[match.start():match.end()] = " " * (match.end() - match.start())
    return "".join(chars)


def find_promise_sentences(text: str) -> list[str]:
    """Sentence-level ADR-003 promise check: the labels (in fixed order, each once) of every promise
    found in any sentence of `text`. Named Q226 exceptions ("make sure") are blanked first."""
    prepared = _without_exceptions(_prepare(text))
    found: set[str] = set()
    for sentence in _SENTENCE_BREAK.split(prepared):
        joined = " ".join(_TOKEN.findall(sentence))
        if not joined:
            continue
        reductions = _blank(joined, _REDUCTION_NOUN_SENSES)
        if _LOSS_TERM.search(joined) and _REDUCTION_TERM.search(reductions):
            found.add(PROMISE_REDUCED_LOSS)
        if _NEGATED_LOSS.search(joined) or _NO_CHANCE_OF_LOSS.search(joined) or _NO_DOWNSIDE.search(joined):
            found.add(PROMISE_NO_LOSS)
        if _RETURN_TERM.search(joined) and _ASSURANCE_TERM.search(_blank(joined, _ASSURANCE_NON_SENSES)):
            found.add(PROMISE_RETURNS)
    return [label for label in (PROMISE_REDUCED_LOSS, PROMISE_NO_LOSS, PROMISE_RETURNS) if label in found]


def find_advice_wording(text: str) -> list[str]:
    """Return every ADR-003/Q226 advice-wording hit in `text`: first the Q226 bare words (by their
    Q226 label), then the phrase families (by label), then the sentence-level promise rules (by
    label). Empty list means the text is clean."""
    joined = " ".join(tokenise(text))
    phrases = [label for pattern, label in _COMPILED_PATTERNS if pattern.search(joined)]
    return find_q226_bare_words(text) + phrases + find_promise_sentences(text)


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
#: En and em dashes (U+2013, U+2014) are punctuation, not letters: round 6 added them so the
#: execution gate's own texts ("Prices shown may be stale — confirm to continue.") pass the same
#: check. `{}` are included because this check also runs over un-rendered `MessageTemplate` text
#: (`{slot_name}` placeholders), not only final display strings — a slot's own formatted value is
#: substituted in before anything is shown to a user.
_ALLOWED_PLATFORM_TEXT = re.compile(
    r"^[A-Za-z0-9₹\s.,;:!?()'\"‘’“”%/&@#+=<>*«»_{}\u2013\u2014-]*$"
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
