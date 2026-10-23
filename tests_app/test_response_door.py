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
from ofo_app.basket_post import BasketPost
from ofo_app.main import create_app
from ofo_app.routes import broker

SENTENCE = "Your funds were moved and the order was cancelled."
ALIAS = "you_should_buy_now"  # a snake_case alias is a valid-looking key: it must still never reach the bytes
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
        code: Identifier = Field(serialization_alias=ALIAS)
    return Hostile, lambda code: Hostile(code=code, message=render(code))


def _alias_generator():
    class Hostile(broker.RefusalOut):
        model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True, populate_by_name=True,
                                  alias_generator=AliasGenerator(serialization_alias=lambda name: ALIAS + name))
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
    assert SENTENCE.encode() not in response.content and ALIAS.encode() not in response.content
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
    """The route reads each leg's catalogue answer through tracked_contracts.resolve (issue #500), replaced below."""

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
    stored = SimpleNamespace(id=3, status="draft", revision=2, saved=object(), versions=(),
                             created_at=datetime.datetime(2026, 10, 12, 9, 15, 0, tzinfo=utc),
                             updated_at=datetime.datetime(2026, 10, 12, 9, 15, 0, 250000, tzinfo=utc))

    async def load(db, user_ref, strategy_id):
        return stored

    monkeypatch.setattr(strategies.store, "load", load)
    monkeypatch.setattr(strategies.sf, "to_document", lambda saved: document)

    async def resolve(db, ids):  # issue #500: every leg's answer comes from the one door; here a live contract
        from ofo.instruments.models import InstrumentId
        return tuple(SimpleNamespace(contract_id=i, state="live", feed_id=InstrumentId("NSE_FO", 44624)) for i in ids)

    monkeypatch.setattr(strategies.tracked_contracts, "resolve", resolve)
    app = create_app()

    async def fake_db():
        yield _FakeDb()

    app.dependency_overrides[get_db] = fake_db
    response = _client(app).get("/strategies/3")
    assert response.status_code == 200
    # REQ-038 AC-3 (row 16): versions is always written; an unversioned strategy answers an empty list.
    assert response.content == (
        b'{"id":3,"status":"draft","revision":2,"created_at":"2026-10-12T09:15:00Z",'
        b'"updated_at":"2026-10-12T09:15:00.250000Z","definition":{"schema_version":1,"underlying":"NIFTY","legs":'
        b'[{"contract_id":5,"action":"BUY","contract_state":"live","exchange_segment":"NSE_FO","exchange_token":44624,'
        b'"instrument":"NIFTY2610625000CE","strike":"25000","expiry":"2026-10-27",'
        b'"quantity":75}],"rules_ref":null,"risk_limits":{"max_loss":"5000"},"preferences":{}},"versions":[]}')


def test_golden_a_strategy_with_one_stored_version_answers_its_definition(monkeypatch: pytest.MonkeyPatch) -> None:
    """REQ-038 AC-3 (row 16 fix 1): each version carries its own definition and the sticky flag, in the declared
    field order (bytes written by hand: VersionOut's fields, then the same leg document as above)."""
    import copy  # noqa: PLC0415
    import datetime  # noqa: PLC0415
    from types import SimpleNamespace  # noqa: PLC0415

    from ofo_app.db import get_db  # noqa: PLC0415
    from ofo_app.routes import strategies  # noqa: PLC0415

    document = {"schema_version": 1, "underlying": "NIFTY", "legs": [
        {"contract_id": 5, "action": "BUY", "instrument": "NIFTY2610625000CE", "strike": "25000",
         "expiry": "2026-10-27", "quantity": 75}], "rules_ref": None, "risk_limits": {}, "preferences": {}}
    utc = datetime.UTC
    at = datetime.datetime(2026, 10, 12, 9, 15, 0, tzinfo=utc)
    version = SimpleNamespace(number=1, state="active", based_on=None, created_at=at, confirmed_at=at,
                              reconciled_at=at, outcome=None, reconciliation_required=True, definition_text="{}")
    stored = SimpleNamespace(id=3, status="draft", revision=2, saved=object(), versions=(version,),
                             created_at=at, updated_at=at)

    async def load(db, user_ref, strategy_id):
        return stored

    async def version_saved(db, v):
        assert v is version
        return object()

    async def resolve(db, ids):
        from ofo.instruments.models import InstrumentId  # noqa: PLC0415
        return tuple(SimpleNamespace(contract_id=i, state="live", feed_id=InstrumentId("NSE_FO", 44624)) for i in ids)

    monkeypatch.setattr(strategies.store, "load", load)
    monkeypatch.setattr(strategies.store, "version_saved", version_saved)
    monkeypatch.setattr(strategies.sf, "to_document", lambda saved: copy.deepcopy(document))
    monkeypatch.setattr(strategies.tracked_contracts, "resolve", resolve)
    app = create_app()

    async def fake_db():
        yield _FakeDb()

    app.dependency_overrides[get_db] = fake_db
    response = _client(app).get("/strategies/3")
    assert response.status_code == 200  # noqa: PLR2004
    definition = (b'{"schema_version":1,"underlying":"NIFTY","legs":[{"contract_id":5,"action":"BUY",'
                  b'"contract_state":"live","exchange_segment":"NSE_FO","exchange_token":44624,'
                  b'"instrument":"NIFTY2610625000CE","strike":"25000","expiry":"2026-10-27","quantity":75}],'
                  b'"rules_ref":null,"risk_limits":{},"preferences":{}}')
    assert response.content == (
        b'{"id":3,"status":"draft","revision":2,"created_at":"2026-10-12T09:15:00Z",'
        b'"updated_at":"2026-10-12T09:15:00Z","definition":' + definition + b',"versions":[{"number":1,'
        b'"state":"active","based_on":null,"created_at":"2026-10-12T09:15:00Z","confirmed_at":"2026-10-12T09:15:00Z",'
        b'"reconciled_at":"2026-10-12T09:15:00Z","outcome":null,"reconciliation_required":true,"definition":'
        + definition + b'}]}')


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
    if tp == api_models.InstrumentId:
        return "NSE_FO:44624"
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
    if tp is BasketPost:  # W-095: made only from a real KiteBasket (the owner's 2026-10-16 entry)
        from test_execute_route import _real_basket  # noqa: PLC0415

        return BasketPost.of(_real_basket(), "kitekey")
    raise AssertionError(f"no sample for {tp!r}: the door and this test must learn a new leaf kind together")


def _build(cls, required_only: bool = False):
    values = {}
    for name, info in cls.model_fields.items():
        if required_only and not info.is_required():
            continue
        values[name] = _sample(Annotated[(info.annotation, *info.metadata)] if info.metadata else info.annotation,
                               required_only)
    return cls.model_validate(values)


