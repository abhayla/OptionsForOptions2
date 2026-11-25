"""G2 (modular-doors Phase 8, PLAN 5.8): a paper order is built in ONE place, an exit only by the exit door.

Two rules over ``backend/ofo_app`` (tests excluded):

1. ``NewOrder(...)`` is called only in a home of ``HOMES``: ``paper_exit.py`` ``exit_strategy`` (the exit door),
   ``paper_store.py`` / ``paper_book.py`` (the book's own rows), ``tracked_book.py`` (the real book view),
   ``paper_trigger_store.py`` (rows read back), ``routes/paper.py`` ``place_paper_orders`` (the browser's basket).
2. In the four paper modules (``paper_exit.py``, ``paper_monitor.py``, ``routes/paper.py``, ``routes/tracking.py``) no
   ``"BUY"``/``"SELL"`` conditional expression and no ``_opposite`` call outside the door (``paper_exit.py``), except an
   entry of ``EXEMPT`` (file, function, name) with a category and a reason. "shrink only": a stale entry fails.

Out of scope by key (they build orders of another book or another meaning, not the paper exit): ``ofo/execution/*``,
``reconciliation/resolution.py``, ``adjustment/approaches.py`` and the charge estimates; none is under ``ofo_app`` paper
modules, so only ``ofo_app`` is scanned. Fail closed: an aliased import of ``NewOrder`` or ``_opposite`` and an
unparsable file are problems; ``X = NewOrder`` (a reference that could build later) counts as a build.
"""
from __future__ import annotations

import ast
import re
from collections.abc import Mapping
from pathlib import Path

import pytest

pytestmark = pytest.mark.repo_scan

BACKEND = Path(__file__).resolve().parents[1] / "backend"
EXIT_DOOR = "ofo_app/paper_exit.py"
PAPER_MODULES = ("ofo_app/paper_exit.py", "ofo_app/paper_monitor.py", "ofo_app/routes/paper.py",
                 "ofo_app/routes/tracking.py")
#: file -> the functions that may build a NewOrder (None: any function of the file)
HOMES: dict[str, frozenset[str] | None] = {
    "ofo_app/paper_exit.py": frozenset({"exit_strategy"}),
    "ofo_app/paper_store.py": None,
    "ofo_app/paper_book.py": None,
    "ofo_app/tracked_book.py": None,
    "ofo_app/paper_trigger_store.py": None,
    "ofo_app/routes/paper.py": frozenset({"place_paper_orders"}),
}
SIDE_FLIP = "BUY/SELL IfExp"
CATEGORY = re.compile(r"own_process|display|real_path|awaiting_phase_\d+")
Key = tuple[str, str, str]  # (file under backend/, enclosing function, name)

#: side-flip leftovers in the four paper modules after Phase 4 (none awaits a phase)
EXEMPT: dict[Key, tuple[str, str]] = {
    ("ofo_app/routes/tracking.py", "exit_tracking", SIDE_FLIP): (
        "own_process", "a signed held quantity (BUY +qty, SELL -qty) for the exit's lot check; no order is built"),
}


def _name_of(node: ast.expr) -> str | None:
    return node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute) else None


def scan(rel: str, source: str) -> tuple[list[tuple[str, int, str]], list[str]]:
    """Sites ``(function, line, kind)`` (kind: NewOrder, SIDE_FLIP or _opposite) and fail-closed issues of one file."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [], [f"unparsable file, cannot be checked: {rel}: {exc.msg} (line {exc.lineno})"]
    sites: list[tuple[str, int, str]] = []
    issues: list[str] = []

    def walk(node: ast.AST, func: str) -> None:
        for child in ast.iter_child_nodes(node):
            inner = child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else func
            if isinstance(child, (ast.ImportFrom, ast.Import)):
                issues.extend(f"aliased import: {rel}:{child.lineno} imports {a.name} as {a.asname}; import it by its "
                              f"own name" for a in child.names
                              if a.asname and a.name.rsplit(".", 1)[-1] in ("NewOrder", "_opposite")
                              and a.asname != a.name)
            elif isinstance(child, ast.Call) and _name_of(child.func) in ("NewOrder", "_opposite"):
                sites.append((inner, child.lineno, str(_name_of(child.func))))
            elif isinstance(child, ast.Assign) and _name_of(child.value) in ("NewOrder", "_opposite"):
                sites.append((inner, child.lineno, str(_name_of(child.value))))  # a name that builds later
            elif isinstance(child, ast.IfExp) and any(
                    isinstance(c, ast.Constant) and c.value in ("BUY", "SELL") for c in ast.walk(child)):
                sites.append((inner, child.lineno, SIDE_FLIP))
            walk(child, inner)

    walk(tree, "<module>")
    return sites, issues


def load_sources(backend: Path = BACKEND) -> dict[str, str]:
    return {p.relative_to(backend).as_posix(): p.read_text(encoding="utf-8")
            for p in sorted((backend / "ofo_app").rglob("*.py")) if "alembic" not in p.parts}


def problems(sources: Mapping[str, str], exempt: Mapping[Key, tuple[str, str]] = EXEMPT,
             homes: Mapping[str, frozenset[str] | None] = HOMES) -> list[str]:
    """Pure: the problems of ``sources`` ({file: text}). Empty means the one door holds."""
    out: list[str] = []
    seen: set[Key] = set()
    for rel, text in sorted(sources.items()):
        sites, issues = scan(rel, text)
        out += issues
        for func, line, kind in sites:
            seen.add((rel, func, kind))
            if kind == "NewOrder":
                allowed = rel in homes and (homes[rel] is None or func in (homes[rel] or ()))
                if not allowed:
                    out.append(f"paper order built outside its door: {rel}:{line} in {func} builds NewOrder(). "
                               f"Build it in paper_exit.exit_strategy (an exit) or a home of HOMES, or add "
                               f"(file, function) to HOMES with a reason.")
            elif rel in PAPER_MODULES and rel != EXIT_DOOR and (rel, func, kind) not in exempt:
                out.append(f"exit side flipped outside paper_exit.exit_strategy: {rel}:{line} in {func} uses {kind}. "
                           f"Build the exit through paper_exit.exit_strategy, or add (file, function) to EXEMPT "
                           f"with a category and reason.")
    out += [f"stale exemption: {f}::{fn} no longer calls {n}; delete the entry"
            for (f, fn, n) in sorted(exempt) if (f, fn, n) not in seen]
    out += [f"stale exemption: {f}::{fn} no longer calls NewOrder; delete the entry"
            for f, fns in sorted(homes.items()) for fn in sorted(fns or ()) if (f, fn, "NewOrder") not in seen]
    return out


def test_paper_orders_are_built_only_at_their_door():
    assert problems(load_sources()) == []


def test_exemptions_carry_a_category_and_a_reason():
    bad = [k for k, (category, reason) in EXEMPT.items() if not CATEGORY.fullmatch(category) or not reason.strip()]
    assert bad == []
    assert not [k for k in EXEMPT if k[0] == EXIT_DOOR]  # the door is not an exemption
