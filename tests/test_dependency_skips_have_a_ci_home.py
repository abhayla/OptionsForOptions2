"""Finding test-skipped-in-its-only-ci-job: a test file that calls ``pytest.importorskip`` skips itself wherever the
dependency is missing. The kit's CI job installs only pyyaml, jsonschema and pytest, so such a file must be named in a
step of the project's ``app-tests.yml`` (which installs requirements-app.txt), else it runs nowhere.

The files are found by AST (a comment or string mentioning importorskip does not count). A workflow that cannot be
read fails the test; it never passes by default."""
import ast
import pathlib

import pytest

pytestmark = pytest.mark.repo_scan

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "app-tests.yml"
TESTS = ROOT / "tests"


def _calls_importorskip(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
            if name == "importorskip":
                return True
    return False


def importorskip_files(tests_dir: pathlib.Path = TESTS) -> list[str]:
    """Repo-relative posix paths of every file under tests/ that calls importorskip (unparseable file: raises)."""
    return [path.relative_to(tests_dir.parent).as_posix() for path in sorted(tests_dir.rglob("*.py"))
            if _calls_importorskip(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))]


def unhomed(workflow: pathlib.Path, tests_dir: pathlib.Path = TESTS) -> list[str]:
    text = workflow.read_text(encoding="utf-8")  # unreadable workflow -> exception -> test fails (fail closed)
    return [f for f in importorskip_files(tests_dir) if f not in text]


def test_every_importorskip_file_is_named_in_an_app_tests_step():
    assert importorskip_files(), "the scan found no importorskip file at all: the detector is broken"
    assert unhomed(WORKFLOW) == []


def test_the_scan_goes_red_when_the_step_is_removed(tmp_path):
    stripped = tmp_path / "app-tests.yml"
    stripped.write_text(WORKFLOW.read_text(encoding="utf-8").replace("test_db_run_fresh.py", "x"), encoding="utf-8")
    assert unhomed(stripped) == ["tests/orchestrator/test_db_run_fresh.py"]


def test_an_unreadable_workflow_fails_closed(tmp_path):
    with pytest.raises(OSError):
        unhomed(tmp_path / "missing.yml")


def test_a_comment_mentioning_importorskip_is_not_a_call(tmp_path):
    (tmp_path / "test_a.py").write_text("# pytest.importorskip('x')\nx = 'importorskip('\n", encoding="utf-8")
    (tmp_path / "test_b.py").write_text("import pytest\npytest.importorskip('x')\n", encoding="utf-8")
    assert [pathlib.PurePath(p).name for p in importorskip_files(tmp_path)] == ["test_b.py"]
