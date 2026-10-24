"""gate.py (ADR-181 item 1): the step list is pinned, the first failure stops the gate, a dirty tree or a refused push
never runs a step. This file runs inside the gate's own `tests-orchestrator` step, so it never runs a real step: the
runner and the gh reader are injected fakes."""

import json
import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "orchestrator"))
import gate

SHA = "0123456789abcdef0123456789abcdef01234567"
PY = sys.executable
PYTEST = [PY, "-m", "pytest", "-q", "-p", "no:cacheprovider"]
PYTEST_APP = [PY, "-m", "pytest", "-c", "pytest-app.ini", "-q", "-p", "no:cacheprovider"]
SELECTED = "tests_app/test_a.py"
REFUSED = 2
KEY_LEN = 44  # urlsafe base64 of 32 bytes
CHILD_EXIT = 5
NOT_FOUND = 127
DB_VARS = ("DATABASE_URL", "TEST_DATABASE_URL", "TEST_ADMIN_DATABASE_URL", "OFO_REQUIRE_DB_TESTS")
# Written out by hand from the brief's step list (not read back from gate.STEPS).
EXPECTED = [
    ("clean-tree", ("git", "status", "--porcelain")),
    ("ruff-ratchet", (PY, "scripts/ruff_ratchet.py")),
    ("guard-tests", (*PYTEST, "tests/test_*.py")),
    ("money-guard", (*PYTEST, "tests/test_money_outside_engine.py")),
    ("repo-scan", (*PYTEST, "-m", "repo_scan", "tests")),
    ("tests-errors", (*PYTEST, "tests/errors")),
    ("tests-orchestrator", (*PYTEST, "tests/orchestrator")),
    ("app-selected", (PY, "scripts/orchestrator/select_app_tests.py", "<root>")),
    ("openapi-drift", (*PYTEST_APP, "tests_app/test_openapi_drift.py")),
    ("frontend-lint", ("npm", "run", "lint")),
    ("frontend-vitest-changed", ("npx", "vitest", "run", "--changed", "origin/main")),
    ("coverage", (PY, "scripts/orchestrator/coverage.py", ".", "--check")),
    ("reach-check", (PY, "scripts/orchestrator/reach_check.py", "--root", ".")),
    ("reference-register", (PY, "scripts/orchestrator/reference_register.py", "--check")),
    ("findings-index", (PY, "tools/build_findings_index.py", ".", "--check")),
]


class FakeRunner:
    """Answers by the first word of what runs; records every call (argv, cwd, env)."""

    def __init__(self, dirty="", select_out="0 files\n", fail_at=None, fail_code=1, sha=SHA):
        self.calls = []
        self.dirty = dirty
        self.select_out = select_out
        self.fail_at = fail_at
        self.fail_code = fail_code
        self.sha = sha

    def __call__(self, argv, cwd, env, log):
        self.calls.append((list(argv), cwd, dict(env), log))
        text = " ".join(argv)
        if argv[0] == "git":
            log.write_text(self.dirty if argv[1] == "status" else self.sha + "\n", encoding="utf-8")
            return 0
        log.write_text(self.select_out if "select_app_tests" in text else f"output of {log.stem}\n", encoding="utf-8")
        if self.fail_at and log.stem.startswith(self.fail_at):
            return self.fail_code
        return 0

    def ran(self):
        return [c for c in self.calls if c[0][0] != "git"]


@pytest.fixture
def tree(tmp_path):
    (tmp_path / "frontend" / "node_modules").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    for name in ("test_b.py", "test_a.py", "test_money_outside_engine.py", "conftest.py"):
        (tmp_path / "tests" / name).write_text("", encoding="utf-8")
    return tmp_path


def run(tree, runner, argv=(), reader=None):
    lines = []
    root = tree
    code = gate.main(["--root", str(root), *argv], runner=runner, reader=reader or (lambda b: []), out=lines.append)
    return code, lines


