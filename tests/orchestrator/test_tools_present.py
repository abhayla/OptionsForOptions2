"""The gate's first step names every missing tool, with the exact fix, before anything runs (27 Nov)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "orchestrator"))
import prepush
import tools_present

FOUND = object()
TWO = 2
ONE = 1


def repo_with_pin(tmp_path, pin="ruff==0.15.12"):
    (tmp_path / "requirements-dev.txt").write_text(f"# dev\n{pin}\n", encoding="utf-8")
    return str(tmp_path)


def check(repo, ruff="0.15.12", missing=(), have_node=True, **kw):
    return tools_present.check(
        repo, which=lambda n: "/x/" + n if (have_node or n == "git") else None,
        find_spec=lambda m: None if m in missing else FOUND, ruff_ver=lambda: ruff, **kw)


def test_everything_present_is_an_empty_list(tmp_path):
    assert check(repo_with_pin(tmp_path)) == []


def test_ruff_missing_from_this_python_is_named_with_the_install_command(tmp_path):
    (problem, fix), = check(repo_with_pin(tmp_path), ruff=None)
    assert "ruff" in problem and "python -m ruff" in problem
    assert fix == tools_present.INSTALL_PY


def test_a_ruff_of_another_version_is_a_problem_because_the_baseline_was_counted_with_the_pin(tmp_path):
    (problem, fix), = check(repo_with_pin(tmp_path), ruff="0.16.9")
    assert "0.16.9" in problem and "0.15.12" in problem
    assert fix == "python -m pip install ruff==0.15.12"


def test_each_missing_python_module_is_named(tmp_path):
    problems = check(repo_with_pin(tmp_path), missing=("fastapi", "sqlalchemy"))
    assert [p for p, _ in problems] == ["python module fastapi is missing", "python module sqlalchemy is missing"]


def test_node_modules_is_required_only_when_a_frontend_step_is_planned(tmp_path):
    repo = repo_with_pin(tmp_path)
    assert check(repo, need_frontend=False) == []
    (problem, fix), = check(repo, need_frontend=True)
    assert "node_modules" in problem and fix == "cd frontend && npm ci"
    (tmp_path / "frontend" / "node_modules").mkdir(parents=True)
    assert check(repo, need_frontend=True) == []


def test_missing_node_is_named_when_a_frontend_step_is_planned(tmp_path):
    (problem, _), = check(repo_with_pin(tmp_path), need_frontend=True, have_node=False)
    assert "node/npm" in problem


def test_a_missing_pin_file_still_requires_ruff_to_be_importable(tmp_path):
    assert len(check(str(tmp_path), ruff=None)) == ONE
    assert check(str(tmp_path), ruff="9.9.9") == []


def test_report_lists_every_problem_and_says_nothing_ran(tmp_path):
    text = tools_present.report(check(repo_with_pin(tmp_path), ruff=None, missing=("mypy",)))
    assert text.startswith("TOOLS MISSING (2)") and "nothing was run" in text and text.count("fix:") == TWO


def test_the_gate_stops_with_exit_2_before_any_step_when_a_tool_is_missing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(tools_present, "check", lambda *a, **k: [("ruff is missing", "pip install ruff")])
    monkeypatch.setattr(prepush, "frontend_changes", lambda repo: [])

    def boom(*a, **k):
        raise AssertionError("a step ran although a tool is missing")

    monkeypatch.setattr(prepush, "run_all", boom)
    assert prepush.main(["--repo", str(tmp_path)]) == TWO
    assert "TOOLS MISSING (1)" in capsys.readouterr().out


def test_the_gate_goes_on_when_every_tool_is_present(tmp_path, monkeypatch):
    seen = {}

    def fake_check(repo, need_frontend=False, **k):
        seen["fe"] = need_frontend
        return []

    monkeypatch.setattr(tools_present, "check", fake_check)
    monkeypatch.setattr(prepush, "frontend_changes", lambda repo: ["src/a.js"])
    monkeypatch.setattr(prepush, "run_all", lambda *a, **k: 0)
    assert prepush.main(["--repo", str(tmp_path)]) == 0
    assert seen["fe"] is True
