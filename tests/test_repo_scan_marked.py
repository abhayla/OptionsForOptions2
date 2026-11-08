"""Finding repo-wide-scan-outside-targeted-tests: every test module that walks the source tree carries `repo_scan`.

`python -m pytest -q -p no:cacheprovider -m repo_scan tests` then runs every repo-wide scan in one fast command.
A module counts as a scan when its code calls one of the tree-walking shapes in SCAN_CALLS (an allow-list taken
from the scans found on main: `.rglob`, `.glob`, `.iterdir`, `os.walk`). It is marked when it sets
`pytestmark = pytest.mark.repo_scan` (alone or in a list), or every `test_*` function and every method of a `Test*`
class carries the mark (own decorator, or a class-level pytestmark/decorator).

BLIND SPOTS of the shape detection (these are covered ONLY by the named list NAMED_SCANS below, the first layer):
a scan through `inspect.getsource` over modules other than the one under test; `ast.parse` on a file list built by a
helper in another module; paths joined with '/' over a fixed list; schema-wide queries (`information_schema`, which
reads the database, not files). A new scan of those kinds must be added to NAMED_SCANS by hand.
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
    "tests/test_adjust_scenarios.py":
        "globs tests/fixtures/adjust_scenarios only to list the ADJ-*.json scenario files; reads no source module",
    "tests/adjustment/test_whole_trade.py":
        "globs tests/fixtures/adjust_scenarios only to list the ADJ-*.json scenario files; reads no source module",
}

# First layer: scans that MUST carry the mark, by node id (file::test). The first three are the finding's occurrences.
NAMED_SCANS = (
    "tests/errors/test_producer_inventory.py::test_every_producer_in_scope_is_routed_through_render",
    "tests/engine/test_pricing_scan.py::test_no_product_module_reaches_a_pricing_function",
    "tests_app/test_broker_instruments.py::test_ac3_no_table_but_broker_instruments_has_a_zerodha_id_column",
    "tests/test_no_wall_clock_asserts.py::test_guard_no_test_compares_elapsed_wall_clock_time_to_a_number",
    "tests/test_fixture_symbols.py::test_every_tradingsymbol_literal_in_tests_resolves_in_the_catalogue",
)


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


def _pytestmark_has_mark(body: list[ast.stmt]) -> bool:
    for node in body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets):
            value = node.value
            items = value.elts if isinstance(value, (ast.List, ast.Tuple)) else [value]
            if any(_is_mark(i) for i in items):
                return True
    return False


def _test_items(tree: ast.Module) -> dict[str, bool]:
    """`name` / `Class::name` -> carries the mark (own, class-level or module-level)."""
    funcs = (ast.FunctionDef, ast.AsyncFunctionDef)
    module_marked = _pytestmark_has_mark(tree.body)
    out: dict[str, bool] = {}
    for node in tree.body:
        if isinstance(node, funcs) and node.name.startswith("test_"):
            out[node.name] = module_marked or any(_is_mark(d) for d in node.decorator_list)
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            class_marked = (module_marked or _pytestmark_has_mark(node.body)
                            or any(_is_mark(d) for d in node.decorator_list))
            for item in node.body:
                if isinstance(item, funcs) and item.name.startswith("test_"):
                    out[f"{node.name}::{item.name}"] = class_marked or any(_is_mark(d) for d in item.decorator_list)
    return out


def module_is_marked(tree: ast.Module) -> bool:
    """Every test function and every method of a `Test*` class carries repo_scan."""
    items = _test_items(tree)
    return bool(items) and all(items.values())


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


def missing_named_scans(root: Path, names: tuple[str, ...]) -> list[str]:
    """Node ids in `names` whose test is absent from its file or lacks the mark."""
    bad = []
    for node_id in names:
        rel, _, name = node_id.partition("::")
        path = root / rel
        items = _test_items(ast.parse(path.read_text(encoding="utf-8"))) if path.is_file() else {}
        if not items.get(name, False):
            bad.append(node_id)
    return bad


def test_named_scans_exist_and_carry_the_mark():
    """First layer: each named scan (incl. the DB-backed broker-identifier column rule) is present and marked."""
    assert missing_named_scans(ROOT, NAMED_SCANS) == []


def test_named_scan_check_flags_unmarked_missing_and_class_methods(tmp_path):
    """Red cases: unmarked, absent and wrong-file ids are reported; class-level and per-method marks count."""
    lines = [
        "import pytest", "",
        "@pytest.mark.repo_scan", "def test_a():", "    pass", "",
        "def test_b():", "    pass", "",
        "class TestC:", "    pytestmark = pytest.mark.repo_scan", "", "    def test_d(self):", "        pass", "",
        "class TestE:", "    @pytest.mark.repo_scan", "    def test_f(self):", "        pass", "",
        "    def test_g(self):", "        pass", "",
    ]
    (tmp_path / "t.py").write_text(chr(10).join(lines), encoding="utf-8")
    ids = ("t.py::test_a", "t.py::test_b", "t.py::test_missing", "nofile.py::test_a", "t.py::TestC::test_d",
           "t.py::TestE::test_f", "t.py::TestE::test_g")
    assert missing_named_scans(tmp_path, ids) == ["t.py::test_b", "t.py::test_missing", "nofile.py::test_a",
                                                  "t.py::TestE::test_g"]
