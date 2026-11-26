"""ADR-330 standing instruction: ONE module raises, answers and closes alerts. AST scan of backend/ofo_app and
backend/ofo.

Writing side: a call of open_suggestion, record_held, add_alert; a call of lapse, lapse_all, close_suggestion, _close,
dismiss or act_on on the playbook store (``store.`` / ``pb.`` / ``playbook_store.`` / a bare name); an SQL string with
INSERT INTO or UPDATE of adjustment_suggestions / paper_alerts (quoted ``"public"."adjustment_suggestions"`` and any
letter case included); all outside the allowed homes fail with file, line and the module to use
(``ofo_app.actionable_alerts``). The homes are matched by FULL repo path, never by file name (a file named like a home
elsewhere is not one). Exemptions are keyed (path, function) with a category; a stale one fails.

Also caught: ``import x as actionable_alerts`` / ``from x import y as actionable_alerts`` where x is not
``ofo_app.actionable_alerts`` (the scan trusts calls on that name), and ``from ... import open_suggestion as other``
(a renamed writer).

Not scanned: worker_watch / notifier (the worker-silence notice is not an alert of a strategy).
Known bypasses (written, not caught): a call through ``getattr`` or an alias made by assignment (``f = store.lapse``);
SQL built from pieces that never contain the words together; a raw INSERT or UPDATE in a file outside backend/; a stored
procedure; a generic-named call (``_close``, ``dismiss``) on an owner other than the store names above.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

pytestmark = pytest.mark.repo_scan

ROOT = pathlib.Path(__file__).resolve().parent.parent
APP = "backend/ofo_app/"
AA, PB, PTS = APP + "actionable_alerts.py", APP + "playbook_store.py", APP + "paper_trigger_store.py"
#: call -> the repo paths allowed to make it
CALLS: dict[str, frozenset[str]] = {
    "open_suggestion": frozenset({AA, PB}), "record_held": frozenset({AA, PB}), "add_alert": frozenset({AA, PTS}),
    "lapse": frozenset({AA, PB}), "lapse_all": frozenset({AA, PB}), "close_suggestion": frozenset({AA, PB}),
    "_close": frozenset({AA, PB}), "dismiss": frozenset({AA, PB}), "act_on": frozenset({AA, PB}),
}
#: names common enough elsewhere (alert_gate._close, state.dismiss): flagged only on the playbook store's names
GENERIC = {"lapse", "_close", "dismiss", "act_on"}
STORE_NAMES = {"store", "pb", "playbook_store"}
TABLES = ("adjustment_suggestions", "paper_alerts")
SQL_HOMES = frozenset({AA, PB, PTS})
USE = "ofo_app.actionable_alerts"
EXEMPT: dict[tuple[str, str], str] = {}


def _sql_writes(value: str) -> str | None:
    """'INSERT INTO' or 'UPDATE' of an alert table in a string constant, whatever the quoting, case or spacing."""
    low = " ".join(value.lower().replace('"', "").split())
    for t in TABLES:
        for verb in ("insert into", "update"):
            if f"{verb} public.{t}" in low or f"{verb} {t}" in low:
                return verb.upper()
    return None


def _import_problems(node: ast.Import | ast.ImportFrom) -> list[tuple[str, int, str]]:
    """The import-statement bypasses of one import node (an alias of the module, a renamed call)."""
    found: list[tuple[str, int, str]] = []
    module = getattr(node, "module", None) or ""
    for a in node.names:
        full = module + "." + a.name
        from_pkg = isinstance(node, ast.ImportFrom) and module == "ofo_app" and a.name == "actionable_alerts"
        if a.asname == "actionable_alerts" and not full.endswith("ofo_app.actionable_alerts") and not from_pkg:
            found.append(("<module>", node.lineno, f"{a.name} imported as actionable_alerts: use {USE} itself"))
        if isinstance(node, ast.ImportFrom) and a.name in CALLS and a.asname and a.asname != a.name:
            found.append(("<module>", node.lineno, f"{a.name} renamed on import: call it by its name from {USE}"))
    return found


def problems_in(name: str, source: str) -> list[tuple[str, int, str]]:
    """(function, line, message) for every bypass in one file's source."""
    found: list[tuple[str, int, str]] = []
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            found.extend(_import_problems(node))

    def walk(node: ast.AST, fn: str) -> None:
        for child in ast.iter_child_nodes(node):
            inner = child.name if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef) else fn
            if isinstance(child, ast.Call):
                f = child.func
                called = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
                owner = getattr(f.value, "id", "") if isinstance(f, ast.Attribute) else None
                lapse_bare = owner is None and called == "lapse"
                if called in CALLS and owner != "actionable_alerts" and name not in CALLS[called] \
                        and (called not in GENERIC or owner in STORE_NAMES or lapse_bare):
                    found.append((fn, child.lineno, f"{called}() outside the one module: use {USE}"))
            if isinstance(child, ast.Constant) and isinstance(child.value, str) and name not in SQL_HOMES:
                verb = _sql_writes(child.value)
                if verb:
                    found.append((fn, child.lineno, f"{verb} of an alert table outside the one module: use {USE}"))
            walk(child, inner)
    walk(tree, "<module>")
    return found


