"""UserFacingError: the four-part message required by REQ-065 AC-2, ADR-003 wording enforced.

REQ-065 AC-2: "Every user-facing error states what happened, the impact, what is blocked and the
next action."

ADR-003: decision-support wording only — never "you should", "best" (trade/adjustment), a
"recommended trade", "guaranteed", "risk-free", or "certain profit"; no promise of returns or of
reduced losses. Enforced by the shared checker in ``ofo.wording`` (W-024 fix round: this module used
to carry its own exact-substring denylist, which a verifier showed missed word-stem variants such as
"We guarantee returns", "sure-shot", "risk free" written with two spaces, and a zero-width space
smuggled through as a "non-empty" field — the class-level fix moved the denylist and the blank/
duplicate checks below to one shared module used by every text-facing part of this codebase).
"""

from __future__ import annotations

from dataclasses import dataclass

from ofo.wording import find_advice_wording, is_blank_after_normalising, normalise_for_wording_scan

from .classes import ErrorClass

#: Re-exported for callers that used to import the denylist directly from this module. The shared
#: checker (``ofo.wording.ADVICE_WORDING_PATTERNS``) is the single source of truth; this is a derived
#: view of its labels, not a second list to keep in sync by hand.
from ofo.wording import ADVICE_WORDING_PATTERNS

BANNED_PHRASES: tuple[str, ...] = tuple(label for _pattern, label in ADVICE_WORDING_PATTERNS)


def scan_for_banned_phrases(*texts: str) -> list[str]:
    """Return every ADR-003 advice-wording family found (delegates to
    ``ofo.wording.find_advice_wording``) across `texts`, in list order."""
    hits: list[str] = []
    for text in texts:
        hits.extend(find_advice_wording(text))
    return hits


_PART_NAMES: tuple[str, ...] = ("what_happened", "impact", "what_is_blocked", "next_action")


@dataclass(frozen=True)
class UserFacingError:
    """An error shown to a user: classified, with all four REQ-065 AC-2 parts filled.

    Construction fails closed:
    - any of the four text parts (or `code`) missing, or blank once zero-width/format characters are
      stripped and whitespace is collapsed, raises `ValueError` rather than silently defaulting;
    - any of the four text parts (or `code`) containing ADR-003 banned advice wording raises
      `ValueError`;
    - any two of the four text parts being identical once normalised (casefolded, whitespace
      collapsed) raises `ValueError` — a template that just repeats "Same." for every part is not a
      real four-part explanation.
    """

    error_class: ErrorClass
    code: str
    what_happened: str
    impact: str
    what_is_blocked: str
    next_action: str

    def __post_init__(self) -> None:
        if not isinstance(self.error_class, ErrorClass):
            raise ValueError(f"error_class must be an ErrorClass member, got {self.error_class!r}")

        if not isinstance(self.code, str) or is_blank_after_normalising(self.code):
            raise ValueError("code is required and must be non-empty (after normalising)")

        parts = {name: getattr(self, name) for name in _PART_NAMES}
        for name, value in parts.items():
            if not isinstance(value, str) or is_blank_after_normalising(value):
                raise ValueError(f"{name} is required and must be non-empty text (after normalising)")

        hits = scan_for_banned_phrases(self.code, *parts.values())
        if hits:
            raise ValueError(
                f"UserFacingError text contains banned advice wording (ADR-003): {sorted(set(hits))}"
            )

        normalised = {name: normalise_for_wording_scan(value) for name, value in parts.items()}
        seen: dict[str, str] = {}
        for name, value in normalised.items():
            if value in seen:
                raise ValueError(
                    f"UserFacingError parts '{seen[value]}' and '{name}' are identical after "
                    "normalising — the four parts must each say something distinct"
                )
            seen[value] = name

    def as_dict(self) -> dict[str, str]:
        return {
            "error_class": self.error_class.name,
            "code": self.code,
            "what_happened": self.what_happened,
            "impact": self.impact,
            "what_is_blocked": self.what_is_blocked,
            "next_action": self.next_action,
        }
