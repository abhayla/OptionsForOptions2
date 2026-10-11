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
from typing import Annotated, Literal

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


@pytest.mark.filterwarnings("ignore::DeprecationWarning")
@pytest.mark.parametrize("name", sorted(VARIANTS))
def test_a_hostile_model_with_the_class_check_off_is_refused_by_the_door_alone(name: str, class_check_off: None) -> None:
    """AC-2: on main these answered 200 WITH the sentence (commit 5ddda05, red); behind the door they answer 500 without it."""
    model, make = VARIANTS[name]()
    _assert_internal_failure_without_the_sentence(_client(_hostile_app(model, make)).get(PATH))


@pytest.mark.filterwarnings("ignore::DeprecationWarning")
@pytest.mark.parametrize("name", sorted(VARIANTS))
def test_a_hostile_model_is_refused_at_class_creation_with_the_class_check_on(name: str) -> None:
    """AC-2: the class-time layer (the early warning) refuses each hostile shape when the class is created."""
    with pytest.raises(TypeError):
        VARIANTS[name]()


# --- the real strategies route: a permanent golden (bytes derived by hand from the declared field order) ---------------

class _FakeDb:
    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


def test_golden_a_strategies_route_answers_the_exact_bytes_with_exclude_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-2: GET /strategies/{id} (exclude_unset, nested models, datetimes with and without microseconds, Optional)
    answers byte for byte what the pre-door serializer answered."""
    import datetime
    from types import SimpleNamespace

    from ofo_app.db import get_db
    from ofo_app.routes import strategies

    document = {"schema_version": 1, "underlying": "NIFTY", "legs": [
        {"contract_id": 5, "action": "BUY", "instrument": "NIFTY2610625000CE", "strike": "25000",
         "expiry": "2026-10-27", "quantity": 75}], "rules_ref": None, "risk_limits": {"max_loss": "5000"},
        "preferences": {}}
    utc = datetime.timezone.utc
    stored = SimpleNamespace(id=3, status="draft", revision=2, saved=object(),
                             created_at=datetime.datetime(2026, 10, 12, 9, 15, 0, tzinfo=utc),
                             updated_at=datetime.datetime(2026, 10, 12, 9, 15, 0, 250000, tzinfo=utc))

    async def load(db, user_ref, strategy_id):
        return stored

    monkeypatch.setattr(strategies.store, "load", load)
    monkeypatch.setattr(strategies.sf, "to_document", lambda saved: document)
    app = create_app()

    async def fake_db():
        yield _FakeDb()

    app.dependency_overrides[get_db] = fake_db
    response = _client(app).get("/strategies/3")
    assert response.status_code == 200
    assert response.content == (
        b'{"id":3,"status":"draft","revision":2,"created_at":"2026-10-12T09:15:00Z",'
        b'"updated_at":"2026-10-12T09:15:00.250000Z","definition":{"schema_version":1,"underlying":"NIFTY","legs":'
        b'[{"contract_id":5,"action":"BUY","instrument":"NIFTY2610625000CE","strike":"25000","expiry":"2026-10-27",'
        b'"quantity":75}],"rules_ref":null,"risk_limits":{"max_loss":"5000"},"preferences":{}}}')


# --- every app ApiModel is swept: it emits, and its bytes equal the old serializer's (temporary parity) ----------------

def _app_models() -> list:
    found = []

    def walk(cls) -> None:
        for sub in cls.__subclasses__():
            if sub.__module__.startswith("ofo_app."):
                found.append(sub)
            walk(sub)

    walk(api_models.ApiModel)
    return sorted(set(found), key=lambda c: (c.__module__, c.__name__))


def _sample(tp, required_only: bool = False):
    import datetime
    import types
    import typing
    from decimal import Decimal

    if tp == CatalogueText:
        return render("user_input_request_invalid")
    if tp == Identifier:
        return "abc-1.2"
    if tp == api_models.Money:
        return Decimal("24500.50")
    origin = typing.get_origin(tp)
    if origin is Literal:
        return typing.get_args(tp)[0]
    if origin in (list, tuple):
        return origin([_sample(typing.get_args(tp)[0])] * 2)
    if origin in (typing.Union, types.UnionType):
        return _sample([a for a in typing.get_args(tp) if a is not type(None)][0])
    if origin is dict:
        return {"key": _sample(typing.get_args(tp)[1])}
    if tp is bool:
        return True
    if tp is int:
        return 7
    if tp is datetime.datetime:
        return datetime.datetime(2026, 10, 12, 9, 15, 0, 120000, tzinfo=datetime.timezone.utc)
    if tp is datetime.date:
        return datetime.date(2026, 10, 27)
    if isinstance(tp, type) and issubclass(tp, api_models.ApiModel):
        return _build(tp, required_only)
    raise AssertionError(f"no sample for {tp!r}: the door and this test must learn a new leaf kind together")


def _build(cls, required_only: bool = False):
    values = {}
    for name, info in cls.model_fields.items():
        if required_only and not info.is_required():
            continue
        values[name] = _sample(Annotated[(info.annotation, *info.metadata)] if info.metadata else info.annotation,
                               required_only)
    return cls.model_validate(values)


def test_the_app_models_are_all_swept() -> None:
    """AC-2: every app ApiModel subclass (recounted after W-068: 17) is in the sweep, so none can skip the door tests."""
    assert {c.__name__ for c in _app_models()} == {
        "BrokerRedirectOut", "RefusalOut", "ExpiriesOut", "ContractOut", "ContractsOut", "HealthOut", "PlannedEntryOut",
        "PlannedEntriesOut", "LegOut", "RiskLimitsOut", "PreferencesOut", "DefinitionOut", "StrategyOut", "SummaryOut",
        "StrategyListOut", "EntryOut", "HistoryOut"}


@pytest.mark.parametrize("required_only", [False, True])
def test_every_app_model_emits_the_bytes_the_old_serializer_wrote(required_only: bool) -> None:
    """AC-2 (parity with pydantic's JSON form; temporary, deleted at the end of W-069): every field set, and only the
    required fields set under exclude_unset."""
    for cls in _app_models():
        model = _build(cls, required_only)
        old = json.dumps(model.model_dump(mode="json", exclude_unset=required_only), ensure_ascii=False,
                         allow_nan=False, separators=(",", ":")).encode()
        assert api_models.emit(model, exclude_unset=required_only) == old, cls.__name__


# --- the leaf table, generated: every slot kind against a pool of every other kind -------------------------------------

def _leaf_matrix_pool() -> dict:
    import datetime
    from decimal import Decimal

    from pydantic import BaseModel

    from ofo.errors.explanations import UserWords, render_explanation

    class Sentence(str):
        pass

    class Words(enum.Enum):
        SAID = SENTENCE

    class Foreign(BaseModel):
        a: int = 1

    utc = datetime.timezone.utc
    return {
        "sentence": SENTENCE, "ident": "abc-1", "str_subclass": Sentence("abc-1"), "user_words": str.__new__(UserWords, "abc-1"),
        "float": 1.5, "nan": Decimal("NaN"), "inf": Decimal("Infinity"), "money": Decimal("1.50"),
        "naive_dt": datetime.datetime(2026, 1, 2, 3, 4, 5), "aware_dt": datetime.datetime(2026, 1, 2, 3, 4, 5, tzinfo=utc),
        "date": datetime.date(2026, 1, 2), "bytes": b"abc-1", "enum": Words.SAID, "int": 7, "bool": True, "none": None,
        "sentence_key_dict": {SENTENCE: 7}, "good_dict": {"k": 7}, "foreign": Foreign(), "list_int": [7],
        "list_sentence": [SENTENCE], "tuple_int": (7,), "catalogue": render("user_input_request_invalid"),
        "explanation": render_explanation("rule_no_condition_detail"), "literal_a": "A", "literal_1": 1,
    }


#: slot -> names of the pool values that belong in it, written by hand from the spec (exact types only).
LEAF_SLOTS = {
    "Identifier": (Identifier, {"ident", "literal_a"}),  # "A" is an exact str in the pattern
    "Money": (api_models.Money, {"money"}),
    "int": (int, {"int", "literal_1"}),
    "bool": (bool, {"bool"}),
    "datetime": (__import__("datetime").datetime, {"aware_dt"}),
    "date": (__import__("datetime").date, {"date"}),
    "Literal_str": (Literal["A", "B"], {"literal_a"}),
    "Literal_int": (Literal[1, 2], {"literal_1"}),
    "CatalogueText": (CatalogueText, {"catalogue", "explanation"}),
    "list_int": (list[int], {"list_int"}),
    "tuple_int": (tuple[int, ...], {"tuple_int"}),
    "optional_int": (__import__("typing").Optional[int], {"int", "literal_1", "none"}),
    "dict_ident_int": (dict[Identifier, int], {"good_dict"}),
}


@pytest.mark.parametrize("slot", sorted(LEAF_SLOTS))
def test_only_the_exact_allowed_pairs_emit(slot: str) -> None:
    """AC-2: for every slot kind, a pool of every other kind (a sentence, a str subclass, UserWords, float, NaN, a naive
    datetime, bytes, an Enum member, a dict with a sentence key, a foreign BaseModel ...) is refused; only the exact
    allowed types emit. The pool is the independent table; the door is not asked what it allows."""
    tp, allowed = LEAF_SLOTS[slot]

    class Slot(api_models.ApiModel):
        value: tp  # type: ignore[valid-type]

    pool = _leaf_matrix_pool()
    # a valid instance first (so validation is not what refuses), then the value swapped in underneath the model
    good = Slot.model_validate({"value": pool[sorted(allowed)[0]]})
    refused, emitted = [], []
    for name, value in pool.items():
        object.__setattr__(good, "value", value)
        try:
            api_models.emit(good)
            emitted.append(name)
        except api_models.DoorRefused:
            refused.append(name)
    assert set(emitted) == allowed, (slot, emitted)
    assert set(refused) == set(pool) - allowed


def test_a_dict_with_a_sentence_key_is_refused_and_the_log_names_no_value(caplog: pytest.LogCaptureFixture) -> None:
    """AC-2: dict keys are re-checked (a key is text); a refusal logs the field path and type name, never the value."""
    class Out(api_models.ApiModel):
        table: dict[Identifier, int]

    model = Out(table={"k": 1})
    object.__setattr__(model, "table", {SENTENCE: 1})
    with caplog.at_level("ERROR", logger="ofo_app.main"), pytest.raises(api_models.DoorRefused):
        api_models.emit(model)
    text = " ".join(r.getMessage() for r in caplog.records)
    assert "Out.table" in text and SENTENCE not in text


def test_a_refused_value_is_logged_by_path_and_type_never_by_value(caplog: pytest.LogCaptureFixture,
                                                                   monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-2: through the real stack, the hostile enum member is refused and the log holds its field path and type name only."""
    class Words(enum.Enum):
        SAID = SENTENCE

    monkeypatch.setattr(api_models, "_refuse_open_doors", lambda cls: None)
    monkeypatch.setattr(api_models, "check_field_type", lambda tp, where: None)

    class Hostile(broker.RefusalOut):
        code: Words

    app = _hostile_app(Hostile, lambda code: Hostile(code=Words.SAID, message=render(code)))
    with caplog.at_level("ERROR"):
        _client(app).get(PATH)
    text = " ".join(r.getMessage() for r in caplog.records)
    assert "Hostile.code" in text and "Words" in text and SENTENCE not in text


def test_exclude_unset_leaves_out_every_unset_field_at_every_level() -> None:
    """AC-2: the route's own exclude_unset flag reaches nested models (strategy forms keep their stored keys exactly)."""
    from ofo_app.routes.strategies import DefinitionOut

    model = DefinitionOut.model_validate({
        "schema_version": 1, "underlying": "NIFTY", "legs": [], "rules_ref": None, "risk_limits": {"max_loss": "5"},
        "preferences": {}})
    assert api_models.emit(model, exclude_unset=True) == (
        b'{"schema_version":1,"underlying":"NIFTY","legs":[],"rules_ref":null,"risk_limits":{"max_loss":"5"},'
        b'"preferences":{}}')
    assert b'"max_capital":null' in api_models.emit(model)


def test_extras_refuse_the_whole_response_and_are_never_dropped(class_check_off: None) -> None:
    """AC-2: a model carrying extra fields is refused outright (silently dropping them would hide the attack)."""
    class Loose(api_models.ApiModel):
        model_config = ConfigDict(extra="allow", frozen=True, arbitrary_types_allowed=True)
        ok: bool

    with pytest.raises(api_models.DoorRefused):
        api_models.emit(Loose(ok=True, note=SENTENCE))


def test_a_value_swapped_underneath_a_validated_model_is_refused() -> None:
    """AC-2: object.__setattr__ cannot smuggle a sentence in: the door re-checks every value against its slot."""
    model = broker.RefusalOut(code="broker_state_invalid", message=render("broker_state_invalid"))
    object.__setattr__(model, "code", SENTENCE)
    with pytest.raises(api_models.DoorRefused):
        api_models.emit(model)


def test_emitted_bytes_and_closed_responses_cannot_be_forged() -> None:
    """AC-2: only emit() makes the bytes a ClosedResponse takes."""
    from ofo_app.errors import ClosedResponse

    with pytest.raises(TypeError):
        api_models.Emitted(b'{"note":"free text"}')
    with pytest.raises(TypeError):
        ClosedResponse(b'{"note":"free text"}')  # type: ignore[arg-type]
    with pytest.raises(api_models.DoorRefused):
        api_models.emit_message("free text")  # type: ignore[arg-type]
    with pytest.raises(api_models.DoorRefused):
        api_models.emit({"code": "x"})  # type: ignore[arg-type]


# --- the wrapper and the seal: nothing but a sealed door response leaves the app ---------------------------------------

def _app_with_routes(*routes):
    app = create_app()
    for route in routes:
        app.router.routes.insert(0, route)
    return app


def _closed(path, endpoint, model=broker.RefusalOut):
    return create_app().router.route_class(path, endpoint, response_model=model, methods=["GET"])


@pytest.mark.parametrize("returned", ["dict", "json_response", "model_subclass", "none"])
def test_the_wrapper_refuses_anything_but_exactly_the_response_model(returned: str) -> None:
    """AC-2: a route returning a dict, a raw JSONResponse (passed by a wrapper that accepts any Response), a subclass of
    its model or nothing is answered 500 without the sentence."""
    from fastapi.responses import JSONResponse

    class Sub(broker.RefusalOut):
        pass

    async def endpoint():
        return {"dict": {"code": "broker_state_invalid", "note": SENTENCE},
                "json_response": JSONResponse({"note": SENTENCE}),
                "model_subclass": Sub(code="broker_state_invalid", message=render("broker_state_invalid")),
                "none": None}[returned]

    app = _app_with_routes(_closed("/api/broker/refusals/{code}", endpoint))
    _assert_internal_failure_without_the_sentence(_client(app).get(PATH))


def test_the_wrapper_is_async_exactly_when_the_endpoint_is() -> None:
    """AC-2: a sync endpoint stays sync (FastAPI runs it in a thread), an async one stays async."""
    import inspect

    def sync_endpoint():
        return broker.RefusalOut(code="broker_state_invalid", message=render("broker_state_invalid"))

    async def async_endpoint():
        return sync_endpoint()

    for endpoint in (sync_endpoint, async_endpoint):
        route = _closed("/x", endpoint)
        assert inspect.iscoroutinefunction(route.endpoint) == inspect.iscoroutinefunction(endpoint)
        assert _client(_app_with_routes(route)).get("/x").status_code == 200


def test_an_unsealed_response_from_anywhere_else_is_dropped_whole_and_answered_500() -> None:
    """AC-2: a raw Starlette route, a plain APIRoute, a mounted app and the outcome path under another method each
    answer 500 with the internal message and none of their own body (the seal check in the boundary)."""
    from fastapi import FastAPI
    from fastapi.routing import APIRoute
    from starlette.responses import PlainTextResponse
    from starlette.routing import Mount, Route

    async def raw(request):
        return PlainTextResponse(SENTENCE)

    async def plain():
        return {"note": SENTENCE}

    sub = FastAPI()
    sub.add_api_route("/inner", plain)
    for route, path in ((Route("/raw", raw), "/raw"), (APIRoute("/plain", plain, methods=["GET"]), "/plain"),
                        (Mount("/mounted", sub), "/mounted/inner"),
                        (APIRoute("/api/strategies/outcome", plain, methods=["GET"]), "/api/strategies/outcome")):
        _assert_internal_failure_without_the_sentence(_client(_app_with_routes(route)).get(path))


def test_a_sealed_response_is_not_mistaken_for_unsealed() -> None:
    """AC-2: the seal check lets every real route through (200) and an unknown path answers the catalogue 404."""
    client = _client(create_app())
    assert client.get(PATH).status_code == 200
    missing = client.get("/no/such/path")
    assert missing.status_code == 404 and json.loads(missing.content)["code"] == "USER_INPUT_003"


# --- ADR-073: /docs, /redoc and /openapi.json only in development and test --------------------------------------------

DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")


@pytest.mark.parametrize("env", ["development", "test"])
def test_the_framework_docs_are_served_in_development_and_test(env: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-2 (ADR-073): the docs pages and the API description answer 200 there, exempt from the door by exact path."""
    monkeypatch.setenv("APP_ENV", env)
    client = _client(create_app())
    assert [client.get(p).status_code for p in DOCS_PATHS] == [200, 200, 200]


@pytest.mark.parametrize("env", ["production", "staging", ""])
def test_the_framework_docs_answer_404_everywhere_else(env: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-2 (ADR-073): in production (and any APP_ENV that is not development or test) none of the three is served."""
    monkeypatch.setenv("APP_ENV", env)
    client = _client(create_app())
    for path in DOCS_PATHS:
        response = client.get(path)
        assert response.status_code == 404, path
        assert json.loads(response.content)["code"] == "USER_INPUT_003"  # user_input_request_not_available
        assert b"openapi" not in response.content.lower() and b"swagger" not in response.content.lower()


# --- the enumeration: every route of the real app is a ClosedRoute, bar the named exemptions --------------------------

@pytest.mark.parametrize("env", ["development", "production"])
def test_every_route_of_the_real_app_goes_through_the_door(env: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-2: each route is exactly a ClosedRoute carrying the door marker, its wrapper is async exactly when the
    original endpoint is, and its response_model is a closed ApiModel from the swept set. Exempt: the outcome route
    (until W-066 / #172) and the framework docs routes, only in development."""
    import inspect

    from fastapi.routing import APIRoute

    from ofo_app.errors import ClosedRoute

    monkeypatch.setenv("APP_ENV", env)
    models = set(_app_models())
    problems, docs_seen = [], set()
    for route in create_app().routes:
        if getattr(route, "path", "") in DOCS_PATHS + ("/docs/oauth2-redirect",) and not isinstance(route, APIRoute):
            docs_seen.add(route.path)
            continue
        if type(route) is APIRoute and route.path == "/api/strategies/outcome" and route.methods == {"POST"}:
            continue
        if type(route) is not ClosedRoute:
            problems.append(f"{getattr(route, 'path', route)}: {type(route).__name__}")
            continue
        original = inspect.unwrap(route.endpoint)
        if getattr(route.endpoint, "ofo_door", False) is not True:
            problems.append(f"{route.path}: no door marker")
        if inspect.iscoroutinefunction(route.endpoint) != inspect.iscoroutinefunction(original):
            problems.append(f"{route.path}: wrapper kind differs from the endpoint's")
        if route.response_model not in models:
            problems.append(f"{route.path}: response_model {route.response_model!r}")
    assert problems == []
    assert docs_seen == (set(DOCS_PATHS) | {"/docs/oauth2-redirect"} if env == "development" else set())


def test_the_exemptions_are_exactly_the_outcome_route_and_the_docs_paths() -> None:
    """AC-2: the boundary exempts only (POST, outcome) and the docs GET paths, nothing wider."""
    from ofo_app import errors

    assert errors.OUTCOME_EXEMPTION == ("POST", "/api/strategies/outcome")
