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
import pathlib
import shutil
import sys
import tempfile
from collections import deque
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


# ---- the import closure of the leg-edit route (structural, REQ-076 AC-5 fix round 2) ------------------------------
# The direct-import scan above saw leg_edit import only ``ofo_app.freeze_store`` and passed, while freeze_store imported
# ``ofo.execution.freeze``: the route reached an order module one hop away. This walks every hop, function-level imports
# included. Other routes reach order code too (pre-existing coupling, recorded in #532): not this row, so only the
# leg-edit route is walked here.

MIN_REASON_WORDS = 4
BACKEND = pathlib.Path(__file__).resolve().parents[1] / "backend"
LEG_EDIT = "ofo_app.routes.leg_edit"

#: (importer, order module it imports) -> why that one path is allowed. Exactly four; a fifth is a new path and must be
#: argued for in the change that adds it (the pinned test below fails until the reason and the pin are both written).
ALLOWED_ORDER_PATHS: dict[tuple[str, str], str] = {
    ("ofo.errors.slots", "ofo.execution.safety"): "the error slot catalogue names the safety checks' reason codes",
    ("ofo.errors.gate_slots", "ofo.execution.context"): "the gate slot catalogue names the execution context's codes",
    ("ofo_app.api_models", "ofo_app.basket_post"): "the shared API models include the basket-post reply shapes",
    ("ofo_app.outcome_margin", "ofo.execution.margin_gate"): "the outcome margin read uses the gate's busy code",
}
PINNED_PATHS = {
    ("ofo.errors.slots", "ofo.execution.safety"), ("ofo.errors.gate_slots", "ofo.execution.context"),
    ("ofo_app.api_models", "ofo_app.basket_post"), ("ofo_app.outcome_margin", "ofo.execution.margin_gate")}


def _is_order_module(name: str) -> bool:
    return _is_order_import(name) or name == "ofo.orders" or name.startswith(("ofo.orders.", "ofo_app.execute"))


def _module_file(root: pathlib.Path, module: str) -> pathlib.Path | None:
    base = root.joinpath(*module.split("."))
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def _own(name: str) -> bool:
    return name in ("ofo", "ofo_app") or name.startswith(("ofo.", "ofo_app."))


def _from_import(root: pathlib.Path, package: str, node: ast.ImportFrom) -> tuple[set[str], str | None]:
    """(modules a ``from`` import brings in, the module it names when that has no source file)."""
    base = node.module or ""
    if node.level:
        parts = package.split(".")
        base = ".".join(parts[:len(parts) - (node.level - 1)] + ([base] if base else []))
    if not _own(base):
        return set(), None
    if _module_file(root, base) is None:
        return set(), base
    return {base} | {f"{base}.{a.name}" for a in node.names if _module_file(root, f"{base}.{a.name}")}, None


def _source_imports(root: pathlib.Path, module: str, path: pathlib.Path) -> tuple[set[str], list[str]]:
    """(ofo / ofo_app modules this file imports, anywhere in it; problems the walker cannot resolve)."""
    names: set[str] = set()
    problems: list[str] = []
    package = module if path.name == "__init__.py" else module.rpartition(".")[0]
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names |= {a.name for a in node.names if _own(a.name)}
        elif isinstance(node, ast.ImportFrom):
            more, missing = _from_import(root, package, node)
            names |= more
            if missing:
                problems.append(f"{module}: imports {missing}, no source file under {root.name}: cannot be walked")
        elif isinstance(node, ast.Call):
            func = node.func
            called = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""
            if called in ("__import__", "import_module"):
                problems.append(f"{module}: dynamic import at line {node.lineno} ({path.name}): cannot be walked")
    return names, problems