def scan(files: dict[str, str]) -> list[str]:
    """``files``: full repo path -> source. Homes are matched by the full path."""
    out, used = [], set()
    for name, source in files.items():
        for fn, line, msg in problems_in(name, source):
            if (name, fn) in EXEMPT:
                used.add((name, fn))
                continue
            out.append(f"{name}:{line}: {msg}")
    out += [f"stale exemption {k} ({v}): no bypass there any more" for k, v in EXEMPT.items()
            if k not in used and k[0] in files]
    return out


def _tree() -> dict[str, str]:
    return {str(p.relative_to(ROOT)).replace("\\", "/"): p.read_text(encoding="utf-8")
            for top in ("backend/ofo_app", "backend/ofo") for p in (ROOT / top).rglob("*.py")}


def test_no_file_outside_the_one_module_raises_answers_or_closes_an_alert():
    assert scan(_tree()) == []


def test_a_bad_file_gives_exactly_one_problem_and_the_home_none():
    bad = "async def f(db):\n    await store.open_suggestion(db, 'u', 1, 'T-01')\n"
    assert len(scan({APP + "other.py": bad})) == 1
    assert scan({AA: bad}) == []
    sql = "Q = \"INSERT INTO public.adjustment_suggestions (a) VALUES (1)\"\n"
    assert len(scan({APP + "other.py": sql})) == 1


@pytest.mark.parametrize("call", ["lapse", "lapse_all", "close_suggestion", "_close", "dismiss", "act_on"])
def test_every_closing_call_is_caught_outside_the_two_homes(call):
    src = f"async def f(db):\n    await pb.{call}(db, 'u', 1)\n"
    assert len(scan({APP + "other.py": src})) == 1
    assert scan({AA: src}) == scan({PB: src}) == []
    other = f"def f(s):\n    return s.{call}(1)\n"  # another owner: only the non-generic names are the store's alone
    assert len(scan({APP + "other.py": other})) == (0 if call in GENERIC else 1)


@pytest.mark.parametrize("sql", [
    'UPDATE "public"."adjustment_suggestions" SET outcome = 1', "update public.ADJUSTMENT_SUGGESTIONS set a = 1",
    "UPDATE   adjustment_suggestions\n SET a = 1", "Insert Into \"public\".\"paper_alerts\" (a) VALUES (1)"])
def test_quoted_and_case_variants_of_a_write_are_caught(sql):
    assert len(scan({APP + "other.py": f"Q = {sql!r}\n"})) == 1
    assert scan({PB: f"Q = {sql!r}\n"}) == []


def test_a_home_is_matched_by_its_full_path_not_its_file_name():
    bad = "async def f(db):\n    await store.open_suggestion(db, 'u', 1, 'T-01')\n"
    assert len(scan({"backend/ofo_app/routes/actionable_alerts.py": bad})) == 1
    assert len(scan({"backend/ofo/playbook_store.py": bad})) == 1


@pytest.mark.parametrize("src", ["import evil as actionable_alerts\n", "from evil import writer as actionable_alerts\n",
                                 "from ofo_app.playbook_store import open_suggestion as quiet\n"])
def test_an_import_alias_of_the_one_module_or_a_writer_is_caught(src):
    assert len(scan({APP + "other.py": src})) == 1


@pytest.mark.parametrize("src", [
    "from ofo_app import actionable_alerts\n",
    "import ofo_app.actionable_alerts as actionable_alerts\n",
    "from ofo_app import actionable_alerts as actionable_alerts\n",
])
def test_the_real_import_of_the_one_module_is_not_a_problem(src):
    assert scan({APP + "other.py": src}) == []
