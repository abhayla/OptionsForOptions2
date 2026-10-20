"""Typed API response models (W-024 round 9 part 6 fix round, review MAJOR-2; REQ-065 AC-2, ADR-003 Q226).

Every route declares a `response_model` that is an `ApiModel` (asserted over the real app's routes by
tests_app/test_api_models.py). An `ApiModel` cannot hold free text: at class definition every field's type is checked,
and a plain `str` (or anything not listed below) raises TypeError. Allowed leaves:
- `CatalogueText`: a `render()` result (`UserFacingError`, shown as its four parts) or a `render_explanation()`
  result (`ExplanationText`); a plain string is refused at validation, so text built in route code cannot pass;
- `InstrumentId`: a closed `SEGMENT:digits` pattern (`NSE_FO:44595`);
- `dict[Identifier, <allowed>]`: a map whose keys are closed identifiers (a key can never carry a sentence);
- `Identifier`: a closed token (letters, digits, `_ - .`; no `:` or `=`), at most 64 characters and no space, so it can never
  carry a sentence;
- `Literal[...]` of Identifier-pattern strings, `bool` and `int` (no Enum: its values are free text), `Decimal`
  (written as a plain string, project rule), timezone-aware `datetime`, `date`, nested `ApiModel`s, `dict[Identifier, X]`
  and `list`/`tuple`/`Optional` of those;
- `DisplayRupees` (EXECUTE-REVIEW): a Decimal the door writes with the engine's one money formatter (``₹2,40,000.00``);
- `BasketPost` (W-095): the exact Kite basket form text, made only from the sealed basket (`basket_post.py`).
So string building in route code is harmless: it cannot reach a response body.

The class check above is an early warning, not the guarantee (W-069, issue #148). The guarantee is `emit`: the ONE
function that writes a response body. It never calls `model_dump` or pydantic's encoder; it walks the instance by each
field's declared annotation and writes only the leaf types above, each matched on its exact `type()`; keys are the
declared field names only; extra fields, aliases or a changed model config refuse the whole response (`DoorRefused`).
"""

from __future__ import annotations

import datetime
import json
import logging
import re
import types
import typing
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, PlainSerializer, PlainValidator, StringConstraints

from ofo.engine.display import format_rupees
from ofo.errors import UserFacingError
from ofo.errors.explanations import ExplanationText
from ofo_app.basket_post import BasketPost
from ofo_app.closed_namespace import own_names

log = logging.getLogger("ofo_app.main")


def _catalogue_only(value: object) -> UserFacingError | ExplanationText:
    if type(value) is UserFacingError or type(value) is ExplanationText:
        return value  # type: ignore[return-value]
    raise ValueError("a text field takes only a render() or render_explanation() result, never a plain string")


def _serialize(value: UserFacingError | ExplanationText) -> object:
    """Fail closed (round 10 item 2): only a catalogue value is written; anything else raises, never passes."""
    if type(value) is UserFacingError:
        return value.as_dict()
    if type(value) is ExplanationText:
        return str.__str__(value)
    raise TypeError(f"a CatalogueText field holds {type(value).__name__}, not a render()/render_explanation() result")


CatalogueText = Annotated[object, PlainValidator(_catalogue_only), PlainSerializer(_serialize)]
#: Round 10 item 4: a closed pattern - letters, digits, `_ - .` only (no `:`, no `=`, no whitespace), so a
#: `key:value` or `key=value` pair (e.g. `access_token:...`) can never pass as an id; at most IDENTIFIER_MAX characters.
IDENTIFIER_MAX = 64
Identifier = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_\-.]{1,%d}$" % IDENTIFIER_MAX)]
#: An instrument id as the exchange segment and token, `NSE_FO:44595` (W-066): capitals and `_` before one `:`, digits after;
#: no space or other character, so it can never carry a sentence.
InstrumentId = Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z_]{0,15}:[0-9]{1,12}$")]
Money = Annotated[Decimal, PlainSerializer(lambda v: format(v, "f"), return_type=str)]
#: EXECUTE-REVIEW (ADR-008): a rupee amount the SCREEN shows. The model holds the Decimal; the door writes it through the
#: engine's one money formatter (``ofo.engine.display.format_rupees``: lakh grouping, true minus, paisa), so no
#: browser or route code builds the text.
DisplayRupees = Annotated[Decimal, PlainSerializer(format_rupees, return_type=str)]
_IDENTIFIER = re.compile(r"[A-Za-z0-9_\-.]{1,%d}" % IDENTIFIER_MAX)  # the same pattern, re-checked at the door
_INSTRUMENT_ID = re.compile(r"[A-Z][A-Z_]{0,15}:[0-9]{1,12}")  # InstrumentId's pattern, re-checked at the door
_FIELD_NAME = re.compile(r"[a-z][a-z0-9_]{0,63}")  # a declared field name is the only key a body may carry

