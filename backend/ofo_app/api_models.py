"""Typed API response models (W-024 round 9 part 6 fix round, review MAJOR-2; REQ-065 AC-2, ADR-003 Q226).

Every route declares a `response_model` that is an `ApiModel` (asserted over the real app's routes by
tests_app/test_api_models.py). An `ApiModel` cannot hold free text: at class definition every field's type is checked,
and a plain `str` (or anything not listed below) raises TypeError. Allowed leaves:
- `CatalogueText`: a `render()` result (`UserFacingError`, shown as its four parts) or a `render_explanation()`
  result (`ExplanationText`); a plain string is refused at validation, so text built in route code cannot pass;
- `Identifier`: a closed token (letters, digits, `_ - . :`), at most 64 characters and no space, so it can never
  carry a sentence;
- `Literal[...]` of strings, `bool`, `int`, `Decimal` (serialized as a string, project rule), `datetime`, `date`,
  `Enum` subclasses, nested `ApiModel`s, and `list`/`tuple`/`Optional` of those.
So string building in route code is harmless: it cannot reach a response body.
"""

from __future__ import annotations

import datetime
import enum
import types
import typing
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, PlainSerializer, PlainValidator, StringConstraints

from ofo.errors import UserFacingError
from ofo.errors.explanations import ExplanationText


def _catalogue_only(value: object) -> UserFacingError | ExplanationText:
    if type(value) is UserFacingError or type(value) is ExplanationText:
        return value  # type: ignore[return-value]
    raise ValueError("a text field takes only a render() or render_explanation() result, never a plain string")


def _serialize(value: UserFacingError | ExplanationText) -> object:
    return value.as_dict() if type(value) is UserFacingError else str.__str__(value)


CatalogueText = Annotated[object, PlainValidator(_catalogue_only), PlainSerializer(_serialize)]
Identifier = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_\-.:]{1,64}$")]
Money = Annotated[Decimal, PlainSerializer(lambda v: str(v), return_type=str)]

_LEAVES: tuple[type, ...] = (bool, int, Decimal, datetime.datetime, datetime.date)


def check_field_type(tp: Any, where: str) -> None:
    """Raise TypeError unless `tp` is one of the allowed shapes (module docstring)."""
    if tp is CatalogueText or tp is Identifier or tp is Money:
        return
    origin = typing.get_origin(tp)
    if origin is Annotated:
        raise TypeError(f"{where}: only CatalogueText, Identifier and Money may be Annotated types")
    if origin is Literal:
        if all(isinstance(a, (str, int, bool)) for a in typing.get_args(tp)):
            return
        raise TypeError(f"{where}: Literal values must be str/int/bool")
    if origin in (list, tuple, typing.Union, types.UnionType):
        for arg in typing.get_args(tp):
            if arg is not type(None) and arg is not Ellipsis:
                check_field_type(arg, where)
        return
    if isinstance(tp, type):
        if issubclass(tp, ApiModel) or issubclass(tp, enum.Enum) or tp in _LEAVES:
            return
    raise TypeError(f"{where}: {tp!r} is not allowed in an API response (free text must be CatalogueText)")


class ApiModel(BaseModel):
    """Base of every response model: closed, frozen, and free-text-proof by construction."""

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:
        super().__pydantic_init_subclass__(**kwargs)
        for name, info in cls.model_fields.items():
            annotation = info.annotation
            if info.metadata:  # Annotated[...] was unpacked: compare the original alias by identity
                annotation = Annotated[(annotation, *info.metadata)]  # type: ignore[valid-type]
                if annotation != CatalogueText and annotation != Identifier and annotation != Money:
                    raise TypeError(f"{cls.__name__}.{name}: only CatalogueText, Identifier and Money may be "
                                    f"Annotated types")
                continue
            check_field_type(annotation, f"{cls.__name__}.{name}")
