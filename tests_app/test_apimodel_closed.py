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

    assert Out(ok=True).model_dump(mode="json") == {"ok": True}


def test_serialize_fails_closed_on_a_plain_str():
    from ofo_app.api_models import _serialize

    with pytest.raises(TypeError):
        _serialize("free text built in route code")
