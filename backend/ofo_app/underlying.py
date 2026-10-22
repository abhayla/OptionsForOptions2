"""The one `Underlying` type every route and push model uses for an underlying (W-129; REQ-001 AC-1/AC-4).

The set lives in ONE home: ``ofo.instruments.catalogue.SUPPORTED_UNDERLYINGS`` (name -> exchange segment). This module
builds the API type from it, so a route cannot retype the set (a repo test also fails on a retyped ``Literal``). The
error boundary and the sockets turn any ``literal_error`` on a field named ``underlying`` into the catalogue message.

A value outside the set (including a wrong-case ``nifty``: no silent normalising) is refused with the catalogue message
``gate_underlying_unsupported`` on every route and socket. The symbol is shown only when it has a symbol shape (letters
and digits, at most 20); anything else gets the fixed input error and is never echoed.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any, Literal

from ofo.errors import UserFacing, UserFacingError, render
from ofo.instruments.catalogue import SUPPORTED_UNDERLYINGS

_SHAPE = re.compile(r"[A-Za-z][A-Za-z0-9]{0,19}")


class CatalogueRefused(UserFacing, Exception):
    """A refused call: carries only its `render()` message; the error boundary shows it (422)."""

    def __init__(self, template: str, **slots: Any) -> None:
        self.message: UserFacingError = render(template, **slots)
        super().__init__(template)


def refusal_message(value: object) -> UserFacingError:
    """The message for a value outside the set."""
    if isinstance(value, str) and _SHAPE.fullmatch(value):
        return render("gate_underlying_unsupported", symbol=value)
    return render("user_input_request_invalid")  # not even a symbol shape: the fixed input error, never echoed


def require_supported(value: str) -> str:
    """Return `value` if it is a supported underlying, else raise `CatalogueRefused` (path parameters)."""
    if value in SUPPORTED_UNDERLYINGS:
        return value
    if _SHAPE.fullmatch(value):
        raise CatalogueRefused("gate_underlying_unsupported", symbol=value)
    raise CatalogueRefused("user_input_request_invalid")


#: THE type of an underlying field in every request, response and socket model: a Literal of the home's keys (the
#: response door takes only closed types, and a Literal is one). mypy cannot read a computed Literal, so it sees Any here.
Underlying = Literal[tuple(SUPPORTED_UNDERLYINGS)]  # type: ignore[valid-type]
FIELD_NAME = "underlying"


def refusal_of(errors: Iterable[Mapping[str, Any]]) -> UserFacingError | None:
    """The catalogue message for the first unsupported-underlying problem in a pydantic error list, else None."""
    for problem in errors:
        loc = tuple(problem.get("loc", ()))
        if problem.get("type") == "literal_error" and loc and loc[-1] == FIELD_NAME:
            return refusal_message(problem.get("input"))
    return None
