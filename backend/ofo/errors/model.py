"""UserFacingError: the four-part message required by REQ-065 AC-2, ADR-003 wording enforced.

REQ-065 AC-2: "Every user-facing error states what happened, the impact, what is blocked and the
next action."

Round 3 (RCA): rounds 1-2 accepted four free-text strings at runtime, so any caller could show any
sentence, and a denylist over free text can never list every phrasing. Round 3's fix is structural:
`UserFacingError` has NO public constructor. The only way to build one is
`ofo.errors.templates.render(template_id, **slots)`, which fills a fixed, CI-scanned template with
typed, validated slot values (`ofo.errors.slots`). Calling `UserFacingError(...)` directly — with
free text or anything else — always raises `ValueError`.
"""

from __future__ import annotations

from dataclasses import dataclass

from .classes import ErrorClass

_PART_NAMES: tuple[str, ...] = ("what_happened", "impact", "what_is_blocked", "next_action")

#: Module-private sentinel (round-4 fix, REQ-065/W-024 second parked round): the ONE token that
#: `_build` will accept. It is created here and imported ONLY by `ofo.errors.templates` (`render`'s
#: home module); nothing else in the codebase has a reference to it, so nothing else can call
#: `_build` successfully even though `_build` itself is not name-mangled. The AST test
#: (`tests/errors/test_error_catalogue.py`) additionally flags any `_build(`/`object.__new__(...)`
#: call, or any `UserFacingError` subclass, outside this module and `templates.py`.
_RENDER_TOKEN = object()


@dataclass(frozen=True)
class UserFacingError:
    """An error shown to a user: classified, with all four REQ-065 AC-2 parts filled, plus an
    optional `external_text` (a broker/vendor message shown verbatim in its own labelled field —
    never scanned for our wording, never re-worded).

    No public constructor: `UserFacingError(...)` always raises `ValueError`. The only way to build
    an instance is `ofo.errors.templates.render(template_id, **slots)`.
    """

    error_class: ErrorClass
    code: str
    what_happened: str
    impact: str
    what_is_blocked: str
    next_action: str
    external_text: str | None = None

    def __post_init__(self) -> None:
        raise ValueError(
            "UserFacingError has no public constructor (W-024 round 3): build one with "
            "ofo.errors.templates.render(template_id, **slots), never by passing free text directly"
        )

    def __init_subclass__(cls, **kwargs: object) -> None:
        """Round-4 fix: a subclass could otherwise define its own `__init__`/fields and bypass
        `__post_init__`'s refusal entirely. There is no legitimate reason to subclass a message
        carrier that has exactly one builder (`render`); refuse at class-definition time."""
        raise TypeError(
            "UserFacingError must not be subclassed (W-024): the only way to build an instance is "
            "ofo.errors.templates.render(template_id, **slots)"
        )

    @classmethod
    def _build(
        cls,
        *,
        _token: object,
        error_class: ErrorClass,
        code: str,
        what_happened: str,
        impact: str,
        what_is_blocked: str,
        next_action: str,
        external_text: str | None = None,
    ) -> "UserFacingError":
        """Construct an instance WITHOUT running `__post_init__` (bypasses the free-text refusal
        above). Round-4 fix: requires `_token` to be this module's private `_RENDER_TOKEN` object,
        which only `ofo.errors.templates` imports — so even a caller that reaches `_build` directly
        (bypassing the AST guard) cannot supply a valid token from outside this package. Called only
        from `ofo.errors.templates.render`, after every slot has already been validated and every
        part has already come from a CI-scanned template — never called with caller-supplied free
        text."""
        if _token is not _RENDER_TOKEN:
            raise ValueError(
                "UserFacingError._build requires the render()-only sentinel token; build an "
                "instance with ofo.errors.templates.render(template_id, **slots) instead"
            )
        obj = object.__new__(cls)
        object.__setattr__(obj, "error_class", error_class)
        object.__setattr__(obj, "code", code)
        object.__setattr__(obj, "what_happened", what_happened)
        object.__setattr__(obj, "impact", impact)
        object.__setattr__(obj, "what_is_blocked", what_is_blocked)
        object.__setattr__(obj, "next_action", next_action)
        object.__setattr__(obj, "external_text", external_text)
        return obj

    def as_dict(self) -> dict[str, str | None]:
        return {
            "error_class": self.error_class.name,
            "code": self.code,
            "what_happened": self.what_happened,
            "impact": self.impact,
            "what_is_blocked": self.what_is_blocked,
            "next_action": self.next_action,
            "external_text": self.external_text,
        }
