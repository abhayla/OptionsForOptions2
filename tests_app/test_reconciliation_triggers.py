"""#380-2c: every reconciliation trigger the app runs is a pure read through the ONE reconciler (F-42).

Spec basis: REQ-060 (AC-3, AC-6); ADR-079 (re-read Zerodha on every page load of a strategy); ADR-120 (2) (the only
write a reconciliation makes is the recorded mismatch); ADR-134 (no background loop that re-implements Kite's order
book); Q196 (the triggers). Findings checked: verified-on-a-module-the-product-does-not-call (a trigger is pinned on
the module the product's routes import), caller-supplied-verdict-trusted (no trigger hands the reconciler a verdict).

Trigger table (what exists today; the rest are next rows, reported in the #380-2c report, not built):

| trigger (Q196) | exists | where | source | writes |
|---|---|---|---|---|
| after execution | yes | routes/execution_return.py ``_reconcile`` | after_execution | the mismatch only |
| Execute press (read) | yes | routes/execute.py ``_reconcile`` | None | nothing |
| app start / resume | no | - | - | - |
| after reconnect | no | - | - | - |
| periodic | no | - (ADR-134: no polling loop) | - | - |

These tests fail the moment a second path to a verdict, a trigger that touches an order, or an unlisted caller of the
reconciler appears; adding a trigger means adding its row here on purpose.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest
from ofo_app import reconciliation_store

pytestmark = pytest.mark.repo_scan

APP = Path(__file__).resolve().parents[1] / "backend" / "ofo_app"
ROUTES = APP / "routes"

#: Every module that may call the reconciler, with the ``source=`` it passes (None = stores nothing).
CALLERS = {"routes/execute.py": None, "routes/execution_return.py": "after_execution"}
#: Names that place, change or cancel an order or settle a plan: a trigger's function may call none of them.
FORBIDDEN_IN_A_TRIGGER = ("place", "cancel", "modify", "close_plan", "resolve", "mark_", "submit", "send_order",
                          "basket", "adopt", "settle", "reconcile_by")


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _call_names(node: ast.AST) -> list[str]:
    return [ast.unparse(n.func) for n in ast.walk(node) if isinstance(n, ast.Call)]


def _functions(path: Path, name: str) -> list[ast.AST]:
    kinds = (ast.FunctionDef, ast.AsyncFunctionDef)
    return [n for n in ast.walk(_tree(path)) if isinstance(n, kinds) and n.name == name]


def _reconciler_calls(path: Path) -> list[ast.Call]:
    ends = ("reconcile_account", "attribute_and_compare", "route_reconciliation.attribute")
    return [n for n in ast.walk(_tree(path)) if isinstance(n, ast.Call) and ast.unparse(n.func).endswith(ends)]


def test_only_the_listed_triggers_call_the_reconciler():
    """No module outside the two routes (and the reconciler itself) reaches the attribution or the reconciler: a new
    caller is a new trigger and must be added to ``CALLERS`` with its source, on purpose."""
    found = {}
    for path in APP.rglob("*.py"):
        rel = path.relative_to(APP).as_posix()
        if rel.startswith("alembic/") or rel in ("route_reconciliation.py", "reconcile_attribution.py"):
            continue
        calls = _reconciler_calls(path)
        if calls:
            found[rel] = calls
    assert set(found) == set(CALLERS), sorted(found)


@pytest.mark.parametrize(("rel", "source"), sorted(CALLERS.items()))
def test_each_trigger_passes_its_declared_source(rel, source):
    """The execute press stores nothing (``source=None``); the return route is ``after_execution``; every source is
    one the store accepts. A trigger passing another source (or one more call) fails here."""
    (call,) = _reconciler_calls(APP / rel)
    keywords = {k.arg: k.value for k in call.keywords}
    assert "source" in keywords, rel
    assert ast.literal_eval(keywords["source"]) == source
    assert source is None or source in reconciliation_store.SOURCES


@pytest.mark.parametrize("rel", sorted(CALLERS))
def test_a_trigger_is_a_pure_read_it_touches_no_order(rel):
    """The trigger function (``_reconcile`` in each route) makes the Kite reads and the one reconciler call, nothing
    that places, cancels, modifies, closes or settles (ADR-120 (2): the recorded mismatch is the only write)."""
    (fn,) = _functions(APP / rel, "_reconcile")
    names = _call_names(fn)
    assert any(n.endswith("reconcile_account") for n in names), rel
    bad = [n for n in names if any(word in n.lower() for word in FORBIDDEN_IN_A_TRIGGER)]
    assert bad == [], (rel, bad)


def test_the_reconciler_writes_only_the_recorded_mismatch():
    """``route_reconciliation`` calls exactly one store writer, ``record_mismatch`` (through ``_store``), and nothing
    that touches an order or a plan: no second verdict path, no plan close, no resolution."""
    names = _call_names(_tree(APP / "route_reconciliation.py"))
    writers = [n for n in names if n.startswith("reconciliation_store.") or "plan_store" in n or "strategy_store" in n]
    assert set(writers) == {"reconciliation_store.record_mismatch", "reconciliation_store.standalone_for"}
    assert [n for n in names if any(word in n.lower() for word in FORBIDDEN_IN_A_TRIGGER)] == []


def test_the_stored_mismatch_is_written_only_after_a_source_is_checked():
    """A forged or unknown source never reaches the store: ``reconcile_account`` refuses it before the lock."""
    (fn,) = _functions(APP / "route_reconciliation.py", "reconcile_account")
    body = [ast.unparse(s) for s in fn.body[1:]]  # [0] is the docstring
    guard = next(i for i, s in enumerate(body) if "SOURCES" in s)
    lock = next(i for i, s in enumerate(body) if "lock_user" in s)
    store = next(i for i, s in enumerate(body) if "await _store(" in s)
    assert guard < lock < store


def test_no_background_loop_drives_a_reconciliation():
    """ADR-134: no periodic or event loop in the app calls the reconciler (the periodic row is a next row, reported
    with its reason, not built). Any module reaching it from a task or a lifespan is caught by the caller list above;
    this pins the lifespan and the live feeds as well."""
    for rel in ("main.py", "live_market.py", "live_push.py", "kite_ws.py", "replay_mode.py"):
        text = (APP / rel).read_text(encoding="utf-8")
        assert "reconcile_account" not in text and "route_reconciliation" not in text, rel