_LEAVES: tuple[type, ...] = (bool, int, Decimal, datetime.datetime, datetime.date, BasketPost)


def _closed_literal(tp: Any) -> bool:
    """Literal arguments are exact ints, bools or Identifier-pattern strs (a sentence can never be one)."""
    return all(type(a) in (int, bool) or (type(a) is str and _IDENTIFIER.fullmatch(a) is not None)
               for a in typing.get_args(tp))


def check_field_type(tp: Any, where: str) -> None:
    """Raise TypeError unless `tp` is one of the allowed shapes (module docstring)."""
    if tp == CatalogueText or tp == Identifier or tp == Money or tp == InstrumentId or tp == DisplayRupees:
        return
    origin = typing.get_origin(tp)
    if origin is Annotated:
        raise TypeError(f"{where}: only CatalogueText, Identifier, InstrumentId, Money and DisplayRupees may be Annotated types")
    if origin is Literal:
        if _closed_literal(tp):
            return
        raise TypeError(f"{where}: Literal values must be ints, bools or Identifier-pattern strs")
    if origin is dict:
        key, value = typing.get_args(tp)
        if key != Identifier:
            raise TypeError(f"{where}: a dict key must be an Identifier")
        check_field_type(value, where)
        return
    if origin in (list, tuple, typing.Union, types.UnionType):
        for arg in typing.get_args(tp):
            if arg is not type(None) and arg is not Ellipsis:
                check_field_type(arg, where)
        return
    if isinstance(tp, type):
        if issubclass(tp, ApiModel) or tp in _LEAVES:
            return
    raise TypeError(f"{where}: {tp!r} is not allowed in an API response (free text must be CatalogueText)")


#: Everything pydantic itself puts in a subclass's own namespace, plus the class-statement dunders. A subclass body may
#: hold field annotations, `model_config` and a docstring ONLY (round 10 item 2): any other entry - a method, property,
#: `computed_field`, `field_serializer`, `model_serializer`, a `model_dump`/`model_construct` override, a descriptor -
#: is refused at class creation. A closed allowlist of names, so an unforeseen hook fails closed.
_PYDANTIC_NAMESPACE = frozenset({
    "__abstractmethods__", "__annotations__", "__class_vars__", "__doc__", "__firstlineno__", "__hash__", "__module__",
    "__qualname__", "__orig_bases__", "__parameters__", "__private_attributes__", "__pydantic_complete__",
    "__pydantic_computed_fields__", "__pydantic_core_schema__", "__pydantic_custom_init__", "__pydantic_decorators__",
    "__pydantic_fields__", "__pydantic_generic_metadata__", "__pydantic_parent_namespace__", "__pydantic_post_init__",
    "__pydantic_serializer__", "__pydantic_setattr_handlers__", "__pydantic_validator__", "__signature__",
    "__static_attributes__", "_abc_impl", "model_config", "__annotate__", "__annotate_func__",
    "__annotations_cache__",
})


def _has_alias(info: Any) -> bool:
    return info.alias is not None or info.serialization_alias is not None or info.validation_alias is not None


def _refuse_open_doors(cls: type) -> None:
    """Raise TypeError unless `cls` is a closed ApiModel: data fields only, no hook that can write a response body."""
    for base in cls.__mro__[1:]:
        if base in ApiModel.__mro__:
            continue
        if not (isinstance(base, type) and issubclass(base, ApiModel)):
            raise TypeError(f"{cls.__name__}: an ApiModel inherits only from ApiModel classes, not {base.__name__}")
    extra = [name for name in own_names(cls) if name not in _PYDANTIC_NAMESPACE]
    if extra:
        raise TypeError(f"{cls.__name__}: an ApiModel body holds fields only; refused {extra} (no method, property, "
                        f"computed_field, serializer or override may shape a response)")
    if cls.model_config != ApiModel.model_config:  # type: ignore[attr-defined]
        raise TypeError(f"{cls.__name__}: an ApiModel's model_config is the base one exactly (no extra=allow, alias "
                        f"generator, json_encoders or other setting may shape a response)")
    aliased = [name for name, info in cls.model_fields.items() if _has_alias(info)]  # type: ignore[attr-defined]
    if aliased:
        raise TypeError(f"{cls.__name__}: a field carries an annotation and a default only, never an alias {aliased}")
    d = cls.__pydantic_decorators__  # type: ignore[attr-defined]
    hooks = {"computed_fields": d.computed_fields, "field_serializers": d.field_serializers,
             "model_serializers": d.model_serializers, "field_validators": d.field_validators,
             "model_validators": d.model_validators, "validators": d.validators, "root_validators": d.root_validators}
    if any(hooks.values()):
        raise TypeError(f"{cls.__name__}: an ApiModel has no pydantic decorators "
                        f"({[k for k, v in hooks.items() if v]})")


