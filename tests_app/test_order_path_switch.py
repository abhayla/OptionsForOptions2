"""W-121 (REQ-073 AC-6, ADR-165): the order path is switched off by one server switch.

AC-6: "every route that prepares, posts or checks an order at a broker (Execute, the return check, and any basket or
trigger route added later) refuses before any Zerodha read or database write, and the screens offer no Execute action".

Core proof: ``create_app()`` with APP_ENV unset and OFO_ORDER_PATH=1 answers POST /strategies/1/execute and
/strategies/1/execution/return with the refusal; the fake Kite session and the database session are never asked for.

Pinned tables (exact, nothing else turns the path on):
- APP_ENV must be exactly ``test``: unset, ``production``, ``staging``, ``TEST``, `` test `` (spaces), ``testing``
  -> off.
- OFO_ORDER_PATH under APP_ENV=test: ``1``, ``true``, ``yes``, ``on`` (case and edge spaces ignored) -> on;
  ``0``, empty, ``off``, ``no``, ``false``, unset, anything else -> off.

Second layer (repo_scan): every route of ``create_app()`` whose endpoint module imports an order module (by IMPORT
SOURCE, not by path text) carries ``require_order_path`` in its dependency tree; a route whose module cannot be
resolved fails the scan (fail closed).
"""
from __future__ import annotations

import ast
import importlib.util
import inspect
import sys
from collections.abc import Iterator
from http import HTTPStatus

import pytest
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient
from ofo_app import order_path_switch as switch
from ofo_app.db import get_db
from ofo_app.main import create_app
from ofo_app.routes import execute, execution_return
from sqlalchemy import text

SENTENCE = "Placing orders from this app is switched off for now."
ORDER_ROUTES = ("/strategies/1/execute", "/strategies/1/execution/return")

#: The import sources that make a module an ORDER module (it prepares, posts or checks an order at a broker). A module
#: matches when an import resolves to one of these dotted names or to anything below it.
ORDER_SOURCES = ("ofo.execution", "ofo_app.execute_plan", "ofo_app.execution_plan_store", "ofo_app.basket_post",
                 "ofo_app.checked_basket", "ofo_app.execution_return", "ofo_app.return_book")

#: Routes that import an order module and may stay open. Exactly none: a read route that needs one gets listed here,
#: with the reason, by the change that adds it (guard-as-forbidden-list: the allowed set is named, not the forbidden).
OPEN_ORDER_MODULE_ROUTES: frozenset[tuple[str, str]] = frozenset()

#: Framework routes (docs pages, only mounted in test) whose endpoint module is the framework itself.
FRAMEWORK_MODULES = frozenset({"fastapi.applications"})


