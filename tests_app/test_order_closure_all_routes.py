"""W-121 (REQ-073 AC-6, #532 C2): every route module's import closure reaches order code only through pinned edges.

AC-6: "every route that prepares, posts or checks an order at a broker (Execute, the return check, and any basket or
trigger route ...)" refuses while the order path is off. ``test_order_path_switch`` walks the leg-edit route only; this
walks EVERY module under ``backend/ofo_app/routes`` (a glob, so a route file added later is walked with no edit here).

Core: the walker of ``test_order_path_switch`` (reused, never copied), run per route, returns a finite set of
(importer, order module) crossings; each is pinned in ``ROUTE_ORDER_EDGES`` with a reason, on top of the five shared
paths in ``ALLOWED_ORDER_PATHS``. The two order routes (``ORDER_ROUTE_MODULES``) ARE the order path: they are not
walked, and for any other route they are terminal order modules (importing one is an edge; its closure is not walked).

Scope: an import is not a call. This pins the IMPORT closure only; it does not say the code is called, and it does not
test that the order routes refuse (the AC-6 tests in ``test_order_path_switch`` do). Removing the coupling is a later
row: the edges below record it, they do not bless it.
"""
from __future__ import annotations

import inspect
import pathlib
import shutil
import tempfile

import pytest
from fastapi.routing import APIRoute
from ofo_app.main import create_app
from test_order_path_switch import (
    ALLOWED_ORDER_PATHS,
    BACKEND,
    FRAMEWORK_MODULES,
    MIN_REASON_WORDS,
    _has_guard,
    _tree,
    no_dotenv,  # noqa: F401 - fixture
    order_closure_problems,
    order_entry_problems,
)

#: The routes that carry the order-path switch dependency: the order path itself (not walked; terminal for the rest).
ORDER_ROUTE_MODULES: frozenset[str] = frozenset({"ofo_app.routes.execute", "ofo_app.routes.execution_return"})
ROUTES_PACKAGE = "ofo_app.routes"

#: Crossings by importer, reused by every route that reaches that importer. Reason = what the importer uses.
STRATEGY_STORE: dict[tuple[str, str], str] = {
    ("ofo_app.strategy_store", "ofo_app.execute_plan"):
        "the has-executed check reads the latest filled plan from execute_plan",
    ("ofo_app.strategy_store", "ofo_app.execution_plan_store"):
        "the has-executed check reads stored plan versions from the plan store",
}
KITE_REPLIES: dict[tuple[str, str], str] = {
    ("ofo_app.kite_replies", "ofo.execution.partial"):
        "the Kite reply parser returns the partial-fill rule's broker status type",
    ("ofo_app.kite_replies", "ofo.orders.model"):
        "the Kite reply parser builds fill events and order states from replies",
}
RECONCILE_ATTRIBUTION: dict[tuple[str, str], str] = {
    ("ofo_app.reconcile_attribution", "ofo.execution.basket"):
        "attribution reads the order tag format to tell this app's orders",
    ("ofo_app.reconcile_attribution", "ofo_app.execute_plan"):
        "attribution takes held units from the plan's fills",
    ("ofo_app.reconcile_attribution", "ofo_app.execution_plan_store"):
        "attribution reads each strategy's stored plans",
    ("ofo_app.reconcile_attribution", "ofo_app.execution_return"):
        "attribution asks the return check whether an order drifted",
}


def _execute_route_edge(route: str, why: str) -> dict[tuple[str, str], str]:
    return {(f"{ROUTES_PACKAGE}.{route}", "ofo_app.routes.execute"): why}


#: route module -> {(importer, order module): reason}. Every route not listed has no crossing beyond the shared paths.
ROUTE_ORDER_EDGES: dict[str, dict[tuple[str, str], str]] = {
    # GC-ADJ2 1C: the playbook check reads plans and rule memory through playbook_store (its ownership check)
    "ofo_app.routes.adjustment_check": {**STRATEGY_STORE},
    # GC-ADJ2 5: the opportunities inbox records outcomes through playbook_store (its strategy_store import)
    "ofo_app.routes.adjustment_opportunities": {**STRATEGY_STORE},
    # GC-ADJ2 4: the plan sheet accepts a plan through playbook_store (its strategy_store import)
    "ofo_app.routes.adjustment_plan": {**STRATEGY_STORE},
    "ofo_app.routes.broker_status": _execute_route_edge(
        "broker_status", "the status route reuses the execute route's clock provider"),
    "ofo_app.routes.features": {**STRATEGY_STORE},
    "ofo_app.routes.paper": {**STRATEGY_STORE},
    # GC-ADJ2 2: the playbook routes call playbook_store, whose strategy_store import reaches the plan modules
    "ofo_app.routes.playbooks": {**STRATEGY_STORE},
    "ofo_app.routes.positions": {
        **_execute_route_edge("positions", "the positions route reuses the execute route's Kite session and clock"),
        **STRATEGY_STORE, **KITE_REPLIES, **RECONCILE_ATTRIBUTION},
    "ofo_app.routes.ready_made": {**STRATEGY_STORE},
    "ofo_app.routes.strategies": {**STRATEGY_STORE},
    "ofo_app.routes.tracking": {**STRATEGY_STORE},
    "ofo_app.routes.zerodha_account": _execute_route_edge(
        "zerodha_account", "the account route reuses the execute route's Kite session provider"),
}
#: One constant, so a new edge is a reviewed diff and never a silent pass.
PINNED_EDGE_COUNT = 29  # GC-ADJ2 5: +2 adjustment_opportunities, +2 adjustment_plan (both via playbook_store)


