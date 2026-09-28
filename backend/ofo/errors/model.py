"""UserFacingError: the four-part message required by REQ-065 AC-2, ADR-003 wording enforced.

REQ-065 AC-2: "Every user-facing error states what happened, the impact, what is blocked and the
next action."

ADR-003: decision-support wording only — never "you should", "best" (trade/adjustment), a
"recommended trade", "guaranteed", "risk-free", or "certain profit"; no promise of returns or of
reduced losses.
"""

from __future__ import annotations

from dataclasses import dataclass

from .classes import ErrorClass

# ADR-003 forbidden wording (case-insensitive substring match). This is the exact list named in
# W-024's brief ("no advice words ... ADR-003 list above"), which itself quotes ADR-003's forbidden
# phrases (collapsing "best trade"/"best adjustment"/"best" into the single broader "best" so a
# message cannot dodge the ban by rephrasing which noun follows "best").
BANNED_PHRASES: tuple[str, ...] = (
    "you should",
    "best",
    "guaranteed",
    "recommended trade",
    "risk-free",
    "certain profit",
)


def scan_for_banned_phrases(*texts: str) -> list[str]:
    """Return every ADR-003 banned phrase found (case-insensitive) across `texts`, in list order."""
    hits: list[str] = []
    for text in texts:
        lowered = text.lower()
        for phrase in BANNED_PHRASES:
            if phrase in lowered:
                hits.append(phrase)
    return hits


@dataclass(frozen=True)
class UserFacingError:
    """An error shown to a user: classified, with all four REQ-065 AC-2 parts filled.

    Construction fails closed: any of the four text parts missing/blank, or containing an
    ADR-003 banned phrase, raises `ValueError` rather than silently defaulting or truncating.
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

        if not isinstance(self.code, str) or not self.code.strip():
            raise ValueError("code is required and must be non-empty")

        parts = {
            "what_happened": self.what_happened,
            "impact": self.impact,
            "what_is_blocked": self.what_is_blocked,
            "next_action": self.next_action,
        }
        for name, value in parts.items():
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} is required and must be non-empty text")

        hits = scan_for_banned_phrases(*parts.values())
        if hits:
            raise ValueError(
                f"UserFacingError text contains banned advice wording (ADR-003): {sorted(set(hits))}"
            )

    def as_dict(self) -> dict[str, str]:
        return {
            "error_class": self.error_class.name,
            "code": self.code,
            "what_happened": self.what_happened,
            "impact": self.impact,
            "what_is_blocked": self.what_is_blocked,
            "next_action": self.next_action,
        }
