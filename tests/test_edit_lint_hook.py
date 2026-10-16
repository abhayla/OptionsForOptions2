"""edit_lint PostToolUse hook (REQ-075 AC-8): routing, fail-open, output shape, truncation, one real ruff run."""
import io
import json
import pathlib
import shutil
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "hooks"))
import edit_lint  # noqa: E402

BAD_PY = "import os\nfrom datetime import datetime\nx = datetime.now()\ntry:\n    pass\nexcept Exception:\n    pass\n"


def _fake_repo(base):
    """A temp checkout of 'this repo': own .git plus the hook-script marker."""
    (base / ".git").mkdir(exist_ok=True)
    marker = base / edit_lint.REPO_MARKER
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("")
    return base


def test_command_for_python_uses_ruff_rules(monkeypatch):
    monkeypatch.setattr(edit_lint, "ruff_argv", lambda: ["ruff-bin"])
    cmd = edit_lint.command_for(ROOT / "backend" / "ofo" / "x.py", ROOT)
    assert cmd is not None and cmd[0] == "ruff-bin" and "-m" not in cmd
    assert edit_lint.RUFF_RULES in cmd


def test_command_for_alembic_versions_is_none():
    assert edit_lint.command_for(ROOT / "backend" / "ofo_app" / "alembic" / "versions" / "001_x.py", ROOT) is None


def test_command_for_outside_repo_and_docs_is_none(tmp_path):
    assert edit_lint.command_for(tmp_path / "x.py", ROOT) is None
    assert edit_lint.command_for(ROOT / "docs" / "a.md", ROOT) is None


def test_command_for_vue_needs_eslint(tmp_path):
    root = _fake_repo(tmp_path)
    (root / "frontend" / "src").mkdir(parents=True)
    vue = root / "frontend" / "src" / "A.vue"
    assert edit_lint.command_for(vue, root) is None  # eslint not installed
    eslint = root / "frontend" / "node_modules" / "eslint" / "bin" / "eslint.js"
    eslint.parent.mkdir(parents=True)
    eslint.write_text("")
    cmd = edit_lint.command_for(vue, root)
    assert cmd is not None and cmd[0] == "node" and str(eslint) in cmd


def test_lint_fails_open_on_missing_tool(monkeypatch, tmp_path):
    f = tmp_path / "a.py"
    f.write_text(BAD_PY)

    def boom(*a, **k):
        raise OSError("no tool")

    monkeypatch.setattr(edit_lint, "command_for", lambda p, r: ["nonexistent-tool"])
    monkeypatch.setattr(subprocess, "Popen", boom)
    assert edit_lint.lint(f, tmp_path) == ""


def _run_main(monkeypatch, capsys, payload):
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    monkeypatch.setattr(sys, "stdin", type("S", (), {"buffer": io.BytesIO(raw.encode())})())
    edit_lint.main()
    return capsys.readouterr().out


def test_main_prints_context_when_findings(monkeypatch, capsys):
    monkeypatch.setattr(edit_lint, "lint", lambda p, r: "a.py:1:1: F401 unused")
    out = _run_main(monkeypatch, capsys, {"tool_input": {"file_path": str(ROOT / "backend" / "a.py")}})
    spec = json.loads(out)["hookSpecificOutput"]
    assert spec["hookEventName"] == "PostToolUse"
    assert "F401" in spec["additionalContext"]


def test_main_silent_when_clean_or_bad_input(monkeypatch, capsys):
    monkeypatch.setattr(edit_lint, "lint", lambda p, r: "")
    assert _run_main(monkeypatch, capsys, {"tool_input": {"file_path": str(ROOT / "backend" / "a.py")}}) == ""
    assert _run_main(monkeypatch, capsys, "{not json") == ""
    assert _run_main(monkeypatch, capsys, {"tool_input": {}}) == ""


def test_truncation_to_20_lines(monkeypatch, tmp_path):
    f = tmp_path / "a.py"
    f.write_text("x")
    out = "\n".join(f"a.py:{i}:1: F401 x" for i in range(25))
    monkeypatch.setattr(edit_lint, "command_for", lambda p, r: ["tool"])
    monkeypatch.setattr(edit_lint, "_run", lambda cmd, cwd: (1, out))
    lines = edit_lint.lint(f, tmp_path).splitlines()
    assert len(lines) == edit_lint.MAX_LINES + 1 and lines[-1] == "... 5 more"