#: The allow-list of every app ApiModel subclass, module-qualified and sorted (replaces the hand-recounted count).
#: A model added or removed without this list changing fails the test below, naming the added and missing names.
#: To add one: insert its `module.Name` in sorted order.
APP_MODELS = (
    "ofo_app.chain_push.ChainCellOut",
    "ofo_app.chain_push.ChainOut",
    "ofo_app.chain_push.ChainRowOut",
    "ofo_app.index_push.IndexOut",
    "ofo_app.index_push.IndicesOut",
    "ofo_app.routes.broker.BrokerRedirectOut",
    "ofo_app.routes.broker.RefusalOut",
    "ofo_app.routes.broker_capabilities.CapabilitiesOut",
    "ofo_app.routes.broker_status.BrokerStatusOut",
    "ofo_app.routes.broker_status.DisconnectOut",
    "ofo_app.routes.broker_status.StatusOut",
    "ofo_app.routes.catalogue.ContractOut",
    "ofo_app.routes.catalogue.ContractsOut",
    "ofo_app.routes.catalogue.ExpiriesOut",
    "ofo_app.routes.execute.BasketOrderOut",
    "ofo_app.routes.execute.CostOut",
    "ofo_app.routes.execute.ExecuteOut",
    "ofo_app.routes.execution_return.ReturnContractOut",
    "ofo_app.routes.execution_return.ReturnExternalOut",
    "ofo_app.routes.execution_return.ReturnOut",
    "ofo_app.routes.execution_return.ReturnPlanOut",
    "ofo_app.routes.features.FeaturesOut",
    "ofo_app.routes.health.HealthOut",
    "ofo_app.routes.outcome.AdvancedLegOut",
    "ofo_app.routes.outcome.CellOut",
    "ofo_app.routes.outcome.ColumnOut",
    "ofo_app.routes.outcome.LegOut",
    "ofo_app.routes.outcome.LevelOut",
    "ofo_app.routes.outcome.MarginOut",
    "ofo_app.routes.outcome.OutcomeResponse",
    "ofo_app.routes.outcome.PayoffOut",
    "ofo_app.routes.outcome.PointOut",
    "ofo_app.routes.outcome.RowOut",
    "ofo_app.routes.outcome.ScenarioOut",
    "ofo_app.routes.outcome.SummaryOut",
    "ofo_app.routes.outcome.TableOut",
    "ofo_app.routes.planned_entry.PlannedEntriesOut",
    "ofo_app.routes.planned_entry.PlannedEntryOut",
    "ofo_app.routes.positions.PositionsOut",
    "ofo_app.routes.positions.StrategyContractOut",
    "ofo_app.routes.positions.StrategyPositionsOut",
    "ofo_app.routes.ready_made.LoadTemplateIn",
    "ofo_app.routes.ready_made.PlacedLegOut",
    "ofo_app.routes.ready_made.QuickPickIn",
    "ofo_app.routes.ready_made.ReadyMadeOut",
    "ofo_app.routes.strategies.DefinitionOut",
    "ofo_app.routes.strategies.EntryOut",
    "ofo_app.routes.strategies.HistoryOut",
    "ofo_app.routes.strategies.LegOut",
    "ofo_app.routes.strategies.PreferencesOut",
    "ofo_app.routes.strategies.RiskLimitsOut",
    "ofo_app.routes.strategies.StrategyListOut",
    "ofo_app.routes.strategies.StrategyOut",
    "ofo_app.routes.strategies.SummaryOut",
    "ofo_app.routes.strategies.VersionOut",
    "ofo_app.routes.strategy_templates.TemplateLegOut",
    "ofo_app.routes.strategy_templates.TemplateOut",
    "ofo_app.routes.strategy_templates.TemplatesOut",
    "ofo_app.routes.tracking.DetectionOut",
    "ofo_app.routes.tracking.TrackingIndexOut",
    "ofo_app.routes.tracking.TrackingLegOut",
    "ofo_app.routes.tracking.TrackingOut",
    "ofo_app.routes.zerodha_account.BrokerAccountOut",
    "ofo_app.routes.zerodha_account.MarginOut",
    "ofo_app.routes.zerodha_account.MaskedUserIdOut",
)


def test_the_app_models_are_all_swept() -> None:
    """AC-2: every app ApiModel subclass (recounted after W-068: 17; W-066 adds the outcome route's 13) is in the sweep,
    so none can skip the door tests."""
    assert {(c.__module__.rsplit(".", 1)[-1], c.__name__) for c in _app_models()} >= {
        ("outcome", n) for n in ("CellOut", "ColumnOut", "RowOut", "TableOut", "LevelOut", "ScenarioOut", "PointOut",
                                 "PayoffOut", "SummaryOut", "MarginOut", "LegOut", "AdvancedLegOut", "OutcomeResponse")}
    found = sorted(f"{c.__module__}.{c.__name__}" for c in _app_models())
    added, missing = sorted(set(found) - set(APP_MODELS)), sorted(set(APP_MODELS) - set(found))
    assert found == list(APP_MODELS), f"models not in APP_MODELS: {added}; in APP_MODELS but not found: {missing}"


@pytest.mark.parametrize("required_only", [False, True])
def test_every_app_model_emits_with_exactly_its_declared_keys(required_only: bool) -> None:
    """AC-2: every app model, built from samples of each of its leaf kinds (the sampler raises on a kind the door does
    not know), emits JSON whose keys are its declared field names (only the set ones under exclude_unset).
    The step-5 parity run against model_dump (bytes equal for all 17 models, both modes) passed before this replaced it."""
    for cls in _app_models():
        model = _build(cls, required_only)
        written = json.loads(api_models.emit(model, exclude_unset=required_only))
        expected = [n for n in cls.model_fields if not required_only or cls.model_fields[n].is_required()]
        assert list(written) == expected, cls.__name__


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


def test_extras_set_underneath_a_base_config_model_are_refused_by_the_extras_check_itself() -> None:
    """AC-2: independent of the config check - a model with the exact base config but a populated extras slot."""
    model = broker.RefusalOut(code="broker_state_invalid", message=render("broker_state_invalid"))
    object.__setattr__(model, "__pydantic_extra__", {"note": SENTENCE})
    with pytest.raises(api_models.DoorRefused):
        api_models.emit(model)


def test_the_wrapper_itself_refuses_a_raw_response_without_the_boundary() -> None:
    """AC-2: the wrapper (not only the seal check behind it) refuses a raw Response and a dict."""
    import asyncio

    from fastapi.responses import JSONResponse

    for returned in (JSONResponse({"note": SENTENCE}), {"note": SENTENCE}):
        async def endpoint(returned=returned):
            return returned

        with pytest.raises(api_models.DoorRefused):
            asyncio.run(_closed("/x", endpoint).endpoint())


def test_a_value_swapped_underneath_a_validated_model_is_refused() -> None:
    """AC-2: object.__setattr__ cannot smuggle a sentence in: the door re-checks every value against its slot."""
    model = broker.RefusalOut(code="broker_state_invalid", message=render("broker_state_invalid"))
    object.__setattr__(model, "code", SENTENCE)
    with pytest.raises(api_models.DoorRefused):
        api_models.emit(model)


def test_a_field_name_outside_the_key_pattern_is_refused() -> None:
    """AC-2: the only keys a body may carry are declared names matching ^[a-z][a-z0-9_]{0,63}$ (a name is text too)."""
    class Odd(api_models.ApiModel):
        Note_Of_Words: bool

    with pytest.raises(api_models.DoorRefused):
        api_models.emit(Odd(Note_Of_Words=True))


def test_a_route_keeps_its_declared_success_status_code() -> None:
    """AC-2: the wrapper answers the route's own status_code (201 for Save Draft), not a default 200."""
    async def endpoint():
        return broker.RefusalOut(code="broker_state_invalid", message=render("broker_state_invalid"))

    route = create_app().router.route_class("/x", endpoint, response_model=broker.RefusalOut, methods=["GET"],
                                            status_code=201)
    assert _client(_app_with_routes(route)).get("/x").status_code == 201


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


