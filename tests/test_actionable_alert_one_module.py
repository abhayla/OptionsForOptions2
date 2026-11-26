"""ADR-330 standing instruction: ONE module raises alerts. AST scan of backend/ofo_app and backend/ofo.

A call of open_suggestion, record_held or add_alert, or an SQL string with INSERT INTO adjustment_suggestions /
paper_alerts, outside the stores that define them fails with file, line and the module to use
(``ofo_app.actionable_alerts``). Exemptions are keyed (file, function) with a category; a stale one fails.

Not scanned: worker_watch / notifier (the worker-silence notice is not an alert of a strategy).
Known bypasses (written, not caught): a call through ``getattr`` or an alias of the function name; SQL built from
pieces that never contain the words together; a raw INSERT in a file outside backend/; a stored procedure.
"""
from __future__ import annotations

import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
HOMES = {"actionable_alerts.py", "playbook_store.py", "paper_trigger_store.py"}
CALLS = {"open_suggestion", "record_held", "add_alert"}
TABLES = ("adjustment_suggestions", "paper_alerts")
USE = "ofo_app.actionable_alerts"
EXEMPT = {("paper_monitor.py", "_fire"): "wave2-refactor-owns-file"}


def problems_in(name: str, source: str) -> list[tuple[str, int, str]]:
    """(function, line, message) for every bypass in one file's source."""
    found: list[tuple[str, int, str]] = []

    def walk(node: ast.AST, fn: str) -> None:
        for child in ast.iter_child_nodes(node):
            inner = child.name if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef) else fn
            if isinstance(child, ast.Call):
                f = child.func
                called = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
                if called in CALLS and getattr(f.value if isinstance(f, ast.Attribute) else None, "id", "") != "actionable_alerts":
                    found.append((fn, child.lineno, f"{called}() outside the one module: use {USE}"))
            if isinstance(child, ast.Constant) and isinstance(child.value, str):
                low = " ".join(child.value.lower().split())
                if any(f"insert into public.{t}" in low or f"insert into {t}" in low for t in TABLES):
                    found.append((fn, child.lineno, f"INSERT INTO an alert table outside the one module: use {USE}"))
            walk(child, inner)
    walk(ast.parse(source), "<module>")
    return found


def scan(files: dict[str, str]) -> list[str]:
    out, used = [], set()
    for name, source in files.items():
        base = name.rsplit("/", 1)[-1]
        if base in HOMES:
            continue
        for fn, line, msg in problems_in(name, source):
            if (base, fn) in EXEMPT:
                used.add((base, fn))
                continue
            out.append(f"{name}:{line}: {msg}")
    out += [f"stale exemption {k} ({v}): no bypass there any more" for k, v in EXEMPT.items()
            if k not in used and any(n.endswith(k[0]) for n in files)]
    return out


def _tree() -> dict[str, str]:
    return {str(p.relative_to(ROOT)): p.read_text(encoding="utf-8")
            for top in ("backend/ofo_app", "backend/ofo") for p in (ROOT / top).rglob("*.py")}


def test_no_file_outside_the_one_module_raises_an_alert():
    assert scan(_tree()) == []


def test_a_bad_file_gives_exactly_one_problem_and_the_home_none():
    bad = "async def f(db):\n    await store.open_suggestion(db, 'u', 1, 'T-01')\n"
    assert len(scan({"backend/ofo_app/other.py": bad})) == 1
    assert scan({"backend/ofo_app/actionable_alerts.py": bad}) == []
    sql = "Q = \"INSERT INTO public.adjustment_suggestions (a) VALUES (1)\"\n"
    assert len(scan({"backend/ofo_app/other.py": sql})) == 1
