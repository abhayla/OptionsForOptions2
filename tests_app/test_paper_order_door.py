"""GC-TP step 1b (REQ-109 AC-3, ADR-207): the paper order book never reaches an order door.

The paper route, store and engine modules are walked with the same import-closure walker as every route
(``test_order_path_switch.order_closure_problems``, reused, not copied) and the same order-module list (its
``ORDER_SOURCES`` and ``ofo.orders``), plus the Kite client modules that can place an order, GTT or basket at Zerodha
(``EXTRA_DOORS``). The only crossings are the ones the saved-strategy store already has (``STRATEGY_STORE``: its
has-executed check), pinned and each used.

Extending: step 7 added the paper monitor and step 5b the expiry settlement to ``PAPER_MODULES``; nothing else changes.
"""
from __future__ import annotations

import shutil

import pytest
from test_order_closure_all_routes import ORDER_ROUTE_MODULES, STRATEGY_STORE
from test_order_path_switch import ALLOWED_ORDER_PATHS, BACKEND, _module_file, order_closure_problems

pytestmark = pytest.mark.repo_scan

#: The modules that make up the paper order book. Add a module here (step 7: the monitor) and it is walked too.
PAPER_MODULES: tuple[str, ...] = ("ofo_app.routes.paper", "ofo_app.paper_store", "ofo.engine.orderbook",
                                  "ofo.tracking.orderbook", "ofo_app.paper_monitor", "ofo_app.paper_trigger_store",
                                  "ofo.tracking.stops", "ofo_app.paper_settlement")
#: Order doors beyond the shared order list: the order audit, order book and order-path-switch modules. A paper module
#: reaching one is red. The Kite client is NOT listed: the paper book reads live prices through it (a read), and the
#: order, GTT and basket doors sit in the modules above. A GTT or alert-trigger module added later must be listed
#: here (``test_a_gtt_or_trigger_module_is_listed_as_a_door``).
EXTRA_DOORS: frozenset[str] = frozenset({"ofo_app.order_audit", "ofo_app.order_book_store",
                                         "ofo_app.order_path_switch"})
ALLOWED = {**ALLOWED_ORDER_PATHS, **STRATEGY_STORE}
TERMINAL = ORDER_ROUTE_MODULES | EXTRA_DOORS


def paper_problems(root=BACKEND, modules=PAPER_MODULES):
    return order_closure_problems(list(modules), root, ALLOWED, TERMINAL)


def test_the_paper_modules_exist():
    assert [m for m in PAPER_MODULES if _module_file(BACKEND, m) is None] == []
    assert [m for m in EXTRA_DOORS if _module_file(BACKEND, m) is None] == []  # a renamed door must be re-listed


def test_the_paper_order_book_reaches_no_order_door():
    problems, used = paper_problems()
    assert problems == []
    assert set(STRATEGY_STORE) <= used  # an allowed crossing the walk no longer uses is stale


def test_a_gtt_or_trigger_module_is_listed_as_a_door():
    """No backend module is named for a GTT or an alert trigger today; one added later fails here until it is listed."""
    named = sorted(f"{'.'.join(f.relative_to(BACKEND).with_suffix('').parts)}" for f in BACKEND.rglob("*.py")
                   if any(word in f.stem for word in ("gtt", "alert_trigger")) and "alembic" not in f.parts)
    assert [m for m in named if m not in EXTRA_DOORS] == []


def _mutated(tmp_path, module_file: str, extra: str):
    root = tmp_path / "backend"
    shutil.copytree(BACKEND, root, ignore=shutil.ignore_patterns("__pycache__", "alembic"))
    target = root.joinpath(*module_file.split("/"))
    target.write_text(target.read_text(encoding="utf-8") + "\n" + extra + "\n", encoding="utf-8")
    return root


@pytest.mark.parametrize(("module_file", "extra", "door"), [
    ("ofo/engine/orderbook.py", "from ofo.execution import basket  # noqa: F401", "ofo.execution.basket"),
    ("ofo_app/paper_store.py", "from ofo_app import execute_plan  # noqa: F401", "ofo_app.execute_plan"),
    ("ofo_app/routes/paper.py", "from ofo_app import order_audit  # noqa: F401", "ofo_app.order_audit"),
    ("ofo/tracking/orderbook.py", "from ofo.orders import model  # noqa: F401", "ofo.orders.model"),
    ("ofo_app/routes/paper.py", "from ofo_app.routes import execute  # noqa: F401", "ofo_app.routes.execute"),
    ("ofo_app/paper_monitor.py", "from ofo_app import execute_plan  # noqa: F401", "ofo_app.execute_plan"),
    ("ofo_app/paper_trigger_store.py", "from ofo_app import order_audit  # noqa: F401", "ofo_app.order_audit"),
    ("ofo/tracking/stops.py", "from ofo.execution import basket  # noqa: F401", "ofo.execution.basket"),
])
def test_mutation_a_forbidden_import_in_any_paper_module_is_red_with_its_chain(tmp_path, module_file, extra, door):
    problems, _ = paper_problems(_mutated(tmp_path, module_file, extra))
    assert any(p.endswith(f"-> {door}") for p in problems), problems


def test_mutation_a_new_paper_module_is_walked_when_listed(tmp_path):
    root = _mutated(tmp_path, "ofo_app/paper_store.py", "")
    (root / "ofo_app" / "paper_monitor.py").write_text("from ofo.execution import basket\n", encoding="utf-8")
    problems, _ = paper_problems(root, (*PAPER_MODULES, "ofo_app.paper_monitor"))
    assert "order module reached outside the allow-list: ofo_app.paper_monitor -> ofo.execution.basket" in problems