def _reach(root: pathlib.Path, via: set[str | None], name: str,
           allowed: dict[tuple[str, str], str]) -> tuple[list[str], list[str], set[tuple[str, str]]]:
    """(non-order modules reached through ``name`` and its packages, order modules refused, allow-list entries used)
    for the module ``via`` names first (itself, then the module that imported it). An allow-list
    entry covers its own importer and the one module it directly imports (``via``): outcome_margin and the margin
    client it uses (kite_margin) both import the gate's busy code, which is the single listed path."""
    parts = name.split(".")
    onward: list[str] = []
    refused: list[str] = []
    used: set[tuple[str, str]] = set()
    for reached in (".".join(parts[:i]) for i in range(1, len(parts) + 1)):
        if _module_file(root, reached) is None:
            continue
        if not _is_order_module(reached):
            onward.append(reached)
            continue
        ok = [k for k in allowed if k[0] in via and (reached == k[1] or k[1].startswith(reached + "."))]
        used |= set(ok)
        if not ok:
            refused.append(reached)
    return onward, refused, used


def order_closure_problems(starts: list[str], root: pathlib.Path,
                           allowed: dict[tuple[str, str], str]) -> tuple[list[str], set[tuple[str, str]]]:
    """Walk the import closure of ``starts``; a problem for every order module reached outside ``allowed`` (with the
    chain printed), every dynamic import and every import that cannot be resolved; also the allowed paths used."""
    parent: dict[str, str | None] = dict.fromkeys(starts)
    queue = deque(starts)
    problems: list[str] = []
    used: set[tuple[str, str]] = set()

    def chain(module: str) -> str:
        out = []
        while module:
            out.append(module)
            module = parent[module]
        return " -> ".join(reversed(out))

    while queue:
        module = queue.popleft()
        path = _module_file(root, module)
        if path is None:
            problems.append(f"{module}: no source file under {root.name}: cannot be walked")
            continue
        try:
            names, found = _source_imports(root, module, path)
        except SyntaxError as exc:
            problems.append(f"{module}: cannot be parsed ({exc})")
            continue
        problems += found
        for name in sorted(names):
            onward, refused, hit = _reach(root, {module, parent[module]}, name, allowed)
            used |= hit
            for reached in onward:
                if reached not in parent:
                    parent[reached] = module
                    queue.append(reached)
            if refused:  # one problem per import, naming the deepest module (its package parents came with it)
                problems.append(f"order module reached outside the allow-list: {chain(module)} -> {refused[-1]}")
    return problems, used


@pytest.mark.repo_scan
def test_ac6_the_leg_edit_route_reaches_no_order_module_except_the_four_named_paths():
    """Core (AC-5 fix round 2): the closure of the leg-edit route holds no ofo.execution / ofo.orders /
    ofo_app.execute* module except through the four named shared paths, and every one of those is used."""
    problems, used = order_closure_problems([LEG_EDIT], BACKEND, ALLOWED_ORDER_PATHS)
    assert not problems, "\n".join(problems)
    assert used == set(ALLOWED_ORDER_PATHS), "an allow-list entry the leg-edit route no longer uses must be removed"


def test_ac6_the_allow_list_is_the_four_named_paths_each_with_a_reason():
    """A fifth path, or an entry with no reason, fails here until the change that adds it says why."""
    assert set(ALLOWED_ORDER_PATHS) == PINNED_PATHS
    assert all(len(reason.split()) >= MIN_REASON_WORDS for reason in ALLOWED_ORDER_PATHS.values())


def test_ac6_mutation_a_fifth_allow_list_entry_is_not_the_pinned_four():
    """Mutation: one more entry (with a reason) differs from the pin, so the pinned test above would go red."""
    fifth = {("ofo_app.freeze_store", "ofo.execution.freeze"): "the plan side reads the freeze rule"}
    grown = {**ALLOWED_ORDER_PATHS, **fifth}
    assert set(grown) != PINNED_PATHS