def route_modules(backend: pathlib.Path) -> list[str]:
    """Every module under ofo_app/routes except the package init, sorted (a later-added route file is included)."""
    return [f"{ROUTES_PACKAGE}.{f.stem}" for f in sorted((backend / "ofo_app" / "routes").glob("*.py"))
            if f.name != "__init__.py"]


def route_closure_problems(
        backend: pathlib.Path, edges: dict[str, dict[tuple[str, str], str]],
) -> tuple[list[str], list[tuple[str, int, int]]]:
    """(problems, per-route rows). A problem for every order module a non-order route reaches outside the shared paths
    plus its own edges (chain printed), every unwalkable import, every recorded edge the walk did not use (stale) and
    every edge naming a route that does not exist."""
    problems: list[str] = []
    rows: list[tuple[str, int, int]] = []
    routes = route_modules(backend)
    problems += [f"{route}: edges recorded for a route that does not exist" for route in edges if route not in routes]
    for route in routes:
        if route in ORDER_ROUTE_MODULES:
            continue
        own = edges.get(route, {})
        found, used = order_closure_problems([route], backend, {**ALLOWED_ORDER_PATHS, **own}, ORDER_ROUTE_MODULES)
        problems += found
        problems += [f"{route}: stale edge {edge} (no longer used)" for edge in sorted(set(own) - used)]
        rows.append((route, len(own), len(used - set(ALLOWED_ORDER_PATHS))))
    return problems, rows


@pytest.mark.repo_scan
def test_ac6_every_route_reaches_order_code_only_through_the_shared_paths_and_its_pinned_edges():
    """Core: all route modules of the real tree, one walk each; nothing outside SHARED + own edges, no edge unused."""
    problems, _ = route_closure_problems(BACKEND, ROUTE_ORDER_EDGES)
    assert not problems, "\n".join(problems)


@pytest.mark.repo_scan
def test_ac6_the_recorded_edges_are_pinned_in_count_and_each_has_a_reason():
    assert sum(len(edges) for edges in ROUTE_ORDER_EDGES.values()) == PINNED_EDGE_COUNT
    assert all(len(reason.split()) >= MIN_REASON_WORDS for edges in ROUTE_ORDER_EDGES.values()
               for reason in edges.values())
    assert all(importer.startswith(("ofo_app.", "ofo.")) for edges in ROUTE_ORDER_EDGES.values()
               for importer, _ in edges)


@pytest.mark.repo_scan
def test_ac6_every_recorded_edge_names_a_real_importer_and_one_real_order_module():
    """Checker k2: an edge naming ``ofo.orders.model.no_such_module`` passed the prefix match; now it must resolve."""
    entries = {edge for edges in ROUTE_ORDER_EDGES.values() for edge in edges}
    assert order_entry_problems(BACKEND, entries, ORDER_ROUTE_MODULES) == []


@pytest.mark.repo_scan
def test_ac6_the_walked_routes_are_the_modules_under_routes_that_the_app_serves(no_dotenv, monkeypatch):  # noqa: F811
    """Checker k3: leaving a route file out of the walk passed. The walked set must equal the endpoint modules that
    ``create_app()`` serves from ``ofo_app.routes`` (an app route in a file the walk does not list is red)."""
    monkeypatch.setenv("APP_ENV", "test")
    # a door socket route wraps its endpoint (``ofo_endpoint``); every other route's endpoint is the function itself
    served = {inspect.unwrap(getattr(route.endpoint, "ofo_endpoint", route.endpoint)).__module__
              for route in create_app().routes if getattr(route, "endpoint", None) is not None}
    assert {m for m in served if m.startswith(ROUTES_PACKAGE + ".")} == set(route_modules(BACKEND))


@pytest.mark.repo_scan
def test_ac6_the_order_routes_are_the_routes_that_carry_the_switch(no_dotenv, monkeypatch):  # noqa: F811
    """ORDER_ROUTE_MODULES must equal the modules of the routes that carry the switch dependency (the existing scan's
    guard helper), so a new guarded route cannot be skipped by this walk."""
    monkeypatch.setenv("APP_ENV", "test")
    guarded = {inspect.unwrap(route.endpoint).__module__ for route in create_app().routes
               if isinstance(route, APIRoute) and _has_guard(route)
               and inspect.unwrap(route.endpoint).__module__ not in FRAMEWORK_MODULES}
    assert guarded == set(ORDER_ROUTE_MODULES)
    assert set(ORDER_ROUTE_MODULES) <= set(route_modules(BACKEND))


