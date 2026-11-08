"""Step 2 (ADR-243): every production call of ``paper_store.place`` names ``entry=`` explicitly.

A caller that forgets ``entry=`` would silently store no entry facts at a strategy's first fill (the default is
None). The scan walks backend/ofo_app and parses each module; a call counts when it is ``paper_store.place(...)``,
or a bare name bound by ``from ofo_app.paper_store import place`` (optionally renamed). ``entry=`` must be a
keyword; ``**kwargs`` does not count (cannot be resolved: fail closed).
"""
import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.repo_scan

MIN_PLACE_CALLS = 3  # the scan must see at least this many production paper_store.place calls
ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "backend" / "ofo_app"


def _bad_calls(tree: ast.AST) -> list[int]:
    module_names: set[str] = {"paper_store"}
    func_names: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module and n.module.endswith("paper_store"):
            func_names |= {a.asname or a.name for a in n.names if a.name == "place"}
        elif isinstance(n, ast.ImportFrom):
            module_names |= {a.asname for a in n.names if a.name == "paper_store" and a.asname}
        elif isinstance(n, ast.Import):
            module_names |= {a.asname for a in n.names if a.asname and a.name.endswith("paper_store")}
    bad = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        hit = (isinstance(f, ast.Attribute) and f.attr == "place" and isinstance(f.value, ast.Name)
               and f.value.id in module_names) or (isinstance(f, ast.Name) and f.id in func_names)
        if hit and not any(k.arg == "entry" for k in n.keywords):
            bad.append(n.lineno)
    return bad


def _scan(root: Path) -> tuple[list[str], int]:
    problems, calls = [], 0
    for path in sorted(root.rglob("*.py")):
        if path.name == "paper_store.py":
            continue
        src = path.read_text(encoding="utf-8")
        calls += src.count("paper_store.place(")
        problems += [f"{path.name}:{ln}" for ln in _bad_calls(ast.parse(src))]
    return problems, calls


def test_every_production_place_call_names_entry():
    problems, calls = _scan(APP)
    assert calls >= MIN_PLACE_CALLS, (
        f"the scan found only {calls} paper_store.place calls: it is not looking at the right tree"
    )
    assert problems == [], f"paper_store.place called without entry= at {problems}"


def test_scan_detects_a_caller_that_drops_entry(tmp_path):
    (tmp_path / "x.py").write_text("from ofo_app import paper_store\n"
                                   "async def f(c):\n    await paper_store.place(c, 'u', 1, [])\n")
    (tmp_path / "y.py").write_text("from ofo_app.paper_store import place as p\n"
                                   "async def f(c):\n    await p(c, 'u', 1, [], **{})\n")
    problems, _ = _scan(tmp_path)
    assert problems == ["x.py:3", "y.py:3"]
