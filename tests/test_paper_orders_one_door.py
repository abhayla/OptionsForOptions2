"""G2 (modular-doors Phase 8, PLAN 5.8): a paper order is built in ONE place, an exit only by the exit door.

Two rules over ``backend/ofo_app`` (tests excluded):

1. ``NewOrder(...)`` is called only in a home of ``HOMES``: ``paper_exit.py`` ``exit_strategy`` (the exit door),
   ``paper_store.py`` / ``paper_book.py`` (the book's own rows), ``tracked_book.py`` (the real book view),
   ``paper_trigger_store.py`` (rows read back), ``routes/paper.py`` ``_place_orders`` (the browser's basket).
2. In the four paper modules (``paper_exit.py``, ``paper_monitor.py``, ``routes/paper.py``, ``routes/tracking.py``) no
   ``"BUY"``/``"SELL"`` conditional expression and no ``_opposite`` call outside the door (``paper_exit.py``), except an
   entry of ``EXEMPT`` (file, function, name) with a category and a reason. "shrink only": a stale entry fails.

Out of scope by key (they build orders of another book or another meaning, not the paper exit): ``ofo/execution/*``,
``reconciliation/resolution.py``, ``adjustment/approaches.py`` and the charge estimates; none is under ``ofo_app`` paper
modules, so only ``ofo_app`` is scanned. Fail closed: an aliased import of ``NewOrder`` or ``_opposite`` and an
unparsable file are problems. Every Load of the name ``NewOrder`` or ``_opposite`` that is not part of an import
counts as a build outside the homes: a call, ``X = NewOrder``, ``partial(NewOrder, 1)``, ``return NewOrder``,
``map(NewOrder, rows)``, a keyword value, a tuple, a class base and ``getattr(m, "NewOrder")`` with a constant name.
A type annotation (argument, return or ``AnnAssign`` annotation) is excluded: a hint builds nothing.
Limits (not claims): ``dataclasses.replace(order, ...)`` and ``type(order)(...)`` copy an order without the name and are
not caught; ``getattr`` with a non-constant name is not seen; a side flip is caught only as a ``BUY``/``SELL`` IfExp
(``dict`` lookup, ``if`` statement, ``==`` chains are not); keys count functions, not sites (a second build in an
allowed function is not seen).
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
    "ofo_app/routes/paper.py": frozenset({"_place_orders"}),  # FD2: place_paper_orders hands its basket to this
}
SIDE_FLIP = "BUY/SELL IfExp"
WATCHED = ("NewOrder", "_opposite")
CATEGORY = re.compile(r"own_process|display|real_path|awaiting_phase_\d+")
Key = tuple[str, str, str]  # (file under backend/, enclosing function, name)

#: side-flip leftovers in the four paper modules after Phase 4 (none awaits a phase)
# #729: the tracking exit reads the net under the lock (no signed held qty left)
EXEMPT: dict[Key, tuple[str, str]] = {}


def _name_of(node: ast.expr) -> str | None:
    return node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute) else None


def _annotation_ids(node: ast.AST) -> set[int]:
    """Ids of the annotation children of ``node``: a type hint builds nothing."""
    ann = None
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        ann = node.returns
    elif isinstance(node, (ast.arg, ast.AnnAssign)):
        ann = node.annotation
    return {id(ann)} if ann is not None else set()


def _alias_issues(rel: str, node: ast.Import | ast.ImportFrom) -> list[str]:
    return [f"aliased import: {rel}:{node.lineno} imports {a.name} as {a.asname}; import it by its own name"
            for a in node.names
            if a.asname and a.name.rsplit(".", 1)[-1] in WATCHED and a.asname != a.name]


def _site_kind(node: ast.AST) -> str | None:
    """NewOrder / _opposite for a Load of the name or a constant getattr of it, SIDE_FLIP for a BUY/SELL IfExp."""
    if isinstance(node, (ast.Name, ast.Attribute)) and isinstance(node.ctx, ast.Load) and _name_of(node) in WATCHED:
        return _name_of(node)
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("getattr", "hasattr")
            and len(node.args) > 1 and isinstance(node.args[1], ast.Constant) and node.args[1].value in WATCHED):
        return str(node.args[1].value)
    if isinstance(node, ast.IfExp) and any(isinstance(c, ast.Constant) and c.value in ("BUY", "SELL")
                                           for c in ast.walk(node)):
        return SIDE_FLIP
    return None


def scan(rel: str, source: str) -> tuple[list[tuple[str, int, str]], list[str]]:
    """Sites ``(function, line, kind)`` (kind: NewOrder, SIDE_FLIP or _opposite) and fail-closed issues of one file."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [], [f"unparsable file, cannot be checked: {rel}: {exc.msg} (line {exc.lineno})"]
    sites: list[tuple[str, int, str]] = []
    issues: list[str] = []

    def walk(node: ast.AST, func: str) -> None:
        skip = _annotation_ids(node)
        for child in ast.iter_child_nodes(node):
            if id(child) in skip:
                continue
            inner = child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else func
            if isinstance(child, (ast.ImportFrom, ast.Import)):
                issues.extend(_alias_issues(rel, child))
                continue  # the names of an import are not uses
            kind = _site_kind(child)
            if kind:
                sites.append((inner, child.lineno, kind))
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


# ---- mutation tests: the guard goes red where it should and only there -----------------------------------------------
BUILD = "def make(a):\n    return NewOrder(1, 'BUY', 1, a, 'open', None)\n"
FLIP = "def f(side):\n    return 'SELL' if side == 'BUY' else 'BUY'\n"
FLIP_ENTRY: dict[Key, tuple[str, str]] = {("ofo_app/routes/paper.py", "f", SIDE_FLIP): ("display", "a label")}


