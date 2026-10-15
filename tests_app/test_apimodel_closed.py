"""W-024 round 10 item 2 (issue 30 round-9 MAJOR 2): `ApiModel` is closed. A subclass holds FIELDS ONLY.

The structural door is the class body: `__pydantic_init_subclass__` refuses any subclass whose own namespace defines a
method, property, descriptor, `computed_field`, `field_serializer` or `model_serializer`, so no hook can put free text
into a response body; `model_construct` (which skips validation) raises on every ApiModel; and `_serialize` fails
closed on anything that is not a catalogue value.
"""

from __future__ import annotations

import pytest
from pydantic import computed_field, field_serializer, model_serializer


def test_a_subclass_defining_model_construct_is_refused():
    from ofo_app.api_models import ApiModel

    with pytest.raises(TypeError):
        class Bad(ApiModel):
            ok: bool

            @classmethod
            def model_construct(cls, *a, **k):  # noqa: ANN206
                return super().model_construct(*a, **k)


def test_model_construct_on_any_apimodel_raises():
    from ofo_app.api_models import ApiModel

    class Out(ApiModel):
        ok: bool

    with pytest.raises(TypeError):
        Out.model_construct(ok="free text from route code")


def test_a_computed_field_returning_str_is_refused():
    from ofo_app.api_models import ApiModel

    with pytest.raises(TypeError):
        class Bad(ApiModel):
            ok: bool

            @computed_field  # type: ignore[prop-decorator]
            @property
            def note(self) -> str:
                return "free text"


def test_a_field_serializer_is_refused():
    from ofo_app.api_models import ApiModel

    with pytest.raises(TypeError):
        class Bad(ApiModel):
            ok: bool

            @field_serializer("ok")
            def _ok(self, v: bool) -> str:
                return "free text"


def test_a_model_serializer_is_refused():
    from ofo_app.api_models import ApiModel

    with pytest.raises(TypeError):
        class Bad(ApiModel):
            ok: bool

            @model_serializer
            def _all(self) -> dict:
                return {"note": "free text"}


def test_overriding_model_dump_is_refused():
    """FastAPI serialises a returned model through model_dump(); an override would be a fourth door."""
    from ofo_app.api_models import ApiModel

    with pytest.raises(TypeError):
        class Bad(ApiModel):
            ok: bool

            def model_dump(self, *a, **k):  # noqa: ANN201
                return {"note": "free text"}


def test_a_mixin_base_carrying_a_hook_is_refused():
    from ofo_app.api_models import ApiModel

    class Mixin:
        def model_dump(self, *a, **k):  # noqa: ANN201
            return {"note": "free text"}

    with pytest.raises(TypeError):
        class Bad(Mixin, ApiModel):
            ok: bool


def test_model_copy_with_update_raises():
    from ofo_app.api_models import ApiModel

    class Out(ApiModel):
        ok: bool

    with pytest.raises(TypeError):
        Out(ok=True).model_copy(update={"ok": "free text"})


def test_a_closed_subclass_still_builds_and_serialises():
    from ofo_app.api_models import ApiModel

    class Out(ApiModel):
        ok: bool

    from ofo_app.api_models import emit

    assert emit(Out(ok=True)) == b'{"ok":true}'  # the door (W-069), not model_dump


def test_a_changed_model_config_is_refused():
    """AC-2 (W-069): a subclass's model_config equals the base exactly - extra=allow, alias generators and json_encoders
    are the settings that put free text into a body."""
    from pydantic import ConfigDict

    from ofo_app.api_models import ApiModel

    for config in (dict(extra="allow"), dict(alias_generator=str.upper), dict(json_encoders={bool: str})):
        with pytest.raises(TypeError):
            class Bad(ApiModel):
                model_config = ConfigDict(**{**dict(extra="forbid", frozen=True, arbitrary_types_allowed=True), **config})
                ok: bool


def test_a_field_alias_is_refused():
    """AC-2 (W-069): a field carries an annotation and a default only."""
    from pydantic import Field

    from ofo_app.api_models import ApiModel

    for kwargs in (dict(alias="x y"), dict(serialization_alias="x y"), dict(validation_alias="x y")):
        with pytest.raises(TypeError):
            class Bad(ApiModel):
                ok: bool = Field(default=True, **kwargs)


def test_an_enum_a_free_text_literal_and_an_open_dict_are_refused():
    """AC-2 (W-069): no Enum (its values are text), a Literal only of Identifier-pattern strs, a dict only keyed by Identifier."""
    import enum
    from typing import Literal

    from ofo_app.api_models import ApiModel, Identifier

    class Words(enum.Enum):
        A = "a"

    for tp in (Words, Literal["Leg one is done."], dict[str, int], dict[Identifier, str]):
        with pytest.raises(TypeError):
            type("Bad", (ApiModel,), {"__annotations__": {"v": tp}})

    class Good(ApiModel):
        a: Literal["ok", 3, True]
        b: dict[Identifier, int]

    assert set(Good.model_fields) == {"a", "b"}


def test_serialize_fails_closed_on_a_plain_str():
    from ofo_app.api_models import _serialize

    with pytest.raises(TypeError):
        _serialize("free text built in route code")