def test_the_boundary_drops_every_message_of_an_unsealed_response_and_sends_only_the_500() -> None:
    """AC-2: driven as bare ASGI - the unsealed start AND its body chunks never reach the wire; exactly one 500 does."""
    import asyncio

    from ofo_app.errors import _Boundary

    async def unsealed_app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"text/plain")]})
        await send({"type": "http.response.body", "body": SENTENCE.encode(), "more_body": True})
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    sent = []

    async def send(message):
        sent.append(message)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {"type": "http", "method": "GET", "path": "/x", "headers": [], "query_string": b"", "raw_path": b"/x",
             "scheme": "http", "server": ("t", 80), "client": ("c", 1), "http_version": "1.1", "root_path": ""}
    asyncio.run(_Boundary(unsealed_app)(scope, receive, send))
    starts = [m for m in sent if m["type"] == "http.response.start"]
    assert [m["status"] for m in starts] == [500]
    assert SENTENCE.encode() not in b"".join(m.get("body", b"") for m in sent)


def _run_wrapper(returned):
    import asyncio

    async def endpoint():
        return returned

    return asyncio.run(_closed("/x", endpoint).endpoint())


def test_a_sealed_response_whose_body_was_changed_after_construction_is_refused() -> None:
    """AC-2 (review MAJOR 1): `r = respond(model, 200); r.body = sentence` is refused by the wrapper, and by the seal
    itself when the response reaches the boundary by another path."""
    from ofo_app.errors import respond

    def mutated():
        r = respond(broker.RefusalOut(code="broker_state_invalid", message=render("broker_state_invalid")), 200)
        r.body = b"Z" * len(r.body)  # same length, so only the body check (not content-length) can catch it
        return r

    with pytest.raises(api_models.DoorRefused):
        _run_wrapper(mutated())

    async def raw_route(request):  # a plain Starlette route returning the mutated sealed response
        return mutated()

    from starlette.routing import Route

    _assert_internal_failure_without_the_sentence(_client(_app_with_routes(Route("/m", raw_route))).get("/m"))


def test_a_sealed_response_whose_headers_were_changed_after_construction_is_refused() -> None:
    """AC-2 (review MAJOR 1): a header outside the door's set, or a content-length that is not the body's, is refused."""
    from ofo_app.errors import respond

    model = broker.RefusalOut(code="broker_state_invalid", message=render("broker_state_invalid"))
    for change in (lambda r: r.headers.__setitem__("x-note", SENTENCE),
                   lambda r: r.headers.__setitem__("content-length", "1")):
        r = respond(model, 200)
        change(r)
        with pytest.raises(api_models.DoorRefused):
            _run_wrapper(r)


def test_a_sealed_redirect_is_made_only_by_typed_redirect_and_checked_again_when_sent() -> None:
    """AC-2 (review MAJOR 1): SealedRedirect cannot be built directly (open redirect); a Location changed after
    typed_redirect is refused; neither door class can be subclassed."""
    from ofo_app.errors import ClosedResponse, SealedRedirect, typed_redirect

    with pytest.raises(TypeError):
        SealedRedirect("https://evil.example/")
    with pytest.raises(TypeError):
        SealedRedirect("/connected", {})
    model = broker.BrokerRedirectOut(redirect="connected")
    ok = typed_redirect(model, "/connected")
    assert _run_wrapper(ok) is ok
    bad = typed_redirect(model, "/connected")
    bad.headers["location"] = "https://evil.example/"
    with pytest.raises(api_models.DoorRefused):
        _run_wrapper(bad)
    other = typed_redirect(model, "/connected")
    other.headers["location"] = "/somewhere-else"  # still a path on this site, but not the one that was made
    with pytest.raises(api_models.DoorRefused):
        _run_wrapper(other)
    from ofo_app import errors

    with pytest.raises(api_models.DoorRefused):  # even with the mint token the header table refuses an outside Location
        SealedRedirect("https://evil.example/", _mint=errors._REDIRECT_MINT)
    for base in (ClosedResponse, SealedRedirect):
        with pytest.raises(TypeError):
            type("Sub", (base,), {})


def _app_with_env_file(tmp_path, monkeypatch, text, set_env=None):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(text, encoding="utf-8")
    monkeypatch.delenv("APP_ENV", raising=False)
    if set_env is not None:
        monkeypatch.setenv("APP_ENV", set_env)
    return _client(create_app())


def test_docs_follow_the_one_settings_source_so_a_dotenv_production_has_none(tmp_path, monkeypatch) -> None:
    """AC-2 (ADR-073, review MAJOR 2): APP_ENV=production only in a .env file, APP_ENV unset, or an unknown value:
    /docs and /openapi.json answer 404. Only an explicit development or test serves them (from the file too)."""
    for text, env, expected in (("APP_ENV=production\n", None, 404), ("", None, 404), ("APP_ENV=staging\n", None, 404),
                                ("APP_ENV=production\n", "production", 404), ("APP_ENV=production\n", "development", 200),
                                ("APP_ENV=development\n", None, 200), ("APP_ENV=test\n", None, 200)):
        client = _app_with_env_file(tmp_path, monkeypatch, text, env)
        assert [client.get(p).status_code for p in DOCS_PATHS] == [expected] * 3, (text, env)


def test_replay_mode_is_refused_outside_test_from_either_source(tmp_path, monkeypatch) -> None:
    """AC-2 (review MAJOR 2): OUTCOME_REPLAY with APP_ENV production (.env only), unset, or development refuses to start."""
    from ofo_app.replay_mode import ReplayRefused

    monkeypatch.setenv("OUTCOME_REPLAY", "1")
    for text, env in (("APP_ENV=production\n", None), ("", None), ("", "development")):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".env").write_text(text, encoding="utf-8")
        monkeypatch.delenv("APP_ENV", raising=False)
        if env:
            monkeypatch.setenv("APP_ENV", env)
        with pytest.raises(ReplayRefused):
            create_app()


@pytest.mark.parametrize("value,text", [(__import__("decimal").Decimal("1365.00"), "1365.00"),
                                        (__import__("decimal").Decimal("1E+3"), "1000"),
                                        (__import__("decimal").Decimal("0E-8"), "0.00000000"),
                                        (__import__("decimal").Decimal("-0.00"), "-0.00")])
def test_money_is_written_as_a_plain_decimal_string(value, text) -> None:
    """AC-2: the Money format is pinned (no exponent form, scale and sign kept)."""
    class Out(api_models.ApiModel):
        v: api_models.Money

    assert api_models.emit(Out(v=value)) == b'{"v":"' + text.encode() + b'"}'


def test_nested_subclass_tuple_length_and_list_subclass_are_refused() -> None:
    """AC-2: a subclass in a nested model slot, a tuple of the wrong length and a list subclass are all refused."""
    class Inner(api_models.ApiModel):
        ok: bool

    class Outer(api_models.ApiModel):
        inner: Inner
        pair: tuple[int, int]
        items: list[int]

    class InnerSub(Inner):
        pass

    class Items(list):
        pass

    good = Outer(inner=Inner(ok=True), pair=(1, 2), items=[1])
    assert api_models.emit(good) == b'{"inner":{"ok":true},"pair":[1,2],"items":[1]}'
    for name, value in (("inner", InnerSub(ok=True)), ("pair", (1, 2, 3)), ("items", Items([1]))):
        model = Outer(inner=Inner(ok=True), pair=(1, 2), items=[1])
        object.__setattr__(model, name, value)
        with pytest.raises(api_models.DoorRefused):
            api_models.emit(model)


def test_a_trailing_slash_is_a_catalogue_404_not_a_logged_500() -> None:
    """AC-2: the router's own slash redirect is off (it was an unsealed response)."""
    response = _client(create_app()).get("/health/")
    assert response.status_code == 404 and json.loads(response.content)["code"] == "USER_INPUT_003"


