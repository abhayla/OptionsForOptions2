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

import weakref
from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Any

from .classes import ErrorClass

_FIELD_NAMES: tuple[str, ...] = (
    "error_class",
    "code",
    "what_happened",
    "impact",
    "what_is_blocked",
    "next_action",
    "external_text",
)


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

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError(f"UserFacingError is immutable; cannot set {name!r}")

    def __delattr__(self, name: str) -> None:
        raise AttributeError(f"UserFacingError is immutable; cannot delete {name!r}")

    def __reduce__(self) -> Any:
        raise TypeError("UserFacingError cannot be pickled or copied; render() a new one")

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
        return _fields_of(self)["external_text"]

    def as_dict(self) -> dict[str, str | None]:
        fields = _fields_of(self)
        return {
            "error_class": fields["error_class"].name,
            "code": fields["code"],
            "what_happened": fields["what_happened"],
            "impact": fields["impact"],
            "what_is_blocked": fields["what_is_blocked"],
            "next_action": fields["next_action"],
            "external_text": fields["external_text"],
        }

    def __repr__(self) -> str:
        try:
            fields = _fields_of(self)
        except ValueError:
            return "<UserFacingError: not issued by render()>"
        return f"<UserFacingError {fields['error_class'].name} {fields['code']}>"


def _make_machinery() -> tuple[
    Callable[[], object],
    Callable[..., UserFacingError],
    Callable[[UserFacingError], Mapping[str, Any]],
]:
    """Create the token, the registry and the three functions that use them. The token and the
    registry exist only in this closure; nothing else in the process holds a reference to them."""
    token = object()
    claimed = False
    issued: "weakref.WeakKeyDictionary[UserFacingError, Mapping[str, Any]]" = weakref.WeakKeyDictionary()

    def claim_render_token() -> object:
        nonlocal claimed
        if claimed:
            raise RuntimeError("the render token was already claimed by ofo.errors.templates.render")
        claimed = True
        return token

    def build(_token: object, **fields: Any) -> UserFacingError:
        if _token is not token:
            raise ValueError("_build requires render()'s token; build a message with ofo.errors.render()")
        if set(fields) != set(_FIELD_NAMES):
            raise ValueError(f"_build requires exactly the fields {_FIELD_NAMES}, got {sorted(fields)}")
        obj = object.__new__(UserFacingError)
        issued[obj] = MappingProxyType(dict(fields))
        return obj

    def fields_of(obj: UserFacingError) -> Mapping[str, Any]:
        fields = issued.get(obj)
        if fields is None:
            raise ValueError("this UserFacingError was not issued by render() and carries no message")
        return fields

    return claim_render_token, build, fields_of


_claim_render_token, _build, _fields_of = _make_machinery()
del _make_machinery
