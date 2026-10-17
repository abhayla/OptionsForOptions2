"""Finding repo-wide-scan-outside-targeted-tests: every test module that walks the source tree carries `repo_scan`.

`python -m pytest -q -p no:cacheprovider -m repo_scan tests` then runs every repo-wide scan in one fast command.
A module counts as a scan when its code calls one of the tree-walking shapes in SCAN_CALLS (an allow-list taken
from the scans found on main: `.rglob`, `.glob`, `.iterdir`, `os.walk`). It is marked when it sets
`pytestmark = pytest.mark.repo_scan` (alone or in a list) or every `test_*` function carries the decorator.
"""
import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.repo_scan

ROOT = Path(__file__).resolve().parents[1]
TEST_TREES = ("tests", "tests_app")
MARK = "repo_scan"
SCAN_ATTRS = frozenset({"rglob", "glob", "iterdir"})
SCAN_CALLS = SCAN_ATTRS | {"os.walk"}  # the closed list of scan shapes; anything else is not a scan
# Modules that glob a directory but do not scan the source tree, each with the reason (a closed list, no patterns).
NOT_SCANS = {
    "tests/hooks/test_verifier_inflight_gate.py":
        "globs the hook folder only to copy it into a tmp dir for ~100 s of mutation runs; not a source-tree scan",
}


def _is_mark(node: ast.AST) -> bool:
    """True for `pytest.mark.repo_scan` (possibly called)."""
    if isinstance(node, ast.Call):
        node = node.func
    return isinstance(node, ast.Attribute) and node.attr == MARK and isinstance(node.value, ast.Attribute) \
        and node.value.attr == "mark"


def scan_calls(tree: ast.AST) -> list[int]:
    """Line numbers of tree-walking calls (allow-list SCAN_CALLS)."""
    lines = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        func = node.func
        if func.attr in SCAN_ATTRS or (func.attr == "walk" and isinstance(func.value, ast.Name)
                                       and func.value.id == "os"):
            lines.append(node.lineno)
    return lines


def module_is_marked(tree: ast.Module) -> bool:
    """Module-level `pytestmark` naming repo_scan, or every top-level test function decorated with it."""
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets):
            value = node.value
            items = value.elts if isinstance(value, (ast.List, ast.Tuple)) else [value]
            if any(_is_mark(i) for i in items):
                return True
    funcs = (ast.FunctionDef, ast.AsyncFunctionDef)
    tests = [n for n in tree.body if isinstance(n, funcs) and n.name.startswith("test_")]
    return bool(tests) and all(any(_is_mark(d) for d in t.decorator_list) for t in tests)


def unmarked_scans(paths: list[Path]) -> list[str]:
    """`path:line` of the first scan call in each test module that walks the tree without the mark."""
    bad = []
    for path in paths:
        if path.is_relative_to(ROOT) and path.relative_to(ROOT).as_posix() in NOT_SCANS:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        lines = scan_calls(tree)
        if lines and not module_is_marked(tree):
            bad.append(f"{path.as_posix()}:{lines[0]}")
    return bad


def _test_files() -> list[Path]:
    return sorted(p for tree in TEST_TREES for p in (ROOT / tree).rglob("test_*.py"))


def test_every_scan_test_module_carries_the_repo_scan_mark():
    """Main's tree: no test module walks the source tree without `repo_scan`."""
    files = _test_files()
    assert len(files) > 100  # the walk found the real trees
    bad = unmarked_scans(files)
    assert bad == [], f"scan tests without @pytest.mark.repo_scan (add `pytestmark = pytest.mark.repo_scan`): {bad}"
    assert all((ROOT / rel).is_file() for rel in NOT_SCANS)  # a stale exemption fails


def test_unmarked_scan_in_scratch_file_is_flagged(tmp_path):
    """Red case: a scratch scan with no mark is reported; the same file with the mark (module or each test) is not."""
    scan = "from pathlib import Path\n\ndef test_x():\n    assert list(Path('.').rglob('*.py'))\n"
    plain = tmp_path / "test_a.py"
    plain.write_text(scan, encoding="utf-8")
    assert unmarked_scans([plain]) == [f"{plain.as_posix()}:4"]
    walker = tmp_path / "test_b.py"
    walker.write_text("import os\n\ndef test_x():\n    assert list(os.walk('.'))\n", encoding="utf-8")
    assert len(unmarked_scans([walker])) == 1
    module_marked = tmp_path / "test_c.py"
    module_marked.write_text("import pytest\npytestmark = [pytest.mark.network, pytest.mark.repo_scan]\n" + scan,
                             encoding="utf-8")
    assert unmarked_scans([module_marked]) == []
    func_marked = tmp_path / "test_d.py"
    func_marked.write_text(scan.replace("def test_x", "@pytest.mark.repo_scan\ndef test_x").replace(
        "from pathlib", "import pytest\nfrom pathlib"), encoding="utf-8")
    assert unmarked_scans([func_marked]) == []
    half = tmp_path / "test_e.py"
    half.write_text("import pytest\nfrom pathlib import Path\n\n@pytest.mark.repo_scan\ndef test_a():\n    "
                    "list(Path('.').glob('*'))\n\ndef test_b():\n    pass\n", encoding="utf-8")
    assert len(unmarked_scans([half])) == 1  # one unmarked test in a scanning module still fails
    other_mark = tmp_path / "test_f.py"
    other_mark.write_text("import pytest\npytestmark = pytest.mark.network\n" + scan, encoding="utf-8")
    assert len(unmarked_scans([other_mark])) == 1
    non_scan = tmp_path / "test_g.py"
    non_scan.write_text("def test_x():\n    assert sorted([1]) == [1]\n", encoding="utf-8")
    assert unmarked_scans([non_scan]) == []