def test_request_validation_errors_answer_422_with_the_catalogue_body() -> None:
    """AC-2: a bad body on POST /strategies and a missing query on the catalogue route are 422 with the catalogue body
    (same as main: probed on both checkouts)."""
    import datetime

    from ofo_app.db import get_db
    from ofo_app.routes import catalogue

    app = create_app()

    async def fake_db():
        yield _FakeDb()

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[catalogue.get_today] = lambda: datetime.date(2026, 10, 12)
    client = _client(app)
    for response in (client.post("/strategies", json={"underlying": "NIFTY", "legs": "x"}),
                     client.get("/api/catalogue/NIFTY/contracts")):
        assert response.status_code == 422
        assert json.loads(response.content)["code"] == "USER_INPUT_002"  # user_input_request_invalid


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
    original endpoint is, and its response_model is a closed ApiModel from the swept set. Exempt: the framework docs
    routes only, only in development (the outcome route joined the door in W-066 / #172)."""
    monkeypatch.setenv("APP_ENV", env)
    problems, docs_seen = _route_problems(create_app().routes)
    assert problems == []
    assert docs_seen == (set(DOCS_PATHS) | {"/docs/oauth2-redirect"} if env == "development" else set())


def _route_problems(routes) -> tuple[list[str], set[str]]:
    """The enumeration over any route list: (problems, docs paths seen). No route is exempt (W-066 moved the outcome
    route onto the door, issue #172)."""
    import inspect

    from fastapi.routing import APIRoute

    from ofo_app.errors import ClosedRoute, ClosedWebSocketRoute

    models = set(_app_models())
    problems, docs_seen = [], set()
    for route in routes:
        if getattr(route, "path", "") in DOCS_PATHS + ("/docs/oauth2-redirect",) and not isinstance(route, APIRoute):
            docs_seen.add(route.path)
            continue
        if type(route) is ClosedWebSocketRoute:  # W-065: the door's socket class, minted messages only
            if getattr(route.endpoint, "ofo_door", False) is not True:
                problems.append(f"{route.path}: no door marker")
            if not route.message_models or not set(route.message_models) <= models:
                problems.append(f"{route.path}: message_models {route.message_models!r}")
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
    return problems, docs_seen


def test_a_stand_in_route_at_the_outcome_path_is_not_exempt() -> None:
    """Round 9: a plain APIRoute at POST /api/strategies/outcome whose endpoint is not the real one is a problem."""
    from fastapi.routing import APIRoute

    def stand_in() -> dict:
        return {"raw": "UNMINTED"}

    routes = [*create_app().routes, APIRoute("/api/strategies/outcome", stand_in, methods=["POST"])]
    problems, _ = _route_problems(routes)
    assert any("/api/strategies/outcome" in p for p in problems), problems


def test_a_socket_route_off_the_door_is_a_problem() -> None:
    """W-065: only the door's socket class passes the enumeration. A plain APIWebSocketRoute at the live path, a door
    socket whose endpoint lost the door marker, and one declaring a model that is not an app ApiModel each fail it."""
    from fastapi.routing import APIWebSocketRoute

    from ofo_app.api_models import ApiModel
    from ofo_app.errors import ClosedWebSocketRoute
    from ofo_app.routes.outcome import OutcomeResponse

    async def raw(websocket) -> None:
        await websocket.accept()

    async def endpoint(socket) -> None:
        return None

    unmarked = ClosedWebSocketRoute("/api/strategies/live2", endpoint, message_models=(OutcomeResponse,))
    unmarked.endpoint = endpoint

    class Foreign(ApiModel):
        pass

    Foreign.__module__ = "elsewhere"
    foreign = ClosedWebSocketRoute("/api/strategies/live3", endpoint, message_models=(Foreign,))
    for route, path in ((APIWebSocketRoute("/api/strategies/live", raw), "/api/strategies/live"),
                        (unmarked, "/api/strategies/live2"), (foreign, "/api/strategies/live3")):
        problems, _ = _route_problems([*create_app().routes, route])
        assert any(p.startswith(path + ":") for p in problems), (path, problems)
    assert _route_problems(create_app().routes)[0] == []  # the real live route passes


def test_add_socket_route_takes_only_the_door_socket_class() -> None:
    """W-065 round 2: `errors.add_socket_route` appends exactly a ClosedWebSocketRoute; a plain APIWebSocketRoute, a
    Starlette WebSocketRoute and a ClosedRoute are refused and the app's route table is left unchanged."""
    from fastapi.routing import APIWebSocketRoute
    from starlette.routing import WebSocketRoute

    from ofo_app.api_models import DoorRefused
    from ofo_app.errors import ClosedWebSocketRoute, add_socket_route
    from ofo_app.routes.outcome import OutcomeResponse

    async def raw(websocket) -> None:
        await websocket.accept()

    async def endpoint(socket) -> None:
        return None

    app = create_app()
    before = list(app.router.routes)
    for bad in (APIWebSocketRoute("/api/x", raw), WebSocketRoute("/api/x", raw),
                _closed("/api/x", lambda: None)):
        with pytest.raises(DoorRefused):
            add_socket_route(app, bad)
    assert app.router.routes == before
    good = ClosedWebSocketRoute("/api/x", endpoint, message_models=(OutcomeResponse,))
    add_socket_route(app, good)
    assert app.router.routes == [*before, good]


def test_the_exemptions_are_exactly_the_docs_paths() -> None:
    """AC-2: the outcome route is on the door (W-066, #172); the boundary exempts the docs GET paths only."""
    import inspect

    from ofo_app import errors
    from ofo_app.routes import outcome

    assert not hasattr(errors, "OUTCOME_EXEMPTION")
    assert "outcome" not in inspect.getsource(errors.install).lower()
    assert outcome.router.route_class is errors.ClosedRoute


# --- W-070 (issue #197): a door response sends only what the door minted - body, header names AND values, status -------
# Third round of finding sealed-object-mutable-after-seal. Written red first (xfail strict, commit "W-070 step 1") on
# main dbe0786; the xfail marks came off with the fix.

EVIL = "https://evil.example/steal"
_MODEL = broker.RefusalOut(code="broker_state_invalid", message=render("broker_state_invalid"))


def _door(kind: str):
    """A fresh sealed door response: a closed JSON 200, or a sealed redirect to a path on this site."""
    from ofo_app.errors import respond, typed_redirect

    if kind == "closed":
        return respond(_MODEL, 200)
    return typed_redirect(broker.BrokerRedirectOut(redirect="connected"), "/connected")


def _wire(response):
    """Send `response` as bare ASGI; return the messages that reached `send`."""
    import asyncio

    sent = []

    async def send(message):
        sent.append(message)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {"type": "http", "method": "GET", "path": "/x", "headers": [], "query_string": b"", "raw_path": b"/x",
             "scheme": "http", "server": ("t", 80), "client": ("c", 1), "http_version": "1.1", "root_path": ""}
    asyncio.run(response(scope, receive, send))
    return sent


def test_core_an_outside_redirect_set_through_location_on_respond_is_refused_through_the_real_app() -> None:
    """AC-2 (#197 core a): `respond(model, 302)` plus `location` answered a 302 to evil.example on main."""
    from ofo_app.errors import respond

    async def endpoint():
        r = respond(_MODEL, 302)
        r.headers["location"] = EVIL
        return r

    response = _client(_app_with_routes(_closed("/api/broker/refusals/{code}", endpoint))).get(PATH, follow_redirects=False)
    _assert_internal_failure_without_the_sentence(response)
    assert "location" not in response.headers and "evil.example" not in str(response.headers)


def test_core_an_exceptions_www_authenticate_value_never_reaches_the_wire_through_the_real_app() -> None:
    """AC-2 (#197 core b): HTTPException(401, headers={WWW-Authenticate: sentence}) echoed the sentence on main."""
    from fastapi import HTTPException

    from ofo_app.errors import WWW_AUTHENTICATE

    async def endpoint():
        raise HTTPException(401, headers={"WWW-Authenticate": SENTENCE})

    response = _client(_app_with_routes(_closed("/api/broker/refusals/{code}", endpoint))).get(PATH)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == WWW_AUTHENTICATE
    assert SENTENCE not in str(response.headers.items())


@pytest.mark.parametrize("kind", ["closed", "redirect"])
@pytest.mark.parametrize("name", sorted(__import__("ofo_app.errors", fromlist=["x"])._DOOR_HEADERS))
def test_every_door_header_set_to_a_sentence_after_construction_is_refused(name: str, kind: str) -> None:
    """AC-2: header NAMES in the door's set are not enough - a changed VALUE is refused too."""
    r = _door(kind)
    r.headers[name] = SENTENCE
    with pytest.raises(api_models.DoorRefused):
        _run_wrapper(r)


@pytest.mark.parametrize("kind,status", [("closed", 201), ("closed", 302), ("redirect", 301), ("redirect", 200)])
def test_a_status_changed_after_construction_is_refused(kind: str, status: int) -> None:
    """AC-2: the status is part of the frozen state."""
    r = _door(kind)
    r.status_code = status
    with pytest.raises(api_models.DoorRefused):
        _run_wrapper(r)


def test_a_background_task_is_refused_and_never_runs() -> None:
    """AC-2: Starlette runs `background` after the send; the door pins it to None and never runs one."""
    from starlette.background import BackgroundTask
    from starlette.routing import Route

    ran = []
    r = _door("closed")
    r.background = BackgroundTask(lambda: ran.append(1))
    with pytest.raises(api_models.DoorRefused):
        _run_wrapper(r)

    async def raw_route(request):
        mutated = _door("closed")
        mutated.background = BackgroundTask(lambda: ran.append(1))
        return mutated

    _assert_internal_failure_without_the_sentence(_client(_app_with_routes(Route("/m", raw_route))).get("/m"))
    assert ran == []


def test_a_verify_shadowed_on_the_instance_does_not_disable_the_check() -> None:
    """AC-2: verification is a module function; `r.verify = lambda: None` plus a mutated body is still refused."""
    r = _door("closed")
    r.verify = lambda: None
    r.body = b"Z" * len(r.body)
    with pytest.raises(api_models.DoorRefused):
        _run_wrapper(r)


def test_init_headers_called_again_is_refused() -> None:
    """AC-2: `init_headers` rewrites raw_headers after construction: refused for a new name (green on main) and for a
    door-set name with a new value (red on main)."""
    for headers in ({"x": SENTENCE}, {"cache-control": SENTENCE}):
        r = _door("closed")
        r.init_headers(headers)
        with pytest.raises(api_models.DoorRefused):
            _run_wrapper(r)


def test_an_allow_header_value_from_an_exception_is_never_copied() -> None:
    """AC-2: HTTPException(405, headers={Allow: sentence}) answers 405 and the sentence is in no header."""
    from fastapi import HTTPException

    async def endpoint():
        raise HTTPException(405, headers={"Allow": SENTENCE})

    response = _client(_app_with_routes(_closed("/api/broker/refusals/{code}", endpoint))).get(PATH)
    assert response.status_code == 405
    assert SENTENCE not in str(response.headers.items())


def test_a_cookie_set_on_a_sealed_redirect_after_typed_redirect_is_refused() -> None:
    """AC-2: a cookie is passed into the constructor; `set_cookie` afterwards changes the frozen headers: refused."""
    r = _door("redirect")
    r.set_cookie("sid", "stolen")
    with pytest.raises(api_models.DoorRefused):
        _run_wrapper(r)


# --- the closed header table and the frozen send (guards of W-070, each with its own killing test) -------------------

def test_the_frozen_copy_is_what_goes_on_the_wire_even_if_verification_is_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-2: with `_verify` patched to nothing, a changed status, a replaced header list and a background task still
    do not reach the wire - the send is from the frozen copy and never runs `background`."""
    from starlette.background import BackgroundTask

    from ofo_app import errors

    ran = []
    clean = _wire(_door("closed"))
    r = _door("closed")
    monkeypatch.setattr(errors, "_verify", lambda response: None)
    r.status_code = 201
    r.raw_headers.append((b"location", EVIL.encode()))
    r.body = b"Z" * len(r.body)
    r.background = BackgroundTask(lambda: ran.append(1))
    assert _wire(r) == clean
    assert ran == []


def test_the_wire_headers_of_a_closed_response_are_exactly_the_minted_table() -> None:
    """AC-2: content-length, content-type, the no-leak pair - nothing else - for a plain answer; 401 adds the constant."""
    from ofo_app.errors import WWW_AUTHENTICATE

    start = _wire(_door("closed"))[0]
    assert start["status"] == 200
    assert start["headers"] == [(b"content-length", str(len(GOLDEN_REFUSAL)).encode()),
                                (b"content-type", b"application/json"), (b"cache-control", b"no-store"),
                                (b"referrer-policy", b"no-referrer")]
    unauthorised = _client(_app_with_routes(_closed("/api/broker/refusals/{code}", _raise(401)))).get(PATH)
    assert unauthorised.headers["www-authenticate"] == WWW_AUTHENTICATE


def _raise(status, headers=None):
    from fastapi import HTTPException

    async def endpoint():
        raise HTTPException(status, headers=headers)

    return endpoint


def test_a_real_framework_405_still_carries_allow_with_method_tokens() -> None:
    """AC-2 parity: a POST to a GET route is a 405 whose Allow names the method (re-minted, not copied)."""
    response = _client(create_app()).post(PATH)
    assert response.status_code == 405
    assert response.headers["allow"] == "GET"


@pytest.mark.parametrize("given,expected", [("GET, POST", "GET, POST"), ("POST,GET,GET", "GET, POST"),
                                            ("get", None), (SENTENCE, None), ("GET, " + SENTENCE, "GET")])
def test_allow_is_rebuilt_from_method_tokens_only(given: str, expected: str | None) -> None:
    """AC-2: tokens outside the fixed method set are dropped; the survivors are sorted, de-duplicated and re-joined."""
    response = _client(_app_with_routes(_closed("/api/broker/refusals/{code}", _raise(405, {"Allow": given})))).get(PATH)
    assert response.status_code == 405 and response.headers.get("allow") == expected


def test_allow_is_not_minted_for_a_status_that_is_not_405() -> None:
    """AC-2: an exception's Allow on a 404 contributes nothing."""
    response = _client(_app_with_routes(_closed("/api/broker/refusals/{code}", _raise(404, {"Allow": "GET"})))).get(PATH)
    assert response.status_code == 404 and "allow" not in response.headers


def test_the_door_refuses_to_mint_an_allow_or_retry_after_that_is_not_closed() -> None:
    """AC-2: the minting table itself rejects a non-method Allow and a non-digit Retry-After."""
    from ofo_app.errors import ClosedResponse

    body = _MODEL
    for kwargs in ({"allow": (SENTENCE,)}, {"allow": ("get",)}, {"retry_after": SENTENCE}, {"retry_after": "6 0"},
                   {"retry_after": "-1"}, {"retry_after": 60}):
        with pytest.raises(api_models.DoorRefused):
            ClosedResponse(body, 503, **kwargs)
    assert dict(_wire(ClosedResponse(body, 503, retry_after="60"))[0]["headers"])[b"retry-after"] == b"60"


@pytest.mark.parametrize("status", [100, 199, 204, 301, 302, 304, 399, 600, 99999, True, "200"])
def test_a_closed_response_is_refused_for_a_status_that_cannot_carry_its_body(status) -> None:
    """AC-2: no 1xx, 204, 3xx (the `respond(model, 302)` + location attack), 304 or out-of-range status."""
    from ofo_app.errors import ClosedResponse

    with pytest.raises(api_models.DoorRefused):
        ClosedResponse(_MODEL, status)


def test_location_is_never_written_on_a_closed_response() -> None:
    """AC-2: a `location` smuggled into the frozen state of a ClosedResponse is refused by the check itself."""
    from ofo_app import errors

    r = _door("closed")
    r.raw_headers.append((b"location", b"/x"))
    errors._freeze(r)  # even a re-freeze (what a forger would try) is not enough: the type's own rule refuses it
    with pytest.raises(api_models.DoorRefused):
        errors._verify(r)


@pytest.mark.parametrize("field,bad", [("name", "a b"), ("name", ""), ("value", "a b"), ("value", "Max-Age=0"),
                                       ("value", SENTENCE), ("path", "/p q"), ("path", "no-slash"),
                                       ("path", "/p,Domain=x")])
def test_a_cookie_outside_the_token_patterns_is_refused(field: str, bad: str) -> None:
    """AC-2: RedirectCookie name, value and path are token-shaped (a sentence or a space is refused)."""
    from ofo_app.errors import RedirectCookie

    kwargs = {"name": "ofo_kite_login", "path": "/kite/callback", "value": "abc-DEF_123", field: bad}
    with pytest.raises(ValueError):
        RedirectCookie(**kwargs)


def test_a_cookie_is_written_into_the_constructor_and_a_refusal_clears_it() -> None:
    """AC-2: the cookie header is in the frozen state from the start; a cleared cookie carries Max-Age=0."""
    from ofo_app.errors import RedirectCookie, typed_redirect

    model = broker.BrokerRedirectOut(redirect="connected")
    cookie = RedirectCookie("ofo_kite_login", "/kite/callback", value="abc-DEF_123", max_age=600, secure=True)
    headers = dict(_wire(typed_redirect(model, "/connected", cookie))[0]["headers"])
    assert headers[b"set-cookie"] == (b"ofo_kite_login=abc-DEF_123; HttpOnly; Max-Age=600; Path=/kite/callback; "
                                      b"SameSite=lax; Secure")
    cleared = dict(_wire(typed_redirect(model, "/connected", RedirectCookie("ofo_kite_login", "/kite/callback")))[0]
                   ["headers"])
    assert b"Max-Age=0" in cleared[b"set-cookie"] and b"Path=/kite/callback" in cleared[b"set-cookie"]


def test_the_login_refusal_still_clears_the_state_cookie_through_handle_error() -> None:
    """AC-2 parity: a UserFacing exception carrying `clear_cookie` answers with the cookie cleared (Max-Age=0)."""
    from ofo_app.errors import RedirectCookie
    from ofo_app.routes.broker import BrokerLoginRefused

    async def endpoint():
        raise BrokerLoginRefused("broker_login_busy", clear_cookie=RedirectCookie("ofo_kite_login", "/kite/callback"))

    response = _client(_app_with_routes(_closed("/api/broker/refusals/{code}", endpoint))).get(PATH)
    assert "Max-Age=0" in response.headers["set-cookie"] and "Path=/kite/callback" in response.headers["set-cookie"]


def test_no_instance_method_can_stand_in_for_the_check() -> None:
    """AC-2: neither door class has a `verify` method any more (it was resolved on the instance and could be shadowed)."""
    from ofo_app.errors import ClosedResponse, SealedRedirect

    assert not hasattr(ClosedResponse, "verify") and not hasattr(SealedRedirect, "verify")


def test_a_frozen_state_that_was_never_set_or_was_replaced_by_a_wrong_shape_is_refused() -> None:
    """AC-2: a response with no frozen copy, a list for the header pairs, or a header pair that is not bytes is refused."""
    r = _door("closed")
    r.raw_headers[0] = [b"content-length", b"1"]
    with pytest.raises(api_models.DoorRefused):
        _run_wrapper(r)
    r = _door("closed")
    r.raw_headers[0] = ("content-length", "1")
    with pytest.raises(api_models.DoorRefused):
        _run_wrapper(r)
    r = _door("closed")
    del r._frozen
    with pytest.raises(api_models.DoorRefused):
        _run_wrapper(r)


# --- W-070 round 4 (issue #197): the minted record itself is re-checked against the closed table ----------------------
# Finding sealed-object-mutable-after-seal, round 4. Written red first (xfail strict), the marks come off with the fix.

def _through_app(endpoint):
    return _client(_app_with_routes(_closed("/api/broker/refusals/{code}", endpoint))).get(PATH, follow_redirects=False)


def _assert_minted_500(response) -> None:
    _assert_internal_failure_without_the_sentence(response)
    assert response.headers["cache-control"] == "no-store"
    assert "set-cookie" not in response.headers and "public" not in str(response.headers.items())


def test_core_a_record_rewritten_with_a_sentence_header_and_an_attacker_cookie_is_refused_through_the_app() -> None:
    """AC-2 (#197 round 4 core a): headers rewritten, then the record re-frozen with the module's own `_freeze`."""
    from ofo_app import errors

    async def endpoint():
        r = errors.respond(_MODEL, 200)
        r.headers["cache-control"] = SENTENCE
        r.headers["set-cookie"] = "sid=attacker; Domain=example.com; Path=/"
        errors._freeze(r)
        return r

    response = _through_app(endpoint)
    _assert_minted_500(response)
    assert "attacker" not in str(response.headers.items()) and SENTENCE not in str(response.headers.items())


def test_core_b_a_rewritten_record_tuple_with_a_public_cache_control_is_refused_through_the_app() -> None:
    """AC-2 (#197 round 4 core b): `_frozen` assigned a tuple whose cache-control is `public, max-age=31536000`."""
    from ofo_app import errors

    async def endpoint():
        r = errors.respond(_MODEL, 200)
        headers = tuple((k, b"public, max-age=31536000" if k == b"cache-control" else v) for k, v in r.raw_headers)
        r.raw_headers[:] = list(headers)
        r._frozen = (200, headers, r.body, _MODEL, False)
        return r

    _assert_minted_500(_through_app(endpoint))


_BAD_RECORDS = {
    "content-type": lambda h: [(k, b"text/html" if k == b"content-type" else v) for k, v in h],
    "content-length": lambda h: [(k, b"1" if k == b"content-length" else v) for k, v in h],
    "referrer-policy": lambda h: [(k, b"unsafe-url" if k == b"referrer-policy" else v) for k, v in h],
    "www-authenticate": lambda h: h + [(b"www-authenticate", SENTENCE.encode())],
    "retry-after": lambda h: h + [(b"retry-after", b"soon, see https://evil.example")],
    "allow": lambda h: h + [(b"allow", b"GET, SHOUT")],
    "cookie-extra-attribute": lambda h: h + [(b"set-cookie", b"ofo=abc; Domain=example.com; HttpOnly; Path=/")],
    "cookie-sentence": lambda h: h + [(b"set-cookie", b"ofo=" + SENTENCE.encode())],
    "location-on-closed": lambda h: h + [(b"location", b"/x")],
    "duplicate-cache-control": lambda h: h + [(b"cache-control", b"no-store")],
}


@pytest.mark.parametrize("name", sorted(_BAD_RECORDS))
def test_every_value_in_a_rewritten_record_is_rechecked_against_the_closed_table(name: str) -> None:
    """AC-2: the record is re-frozen after each header VALUE rule is broken in turn; the door refuses every one."""
    from ofo_app import errors

    r = _door("closed")
    r.raw_headers[:] = _BAD_RECORDS[name](list(r.raw_headers))
    errors._freeze(r)
    with pytest.raises(api_models.DoorRefused):
        _run_wrapper(r)


@pytest.mark.parametrize("what", ["cookie-domain", "location-outside"])
def test_a_redirect_record_with_an_outside_location_or_a_foreign_cookie_is_refused(what: str) -> None:
    """AC-2: same re-check on a sealed redirect: a cookie with a Domain attribute, a Location off this site."""
    from ofo_app import errors

    r = _door("redirect")
    if what == "cookie-domain":
        r.raw_headers[:] = list(r.raw_headers) + [(b"set-cookie", b"ofo=abc; Domain=example.com; HttpOnly; Path=/")]
    else:
        r.raw_headers[:] = [(k, EVIL.encode() if k == b"location" else v) for k, v in r.raw_headers]
    errors._freeze(r)
    with pytest.raises(api_models.DoorRefused):
        _run_wrapper(r)


def test_a_record_the_door_itself_minted_still_passes_with_every_header_kind() -> None:
    """AC-2 (parity, green before and after): 401 www-authenticate, retry-after, allow and a cookie verify and are sent."""
    from ofo_app.errors import ClosedResponse, RedirectCookie

    r = ClosedResponse(render("broker_state_invalid"), 401, retry_after="60",
                       allow=("POST", "GET"), cookie=RedirectCookie("ofo_kite_login", "/kite/callback", value="abc"))
    sent = _wire(r)
    assert sent[0]["status"] == 401
    headers = dict(sent[0]["headers"])
    assert headers[b"allow"] == b"GET, POST" and headers[b"retry-after"] == b"60"
    assert headers[b"www-authenticate"] == b'Session realm="OptionsForOptions2"'


def test_a_user_facing_refusal_with_no_failure_value_still_clears_its_cookie() -> None:
    """AC-2 (review MINOR-1): the error path with NO `failure` (status from the error class) carries the cookie too;
    a cookie set after construction there, or dropped, is caught (mutation M2c)."""
    from ofo_app.errors import RedirectCookie
    from ofo_app.routes.broker import BrokerLoginRefused

    async def endpoint():
        raise BrokerLoginRefused("broker_state_invalid", clear_cookie=RedirectCookie("ofo_kite_login", "/kite/callback"))

    exc = BrokerLoginRefused("broker_state_invalid")
    assert exc.failure is None  # the path under test: the class status, not a Failure's
    response = _through_app(endpoint)
    assert response.status_code == 401
    assert "Max-Age=0" in response.headers["set-cookie"] and "Path=/kite/callback" in response.headers["set-cookie"]
    assert response.headers["cache-control"] == "no-store"


def test_the_app_middleware_list_is_exactly_the_boundary() -> None:
    """AC-2 (review MINOR-2): middleware added outside `_Boundary` would sit around the door and could rewrite what it
    sent. Adding one is a deliberate change to this list, reviewed with the door."""
    from ofo_app.errors import _Boundary

    assert [m.cls for m in create_app().user_middleware] == [_Boundary]


# --- W-070 round 5 (issue #197): Location is re-minted, not tested against a list of banned characters ----------------
# Finding sealed-object-mutable-after-seal, round 5. Written red first (xfail strict), the marks come off with the fix.

_BAD_LOCATIONS = (["/\t/evil.example/steal", "/ /evil.example/steal", "/%2F/evil.example", "/%2f/evil.example",
                   "/%5Cevil.example", "/a b", "/\x7f/x", "/é"]
                  + [f"/{chr(c)}/evil.example/steal" for c in range(0x20) if c not in (0x0A, 0x0D)])  # CR and LF were refused already


def _redirect_with_location(location: str):
    from ofo_app import errors

    r = _door("redirect")
    r.raw_headers[:] = [(k, location.encode("latin-1") if k == b"location" else v) for k, v in r.raw_headers]
    errors._freeze(r)
    return r


@pytest.mark.parametrize("location", _BAD_LOCATIONS, ids=lambda s: ascii(s))
def test_a_rewritten_and_refrozen_location_that_the_door_would_not_mint_is_refused(location: str) -> None:
    """AC-2 (#197 round 5 core a): a tab, any C0 control, DEL, a space or an encoded slash in the path, re-frozen."""
    with pytest.raises(api_models.DoorRefused):
        _run_wrapper(_redirect_with_location(location))


def test_core_a_tab_location_rewritten_and_refrozen_is_the_minted_500_through_the_app() -> None:
    """AC-2 (#197 round 5 core a): through the real app a raw tab in Location answered a 302 on cce0e6a."""
    async def endpoint():
        return _redirect_with_location("/\t/evil.example/steal")

    response = _through_app(endpoint)
    _assert_minted_500(response)
    assert "location" not in response.headers


@pytest.mark.parametrize("location", ["/\r/evil.example/steal", "/\n/evil.example/steal", "/\\evil.example"])
def test_a_rewritten_location_with_cr_lf_or_a_backslash_stays_refused(location: str) -> None:
    """AC-2 (parity, green before and after): the three characters the old predicate named."""
    with pytest.raises(api_models.DoorRefused):
        _run_wrapper(_redirect_with_location(location))


@pytest.mark.parametrize("location", ["/connected", "/connected?code=broker_state_invalid", "/a/b%20c/d~e_f-g.h", "/%E2%82%AC"])
def test_a_location_the_door_mints_itself_still_verifies(location: str) -> None:
    """AC-2 (parity, green before and after): ordinary paths, a query and percent escapes stay accepted."""
    from ofo_app.errors import typed_redirect

    sent = _wire(typed_redirect(broker.BrokerRedirectOut(redirect="connected"), location))
    assert sent[0]["status"] == 302 and dict(sent[0]["headers"])[b"location"] == location.encode()


# --- W-070 round 6 (issue #197): the door MINTS the body from a model; a ready-made body is never accepted ---------------
# Finding sealed-object-mutable-after-seal, round 6. Written red first (xfail strict, commit "W-070 round 6 step 1"); the
# marks come off with the fix. Rounds 4-5 took an `Emitted` from the caller and scanned for the shapes that forge one; a
# deny-list of object-construction shapes can never be complete (the verifier found five more). Now ClosedResponse takes the
# SOURCE (an ApiModel or a UserFacingError), calls emit itself, and `_verify` re-emits and demands the same bytes.

_FORGED = ('{"code":"x","message":"' + SENTENCE + '"}').encode()


def _emitted_type():
    return type(api_models.emit(broker.BrokerRedirectOut(redirect="connected")))


def _forged_through_the_app(make):
    from ofo_app.errors import ClosedResponse

    async def endpoint():
        return ClosedResponse(make(), 200)

    return _through_app(endpoint)


def _forge_a():
    import copyreg

    return copyreg._reconstructor(_emitted_type(), bytes, _FORGED)


def _forge_b():
    T = _emitted_type()
    return super(T, T).__new__(T, _FORGED)


def _forge_c():
    class F(bytes):
        __slots__ = ()

    f = F(_FORGED)
    f.__class__ = _emitted_type()
    return f


def _forge_d():
    import copyreg
    import pickle

    return pickle.loads(pickle.dumps(copyreg._reconstructor(_emitted_type(), bytes, _FORGED), protocol=0))


@pytest.mark.parametrize("forge", [_forge_a, _forge_b, _forge_c, _forge_d], ids=["A-copyreg", "B-super-new", "C-class-assign", "D-pickle"])
def test_round6_a_forged_body_cannot_even_be_passed_in_through_the_app(forge) -> None:
    """AC-2 (#197 round 6, shapes A-D): a forged `Emitted` handed to the constructor is the minted 500 (the constructor
    takes a model, not bytes)."""
    response = _forged_through_the_app(forge)
    _assert_minted_500(response)


def test_round6_e_a_sealed_body_rewritten_in_place_by_ctypes_fails_the_reemit_through_the_app() -> None:
    """AC-2 (#197 round 6, shape E): `ctypes.memmove` rewrites the bytes of a sealed body; `_verify` re-emits from the
    stored model and the bytes differ, so the answer is the minted 500."""
    import ctypes

    from ofo_app import errors

    async def endpoint():
        r = errors.respond(_MODEL, 200)
        body = r.body
        new = (b'"' + SENTENCE.encode() * 10)[:len(body)]
        ctypes.memmove(id(body) + bytes.__basicsize__ - 1, new, len(new))
        return r

    _assert_minted_500(_through_app(endpoint))


@pytest.mark.parametrize("ready_made", [b'{"note":"free text"}', "emitted"], ids=["bytes", "Emitted"])
def test_round6_the_constructor_refuses_any_ready_made_body(ready_made) -> None:
    """AC-2 (#197 round 6): `ClosedResponse(bytes_or_Emitted, ...)` is a TypeError, even for a genuine `Emitted`."""
    from ofo_app.errors import ClosedResponse

    body = api_models.emit(_MODEL) if ready_made == "emitted" else ready_made
    with pytest.raises(TypeError):
        ClosedResponse(body, 200)  # type: ignore[arg-type]


def test_round6_a_body_swapped_for_another_models_and_refrozen_is_refused() -> None:
    """AC-2 (#197 round 6): the stored source is part of the frozen record, so another model's genuine body, with its
    headers, re-frozen with the module's `_freeze`, no longer equals the re-emit of the stored model."""
    from ofo_app import errors

    other = errors.respond(broker.RefusalOut(code="broker_login_busy", message=render("broker_login_busy")), 200)
    r = _door("closed")
    r.body = other.body
    r.raw_headers[:] = list(other.raw_headers)
    errors._freeze(r)
    with pytest.raises(api_models.DoorRefused):
        _run_wrapper(r)


# --- issue #200 N5: the seal marks only the response actually sent ------------------------------------------------------

def _bare_scope() -> dict:
    return {"type": "http", "method": "GET", "path": "/x", "headers": [], "query_string": b"", "raw_path": b"/x",
            "scheme": "http", "server": ("t", 80), "client": ("c", 1), "http_version": "1.1", "root_path": ""}


def _through_boundary(app) -> list:
    """Run `app` as bare ASGI inside the door's `_Boundary`; return the messages that reached the wire."""
    import asyncio

    from ofo_app.errors import _Boundary

    sent = []

    async def send(message):
        sent.append(message)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    asyncio.run(_Boundary(app)(_bare_scope(), receive, send))
    return sent


def _assert_only_the_internal_500(sent) -> None:
    starts = [m for m in sent if m["type"] == "http.response.start"]
    assert [m["status"] for m in starts] == [500]
    assert all((b"x-evil", b"unminted") not in m["headers"] for m in starts)
    assert SENTENCE.encode() not in b"".join(m.get("body", b"") for m in sent)
    body = json.loads(b"".join(m.get("body", b"") for m in sent))
    assert body["code"] == "INTERNAL_SYSTEM_002"  # catalogue template internal_system_request_failed


def test_n5_a_seal_stamped_by_a_response_that_was_never_sent_does_not_let_raw_bytes_through() -> None:
    """AC-2 (#200 N5, the verifier's probe of 2026-10-12): a door response called as an ASGI app with a send that goes
    nowhere seals nothing; the raw start and body then written through the real send are dropped, and the wire gets
    only the internal-system 500."""
    from ofo_app.errors import respond

    async def nowhere(message):
        return None

    async def app(scope, receive, send):
        await respond(_MODEL, 200)(scope, receive, nowhere)
        await send({"type": "http.response.start", "status": 200, "headers": [(b"x-evil", b"unminted")]})
        await send({"type": "http.response.body", "body": SENTENCE.encode()})

    _assert_only_the_internal_500(_through_boundary(app))


def test_n5_a_door_start_message_changed_on_its_way_to_the_wire_is_dropped() -> None:
    """AC-2 (#200 N5): a send wrapper that edits the door's own start message in place (an added header) before passing
    it on does not get it through: the boundary compares it with the record of what the door sent."""
    from ofo_app.errors import respond

    async def app(scope, receive, send):
        async def editing_send(message):
            if message["type"] == "http.response.start":
                message["headers"].append((b"x-evil", b"unminted"))
            await send(message)
        await respond(_MODEL, 200)(scope, receive, editing_send)

    _assert_only_the_internal_500(_through_boundary(app))


def test_n5_a_door_body_swapped_on_its_way_to_the_wire_is_dropped() -> None:
    """AC-2 (#200 N5): a send wrapper that passes the door's start but swaps its body message for free text gets the body
    dropped: after a sealed start only the very body message the door sent passes."""
    from ofo_app.errors import respond

    async def app(scope, receive, send):
        async def swapping_send(message):
            if message["type"] == "http.response.body":
                message = {"type": "http.response.body", "body": SENTENCE.encode()}
            await send(message)
        await respond(_MODEL, 200)(scope, receive, swapping_send)

    sent = _through_boundary(app)
    assert SENTENCE.encode() not in b"".join(m.get("body", b"") for m in sent)


def test_n5_the_door_messages_sent_twice_by_a_wrapper_reach_the_wire_once() -> None:
    """AC-2 (#200 N5): a send wrapper that passes each door message on twice gets exactly one start and one body
    through: the seal admits one start, then one body, then nothing."""
    from ofo_app.errors import respond

    async def app(scope, receive, send):
        async def twice(message):
            await send(message)
            await send(message)
        await respond(_MODEL, 200)(scope, receive, twice)

    assert _through_boundary(app) == _wire(_door("closed"))


def test_n5_hand_made_copies_of_the_door_messages_after_a_nowhere_send_are_dropped() -> None:
    """AC-2 (#200 N5): the seal vouches for the message objects the door handed to send, not for look-alikes: after a
    door response was called with a send that goes nowhere, byte-identical copies of its start and body sent by hand
    are refused (only the internal-system 500 reaches the wire)."""
    from ofo_app.errors import respond

    copies = [dict(m) for m in _wire(_door("closed"))]

    async def nowhere(message):
        return None

    async def app(scope, receive, send):
        await respond(_MODEL, 200)(scope, receive, nowhere)
        for message in copies:
            await send(dict(message))

    sent = _through_boundary(app)
    assert [m["status"] for m in sent if m["type"] == "http.response.start"] == [500]
    assert json.loads(b"".join(m.get("body", b"") for m in sent))["code"] == "INTERNAL_SYSTEM_002"


def test_n5_the_seal_lets_the_door_response_that_is_really_sent_through_byte_for_byte() -> None:
    """AC-2 (#200 N5, the other branch): a door response sent through the boundary reaches the wire unchanged, and the
    real route still answers its golden bytes."""
    from ofo_app.errors import respond

    async def app(scope, receive, send):
        await respond(_MODEL, 200)(scope, receive, send)

    assert _through_boundary(app) == _wire(_door("closed"))
    response = _client(create_app()).get(PATH)
    assert response.status_code == 200 and response.content == GOLDEN_REFUSAL