def fake_git_dir(monkeypatch, tree):
    answers = {"--absolute-git-dir": str(tree / ".gitdir"), "--show-toplevel": str(tree)}
    monkeypatch.setattr(gate, "git_out", lambda cwd, *a: answers[a[-1]])


def test_step_list_is_pinned():
    """Attack 1: a step removed, reordered or with another argv fails here."""
    assert [(s.name, s.argv) for s in gate.STEPS] == EXPECTED


def test_guard_glob_is_expanded_sorted_and_leaves_out_the_money_guard(tree):
    step = next(s for s in gate.STEPS if s.name == "guard-tests")
    argv = gate.expand(step, tree)
    assert argv[: len(PYTEST)] == PYTEST
    assert argv[len(PYTEST) :] == ["tests/test_a.py", "tests/test_b.py"]


def test_full_pass_prints_gate_pass_last_and_runs_every_step_in_order(tree, monkeypatch):
    fake_git_dir(monkeypatch, tree)
    runner = FakeRunner()
    code, lines = run(tree, runner)
    assert code == 0
    assert lines[-1] == f"GATE PASS {SHA}"
    assert re.fullmatch(r"GATE PASS [0-9a-f]{40}", lines[-1])
    assert sum(1 for ln in lines if ln.startswith("GATE")) == 1
    names = [c[3].stem for c in runner.ran()]
    expected = [n for n, _ in EXPECTED if n != "clean-tree"]
    assert names == expected  # app-selected selected 0 files, so no second app-selected run
    assert any("app-selected:" in ln for ln in lines)


@pytest.mark.parametrize("step", [n for n, _ in EXPECTED if n != "clean-tree"])
def test_first_failure_stops_and_names_the_step(tree, monkeypatch, step):
    """Attack 3: a non-zero exit reaches the gate unmasked; nothing after the failing step runs."""
    fake_git_dir(monkeypatch, tree)
    runner = FakeRunner(fail_at=step, select_out="1 files\n" + SELECTED + "\n", fail_code=7)
    code, lines = run(tree, runner)
    assert code == 1
    assert lines[-1] == f"GATE FAIL {step}: exit 7"
    assert not any(ln.startswith("GATE PASS") for ln in lines)
    ran = [c[3].stem for c in runner.ran()]
    later = [n for n, _ in EXPECTED[[n for n, _ in EXPECTED].index(step) + 1 :]]
    assert not set(later) & set(ran)


def test_failing_log_tail_is_printed_before_the_fail_line(tree, monkeypatch):
    fake_git_dir(monkeypatch, tree)
    code, lines = run(tree, FakeRunner(fail_at="ruff-ratchet"))
    assert code == 1
    assert lines == ["output of ruff-ratchet", "GATE FAIL ruff-ratchet: exit 1"]


def test_select_app_tests_exit_3_fails_app_selected_and_nothing_after_runs(tree, monkeypatch):
    """Attack 2."""
    fake_git_dir(monkeypatch, tree)
    runner = FakeRunner(fail_at="app-selected", fail_code=3)
    code, lines = run(tree, runner)
    assert (code, lines[-1]) == (1, "GATE FAIL app-selected: exit 3")
    assert [c[3].stem for c in runner.ran()][-1] == "app-selected"


@pytest.mark.parametrize(
    "out",
    ["", "garbage\n", "2 files\ntests_app/test_a.py\n", "1 files\nsome/other.py\n", "0 files\ntests_app/test_a.py\n"],
)
def test_unparseable_selection_fails_closed(tree, monkeypatch, out):
    fake_git_dir(monkeypatch, tree)
    code, lines = run(tree, FakeRunner(select_out=out))
    assert (code, lines[-1]) == (1, "GATE FAIL app-selected: exit 1")


