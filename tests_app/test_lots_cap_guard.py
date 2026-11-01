"""GC-SET lots (REQ-167 AC-5) guard: the lot cap is ONE setting (``limits.max_lots``) behind ONE shared check.

Every request-body field named ``lots`` or ``base_lots`` on any route must (a) carry only the type sanity bound in its
schema (never a typed business number) and (b) sit on a route whose endpoint reaches ``check_lots``. A route or model
shape this guard cannot resolve fails closed (an unknown route with such a field is refused until it is listed).
No database; a source read.
"""

from __future__ import annotations

import inspect
import typing

import pytest
from ofo.errors.slots import INT_ABS_MAX
from ofo_app.main import create_app
from ofo_app.routes import leg_edit, outcome
from pydantic import BaseModel

LOT_FIELDS = frozenset({"lots", "base_lots"})
#: route path -> why its endpoint reaches check_lots (asserted by source below)
COVERED = {"/api/strategies/outcome": outcome.outcome_response, "/api/strategies/leg-edit": leg_edit.leg_edit}


def _models_in(annotation: object, seen: set[type]) -> typing.Iterator[type[BaseModel]]:
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        if annotation in seen:
            return
        seen.add(annotation)
        yield annotation
        for field in annotation.model_fields.values():
            yield from _models_in(field.annotation, seen)
    for arg in typing.get_args(annotation):
        yield from _models_in(arg, seen)


def _lot_routes() -> dict[str, list[tuple[type[BaseModel], str]]]:
    """route path -> every (model, field) named in LOT_FIELDS reachable from its request body."""
    found: dict[str, list[tuple[type[BaseModel], str]]] = {}
    for route in create_app().routes:
        body = getattr(route, "body_field", None)
        if body is None:
            continue
        for model in _models_in(body.field_info.annotation, set()):
            hits = [(model, name) for name in model.model_fields if name in LOT_FIELDS]
            if hits:
                found.setdefault(route.path, []).extend(hits)
    return found


def _reaches_check_lots(fn: object) -> bool:
    source = inspect.getsource(fn)  # type: ignore[arg-type]
    if "check_lots(" in source:
        return True
    if "checked_choice(" in source:
        return "check_lots(" in inspect.getsource(outcome.checked_choice)
    return False


def test_the_guard_finds_the_known_lots_routes():
    assert set(_lot_routes()) >= set(COVERED)


def test_every_route_with_a_lots_field_is_listed_and_reaches_the_shared_check():
    routes = _lot_routes()
    assert [p for p in routes if p not in COVERED] == [], "a route takes lots and is not listed in COVERED"
    assert [p for p, fn in COVERED.items() if not _reaches_check_lots(fn)] == []


def test_no_lots_field_types_a_business_number_in_its_schema():
    """Only the type sanity bound (INT_ABS_MAX) may bound a lots field: the cap is the setting."""
    for path, hits in _lot_routes().items():
        for model, name in hits:
            les = [m.le for m in model.model_fields[name].metadata if hasattr(m, "le")]
            assert les == [INT_ABS_MAX], (path, model.__name__, name, les)


def test_mutation_a_route_that_skips_the_shared_check_is_refused():
    async def skipping(req):  # a stand-in endpoint that never reaches the shared check
        return req

    assert _reaches_check_lots(skipping) is False
    with pytest.raises(AssertionError):
        assert [p for p, fn in {"/x": skipping}.items() if not _reaches_check_lots(fn)] == []