class ApiModel(BaseModel):
    """Base of every response model: closed, frozen, and free-text-proof by construction."""

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)

    @classmethod
    def model_construct(cls, *args: Any, **kwargs: Any) -> Any:  # noqa: D102
        raise TypeError(f"{cls.__name__}.model_construct skips validation; an ApiModel is built only by validation")

    def model_copy(self, *args: Any, **kwargs: Any) -> Any:  # noqa: D102
        raise TypeError(f"{type(self).__name__}.model_copy(update=...) skips validation; build a new ApiModel instead")

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:
        super().__pydantic_init_subclass__(**kwargs)
        _refuse_open_doors(cls)
        for name, info in cls.model_fields.items():
            annotation = info.annotation
            if info.metadata:  # Annotated[...] was unpacked: compare the original alias by identity
                annotation = Annotated[(annotation, *info.metadata)]  # type: ignore[valid-type]
                if annotation not in (CatalogueText, Identifier, InstrumentId, Money, DisplayRupees):
                    raise TypeError(f"{cls.__name__}.{name}: only CatalogueText, Identifier, InstrumentId, Money "
                                    f"and DisplayRupees may be Annotated types")
                continue
            check_field_type(annotation, f"{cls.__name__}.{name}")


# ---- the door: the one serializer ---------------------------------------------------------------------------------------

class DoorRefused(Exception):
    """The response could not be written from closed value types. The message names the field path and the type name,
    never the value."""


_TOKEN = object()


class Emitted(bytes):
    """A response body made by `emit` (or `emit_message`) and by nothing else: `ClosedResponse` takes only this type."""

    __slots__ = ()

    def __new__(cls, data: bytes, *, _token: object = None) -> Emitted:
        if _token is not _TOKEN:
            raise TypeError("Emitted bytes are made only by ofo_app.api_models.emit")
        return super().__new__(cls, data)


def _refuse(path: str, value: object, slot: str) -> DoorRefused:
    return DoorRefused(f"{path}: {type(value).__name__} is not a closed {slot} value")


def _catalogue_leaf(value: object, path: str) -> object:
    if type(value) is UserFacingError:
        parts = value.as_dict()
        if all(type(k) is str and (v is None or type(v) is str) for k, v in parts.items()):
            return parts
        raise _refuse(path, value, "catalogue text")
    if type(value) is ExplanationText:
        return str.__str__(value)
    raise _refuse(path, value, "catalogue text")


def _datetime_text(value: object, path: str) -> str:
    if type(value) is datetime.datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise _refuse(path, value, "timezone-aware datetime")
        text = value.isoformat()
        return text[:-6] + "Z" if text.endswith("+00:00") else text
    if type(value) is datetime.date:
        return value.isoformat()
    raise _refuse(path, value, "datetime")


