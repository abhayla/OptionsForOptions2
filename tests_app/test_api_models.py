"""W-024 round 9 part 6 fix round (review MAJOR-2): every route answers with a typed `ApiModel`, whose text fields
take only `render()`/`render_explanation()` results (REQ-065 AC-2, ADR-003 Q226)."""

from __future__ import annotations

from typing import Literal

import pytest
from fastapi.routing import APIRoute

#: FastAPI's own documentation routes (no domain text).
FRAMEWORK_ROUTES = frozenset({"openapi", "swagger_ui_html", "swagger_ui_redirect", "redoc_html"})


def test_every_route_of_the_real_app_declares_an_api_model() -> None:
    from ofo_app.api_models import ApiModel
    from ofo_app.main import create_app

    problems = []
    for route in create_app().routes:
        if getattr(route, "name", "") in FRAMEWORK_ROUTES:
            continue
        if not isinstance(route, APIRoute):  # a websocket or mounted app has no typed body: fail closed
            problems.append(f"{route!r}: not an APIRoute")
        elif not (isinstance(route.response_model, type) and issubclass(route.response_model, ApiModel)):
            problems.append(f"{route.path}: response_model {route.response_model!r}")
    assert problems == []


def test_a_free_str_field_is_refused_at_class_definition() -> None:
    from ofo_app.api_models import ApiModel

    with pytest.raises(TypeError):
        class Bad(ApiModel):
            error: str

    with pytest.raises(TypeError):
        class AlsoBad(ApiModel):
            notes: list[str]


def test_catalogue_text_takes_only_render_results() -> None:
    from ofo.errors import render
    from ofo.errors.explanations import render_explanation
    from ofo_app.api_models import ApiModel, CatalogueText, Identifier

    class Out(ApiModel):
        message: CatalogueText
        line: CatalogueText
        strategy_id: Identifier
        state: Literal["open", "closed"]

    message = render("user_input_lot_size", entered=0)
    out = Out(message=message, line=render_explanation("rule_no_condition_detail"), strategy_id="s-1", state="open")
    dumped = out.model_dump(mode="json")
    assert dumped["message"] == message.as_dict() and dumped["line"] == "no condition"
    for bad in ({"message": "Leg 1 has already expired."}, {"line": "leg expired before execution"},
                {"strategy_id": "leg expired before execution"}):
        with pytest.raises(ValueError):
            Out(**{**dict(message=message, line=render_explanation("rule_no_condition_detail"),
                          strategy_id="s-1", state="open"), **bad})


def test_mutant_model_check_off_lets_a_str_field_through(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mutation: skip the field check -> a free `str` model is accepted (so the refusal above is load-bearing)."""
    from ofo_app import api_models

    monkeypatch.setattr(api_models, "check_field_type", lambda tp, where: None)

    class Loose(api_models.ApiModel):
        error: str

    assert Loose(error="anything at all").error == "anything at all"