@pytest.mark.repo_scan
def test_ac6_report_the_coupling_of_every_route(capsys):
    """Report (run with -s): per route, the pinned edges, the edges used and the order modules reached."""
    _, rows = route_closure_problems(BACKEND, ROUTE_ORDER_EDGES)
    with capsys.disabled():
        print("\nroute | pinned edges | order paths used outside the shared five")
        for route, pinned, used in rows:
            print(f"{route} | {pinned} | {used}")
        print(f"walked {len(rows)} routes, {sum(p for _, p, _ in rows)} edges")
    assert len(rows) == len(route_modules(BACKEND)) - len(ORDER_ROUTE_MODULES)


# ---- mutations --------------------------------------------------------------------------------------------------

def _real_copy(tmp: str) -> pathlib.Path:
    root = pathlib.Path(tmp) / "backend"
    shutil.copytree(BACKEND, root, ignore=shutil.ignore_patterns("__pycache__", "alembic"))
    return root


@pytest.mark.repo_scan
def test_ac6_mutation_health_importing_execute_plan_is_refused_with_its_chain():
    """Proof (real copy): routes/health.py gains one import of ofo_app.execute_plan -> red, chain printed."""
    with tempfile.TemporaryDirectory() as tmp:
        root = _real_copy(tmp)
        health = root / "ofo_app" / "routes" / "health.py"
        health.write_text(health.read_text(encoding="utf-8") + "\nfrom ofo_app import execute_plan  # noqa: F401\n",
                          encoding="utf-8")
        problems, _ = route_closure_problems(root, ROUTE_ORDER_EDGES)
    assert problems == ["order module reached outside the allow-list: ofo_app.routes.health -> ofo_app.execute_plan"]


@pytest.mark.repo_scan
def test_ac6_mutation_a_new_route_file_is_walked_without_editing_the_test(tmp_path):
    """The start set is a glob: a route file added later reaching an order module two hops away is red."""
    root = _tree(tmp_path, {
        "ofo_app/routes/old.py": "X = 1\n",
        "ofo_app/routes/later.py": "from ofo_app import store\n",
        "ofo_app/store.py": "from ofo.execution.freeze import X\n"})
    assert route_modules(root) == ["ofo_app.routes.later", "ofo_app.routes.old"]
    problems, _ = route_closure_problems(root, {})
    assert problems == ["order module reached outside the allow-list: "
                        "ofo_app.routes.later -> ofo_app.store -> ofo.execution.freeze"]


@pytest.mark.repo_scan
def test_ac6_mutation_a_recorded_edge_whose_import_was_removed_fails_as_stale(tmp_path):
    root = _tree(tmp_path, {"ofo_app/routes/r.py": "from ofo_app import store\n", "ofo_app/store.py": "X = 1\n"})
    edge = {("ofo_app.store", "ofo.execution.freeze"): "the store once read the freeze constants"}
    problems, _ = route_closure_problems(root, {"ofo_app.routes.r": edge})
    assert problems == ["ofo_app.routes.r: stale edge ('ofo_app.store', 'ofo.execution.freeze') (no longer used)"]
    assert route_closure_problems(root, {"ofo_app.routes.gone": edge})[0] == [
        "ofo_app.routes.gone: edges recorded for a route that does not exist"]


@pytest.mark.repo_scan
def test_ac6_mutation_an_edge_covers_its_importer_only_not_another_module_of_the_route(tmp_path):
    """An edge for store -> freeze does not allow other -> freeze (importer match, not walk order)."""
    root = _tree(tmp_path, {
        "ofo_app/routes/r.py": "from ofo_app import store, other\n",
        "ofo_app/store.py": "from ofo.execution.freeze import X\n",
        "ofo_app/other.py": "from ofo.execution.freeze import X\n"})
    edge = {("ofo_app.store", "ofo.execution.freeze"): "the store reads the freeze constants only"}
    problems, _ = route_closure_problems(root, {"ofo_app.routes.r": edge})
    assert problems == ["order module reached outside the allow-list: "
                        "ofo_app.routes.r -> ofo_app.other -> ofo.execution.freeze"]


@pytest.mark.repo_scan
def test_ac6_mutation_importing_an_order_route_is_an_edge_and_is_not_walked_through(tmp_path):
    root = _tree(tmp_path, {
        "ofo_app/routes/execute.py": "from ofo.execution.freeze import X\n",
        "ofo_app/routes/r.py": "from ofo_app.routes import execute\n"})
    problems, _ = route_closure_problems(root, {})
    assert problems == ["order module reached outside the allow-list: ofo_app.routes.r -> ofo_app.routes.execute"]


@pytest.mark.repo_scan
@pytest.mark.parametrize("helper", [
    "import importlib\nm = importlib.import_module('ofo.execution.freeze')\n",
    "m = __import__('ofo.execution.freeze')\n"])
def test_ac6_mutation_a_dynamic_import_in_a_reached_module_fails_closed(tmp_path, helper):
    root = _tree(tmp_path, {"ofo_app/routes/r.py": "from ofo_app import helper\n", "ofo_app/helper.py": helper})
    problems, _ = route_closure_problems(root, {})
    assert any("ofo_app.helper: dynamic import" in p and "helper.py" in p for p in problems), problems