def test_mutation_a_build_outside_every_home_gives_exactly_one_problem():
    found = problems({"ofo_app/routes/x.py": BUILD}, exempt={}, homes={})
    assert len(found) == 1
    assert found[0].startswith("paper order built outside its door: ofo_app/routes/x.py:2 in make builds NewOrder().")
    assert "paper_exit.exit_strategy" in found[0]


def test_mutation_the_same_build_in_a_home_gives_none():
    store = {"ofo_app/paper_store.py": HOMES["ofo_app/paper_store.py"]}
    assert problems({"ofo_app/paper_store.py": BUILD}, exempt={}, homes=store) == []
    assert problems({EXIT_DOOR: BUILD.replace("make", "exit_strategy")}, exempt={},
                    homes={EXIT_DOOR: frozenset({"exit_strategy"})}) == []


def test_mutation_a_second_function_in_a_function_keyed_home_is_a_problem():
    found = problems({EXIT_DOOR: BUILD.replace("make", "another")}, exempt={},
                     homes={EXIT_DOOR: frozenset({"exit_strategy"})})
    assert any(p.startswith("paper order built outside its door") and "in another" in p for p in found)


def test_mutation_an_aliased_import_gives_one_problem():
    source = "from ofo_app.paper_book import NewOrder as N\n\ndef make():\n    return N(1)\n"
    found = problems({"ofo_app/routes/x.py": source}, exempt={}, homes={})
    assert len(found) == 1
    assert found[0].startswith("aliased import: ofo_app/routes/x.py:1")


def test_mutation_a_name_that_builds_later_is_a_build():
    found = problems({"ofo_app/routes/x.py": "make = NewOrder\n"}, exempt={}, homes={})
    assert len(found) == 1


def test_mutation_an_unparsable_file_fails_closed():
    found = problems({"ofo_app/x.py": "def f(:\n"}, exempt={}, homes={})
    assert len(found) == 1
    assert found[0].startswith("unparsable file")


def test_mutation_a_side_flip_outside_the_door_gives_one_problem_and_none_in_the_door():
    found = problems({"ofo_app/routes/paper.py": FLIP}, exempt={}, homes={})
    assert len(found) == 1
    assert found[0].startswith("exit side flipped outside paper_exit.exit_strategy: ofo_app/routes/paper.py:2 in f")
    assert problems({EXIT_DOOR: FLIP}, exempt={}, homes={}) == []


def test_mutation_an_opposite_call_in_a_paper_module_gives_one_problem():
    found = problems({"ofo_app/paper_monitor.py": "def f(s):\n    return _opposite(s)\n"}, exempt={}, homes={})
    assert len(found) == 1
    assert "_opposite" in found[0]


def test_mutation_an_exempt_flip_passes_and_a_deleted_one_is_stale():
    assert problems({"ofo_app/routes/paper.py": FLIP}, exempt=FLIP_ENTRY, homes={}) == []
    found = problems({"ofo_app/routes/paper.py": "def f(side):\n    return side\n"}, exempt=FLIP_ENTRY, homes={})
    assert found == [f"stale exemption: ofo_app/routes/paper.py::f no longer calls {SIDE_FLIP}; delete the entry"]


def test_mutation_a_home_function_that_stopped_building_is_stale():
    sources = load_sources()
    sources[EXIT_DOOR] = sources[EXIT_DOOR].replace("NewOrder(", "dict(")
    assert problems(sources) == [
        "stale exemption: ofo_app/paper_exit.py::exit_strategy no longer calls NewOrder; delete the entry"]


@pytest.mark.parametrize("source", [
    "import functools\n\ndef f():\n    return functools.partial(NewOrder, 1)\n",
    "def f():\n    return NewOrder\n",
    "def f(rows):\n    return list(map(NewOrder, rows))\n",
    "def f(h):\n    return h(builder=NewOrder)\n",
    "def f():\n    a, b = NewOrder, 1\n    return a\n",
    "B: type = NewOrder\n",
    "class N2(NewOrder):\n    pass\n",
    "def f(m):\n    return getattr(m, 'NewOrder')\n",
    "def f(m):\n    return m.NewOrder\n",
], ids=["partial", "return", "map", "keyword", "tuple", "annassign-value", "class-base", "getattr-const", "attribute"])
def test_mutation_every_reference_to_neworder_outside_a_home_is_a_problem(source):
    found = problems({"ofo_app/routes/x.py": source}, exempt={}, homes={})
    assert len(found) == 1, found
    assert found[0].startswith("paper order built outside its door: ofo_app/routes/x.py:")
    assert problems({"ofo_app/paper_store.py": source}, exempt={}, homes={"ofo_app/paper_store.py": None}) == []


def test_mutation_an_opposite_reference_in_a_paper_module_is_a_problem():
    found = problems({"ofo_app/paper_monitor.py": "def f(rows):\n    return list(map(_opposite, rows))\n"},
                     exempt={}, homes={})
    assert len(found) == 1
    assert "_opposite" in found[0]


def test_mutation_type_hints_and_imports_are_not_a_build():
    source = ("from ofo.x import NewOrder\n\ndef f(a: NewOrder, *, b: 'NewOrder' = None) -> list[NewOrder]:\n"
              "    c: NewOrder\n    return []\n")
    assert problems({"ofo_app/routes/x.py": source}, exempt={}, homes={}) == []
