"""UserFacingError: the four-part message required by REQ-065 AC-2, built only by `render()`.

REQ-065 AC-2: "Every user-facing error states what happened, the impact, what is blocked and the
next action." Spec basis for the construction rule: owner decision Q226 ("every platform message
comes from a fixed, reviewed template catalogue with typed slots").

Round 5 (issue #30) closes the three ways round 3's verifier built a message without `render()`:
- `_build`: no longer a method of the class. It is a module function that refuses any token but the
  one `render()` claimed at import; the token lives only inside a closure and can be claimed ONCE
  (`_claim_render_token()` raises RuntimeError afterwards), so no other code can obtain it.
- `object.__new__(UserFacingError)`: the class keeps NO text on the instance. Every field is a
  read-only property looked up in a registry that only `_build` writes (held in a closure). An
  instance made any other way has no entry: every read raises ValueError, and it cannot be given
  text (`__slots__` holds only `__weakref__`, and properties have no setter).
- subclassing: `__init_subclass__` raises TypeError; `UserFacingError(...)` / `__new__` raise
  TypeError.
The AST test in tests/errors/test_error_catalogue.py flags any source-level reach for these
internals outside this package.
"""

from __future__ import annotations

import re
import weakref
from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Any

from ofo import wording as _wording

from .classes import ErrorClass
from .slots import ExternalText


def _external_text(fields: Mapping[str, Any]) -> str | None:
    """The labelled quote of Zerodha's or the user's own words, or None (Q226)."""
    external = fields["external"]
    return None if external is None else ExternalText.format(external)

class UserFacingError:
    """An error shown to a user: classified, with all four REQ-065 AC-2 parts filled, plus an
    optional `external_text` (Zerodha's or the user's own words, quoted in a labelled field).

    No public constructor: build one with `ofo.errors.render(template_id, **slots)`.
    """

    __slots__ = ("__weakref__",)

    def __new__(cls, *args: object, **kwargs: object) -> "UserFacingError":
        raise TypeError(
            "UserFacingError has no public constructor (W-024): build one with "
            "ofo.errors.render(template_id, **slots)"
        )

    def __init_subclass__(cls, **kwargs: object) -> None:
        raise TypeError(
            "UserFacingError must not be subclassed (W-024): the only way to build an instance is "
            "ofo.errors.render(template_id, **slots)"
        )

    @property
    def error_class(self) -> ErrorClass:
        return _fields_of(self)["error_class"]

    @property
    def code(self) -> str:
        return _fields_of(self)["code"]

    @property
    def what_happened(self) -> str:
        return _fields_of(self)["what_happened"]

    @property
    def impact(self) -> str:
        return _fields_of(self)["impact"]

    @property
    def what_is_blocked(self) -> str:
        return _fields_of(self)["what_is_blocked"]

    @property
    def next_action(self) -> str:
        return _fields_of(self)["next_action"]

    @property
    def external_text(self) -> str | None:
        return _external_text(_fields_of(self))

    def as_dict(self) -> dict[str, str | None]:
        fields = _fields_of(self)
        return {
            "error_class": fields["error_class"].name,
            "code": fields["code"],
            "what_happened": fields["what_happened"],
            "impact": fields["impact"],
            "what_is_blocked": fields["what_is_blocked"],
            "next_action": fields["next_action"],
            "external_text": _external_text(fields),
        }

    def __repr__(self) -> str:
        try:
            fields = _fields_of(self)
        except ValueError:
            return "<UserFacingError: not issued by render()>"
        return f"<UserFacingError {fields['error_class'].name} {fields['code']}>"


_PART_NAMES: tuple[str, ...] = ("what_happened", "impact", "what_is_blocked", "next_action")
_FIELD_NAMES: frozenset[str] = frozenset({"error_class", "code", "external", *_PART_NAMES})


def _checked(fields: Mapping[str, Any]) -> Mapping[str, Any]:
    """Every check a message must pass, run by the builder on every build AND by `_fields_of` on
    every read (Q230: "The checks run inside the one function that builds a message, so no
    construction route skips them"). Returns the fields as a read-only mapping.

    - exactly the seven fields; `error_class` an `ErrorClass`; `code` that class's name + "_" + 3
      digits (so a code carries no words and matches its class);
    - the four REQ-065 AC-2 parts: each passes `ofo.wording.check_platform_text` (exact str, not
      blank, Latin only, no ADR-003/Q226/Q230 wording), and no two say the same thing;
    - `external`: None or an `ExternalText` (Zerodha's or the user's own words, quoted with its
      label, never scanned: Q226).
    """
    fields = dict(fields)  # one copy, checked and then stored: no value can change between the two
    names = set(fields)
    if names != _FIELD_NAMES:
        raise TypeError(
            f"a message needs exactly the fields {sorted(_FIELD_NAMES)}: "
            f"missing {sorted(_FIELD_NAMES - names)}, unexpected {sorted(names - _FIELD_NAMES)}"
        )
    error_class = fields["error_class"]
    if type(error_class) is not ErrorClass:
        raise TypeError(f"error_class must be an ErrorClass, got {type(error_class).__name__}")
    code = fields["code"]
    if type(code) is not str or not re.fullmatch(rf"{error_class.name}_[0-9]{{3}}", code):
        raise ValueError(f"code must be {error_class.name}_ + 3 digits, got {code!r}")
    seen: dict[str, str] = {}
    for name in _PART_NAMES:
        text = fields[name]
        _wording.check_platform_text(text, f"UserFacingError.{name}")
        key = _wording.normalise_for_duplicate_check(text)
        if key in seen:
            raise ValueError(f"UserFacingError.{name} is a duplicate of {seen[key]}: {text!r}")
        seen[key] = name
    external = fields["external"]
    if external is not None:
        ExternalText.validate(external)
    return MappingProxyType(fields)