@pytest.mark.repo_scan
def test_ac6_mutation_leg_edit_reaching_the_plan_part_of_freeze_store_fails_with_the_chain():
    """Mutation: leg-edit importing freeze_store (its plan part reaches ofo.execution) is red, chain printed."""
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp) / "backend"
        shutil.copytree(BACKEND, root, ignore=shutil.ignore_patterns("__pycache__", "alembic"))
        target = root / "ofo_app" / "routes" / "leg_edit.py"
        target.write_text(target.read_text(encoding="utf-8") + "\nfrom ofo_app import freeze_store  # noqa: F401\n",
                          encoding="utf-8")
        problems, _ = order_closure_problems([LEG_EDIT], root, ALLOWED_ORDER_PATHS)
    assert any(p.startswith(f"order module reached outside the allow-list: {LEG_EDIT} -> ofo_app.freeze_store -> ")
               and "ofo.execution" in p for p in problems), problems


def _tree(tmp_path: pathlib.Path, files: dict[str, str]) -> pathlib.Path:
    for rel, body in {"ofo/__init__.py": "", "ofo/execution/__init__.py": "", "ofo/execution/freeze.py": "X = 1\n",
                      "ofo_app/__init__.py": "", "ofo_app/routes/__init__.py": "", **files}.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    return tmp_path


@pytest.mark.repo_scan
def test_ac6_mutation_a_two_hop_chain_to_an_order_module_fails_with_the_chain_printed(tmp_path):
    """Mutation: route -> store (function-level import) -> ofo.execution.freeze is red, naming every hop."""
    root = _tree(tmp_path, {
        "ofo_app/routes/r.py": "def f():\n    from ofo_app import store\n    return store\n",
        "ofo_app/store.py": "from ofo.execution.freeze import X\n"})
    problems, _ = order_closure_problems(["ofo_app.routes.r"], root, {})
    assert problems == ["order module reached outside the allow-list: "
                        "ofo_app.routes.r -> ofo_app.store -> ofo.execution.freeze"]


@pytest.mark.repo_scan
def test_ac6_mutation_a_listed_path_passes_only_for_its_own_importer(tmp_path):
    """The allow-list names the importer: the same import from another module is still red."""
    root = _tree(tmp_path, {
        "ofo_app/routes/r.py": "from ofo_app import store, other\n",
        "ofo_app/store.py": "from ofo.execution.freeze import X\n",
        "ofo_app/other.py": "from ofo.execution.freeze import X\n"})
    allowed = {("ofo_app.store", "ofo.execution.freeze"): "this store reads the freeze constants only"}
    problems, used = order_closure_problems(["ofo_app.routes.r"], root, allowed)
    assert problems == ["order module reached outside the allow-list: "
                        "ofo_app.routes.r -> ofo_app.other -> ofo.execution.freeze"]
    assert used == set(allowed)


@pytest.mark.repo_scan
@pytest.mark.parametrize("body", [
    "import importlib\nm = importlib.import_module('ofo.execution.freeze')\n",
    "from importlib import import_module\nm = import_module('x')\n",
    "m = __import__('ofo.execution.freeze')\n"])
def test_ac6_mutation_a_dynamic_import_fails_closed_naming_the_file(tmp_path, body):
    root = _tree(tmp_path, {"ofo_app/routes/r.py": body})
    problems, _ = order_closure_problems(["ofo_app.routes.r"], root, {})
    assert any("ofo_app.routes.r: dynamic import" in p and "r.py" in p for p in problems)


@pytest.mark.repo_scan
def test_ac6_mutation_an_unresolvable_import_fails_closed(tmp_path):
    root = _tree(tmp_path, {"ofo_app/routes/r.py": "from ofo_app.nothere import thing\n"})
    problems, _ = order_closure_problems(["ofo_app.routes.r"], root, {})
    assert any("ofo_app.nothere" in p and "cannot be walked" in p for p in problems)
    assert any("ofo_app.missing: no source file" in p
               for p in order_closure_problems(["ofo_app.missing"], root, {})[0])