def _walk(value: object, tp: Any, path: str, exclude_unset: bool) -> object:
    """The value as JSON-ready data, only when its exact type fits the declared slot `tp`."""
    if tp == CatalogueText:
        return _catalogue_leaf(value, path)
    if tp == Identifier:
        if type(value) is str and _IDENTIFIER.fullmatch(value):
            return value
        raise _refuse(path, value, "Identifier")
    if tp == InstrumentId:
        if type(value) is str and _INSTRUMENT_ID.fullmatch(value):
            return value
        raise _refuse(path, value, "InstrumentId")
    if tp == Money:
        if type(value) is Decimal and value.is_finite():
            return format(value, "f")
        raise _refuse(path, value, "Money")
    if tp == DisplayRupees:
        if type(value) is Decimal and value.is_finite():
            return format_rupees(value)
        raise _refuse(path, value, "DisplayRupees")
    if tp is BasketPost:  # W-095: the exact Kite form text, only from the sealed basket (basket_post.py)
        if type(value) is BasketPost:
            return value.as_form()
        raise _refuse(path, value, "BasketPost")
    origin = typing.get_origin(tp)
    if origin is Literal:
        if any(type(a) is type(value) and a == value for a in typing.get_args(tp)) and (
                type(value) is not str or _IDENTIFIER.fullmatch(value)):
            return value
        raise _refuse(path, value, "Literal")
    if origin in (list, tuple):
        if type(value) is not origin:
            raise _refuse(path, value, origin.__name__)
        args = typing.get_args(tp)
        if origin is tuple and not (len(args) == 2 and args[1] is Ellipsis):
            if len(args) != len(value):
                raise _refuse(path, value, "tuple")
            return [_walk(v, a, f"{path}[{i}]", exclude_unset) for i, (v, a) in enumerate(zip(value, args))]
        return [_walk(v, args[0], f"{path}[{i}]", exclude_unset) for i, v in enumerate(value)]
    if origin in (typing.Union, types.UnionType):
        members = typing.get_args(tp)
        if value is None and type(None) in members:
            return None
        for member in members:
            if member is type(None):
                continue
            try:
                return _walk(value, member, path, exclude_unset)
            except DoorRefused:
                continue
        raise _refuse(path, value, "union")
    if origin is dict:
        key_type, value_type = typing.get_args(tp)
        if key_type != Identifier or type(value) is not dict:
            raise _refuse(path, value, "dict")
        if not all(type(k) is str and _IDENTIFIER.fullmatch(k) for k in value):
            raise DoorRefused(f"{path}: a dict key is not an Identifier")
        return {k: _walk(v, value_type, f"{path}{{}}", exclude_unset) for k, v in value.items()}
    if tp is bool or tp is int:
        if type(value) is tp:
            return value
        raise _refuse(path, value, tp.__name__)
    if tp is datetime.datetime or tp is datetime.date:
        if type(value) is tp:
            return _datetime_text(value, path)
        raise _refuse(path, value, tp.__name__)
    if isinstance(tp, type) and issubclass(tp, ApiModel):
        if type(value) is not tp:
            raise _refuse(path, value, tp.__name__)
        return _model_tree(value, exclude_unset, path)
    raise _refuse(path, value, "annotation")


def _field_type(info: Any) -> Any:
    return Annotated[(info.annotation, *info.metadata)] if info.metadata else info.annotation  # type: ignore[valid-type]


_NO_VALUE = object()


def _model_tree(model: ApiModel, exclude_unset: bool, path: str) -> dict[str, object]:
    cls = type(model)
    if cls.model_config != ApiModel.model_config:
        raise DoorRefused(f"{path}: the model config is not the base ApiModel config")
    if model.__pydantic_extra__:
        raise DoorRefused(f"{path}: the model carries extra fields")
    out: dict[str, object] = {}
    for name, info in cls.model_fields.items():
        if _has_alias(info):
            raise DoorRefused(f"{path}.{name}: the field carries an alias")
        if exclude_unset and name not in model.model_fields_set:
            continue
        if not _FIELD_NAME.fullmatch(name):
            raise DoorRefused(f"{path}: a field name is not a closed key")
        value = getattr(model, name, _NO_VALUE)
        if value is _NO_VALUE:
            raise DoorRefused(f"{path}.{name}: the field holds no value")
        out[name] = _walk(value, _field_type(info), f"{path}.{name}", exclude_unset)
    return out


def _encode(tree: object) -> Emitted:
    return Emitted(json.dumps(tree, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8"),
                   _token=_TOKEN)


def emit(model: ApiModel, exclude_unset: bool = False) -> Emitted:
    """THE serializer of every response body: walks `model` by its declared annotations and writes closed value types
    only. Never `model_dump`, `jsonable_encoder` or pydantic's JSON encoder. Raises `DoorRefused` (logging the field
    path and type name, never the value) for anything else."""
    try:
        if not isinstance(model, ApiModel):
            raise _refuse(type(model).__name__, model, "ApiModel")
        return _encode(_model_tree(model, exclude_unset, type(model).__name__))
    except DoorRefused as exc:
        log.error("response door refused: %s", exc)
        raise


def emit_message(message: UserFacingError) -> Emitted:
    """An error body: the flat four-part catalogue message (`as_dict()`), the one other shape the door writes."""
    try:
        if type(message) is not UserFacingError:
            raise _refuse("message", message, "catalogue text")
        return _encode(_catalogue_leaf(message, "message"))
    except DoorRefused as exc:
        log.error("response door refused: %s", exc)
        raise
