"""Guards of the class "scenario fixtures read or loaded around the one loader"
(knowledge/findings/fixture-dates-expire-with-the-clock.json):

* no-DB: no tests_app file reads a scenario fixture file (tests/fixtures/adjust_scenarios, adjust_paths) except
  through ``scenario_mode.read``. The scan follows the fixture DIRECTORY (a path literal, a name bound to one, the
  ``scenario_mode`` import's FIXTURES / PATHS / scenario_path / frame_path) and fails closed on any use it cannot
  resolve to ``<dir> / "_playbooks.json"`` or ``"INDEX.md"`` (non-scenario files).
* DB: loading the library's union twice leaves 0 delisted contracts (nothing is ever re-listed).
"""
from __future__ import annotations

import ast
import pathlib

import pytest

pytestmark = pytest.mark.repo_scan

HERE = pathlib.Path(__file__).resolve().parent
DIRS = {"adjust_scenarios", "adjust_paths"}
ALLOWED = {"_playbooks.json", "INDEX.md"}  # library files that are not scenarios
SM_MARKERS = {"FIXTURES", "PATHS", "scenario_path", "frame_path"}
SM_MODULE = "ofo_app.scenario_mode"
BYPASS_MODULES = {"test_adjust_scenarios"}  # tests/test_adjust_scenarios.py's own ``load`` reads the files directly
#: files that may touch the directory: the one library loader, and tests of scenario_mode's path resolver itself
EXEMPT = {"_scenario_catalogue.py", "test_scenario_isolation.py", "test_scenario_mode.py", pathlib.Path(__file__).name}


def _is_dir_string(value: str) -> bool:
    if any(value.endswith(a) for a in ALLOWED):
        return False
    return value in DIRS or "fixtures/adjust_" in value.replace("\\", "/")


def violations(source: str, name: str = "<src>") -> list[str]:  # noqa: C901, PLR0912 - one readable walk
    """``file:line what`` for every read of a scenario fixture outside ``scenario_mode.read``."""
    tree = ast.parse(source)
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    out: list[str] = []
    sm_aliases: set[str] = set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod in BYPASS_MODULES:
                out.append(f"{name}:{node.lineno} imports from {mod} (reads fixtures around scenario_mode.read)")
            for a in node.names:
                if mod == "ofo_app" and a.name == "scenario_mode":
                    sm_aliases.add(a.asname or a.name)
                if mod == SM_MODULE and a.name in SM_MARKERS:
                    names.add(a.asname or a.name)
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name in BYPASS_MODULES:
                    out.append(f"{name}:{node.lineno} imports {a.name} (reads fixtures around scenario_mode.read)")
                if a.name == SM_MODULE and a.asname:
                    sm_aliases.add(a.asname)
    docstrings = {id(n.value) for n in ast.walk(tree) if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)}

    def seed(node: ast.AST) -> bool:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return id(node) not in docstrings and _is_dir_string(node.value)
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            return node.value.id in sm_aliases and node.attr in SM_MARKERS
        return isinstance(node, ast.Name) and node.id in names and isinstance(node.ctx, ast.Load)

    while True:  # names bound to a marker are markers (to a fixpoint)
        found: list[tuple[ast.AST, int]] = []
        for start in [n for n in ast.walk(tree) if seed(n)]:
            node = start
            while True:
                parent = parents.get(node)
                if isinstance(parent, ast.BinOp) and isinstance(parent.op, ast.Div):
                    right = parent.right
                    if parent.left is node and isinstance(right, ast.Constant) and right.value in ALLOWED:
                        break  # <dir> / "_playbooks.json": a non-scenario file
                    node = parent
                    continue
                if isinstance(parent, (ast.Assign, ast.AnnAssign)) and parent.value is node:
                    targets = parent.targets if isinstance(parent, ast.Assign) else [parent.target]
                    if all(isinstance(t, ast.Name) for t in targets):
                        new = {t.id for t in targets} - names
                        names.update(new)
                        if new:
                            found.append((node, 0))
                        break
                found.append((node, getattr(node, "lineno", 0) or getattr(start, "lineno", 0)))
                break
        if not any(line == 0 for _n, line in found):
            break
    out += sorted({f"{name}:{line} uses the scenario fixture directory outside scenario_mode.read"
                   for _n, line in found if line})
    return out


def test_no_tests_app_file_reads_a_scenario_fixture_except_through_scenario_mode_read():
    bad = [v for p in sorted(HERE.glob("*.py")) if p.name not in EXEMPT
           for v in violations(p.read_text(encoding="utf-8"), p.name)]
    assert bad == [], "\n".join(bad)


@pytest.mark.parametrize(("src", "flagged"), [
    ('FIX = ROOT / "tests" / "fixtures" / "adjust_scenarios"\nd = json.loads((FIX / f"{s}.json").read_text())', True),
    ('d = json.loads((ROOT / "tests" / "fixtures" / "adjust_scenarios" / "ADJ-13.json").read_text())', True),
    ('A = ROOT / "adjust_scenarios"\nB = A\nfor p in B.glob("*.json"): pass', True),  # renamed, then globbed
    ("from ofo_app import scenario_mode as sm\nx = sm.frame_path('PATH-01', 0).read_text()", True),
    ("from ofo_app.scenario_mode import FIXTURES as F\nx = (F / 'ADJ-02.json').read_text()", True),
    ("from test_adjust_scenarios import load", True),
    ('p = "tests/fixtures/adjust_scenarios/ADJ-02.json"\nx = open(p).read()', True),
    ('FIX = ROOT / "adjust_scenarios"\nP = json.loads((FIX / "_playbooks.json").read_text())', False),
    ('P = json.loads((ROOT / "tests/fixtures/adjust_scenarios/_playbooks.json").read_text())', False),
    ('"""tests/fixtures/adjust_scenarios/ADJ-13.json in a docstring"""\nx = scenario_mode.read("ADJ-13")', False),
])
def test_the_scan_flags_every_fixture_read_shape_and_passes_the_rest(src, flagged):
    assert bool(violations(src)) is flagged, violations(src)


async def test_loading_the_library_twice_leaves_no_contract_delisted(app_engine, monkeypatch):
    from _scenario_catalogue import library_contracts, load_library  # noqa: PLC0415
    from ofo_app import catalogue_store, scenario_mode  # noqa: PLC0415
    from sqlalchemy import text  # noqa: PLC0415

    monkeypatch.setenv("DATABASE_URL", app_engine.url.render_as_string(hide_password=False))
    monkeypatch.setenv("APP_ENV", "test")
    await load_library(app_engine)
    await load_library(app_engine)
    ids = {scenario_mode.instrument_id(lc) for lc in library_contracts()}
    async with app_engine.connect() as conn:
        rows = (await conn.execute(text(f"SELECT exchange_segment, exchange_token, delisted, retired "  # noqa: S608
                                        f"FROM {catalogue_store.CONTRACTS}"))).all()
    mine = {f"{s}:{t}": (d, r) for s, t, d, r in rows if f"{s}:{t}" in ids}
    assert set(mine) == ids  # every union member stored
    assert [i for i, (d, r) in mine.items() if d or r] == []  # 0 delisted, 0 retired
