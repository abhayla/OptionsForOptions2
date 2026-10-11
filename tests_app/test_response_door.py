"""AC-2 (REQ-065; ADR-003 Q226; issue #148, W-069): one closed response door.

Every API response body is serialized by `ofo_app.api_models.emit`, which writes only closed value types, so no pydantic
model setting (extra fields, aliases, alias generators, encoders, a free-text Literal or Enum) can put a sentence into
a body. The core proof runs through the real app: the real broker refusal route answers today's bytes, and a hostile
model swapped into that route is refused with the internal-system answer and never reaches the wire.

Deliberately no `from __future__ import annotations`: the hostile models are built inside functions and pydantic must
resolve their annotations from the real objects.
"""

import enum
import json
import re
from typing import Literal

import pytest
from fastapi.testclient import TestClient
from pydantic import AliasGenerator, ConfigDict, Field

from ofo.errors import render
from ofo_app import api_models
from ofo_app.api_models import CatalogueText, Identifier
from ofo_app.main import create_app
from ofo_app.routes import broker

SENTENCE = "Your funds were moved and the order was cancelled."
PATH = "/api/broker/refusals/broker_state_invalid"

#: Captured from main before the door existed (GET of the real route through create_app()): today's exact bytes.
GOLDEN_REFUSAL = (
    b'{"code":"broker_state_invalid","message":{"error_class":"BROKER_AUTHENTICATION","code":"BROKER_AUTHENTICATION_302",'
    b'"what_happened":"This Zerodha login link has expired or was already used.","impact":"Your Zerodha account was not '
    b'connected, and nothing was saved.","what_is_blocked":"Connecting your Zerodha account.","next_action":"Start the '
    b'Zerodha login again from the account page.","external_text":null}}')

#: Until the door is written these expectations fail on main (the red proof); the marker is removed in the door commit.
RED_UNTIL_DOOR = lambda: pytest.mark.xfail(strict=True, reason="W-069 step 1: red on main, green once the door exists")  # noqa: E731


def _client(app) -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def test_core_the_real_refusal_route_answers_todays_bytes() -> None:
    """AC-2: the real route, through create_app(), answers 200 with exactly the bytes main answered before the door."""
    response = _client(create_app()).get(PATH)
    assert response.status_code == 200
    assert response.content == GOLDEN_REFUSAL
    assert response.headers["content-type"] == "application/json"


# --- the hostile variants: each is a model setting that, on main, puts SENTENCE into the body --------------------------

def _extra_allow():
    class Hostile(broker.RefusalOut):
        model_config = ConfigDict(extra="allow", frozen=True, arbitrary_types_allowed=True)
    return Hostile, lambda code: Hostile(code=code, message=render(code), note=SENTENCE)


def _serialization_alias():
    class Hostile(broker.RefusalOut):
        code: Identifier = Field(serialization_alias=SENTENCE)
    return Hostile, lambda code: Hostile(code=code, message=render(code))


def _alias_generator():
    class Hostile(broker.RefusalOut):
        model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True, populate_by_name=True,
                                  alias_generator=AliasGenerator(serialization_alias=lambda name: SENTENCE + name))
    return Hostile, lambda code: Hostile(code=code, message=render(code))


def _json_encoders():
    class Hostile(broker.RefusalOut):
        model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True,
                                  json_encoders={str: lambda value: SENTENCE})
    return Hostile, lambda code: Hostile(code=code, message=render(code))


def _sentence_literal():
    class Hostile(broker.RefusalOut):
        code: Literal[SENTENCE]  # type: ignore[valid-type]
    return Hostile, lambda code: Hostile(code=SENTENCE, message=render(code))


def _sentence_enum():
    class Words(enum.Enum):
        SAID = SENTENCE

    class Hostile(broker.RefusalOut):
        code: Words
    return Hostile, lambda code: Hostile(code=Words.SAID, message=render(code))


VARIANTS = {"extra_allow": _extra_allow, "serialization_alias": _serialization_alias,
            "alias_generator": _alias_generator, "json_encoders": _json_encoders,
            "sentence_literal": _sentence_literal, "sentence_enum": _sentence_enum}


@pytest.fixture
def class_check_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch the class-time layer off: from here the door alone must refuse (it is the guarantee; the class check is
    only the early warning)."""
    monkeypatch.setattr(api_models, "_refuse_open_doors", lambda cls: None)
    monkeypatch.setattr(api_models, "check_field_type", lambda tp, where: None)


def _hostile_app(model, make):
    """The real app with the hostile model answering the real path (inserted first, built by the app's own route class)."""
    app = create_app()

    async def endpoint():
        return make("broker_state_invalid")

    route = app.router.route_class("/api/broker/refusals/{code}", endpoint, response_model=model, methods=["GET"])
    app.router.routes.insert(0, route)
    return app


def _assert_internal_failure_without_the_sentence(response) -> None:
    assert SENTENCE.encode() not in response.content
    assert response.status_code == 500
    body = json.loads(response.content)
    assert body["code"] == "INTERNAL_SYSTEM_002"  # catalogue template internal_system_request_failed
    assert re.search(r"reference ERR-[0-9A-F]{8}\)", body["what_happened"])


@pytest.mark.parametrize("name", sorted(VARIANTS))
@RED_UNTIL_DOOR()
def test_a_hostile_model_with_the_class_check_off_is_refused_by_the_door_alone(name: str, class_check_off: None) -> None:
    """AC-2: on main these answer 200 WITH the sentence (red); behind the door they answer 500 without it."""
    model, make = VARIANTS[name]()
    _assert_internal_failure_without_the_sentence(_client(_hostile_app(model, make)).get(PATH))


@pytest.mark.parametrize("name", sorted(VARIANTS))
@RED_UNTIL_DOOR()
def test_a_hostile_model_is_refused_at_class_creation_with_the_class_check_on(name: str) -> None:
    """AC-2: the class-time layer (the early warning) refuses each hostile shape when the class is created."""
    with pytest.raises(TypeError):
        VARIANTS[name]()