def test_selected_files_run_in_the_app_config_without_database_variables(tree, monkeypatch):
    """Attack 6: no database URL reaches the child, CI's throwaway broker settings do."""
    for var in DB_VARS:
        monkeypatch.setenv(var, "postgresql://real/db")
    monkeypatch.delenv("KITE_API_KEY", raising=False)
    monkeypatch.delenv("BROKER_TOKEN_KEY", raising=False)
    fake_git_dir(monkeypatch, tree)
    runner = FakeRunner(select_out=f"1 files\n{SELECTED}\n")
    code, _ = run(tree, runner)
    assert code == 0
    by_log = {c[3].stem: c for c in runner.ran()}
    argv, _, env, _ = by_log["app-selected-tests"]
    assert argv == [*PYTEST_APP, "-rs", SELECTED]
    for step in ("app-selected-tests", "openapi-drift"):
        step_env = by_log[step][2]
        assert not any(v in step_env for v in DB_VARS)
        assert step_env["KITE_API_KEY"] == "ci_placeholder_key"
        assert len(step_env["BROKER_TOKEN_KEY"]) == KEY_LEN
    assert env["BROKER_TOKEN_KEY"] != by_log["openapi-drift"][2]["BROKER_TOKEN_KEY"]


def test_existing_broker_settings_are_kept(tree, monkeypatch):
    monkeypatch.setenv("KITE_API_KEY", "mine")
    fake_git_dir(monkeypatch, tree)
    runner = FakeRunner()
    run(tree, runner)
    assert {c[2]["KITE_API_KEY"] for c in runner.ran() if c[3].stem == "openapi-drift"} == {"mine"}


def test_dirty_tree_is_refused_and_no_step_runs(tree, monkeypatch):
    """Attack 4."""
    fake_git_dir(monkeypatch, tree)
    runner = FakeRunner(dirty="?? new_file.py\n")
    code, lines = run(tree, runner)
    assert code == REFUSED
    assert lines == ["GATE REFUSED: uncommitted changes"]
    assert runner.ran() == []


def test_tree_changed_by_the_steps_is_not_certified(tree, monkeypatch):
    fake_git_dir(monkeypatch, tree)

    class Dirtying(FakeRunner):
        def __call__(self, argv, cwd, env, log):
            if argv[0] == "git" and argv[1] == "status" and self.ran():
                self.dirty = " M file.py\n"
            return super().__call__(argv, cwd, env, log)

    code, lines = run(tree, Dirtying())
    assert code == REFUSED
    assert not any(ln.startswith("GATE PASS") for ln in lines)


def test_unreadable_head_is_refused(tree, monkeypatch):
    fake_git_dir(monkeypatch, tree)
    code, lines = run(tree, FakeRunner(sha="not-a-sha"))
    assert (code, lines) == (REFUSED, ["GATE REFUSED: cannot read the HEAD sha"])


def test_missing_node_modules_fails_not_skips(tree, monkeypatch):
    """Attack 7."""
    (tree / "frontend" / "node_modules").rmdir()
    fake_git_dir(monkeypatch, tree)
    runner = FakeRunner()
    code, lines = run(tree, runner)
    assert (code, lines[-1]) == (1, "GATE FAIL frontend-lint: exit 1")
    assert "run npm ci in frontend/" in lines[-2]
    assert "frontend-vitest-changed" not in [c[3].stem for c in runner.ran()]


def runs(*pairs, start=100):
    """gh rows from (status, conclusion) pairs, newest first."""
    return [
        {"databaseId": start - i, "status": st, "conclusion": co, "headSha": SHA} for i, (st, co) in enumerate(pairs)
    ]


OK = ("completed", "success")
RED = ("completed", "failure")
PUSH_CASES = [
    ("no run yet", [], False, True),
    ("completed success", runs(OK), False, True),
    ("completed failure", runs(RED), False, True),
    ("completed cancelled", runs(("completed", "cancelled")), False, True),
    ("in_progress", runs(("in_progress", None), OK), False, False),
    ("queued", runs(("queued", None), OK), False, False),
    ("waiting", runs(("waiting", None)), False, False),
    ("requested", runs(("requested", None)), False, False),
    ("pending", runs(("pending", None)), False, False),
    ("unknown status", runs(("zzz", None)), False, False),
    ("fixes-red, newest completed success", runs(OK), True, False),
    ("fixes-red, newest completed failure", runs(RED, OK), True, True),
    ("fixes-red, red but a newer success", runs(OK, RED), True, False),
    ("fixes-red, cancelled newest", runs(("completed", "cancelled"), RED), True, False),
    ("fixes-red, no run", [], True, False),
    ("fixes-red, run in progress over a red", runs(("in_progress", None), RED), True, True),
    ("fixes-red, run in progress over a success", runs(("in_progress", None), OK), True, False),
    ("odd shape", [{"status": "completed"}], False, False),
    ("not a dict", ["x"], False, False),
]