#: ADR-056 decision (1): "a runtime identity check of the wording checker". The functions of
#: `ofo.wording` that a message's check runs (directly or through each other), and the data they
#: read. Captured at import; compared on every build and every read.
_CHECKER_FUNCTIONS: tuple[str, ...] = (
    "check_platform_text", "find_advice_wording", "find_q226_bare_words", "tokenise", "_prepare",
    "_without_exceptions", "is_blank_after_normalising", "normalise_for_wording_scan",
    "is_nfkc_clean_latin", "normalise_for_duplicate_check", "_make_verifier",
    "_make_frozen_module_class",
)
_CHECKER_DATA: tuple[str, ...] = (
    "Q226_BARE_WORDS", "Q226_NAMED_EXCEPTIONS", "ADVICE_WORDING_PATTERNS", "_COMPILED_PATTERNS",
    "_TOKEN", "_EXCEPTION_PATTERNS", "_NEGATION", "_FORMAT_CATEGORY", "_ALLOWED_PLATFORM_TEXT",
    "_SELF_CHECKED_FUNCTIONS", "_SELF_CHECKED_DATA", "_verify_checker", "_FrozenModule",
)


CheckerChanged = _wording.CheckerChanged


def _make_identity_check() -> Callable[[], None]:
    """Caller-side second layer (fix round 1): `ofo.wording` checks itself on every public call
    (`ofo.wording.CheckerChanged`), and this builder checks again, because a swapped ENTRY POINT
    (`check_platform_text` itself) never runs the original's own check. Captures every checker
    function object AND its `__code__` object and every checker data object at import; the returned
    function raises `CheckerChanged` (fail closed) when any differs. Values live only in this closure.
    This module calls the checker only as `_wording.<fn>(...)` (no name imported from ofo.wording)."""
    functions = tuple((name, getattr(_wording, name)) for name in _CHECKER_FUNCTIONS)
    codes = tuple((name, fn.__code__) for name, fn in functions)
    data = tuple((name, getattr(_wording, name)) for name in _CHECKER_DATA)
    missing = object()

    def verify() -> None:
        for (name, fn), (_, code) in zip(functions, codes):
            if getattr(_wording, name, missing) is not fn:
                raise CheckerChanged(f"ofo.wording.{name} is not the function captured at import")
            if fn.__code__ is not code:
                raise CheckerChanged(f"ofo.wording.{name}.__code__ is not the code captured at import")
        for name, value in data:
            if getattr(_wording, name, missing) is not value:
                raise CheckerChanged(f"ofo.wording.{name} is not the object captured at import")

    return verify


def _make_machinery() -> tuple[
    Callable[[], object],
    Callable[..., UserFacingError],
    Callable[[UserFacingError], Mapping[str, Any]],
]:
    """Create the token, the registry and the three functions that use them. The token and the
    registry exist only in this closure. Round 6 (issue #30): the token is no longer what keeps a
    message clean: `inspect.getclosurevars(render)` hands out both the builder and the token, so
    the builder runs every check itself, and so does every read."""
    token = object()
    claimed = False
    issued: "weakref.WeakKeyDictionary[UserFacingError, Mapping[str, Any]]" = weakref.WeakKeyDictionary()
    checked = _checked
    verify_checker = _make_identity_check()

    def claim_render_token() -> object:
        nonlocal claimed
        if claimed:
            raise RuntimeError("the render token was already claimed by ofo.errors.templates.render")
        claimed = True
        return token

    def build(
        _token: object,
        *,
        error_class: ErrorClass,
        code: str,
        what_happened: str,
        impact: str,
        what_is_blocked: str,
        next_action: str,
        external: ExternalText | None,
    ) -> UserFacingError:
        if _token is not token:
            raise ValueError("_build requires render()'s token; build a message with ofo.errors.render()")
        verify_checker()
        fields = checked({
            "error_class": error_class,
            "code": code,
            "what_happened": what_happened,
            "impact": impact,
            "what_is_blocked": what_is_blocked,
            "next_action": next_action,
            "external": external,
        })
        obj = object.__new__(UserFacingError)
        issued[obj] = fields
        return obj

    def fields_of(obj: UserFacingError) -> Mapping[str, Any]:
        fields = issued.get(obj)
        if fields is None:
            raise ValueError("this UserFacingError was not issued by render() and carries no message")
        # Re-checked on every read: an entry written into the registry by any other route (it is
        # reachable with getclosurevars) is refused before a user sees it.
        verify_checker()
        return checked(fields)

    return claim_render_token, build, fields_of


_claim_render_token, _build, _fields_of = _make_machinery()
del _make_machinery, _make_identity_check
