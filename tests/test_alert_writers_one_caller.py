"""G4 (modular-doors Phase 8, PLAN 5.8): each alert or notice writer has ONE caller module.

Rule, over ``backend/ofo_app`` (tests excluded):

- ``add_alert`` (a paper trigger's alert row) only in ``paper_monitor.py`` (or ``paper_exit.py``, if the exit door took
  it over);
- ``open_suggestion`` (an actionable playbook row) only in ``actionable_alerts.py``, the one alert module of ADR-330's
  one-module instruction (Lane J 26 Nov: Lane P moved the call there from ``background.py``; which callers may raise
  an alert through that module is the guard ``test_actionable_alert_one_module.py``);
- ``playbook_store.record_held`` (a held playbook row) only in ``actionable_alerts.py`` (the write) and
  ``background.py`` (its one caller, ``actionable_alerts.record_held``: the name is matched, not the module);
- ``notifier.notify`` (the one outbound notice) only in ``worker_watch.py``.

A call, a reference (``w = add_alert``), ``getattr(obj, "add_alert")`` and a
``from ofo_app.notifier import notify`` each count. No exemption exists today; ``EXEMPT`` (file, function, name)
with a category and a reason is kept so a future one is a reviewed, "shrink only" entry (a stale entry fails).
Fail closed: an aliased import of a writer or of the ``notifier`` module (``from x import add_alert as a``) and an
unparsable file are problems. ``paper_monitor.notify`` (the monitor's own reload nudge) is another function and is
not matched: ``notify`` counts only when read off ``notifier``.
Limits (not claims): ``getattr(notifier, "notify")`` (the dotted ``notify`` is read only as an attribute of the
``notifier`` name, the plain-name getattr rule covers the other writers) and ``importlib.import_module`` of the
notifier are not caught (F9); keys name functions, not sites, so a second call in an allowed function is not counted
(F7).
"""
from __future__ import annotations

import ast
import re
from collections.abc import Mapping
from pathlib import Path

import pytest

pytestmark = pytest.mark.repo_scan

BACKEND = Path(__file__).resolve().parents[1] / "backend"
NOTIFY = "notifier.notify"
#: writer -> the files (under backend/) that may call it
HOMES: dict[str, frozenset[str]] = {
    "add_alert": frozenset({"ofo_app/paper_monitor.py", "ofo_app/paper_exit.py"}),
    "open_suggestion": frozenset({"ofo_app/actionable_alerts.py"}),
    "record_held": frozenset({"ofo_app/actionable_alerts.py", "ofo_app/background.py"}),
    NOTIFY: frozenset({"ofo_app/worker_watch.py"}),
}
PLAIN = frozenset({"add_alert", "open_suggestion", "record_held"})
CATEGORY = re.compile(r"own_process|display|real_path|awaiting_phase_\d+")
Key = tuple[str, str, str]  # (file under backend/, enclosing function, writer)
EXEMPT: dict[Key, tuple[str, str]] = {}


def _is_notifier(node: ast.expr) -> bool:
    return (isinstance(node, ast.Name) and node.id == "notifier") or (
        isinstance(node, ast.Attribute) and node.attr == "notifier")


def _getattr_name(node: ast.AST) -> str | None:
    """The constant name of ``getattr(obj, "<name>")`` / ``hasattr``, when it names a plain writer."""
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("getattr", "hasattr")
            and len(node.args) > 1 and isinstance(node.args[1], ast.Constant) and node.args[1].value in PLAIN):
        return str(node.args[1].value)
    return None


def _imports(rel: str, node: ast.stmt, func: str) -> tuple[list[tuple[str, int, str]], list[str]]:
    """Sites and alias issues of one import statement."""
    sites: list[tuple[str, int, str]] = []
    issues: list[str] = []
    from_notifier = isinstance(node, ast.ImportFrom) and (node.module or "").rsplit(".", 1)[-1] == "notifier"
    for a in getattr(node, "names", []):
        watched = a.name.rsplit(".", 1)[-1] in (PLAIN | {"notifier"}) or (from_notifier and a.name == "notify")
        if watched and a.asname and a.asname != a.name:
            issues.append(f"aliased import: {rel}:{node.lineno} imports {a.name} as {a.asname}; import it by its "
                          f"own name")
        elif from_notifier and a.name == "notify":
            sites.append((func, node.lineno, NOTIFY))
    return sites, issues