@pytest.mark.parametrize(("rows", "fixes_red", "allowed"), [c[1:] for c in PUSH_CASES], ids=[c[0] for c in PUSH_CASES])
def test_pre_push_answers(tree, monkeypatch, rows, fixes_red, allowed):
    """Attack 5 and standing item (d): every gh run state has a tested outcome."""
    fake_git_dir(monkeypatch, tree)
    runner = FakeRunner()
    seen = []
    code, lines = run(
        tree,
        runner,
        ["--pre-push", *(["--fixes-red"] if fixes_red else [])],
        reader=lambda b: seen.append(b) or rows,
    )
    assert seen == [SHA]  # the fake branch name is the fake HEAD answer
    if allowed:
        assert (code, lines[-1]) == (0, f"GATE PASS {SHA}")
    else:
        assert code == REFUSED
        assert lines[-1].startswith("GATE REFUSED push:")
        assert runner.ran() == []


def test_in_progress_message_names_the_run_and_status(tree, monkeypatch):
    fake_git_dir(monkeypatch, tree)
    _, lines = run(tree, FakeRunner(), ["--pre-push"], reader=lambda b: runs(("in_progress", None), start=77))
    assert lines == ["GATE REFUSED push: App tests run 77 is in_progress"]


def test_gh_error_refuses(tree, monkeypatch):
    fake_git_dir(monkeypatch, tree)

    def broken(branch):
        raise RuntimeError("gh exited 1: no auth")

    runner = FakeRunner()
    code, lines = run(tree, runner, ["--pre-push"], reader=broken)
    assert code == REFUSED
    assert lines == ["GATE REFUSED push: cannot read the App tests runs (gh exited 1: no auth)"]
    assert runner.ran() == []


def test_fixes_red_without_pre_push_is_refused(tree, monkeypatch):
    fake_git_dir(monkeypatch, tree)
    runner = FakeRunner()
    code, _ = run(tree, runner, ["--fixes-red"])
    assert code == REFUSED
    assert runner.calls == []


def test_gh_runs_rejects_bad_answers(monkeypatch):
    """The real gh reader: a failing gh, non-JSON and a non-list all raise (so the push is refused)."""

    class Proc:
        def __init__(self, code, out):
            self.returncode, self.stdout, self.stderr = code, out, "err"

    for proc in (Proc(1, "[]"), Proc(0, "not json"), Proc(0, '{"a": 1}')):
        monkeypatch.setattr(gate.subprocess, "run", lambda *a, _p=proc, **k: _p)
        with pytest.raises(RuntimeError):
            gate.gh_runs("main")
    monkeypatch.setattr(gate.subprocess, "run", lambda *a, **k: Proc(0, json.dumps(runs(OK))))
    assert gate.gh_runs("main") == runs(OK)


def test_default_runner_reads_the_exit_code_and_writes_the_log(tmp_path):
    """No shell, no pipe: the child's own exit code comes back, its output lands in the log."""
    log = tmp_path / "x.log"
    child = f"print('hello'); raise SystemExit({CHILD_EXIT})"
    code = gate.default_runner([PY, "-c", child], tmp_path, dict(os.environ), log)
    assert code == CHILD_EXIT
    assert log.read_text(encoding="utf-8").strip() == "hello"


def test_default_runner_missing_tool_fails_closed(tmp_path):
    log = tmp_path / "x.log"
    assert gate.default_runner(["no-such-tool-xyz"], tmp_path, {"PATH": ""}, log) == NOT_FOUND
    assert "cannot find" in log.read_text(encoding="utf-8")