def test_real_ruff_run_names_rules():
    if subprocess.run([sys.executable, "-m", "ruff", "--version"], capture_output=True, check=False).returncode != 0:
        pytest.skip("ruff not installed")
    d = ROOT / "backend" / "_edit_lint_tmp"
    d.mkdir(exist_ok=True)
    try:
        f = d / "sample.py"
        f.write_text(BAD_PY)
        found = edit_lint.lint(f, ROOT)
        for code in ("F401", "DTZ005", "BLE001"):
            assert code in found
        f.write_text("x = 1\n")
        assert edit_lint.lint(f, ROOT) == ""
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_real_eslint_run_flags_unused_variable():
    eslint = ROOT / "frontend" / "node_modules" / "eslint" / "bin" / "eslint.js"
    if not eslint.is_file():
        pytest.skip("frontend/node_modules absent")
    d = ROOT / "frontend" / "src" / "_edit_lint_tmp"
    d.mkdir(exist_ok=True)
    try:
        f = d / "A.vue"
        f.write_text("<script setup>\nconst unused = 1\n</script>\n<template><div /></template>\n")
        assert edit_lint.lint(f, ROOT) != ""
    finally:
        shutil.rmtree(d, ignore_errors=True)


# --- issue 294: bounded run, visible "unavailable" line, this-repo-only ---------------------------------------------

def test_timeout_kills_the_linter_process(monkeypatch, tmp_path):
    """A hung ruff is killed at TIMEOUT_S and reaped (no wall-clock assert: the child's state is checked)."""
    root = _fake_repo(tmp_path)
    f = root / "a.py"
    f.write_text("x = 1\n")
    started = []
    real_popen = subprocess.Popen

    def recording_popen(*a, **k):
        p = real_popen(*a, **k)
        started.append(p)
        return p

    monkeypatch.setattr(edit_lint, "ruff_argv", lambda: [sys.executable, "-c", "import time; time.sleep(30)", "--"])
    monkeypatch.setattr(edit_lint.subprocess, "Popen", recording_popen)
    monkeypatch.setattr(edit_lint, "TIMEOUT_S", 1)
    assert edit_lint.lint(f, root) == ""
    assert len(started) == 1 and started[0].poll() is not None  # killed and reaped, not left running


def test_timeout_with_grandchild_holding_output_still_returns(monkeypatch, tmp_path):
    """The Windows failure: the killed process's child kept the pipe open. Output goes to a file, so it cannot."""
    root = _fake_repo(tmp_path)
    f = root / "a.py"
    f.write_text("x = 1\n")
    code = ("import subprocess, sys, time;"
            "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(8)']);"
            "time.sleep(30)")
    monkeypatch.setattr(edit_lint, "ruff_argv", lambda: [sys.executable, "-c", code, "--"])
    monkeypatch.setattr(edit_lint, "TIMEOUT_S", 1)
    assert edit_lint.lint(f, root) == ""


def test_ruff_argv_is_a_binary_not_python_dash_m():
    argv = edit_lint.ruff_argv()
    if argv is None:
        pytest.skip("ruff not installed")
    assert pathlib.Path(argv[0]).is_file() and pathlib.Path(argv[0]).stem.lower() == "ruff"


def test_main_prints_one_unavailable_line_when_ruff_missing(monkeypatch, capsys, tmp_path):
    root = _fake_repo(tmp_path)
    f = root / "a.py"
    f.write_text("x = 1\n")
    monkeypatch.setattr(edit_lint, "ruff_argv", lambda: None)
    out = _run_main(monkeypatch, capsys, {"tool_input": {"file_path": str(f)}})
    assert len(out.strip().splitlines()) == 1
    ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
    assert "linter unavailable (ruff is not installed)" in ctx


def test_main_prints_one_unavailable_line_when_eslint_missing(monkeypatch, capsys, tmp_path):
    root = _fake_repo(tmp_path)
    vue = root / "frontend" / "src" / "A.vue"
    vue.parent.mkdir(parents=True)
    vue.write_text("<template><div /></template>\n")
    out = _run_main(monkeypatch, capsys, {"tool_input": {"file_path": str(vue)}})
    assert len(out.strip().splitlines()) == 1
    assert "linter unavailable (ESLint is not installed" in json.loads(out)["hookSpecificOutput"]["additionalContext"]


def test_main_exits_zero_path_unlintable_file_is_silent(monkeypatch, capsys, tmp_path):
    root = _fake_repo(tmp_path)
    md = root / "docs" / "a.md"
    md.parent.mkdir()
    md.write_text("x")
    assert _run_main(monkeypatch, capsys, {"tool_input": {"file_path": str(md)}}) == ""


def test_foreign_repo_file_is_not_linted(monkeypatch, capsys, tmp_path):
    """A .py in another checkout (own .git, no marker) is skipped even if ruff would flag it."""
    (tmp_path / ".git").mkdir()
    f = tmp_path / "bad.py"
    f.write_text(BAD_PY)
    called = []
    monkeypatch.setattr(edit_lint, "_run", lambda cmd, cwd: called.append(cmd) or (1, "bad.py:1:1: F401 x"))
    assert edit_lint.command_for(f, tmp_path) is None
    assert edit_lint.lint(f, tmp_path) == ""
    assert _run_main(monkeypatch, capsys, {"tool_input": {"file_path": str(f)}}) == ""
    assert called == []