@pytest.fixture
def no_dotenv(tmp_path, monkeypatch):
    """APP_ENV is read from the process environment, then from ``.env`` in the working directory: use an empty one."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv(switch.ENV_NAME, raising=False)


# ---- the switch ----------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("app_env", [None, "", "production", "staging", "development", "TEST", " test ", "Test",
                                     "testing", "test\n"])
@pytest.mark.parametrize("flag", ["1", "true", "yes", "on"])
def test_ac6_off_under_every_environment_but_exactly_test(no_dotenv, monkeypatch, app_env, flag):
    if app_env is not None:
        monkeypatch.setenv("APP_ENV", app_env)
    monkeypatch.setenv(switch.ENV_NAME, flag)
    assert switch.order_path_on() is False


@pytest.mark.parametrize(("flag", "expected"), [
    ("1", True), ("true", True), ("yes", True), ("on", True), ("ON", True), (" True ", True),
    ("0", False), ("", False), ("off", False), ("no", False), ("false", False), ("2", False), ("enabled", False),
    (None, False),
])
def test_ac6_flag_table_under_app_env_test(no_dotenv, monkeypatch, flag, expected):
    monkeypatch.setenv("APP_ENV", "test")
    if flag is not None:
        monkeypatch.setenv(switch.ENV_NAME, flag)
    assert switch.order_path_on() is expected


def test_ac6_unreadable_environment_is_off(no_dotenv, monkeypatch):
    """A failure to read APP_ENV is off, never on."""
    monkeypatch.setenv(switch.ENV_NAME, "1")

    def broken() -> str:
        raise ValueError("bad .env")

    monkeypatch.setattr(switch, "app_env", broken)
    assert switch.order_path_on() is False


# ---- the core proof over HTTP --------------------------------------------------------------------------------------

class _Counter:
    def __init__(self) -> None:
        self.kite = 0
        self.db = 0


def _app_with_counters(counter: _Counter):
    app = create_app()

    def kite_session():
        counter.kite += 1
        raise AssertionError("a Kite session was asked for while the order path is off")

    async def db():
        counter.db += 1
        raise AssertionError("a database session was asked for while the order path is off")
        yield  # pragma: no cover - makes this an async generator like get_db

    app.dependency_overrides[execute.get_kite_session] = kite_session
    app.dependency_overrides[get_db] = db
    return app


def _client(app) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


@pytest.mark.parametrize("path", ORDER_ROUTES)
async def test_ac6_core_both_order_routes_refuse_before_any_kite_read_or_db_use(no_dotenv, monkeypatch, path):
    """Core: APP_ENV unset + OFO_ORDER_PATH=1 -> the refusal body, 0 Kite sessions, 0 database sessions."""
    monkeypatch.setenv(switch.ENV_NAME, "1")
    counter = _Counter()
    app = _app_with_counters(counter)
    body = {"action": "ENTRY"} if path.endswith("execute") else None
    async with _client(app) as ac:
        response = await ac.post(path, json=body)
    assert response.status_code == HTTPStatus.CONFLICT, response.text
    answer = response.json()
    assert answer["what_happened"] == SENTENCE
    assert answer["next_action"] == "You can build, save and track strategies."
    assert (counter.kite, counter.db) == (0, 0)


async def test_ac6_refusal_comes_before_body_handling_and_gets_no_plan_number(no_dotenv, monkeypatch):
    """A body that would be refused on its own (empty, wrong action) still gets the order-path refusal first."""
    monkeypatch.setenv(switch.ENV_NAME, "1")
    counter = _Counter()
    async with _client(_app_with_counters(counter)) as ac:
        for path, body in (("/strategies/1/execute", {}), ("/strategies/1/execute", {"action": "NOPE"}),
                           ("/strategies/not-a-number/execution/return", None)):
            response = await ac.post(path, json=body)
            assert response.status_code == HTTPStatus.CONFLICT and response.json()["what_happened"] == SENTENCE, path
    assert (counter.kite, counter.db) == (0, 0)


async def test_ac6_the_dependency_is_what_stops_it_not_the_stubs(no_dotenv, monkeypatch):
    """Discrimination: with the switch ON the same request reaches the Kite dependency (the test stub is called), so the
    zero counts above come from the refusal and not from a route that never runs."""
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv(switch.ENV_NAME, "1")
    counter = _Counter()
    async with _client(_app_with_counters(counter)) as ac:
        response = await ac.post("/strategies/1/execute", json={"action": "ENTRY"})
    assert counter.kite == 1  # the stub's own error is the error boundary's 500: not the order-path refusal
    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR


async def test_ac6_no_execution_plan_row_and_no_plan_number_when_off(no_dotenv, monkeypatch, app_engine):
    """The refused POSTs leave the execution plan tables as they were (count before == after), through the real
    ``get_db`` on the test database."""
    monkeypatch.setenv(switch.ENV_NAME, "1")
    count_sql = text("SELECT (SELECT count(*) FROM public.execution_plans), "
                     "(SELECT count(*) FROM public.execution_plan_orders)")
    async with app_engine.connect() as conn:
        before = tuple((await conn.execute(count_sql)).one())
    app = create_app()
    assert get_db not in app.dependency_overrides  # the real session dependency, on the test database
    async with _client(app) as ac:
        for path in ORDER_ROUTES:
            response = await ac.post(path, json={"action": "ENTRY"})
            assert response.status_code == HTTPStatus.CONFLICT
    async with app_engine.connect() as conn:
        after = tuple((await conn.execute(count_sql)).one())
    assert after == before


async def test_features_read_says_off_and_on(no_dotenv, monkeypatch):
    """The screens' read: ``off`` by default, ``on`` only under APP_ENV=test + the flag; the body is exactly order_path
    + the W-125 held list
    (nothing listed outside development/test; under APP_ENV=test every held feature is on)."""
    monkeypatch.setenv(switch.ENV_NAME, "1")
    async with _client(create_app()) as ac:
        off = await ac.get("/features")
        monkeypatch.setenv("APP_ENV", "test")
        on = await ac.get("/features")
    assert off.status_code == on.status_code == HTTPStatus.OK
    held_in_test = ["platform_strikes", "probability_of_profit", "delayed_prices", "history_charts", "events_calendar",
                    "fii_dii", "market_event_warning", "strategy_price_history"]
    assert off.json() == {"order_path": "off", "held": []}
    assert on.json() == {"order_path": "on", "held": held_in_test}


# ---- the structural second layer -----------------------------------------------------------------------------------

def _imports_of(module_name: str) -> set[str]:
    """Every dotted name the module imports, read from its source (``import a.b`` -> a.b; ``from a import b`` -> a.b,
    relative imports resolved). Raises when the module or its source cannot be read: the scan fails closed."""
    module = sys.modules.get(module_name)
    if module is None:
        raise LookupError(f"{module_name}: not imported, cannot be scanned")
    source = inspect.getsource(module)
    out: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            out |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            base = importlib.util.resolve_name("." * node.level + (node.module or ""), module.__package__) \
                if node.level else (node.module or "")
            out.add(base)
            out |= {f"{base}.{alias.name}" for alias in node.names}
    return out


def _is_order_import(dotted: str) -> bool:
    return any(dotted == src or dotted.startswith(src + ".") for src in ORDER_SOURCES)


def _walk(dependant) -> Iterator:
    for sub in dependant.dependencies:
        yield sub
        yield from _walk(sub)


def _has_guard(route: APIRoute) -> bool:
    return any(sub.call is switch.require_order_path for sub in _walk(route.dependant))


def unguarded_order_routes(app) -> list[str]:
    """Routes whose endpoint module imports an order module and that lack the guard (minus the allow-list); a route that
    cannot be resolved is reported too (fail closed). Pure function of the app so the mutation tests can reuse it."""
    problems: list[str] = []
    for route in app.routes:
        label = f"{type(route).__name__} {getattr(route, 'path', '?')}"
        endpoint = getattr(route, "endpoint", None)
        if endpoint is None:
            problems.append(f"{label}: no endpoint, cannot tell what it imports")
            continue
        module_name = getattr(inspect.unwrap(endpoint), "__module__", None)
        if module_name in FRAMEWORK_MODULES:
            continue
        try:
            order_import = any(_is_order_import(name) for name in _imports_of(str(module_name)))
        except (LookupError, OSError, TypeError, SyntaxError) as exc:
            problems.append(f"{label}: {module_name} cannot be scanned ({exc})")
            continue
        if not order_import:
            continue
        key = (getattr(route, "path", ""), module_name)
        if key in OPEN_ORDER_MODULE_ROUTES:
            continue
        if not isinstance(route, APIRoute) or not _has_guard(route):
            problems.append(f"{label}: {module_name} imports an order module without require_order_path")
    return problems


@pytest.mark.repo_scan
def test_ac6_every_route_importing_an_order_module_carries_the_guard(no_dotenv, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")  # the docs routes exist only here: the scan sees them too
    assert unguarded_order_routes(create_app()) == []


@pytest.mark.repo_scan
def test_ac6_the_scan_finds_exactly_the_two_order_routes_and_no_open_one(no_dotenv, monkeypatch):
    """Report: the routes that import an order module are execute and the return check; the allow-list is empty."""
    monkeypatch.setenv("APP_ENV", "test")
    found = set()
    for route in create_app().routes:
        endpoint = getattr(route, "endpoint", None)
        if endpoint is None or getattr(inspect.unwrap(endpoint), "__module__", None) in FRAMEWORK_MODULES:
            continue
        name = inspect.unwrap(endpoint).__module__
        if name in sys.modules and any(_is_order_import(i) for i in _imports_of(name)):
            found.add((route.path, name))
    assert found == {("/strategies/{strategy_id}/execute", execute.__name__),
                     ("/strategies/{strategy_id}/execution/return", execution_return.__name__)}
    assert not OPEN_ORDER_MODULE_ROUTES


@pytest.mark.repo_scan
def test_ac6_mutation_a_new_unguarded_route_importing_an_order_module_is_found(no_dotenv, monkeypatch, tmp_path):
    """Mutation: a scratch module importing ofo.execution.basket, routed without the dependency -> the scan is red."""
    monkeypatch.setenv("APP_ENV", "test")
    scratch = tmp_path / "scratch_basket_route.py"
    scratch.write_text(
        "from fastapi import APIRouter\n"
        "from ofo.execution import basket  # noqa: F401\n"
        "from ofo_app.api_models import ApiModel\n"
        "from ofo_app.errors import ClosedRoute\n"
        "router = APIRouter(route_class=ClosedRoute)\n"
        "class Out(ApiModel):\n    ok: bool\n"
        "@router.post('/scratch/basket', response_model=Out)\n"
        "async def post_basket() -> Out:\n    return Out(ok=True)\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    import scratch_basket_route  # noqa: PLC0415

    app = create_app()
    assert unguarded_order_routes(app) == []
    app.include_router(scratch_basket_route.router)
    assert [p for p in unguarded_order_routes(app) if "/scratch/basket" in p]
    sys.modules.pop("scratch_basket_route", None)


@pytest.mark.repo_scan
def test_ac6_mutation_from_import_form_and_relative_form_are_both_seen(tmp_path):
    """Standing item (c): ``from ofo_app import execute_plan as ep`` names the source through its alias target."""
    assert _is_order_import("ofo_app.execute_plan") and _is_order_import("ofo.execution.basket")
    assert not _is_order_import("ofo_app.execute_planner") and not _is_order_import("ofo.executions")
    imports = _imports_of(execution_return.__name__)
    assert "ofo_app.execute_plan" in imports and "ofo_app.execution_plan_store" in imports


@pytest.mark.repo_scan
def test_ac6_mutation_an_unresolvable_route_fails_closed(no_dotenv, monkeypatch):
    """Mutation: a route whose endpoint module is not importable/readable is reported, not skipped."""
    monkeypatch.setenv("APP_ENV", "test")
    app = create_app()

    def orphan() -> None:  # pragma: no cover - never called
        return None

    orphan.__module__ = "no_such_module_anywhere"
    app.router.routes.append(type("Orphan", (), {"endpoint": staticmethod(orphan), "path": "/orphan"})())
    assert any("/orphan" in p and "cannot be scanned" in p for p in unguarded_order_routes(app))


@pytest.mark.repo_scan
def test_ac6_mutation_dropping_the_dependency_from_a_router_is_found(no_dotenv, monkeypatch):
    """Mutation: strip ``require_order_path`` from the execute route's dependant tree -> the scan names the route."""
    monkeypatch.setenv("APP_ENV", "test")
    app = create_app()
    route = next(r for r in app.routes if getattr(r, "path", "") == "/strategies/{strategy_id}/execute")
    route.dependant.dependencies = [d for d in route.dependant.dependencies if d.call is not switch.require_order_path]
    assert any("/strategies/{strategy_id}/execute" in p for p in unguarded_order_routes(app))