def scan(rel: str, source: str) -> tuple[list[tuple[str, int, str]], list[str]]:
    """Sites ``(function, line, writer)`` and fail-closed issues of one file."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [], [f"unparsable file, cannot be checked: {rel}: {exc.msg} (line {exc.lineno})"]
    sites: list[tuple[str, int, str]] = []
    issues: list[str] = []

    def walk(node: ast.AST, func: str) -> None:
        for child in ast.iter_child_nodes(node):
            inner = child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else func
            if isinstance(child, (ast.Import, ast.ImportFrom)):
                found, bad = _imports(rel, child, inner)
                sites.extend(found)
                issues.extend(bad)
            elif isinstance(child, ast.Name) and child.id in PLAIN:
                sites.append((inner, child.lineno, child.id))
            elif isinstance(child, ast.Attribute) and child.attr in PLAIN:
                sites.append((inner, child.lineno, child.attr))
            elif isinstance(child, ast.Attribute) and child.attr == "notify" and _is_notifier(child.value):
                sites.append((inner, child.lineno, NOTIFY))
            elif _getattr_name(child):
                sites.append((inner, child.lineno, str(_getattr_name(child))))
            walk(child, inner)

    walk(tree, "<module>")
    return sites, issues


def load_sources(backend: Path = BACKEND) -> dict[str, str]:
    return {p.relative_to(backend).as_posix(): p.read_text(encoding="utf-8")
            for p in sorted((backend / "ofo_app").rglob("*.py")) if "alembic" not in p.parts}


def problems(sources: Mapping[str, str], exempt: Mapping[Key, tuple[str, str]] = EXEMPT,
             homes: Mapping[str, frozenset[str]] = HOMES) -> list[str]:
    """Pure: the problems of ``sources`` ({file: text}). Empty means every writer has its one caller."""
    out: list[str] = []
    seen: set[Key] = set()
    for rel, text in sorted(sources.items()):
        sites, issues = scan(rel, text)
        out += issues
        for func, line, writer in sites:
            key = (rel, func, writer)
            seen.add(key)
            if rel not in homes[writer] and key not in exempt:
                door = " or ".join(sorted(homes[writer]))
                out.append(f"alert writer outside its one caller: {rel}:{line} in {func} calls {writer}(). Only "
                           f"{door} may; or add (file, function) to EXEMPT with a category and reason.")
    out += [f"stale exemption: {f}::{fn} no longer calls {n}; delete the entry"
            for (f, fn, n) in sorted(exempt) if (f, fn, n) not in seen]
    return out


def test_every_alert_writer_has_its_one_caller():
    assert problems(load_sources()) == []


def test_exemptions_carry_a_category_and_a_reason():
    bad = [k for k, (category, reason) in EXEMPT.items() if not CATEGORY.fullmatch(category) or not reason.strip()]
    assert bad == []


def test_each_home_still_calls_its_writer():
    """A home that no longer calls its writer is a dead door: the guard would pass for the wrong reason."""
    sites = {rel: {w for _f, _l, w in scan(rel, text)[0]} for rel, text in load_sources().items()}
    called = {w: {rel for rel, ws in sites.items() if w in ws} for w in HOMES}
    assert {w: sorted(called[w]) for w in HOMES if not called[w] & HOMES[w]} == {}


# ---- mutation tests: the guard goes red where it should and only there -----------------------------------------------
CALLS = {
    "add_alert": ("ofo_app/paper_monitor.py", "async def f(c):\n    return await triggers.add_alert(c, 1)\n"),
    "open_suggestion": ("ofo_app/actionable_alerts.py", "async def f(c):\n    return await store.open_suggestion(c)\n"),
    "record_held": ("ofo_app/background.py", "async def f(c):\n    return await store.record_held(c)\n"),
    NOTIFY: ("ofo_app/worker_watch.py", "async def f():\n    return await notifier.notify('a', 'b')\n"),
}


@pytest.mark.parametrize("writer", sorted(CALLS))
def test_mutation_a_bad_sample_gives_exactly_one_problem_and_the_home_none(writer):
    home, source = CALLS[writer]
    found = problems({"ofo_app/routes/x.py": source}, exempt={})
    assert len(found) == 1
    assert found[0].startswith(f"alert writer outside its one caller: ofo_app/routes/x.py:2 in f calls {writer}().")
    assert home in found[0]
    assert problems({home: source}, exempt={}) == []


def test_mutation_add_alert_is_also_allowed_in_the_exit_door():
    assert problems({"ofo_app/paper_exit.py": CALLS["add_alert"][1]}, exempt={}) == []


@pytest.mark.parametrize("source", [
    "from ofo_app.paper_trigger_store import add_alert as a\n\nasync def f():\n    return await a()\n",
    "from ofo_app.playbook_store import open_suggestion as o\n\nasync def f():\n    return await o()\n",
    "from ofo_app.notifier import notify as n\n\nasync def f():\n    return await n('a')\n",
    "from ofo_app import notifier as nt\n\nasync def f():\n    return await nt.notify('a')\n",
])
def test_mutation_an_aliased_import_gives_one_problem(source):
    found = problems({"ofo_app/routes/x.py": source}, exempt={})
    assert len(found) == 1
    assert found[0].startswith("aliased import: ofo_app/routes/x.py:1")


def test_mutation_a_plain_notify_import_and_a_reference_are_sites():
    plain = "from ofo_app.notifier import notify\n\nasync def f():\n    return await notify('a')\n"
    assert len(problems({"ofo_app/routes/x.py": plain}, exempt={})) == 1
    assert len(problems({"ofo_app/routes/x.py": "def f():\n    return add_alert\n"}, exempt={})) == 1


def test_mutation_the_monitors_own_notify_is_not_the_notifier():
    assert problems({"ofo_app/routes/paper.py": "def f():\n    paper_monitor.notify()\n"}, exempt={}) == []


def test_mutation_an_unparsable_file_fails_closed():
    found = problems({"ofo_app/x.py": "def f(:\n"}, exempt={})
    assert len(found) == 1
    assert found[0].startswith("unparsable file")


def test_mutation_a_deleted_exempt_site_is_a_stale_exemption():
    entry: dict[Key, tuple[str, str]] = {("ofo_app/routes/x.py", "f", "add_alert"): ("display", "a shown alert")}
    assert problems({"ofo_app/routes/x.py": CALLS["add_alert"][1]}, exempt=entry) == []
    found = problems({"ofo_app/routes/x.py": "def f():\n    return None\n"}, exempt=entry)
    assert found == ["stale exemption: ofo_app/routes/x.py::f no longer calls add_alert; delete the entry"]
