"""REQ-048 AC-5 (W-134): no request model accepts a field it does not name, so a browser-sent ``eligible`` /
``executable`` / ``tradable`` cannot ride in on any route that leads to an execution decision (T1 #176).

Discovery, not a list: every request body of every route in ``docs/api/openapi.json`` must be a closed object
(``additionalProperties: false``). A body that cannot be resolved fails closed.
Guards knowledge/findings/caller-supplied-verdict-trusted.json."""
import json
import pathlib

OPENAPI = pathlib.Path(__file__).resolve().parents[1] / "docs" / "api" / "openapi.json"
BODY_METHODS = {"post", "put", "patch", "delete"}
#: routes whose body must exist and be closed because they lead to an execution decision
EXECUTION_ROUTES = {"/strategies/{strategy_id}/execute", "/api/strategies/planned-entry"}


def open_request_bodies(doc: dict) -> list[str]:
    schemas = doc["components"]["schemas"]
    found = []
    for path, ops in doc["paths"].items():
        for method, op in ops.items():
            body = op.get("requestBody") if method in BODY_METHODS else None
            if not body:
                continue
            ref = ((body.get("content") or {}).get("application/json") or {}).get("schema", {}).get("$ref", "")
            schema = schemas.get(ref.rsplit("/", 1)[-1])
            if schema is None:
                found.append(f"{method.upper()} {path}: request body not resolvable")
            elif schema.get("additionalProperties") is not False:
                found.append(f"{method.upper()} {path}: {ref.rsplit('/', 1)[-1]} accepts unnamed fields")
    return found


def test_every_request_body_is_a_closed_object():
    assert open_request_bodies(json.loads(OPENAPI.read_text(encoding="utf-8"))) == []


def test_the_execution_routes_are_among_the_checked_bodies():
    doc = json.loads(OPENAPI.read_text(encoding="utf-8"))
    with_body = {p for p, ops in doc["paths"].items() if any(o.get("requestBody") for o in ops.values())}
    assert with_body >= EXECUTION_ROUTES


def test_a_planted_open_request_model_is_red():
    doc = json.loads(OPENAPI.read_text(encoding="utf-8"))
    del doc["components"]["schemas"]["ExecuteIn"]["additionalProperties"]
    assert open_request_bodies(doc) == ["POST /strategies/{strategy_id}/execute: ExecuteIn accepts unnamed fields"]
    doc = json.loads(OPENAPI.read_text(encoding="utf-8"))
    del doc["components"]["schemas"]["ExecuteIn"]
    assert "not resolvable" in open_request_bodies(doc)[0]
