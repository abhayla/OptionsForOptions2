"""gate.py (ADR-181 item 1): the step list is pinned, the first failure stops the gate, a dirty tree or a refused push
never runs a step. This file runs inside the gate's own `tests-orchestrator` step, so it never runs a real step: the
runner and the gh reader are injected fakes."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "orchestrator"))
import gate

SHA = "0123456789abcdef0123456789abcdef01234567"
PY = sys.executable
NO_HYPOTHESIS = ["-p", "no:hypothesispytest"]  # finding local-pytest-plugin-not-in-ci, written out by hand
PYTEST = [PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", *NO_HYPOTHESIS]
PYTEST_APP = [PY, "-m", "pytest", "-c", "pytest-app.ini", "-q", "-p", "no:cacheprovider", *NO_HYPOTHESIS]
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
    ("frontend-format", ("npx", "prettier", "--check")),
    ("frontend-vitest-changed", ("npx", "vitest", "run", "--changed", "origin/main")),
    ("coverage", (PY, "scripts/orchestrator/coverage.py", ".", "--check")),
    ("reach-check", (PY, "scripts/orchestrator/reach_check.py", "--root", ".")),
    ("reference-register", (PY, "scripts/orchestrator/reference_register.py", "--check")),
    ("findings-index", (PY, "tools/build_findings_index.py", ".", "--check")),
    # argv copied from .github/workflows/ci.yml (kit spec checks) and app-tests.yml (frontend build)
    ("kit-settings", (PY, "tools/kit_settings.py", ".", "--check")),
    ("factory-lint", (PY, "tools/factory_lint.py", ".")),
    ("trace-check", (PY, "tools/trace_check.py", ".")),
    ("build-order", (PY, "tools/build_order.py", ".", "--check")),
    ("spec-index", (PY, "tools/build_spec_index.py", ".", "--check")),
    ("spec-digest", (PY, "tools/build_spec_digest.py", ".", "--check")),
    ("spec-dupes", (PY, "tools/spec_dupes.py", ".")),
    ("spec-refs", (PY, "tools/check_spec_refs.py", ".")),
    ("domain-tests", tuple(PYTEST)),
    ("frontend-build", ("npm", "run", "build")),
]
NEW_STEPS = [n for n, _ in EXPECTED[16:]]
# One changed file each: a frontend source (format + build), a domain package with tests, one without, a loose file.
CHANGED_ALL = "frontend/src/a.vue\nbackend/ofo/engine/x.py\nbackend/ofo/nopkg/y.py\nbackend/ofo/loose.py\n"


class FakeRunner:
    """Answers by the first word of what runs; records every call (argv, cwd, env)."""

    def __init__(self, dirty="", select_out="0 files\n", fail_at=None, fail_code=1, changed=""):
        self.calls = []
        self.dirty = dirty
        self.select_out = select_out
        self.fail_at = fail_at
        self.fail_code = fail_code
        self.sha = SHA
        self.changed = changed

    def __call__(self, argv, cwd, env, log):
        self.calls.append((list(argv), cwd, dict(env), log))
        text = " ".join(argv)
        if argv[0] == "git":
            texts = {"status": self.dirty, "diff": self.changed}
            log.write_text(texts.get(argv[1], self.sha + "\n"), encoding="utf-8")
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
    (tmp_path / "tests" / "engine").mkdir(parents=True)
    (tmp_path / "frontend" / "src").mkdir()
    (tmp_path / "frontend" / "src" / "a.vue").write_text("", encoding="utf-8")
    for name in ("test_b.py", "test_a.py", "test_money_outside_engine.py", "conftest.py"):
        (tmp_path / "tests" / name).write_text("", encoding="utf-8")
    return tmp_path


def run(tree, runner, argv=(), reader=None, pr_reader=None):
    lines = []
    root = tree
    code = gate.main(["--root", str(root), *argv], runner=runner, reader=reader or (lambda b: []), out=lines.append,
                     pr_reader=pr_reader or (lambda b: None))
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
    # nothing changed: no prettier run, no domain package, no frontend build
    skipped = ("clean-tree", "frontend-format", "domain-tests", "frontend-build")
    expected = [n for n, _ in EXPECTED if n not in skipped]
    assert names == expected  # app-selected selected 0 files, so no second app-selected run
    assert any("app-selected:" in ln for ln in lines)


@pytest.mark.parametrize("step", [n for n, _ in EXPECTED if n != "clean-tree"])
def test_first_failure_stops_and_names_the_step(tree, monkeypatch, step):
    """Attack 3: a non-zero exit reaches the gate unmasked; nothing after the failing step runs."""
    fake_git_dir(monkeypatch, tree)
    picked = "1 files\n" + SELECTED + "\n"
    runner = FakeRunner(fail_at=step, select_out=picked, fail_code=7, changed=CHANGED_ALL)
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
    bad = FakeRunner()
    bad.sha = "not-a-sha"
    code, lines = run(tree, bad)
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
    ("fixes-red, run in progress newer than the red", runs(("in_progress", None), RED), True, False),
    ("fixes-red, run queued newer than the red", runs(("queued", None), RED), True, False),
    ("fixes-red, run waiting newer than the red", runs(("waiting", None), RED), True, False),
    ("fixes-red, run in progress over a success", runs(("in_progress", None), OK), True, False),
    ("fixes-red, run in progress OLDER than the red", [*runs(RED), *runs(("in_progress", None), start=50)], True, True),
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


def test_format_checks_only_changed_files_under_src(tree, monkeypatch):
    """The format step runs prettier on the changed src files of the right extensions, from frontend/."""
    for name in ("b.js", "c.txt"):
        (tree / "frontend" / "src" / name).write_text("", encoding="utf-8")
    changed = "frontend/src/a.vue\nfrontend/src/b.js\nfrontend/src/c.txt\nfrontend/src/gone.js\nfrontend/e2e/x.js\n"
    fake_git_dir(monkeypatch, tree)
    runner = FakeRunner(changed=changed)
    code, _ = run(tree, runner)
    assert code == 0
    calls = [c for c in runner.ran() if c[3].stem == "frontend-format"]
    want = ["npx", "prettier", "--check", "src/a.vue", "src/b.js"]
    assert [(c[0], c[1]) for c in calls] == [(want, tree / "frontend")]


def test_format_with_no_changed_files_passes_with_zero_files(tree, monkeypatch):
    fake_git_dir(monkeypatch, tree)
    runner = FakeRunner(changed="docs/x.md\n")
    code, _ = run(tree, runner)
    assert code == 0
    assert not [c for c in runner.ran() if c[3].stem == "frontend-format"]
    assert gate_log(tree, "frontend-format") == "0 files"


def gate_log(tree, name):
    return (tree / ".gitdir" / "ofo-gate" / f"{name}.log").read_text(encoding="utf-8").strip()


def test_format_failure_fails_the_gate(tree, monkeypatch):
    fake_git_dir(monkeypatch, tree)
    code, lines = run(tree, FakeRunner(changed="frontend/src/a.vue\n", fail_at="frontend-format"))
    assert (code, lines[-1]) == (1, "GATE FAIL frontend-format: exit 1")


class Committing(FakeRunner):
    """A step that commits: HEAD read after the steps differs from HEAD read before them."""

    def __call__(self, argv, cwd, env, log):
        if argv[0] == "git" and argv[1] == "rev-parse" and self.ran():
            self.sha = "f" * 40
        return super().__call__(argv, cwd, env, log)


def test_a_step_that_moves_head_is_not_certified(tree, monkeypatch):
    """Attack 3 (mutant G2, the HEAD compare removed): a PASS line names the sha the steps ran on, never another."""
    fake_git_dir(monkeypatch, tree)
    code, lines = run(tree, Committing())
    assert code == REFUSED
    assert lines == ["GATE REFUSED: the steps changed the tree or HEAD, so no sha is certified"]
    assert not any(ln.startswith("GATE PASS") for ln in lines)


def test_unreadable_head_after_the_steps_is_not_certified(tree, monkeypatch):
    fake_git_dir(monkeypatch, tree)

    class Broken(FakeRunner):
        def __call__(self, argv, cwd, env, log):
            if argv[0] == "git" and argv[1] == "rev-parse" and self.ran():
                self.sha = "garbage"
            return super().__call__(argv, cwd, env, log)

    code, lines = run(tree, Broken())
    assert code == REFUSED and not any(ln.startswith("GATE PASS") for ln in lines)


def test_fixes_red_message_names_the_newer_run_and_the_red_one(tree, monkeypatch):
    """Attack 4: the push would cancel the newer run, and the refusal says which."""
    fake_git_dir(monkeypatch, tree)
    rows = [*runs(("in_progress", None), start=120), *runs(RED, start=100)]
    runner = FakeRunner()
    code, lines = run(tree, runner, ["--pre-push", "--fixes-red"], reader=lambda b: rows)
    assert code == REFUSED and runner.ran() == []
    assert lines == ["GATE REFUSED push: --fixes-red but App tests run 120 is in_progress, newer than the red run "
                     "100: this push would cancel it"]


@pytest.mark.parametrize("step", NEW_STEPS)
def test_dropping_a_new_ci_step_from_the_tuple_is_caught(tree, monkeypatch, step):
    """Attack 5: with the step gone from STEPS the gate neither runs it nor matches the pinned list."""
    fake_git_dir(monkeypatch, tree)
    monkeypatch.setattr(gate, "STEPS", tuple(s for s in gate.STEPS if s.name != step))
    assert [(s.name, s.argv) for s in gate.STEPS] != EXPECTED
    runner = FakeRunner(changed=CHANGED_ALL)
    code, _ = run(tree, runner)
    assert code == 0
    assert step not in [c[3].stem for c in runner.ran()]


@pytest.mark.parametrize("step", NEW_STEPS)
def test_each_new_ci_step_runs_in_a_full_pass_with_its_ci_argv(tree, monkeypatch, step):
    fake_git_dir(monkeypatch, tree)
    runner = FakeRunner(changed=CHANGED_ALL)
    code, _ = run(tree, runner)
    assert code == 0
    by_name = {c[3].stem: c for c in runner.ran()}
    want = dict(EXPECTED)[step]
    if step == "domain-tests":
        want = (*PYTEST, "tests/engine")
    assert tuple(by_name[step][0]) == tuple(want)


def test_domain_tests_pick_only_packages_with_a_changed_file_and_a_tests_folder(tree, monkeypatch):
    fake_git_dir(monkeypatch, tree)
    (tree / "tests" / "orders").mkdir()
    runner = FakeRunner(changed="backend/ofo/orders/a.py\nbackend/ofo/engine/b.py\nbackend/ofo/engine/c/d.py\n"
                                "backend/ofo/nopkg/y.py\nbackend/ofo/loose.py\nbackend/ofo_app/z.py\n")
    code, _ = run(tree, runner)
    assert code == 0
    [call] = [c for c in runner.ran() if c[3].stem == "domain-tests"]
    assert call[0] == [*PYTEST, "tests/engine", "tests/orders"]


def test_domain_tests_with_no_changed_package_pass_with_zero_packages(tree, monkeypatch):
    fake_git_dir(monkeypatch, tree)
    runner = FakeRunner(changed="docs/x.md\nbackend/ofo/loose.py\n")
    code, _ = run(tree, runner)
    assert code == 0
    assert not [c for c in runner.ran() if c[3].stem == "domain-tests"]
    assert gate_log(tree, "domain-tests") == "0 packages"


def test_frontend_build_runs_in_frontend_when_any_file_there_changed(tree, monkeypatch):
    fake_git_dir(monkeypatch, tree)
    runner = FakeRunner(changed="frontend/package.json\n")
    code, _ = run(tree, runner)
    assert code == 0
    [call] = [c for c in runner.ran() if c[3].stem == "frontend-build"]
    assert (call[0], call[1]) == (["npm", "run", "build"], tree / "frontend")


def test_frontend_build_is_skipped_with_zero_files_when_nothing_there_changed(tree, monkeypatch):
    fake_git_dir(monkeypatch, tree)
    runner = FakeRunner(changed="backend/ofo/engine/b.py\n")
    code, _ = run(tree, runner)
    assert code == 0
    assert "frontend-build" not in [c[3].stem for c in runner.ran()]
    assert gate_log(tree, "frontend-build") == "0 files"


@pytest.mark.parametrize("name", ["domain-tests", "frontend-build"])
def test_a_failing_git_diff_fails_the_conditional_step_closed(tree, name):
    """Standing item (c): when the changed-file list cannot be read, the step fails; it never counts as 'no change'."""

    def broken(argv, cwd, env, log):
        log.write_text("fatal: bad revision 'origin/main...HEAD'\n", encoding="utf-8")
        return 128

    step = next(s for s in gate.STEPS if s.name == name)
    log_dir = tree / "logs"
    log_dir.mkdir()
    assert gate.run_step(step, tree, broken, log_dir) == (128, f"{name}-files.log")


def test_frontend_build_without_node_modules_fails_when_a_frontend_file_changed(tree):
    (tree / "frontend" / "node_modules").rmdir()
    runner = FakeRunner(changed="frontend/src/a.vue\n")
    step = next(s for s in gate.STEPS if s.name == "frontend-build")
    log_dir = tree / "logs"
    log_dir.mkdir()
    assert gate.run_step(step, tree, runner, log_dir) == (1, None)
    assert "run npm ci" in (log_dir / "frontend-build.log").read_text(encoding="utf-8")


CLOSE_CMD = [PY, "scripts/orchestrator/pr_close_check.py", "--pr", "7"]


def test_pre_push_runs_pr_close_check_for_the_open_pr_before_any_step(tree, monkeypatch):
    fake_git_dir(monkeypatch, tree)
    runner = FakeRunner()
    code, lines = run(tree, runner, ["--pre-push"], pr_reader=lambda b: 7)
    assert (code, lines[-1]) == (0, f"GATE PASS {SHA}")
    assert runner.ran()[0][0] == CLOSE_CMD


def test_pr_close_check_failure_fails_the_gate_and_no_step_runs(tree, monkeypatch):
    fake_git_dir(monkeypatch, tree)
    runner = FakeRunner(fail_at="pr-close-check")
    code, lines = run(tree, runner, ["--pre-push"], pr_reader=lambda b: 7)
    assert (code, lines[-1]) == (1, "GATE FAIL pr-close-check: exit 1")
    assert [c[0] for c in runner.ran()] == [CLOSE_CMD]


def test_no_open_pr_skips_pr_close_check_with_a_printed_line(tree, monkeypatch):
    fake_git_dir(monkeypatch, tree)
    runner = FakeRunner()
    code, lines = run(tree, runner, ["--pre-push"], pr_reader=lambda b: None)
    assert code == 0 and f"pr-close-check: skipped, {SHA} has no open PR" in lines
    assert CLOSE_CMD not in [c[0] for c in runner.ran()]


def test_gh_error_reading_the_pr_refuses_and_no_step_runs(tree, monkeypatch):
    fake_git_dir(monkeypatch, tree)

    def broken(branch):
        raise RuntimeError("gh exited 4: no auth")

    runner = FakeRunner()
    code, lines = run(tree, runner, ["--pre-push"], pr_reader=broken)
    assert code == REFUSED and runner.ran() == []
    assert lines == [f"GATE REFUSED push: cannot read the PR of {SHA} (gh exited 4: no auth)"]


def test_without_pre_push_the_pr_is_never_read(tree, monkeypatch):
    fake_git_dir(monkeypatch, tree)

    def boom(branch):
        raise AssertionError("pr_reader called without --pre-push")

    assert run(tree, FakeRunner(), pr_reader=boom)[0] == 0


class Proc:
    def __init__(self, code, out="", err=""):
        self.returncode, self.stdout, self.stderr = code, out, err


@pytest.mark.parametrize(
    ("proc", "expected"),
    [
        (Proc(0, '{"number": 12}'), 12),
        (Proc(1, "", 'no pull requests found for branch "x"'), None),
        (Proc(1, "", "HTTP 401: bad credentials"), RuntimeError),
        (Proc(0, "not json"), RuntimeError),
        (Proc(0, "{}"), RuntimeError),
        (Proc(0, "[1]"), RuntimeError),
        (Proc(0, '{"number": "12"}'), RuntimeError),
        (Proc(0, '{"number": 0}'), RuntimeError),
        (Proc(0, '{"number": true}'), RuntimeError),
        (OSError("no gh"), RuntimeError),
        (subprocess.TimeoutExpired("gh", 60), RuntimeError),
    ],
    ids=["open", "no-pr", "gh-error", "bad-json", "no-number", "list", "str-number", "zero", "bool", "no-gh",
         "timeout"],
)
def test_gh_pr_number_every_answer_state(monkeypatch, proc, expected):
    """Standing item (d): PR open, no PR, gh error, bad JSON and the odd shapes each have one outcome."""

    def fake(*a, **k):
        if isinstance(proc, BaseException):
            raise proc
        return proc

    monkeypatch.setattr(gate.subprocess, "run", fake)
    if expected is RuntimeError:
        with pytest.raises(RuntimeError):
            gate.gh_pr_number("b")
    else:
        assert gate.gh_pr_number("b") == expected


def test_every_pytest_step_turns_the_local_only_hypothesis_plugin_off():
    """Attack 2: a pytest step without `-p no:hypothesispytest` fails here, so the local gate loads what CI loads."""
    pytest_steps = [s for s in gate.STEPS if "pytest" in s.argv]
    assert [s.name for s in pytest_steps] == [n for n, argv in EXPECTED if "pytest" in argv]
    assert len(pytest_steps) == 7  # guard, money, repo-scan, errors, orchestrator, openapi-drift, domain
    for step in pytest_steps:
        argv = list(step.argv)
        assert any(argv[i : i + 2] == NO_HYPOTHESIS for i in range(len(argv))), step.name


def test_the_app_selected_run_also_turns_the_plugin_off():
    assert [*PYTEST_APP, "-rs"] == gate.APP_SELECTED_RUN
    assert gate.APP_SELECTED_RUN[-3:-1] == NO_HYPOTHESIS


BAD, GOOD = "BAD <div></div>", "good"


class FormatRunner(FakeRunner):
    """git answers for the format ratchet and a fake prettier: exit 1 when a file starts with BAD, else `prettier_code`.
    Exit codes to force: prettier_code, show_code (git show of the base file), head_show_code, merge_base_code."""

    def __init__(self, names, added=(), base=None, **codes):
        super().__init__()
        self.names, self.added, self.base = names, set(added), base or {}
        self.prettier_code = codes.get("prettier_code")
        self.show_code, self.merge_base_code = codes.get("show_code", 0), codes.get("merge_base_code", 0)
        self.head_show_code = codes.get("head_show_code", 0)
        self.prettier_calls = []

    def show(self, ref, cwd, log):
        """`git show <rev>:frontend/<rel>`: HEAD is what the work tree holds in these tests, any other rev the base."""
        rev, rel = ref.split(":frontend/", 1)
        if rev == "HEAD":
            log.write_text((cwd / "frontend" / rel).read_text(encoding="utf-8"), encoding="utf-8")
            return self.head_show_code
        log.write_text(self.base.get(rel, ""), encoding="utf-8")
        return self.show_code

    def __call__(self, argv, cwd, env, log):
        if argv[:2] == ["git", "show"]:
            self.calls.append((list(argv), cwd, dict(env), log))
            return self.show(argv[2], cwd, log)
        if argv[:2] == ["git", "merge-base"] and self.merge_base_code:
            self.calls.append((list(argv), cwd, dict(env), log))
            log.write_text("fatal\n", encoding="utf-8")
            return self.merge_base_code
        if argv[:2] == ["git", "diff"] and any(a.startswith("--diff-filter") for a in argv):
            self.calls.append((list(argv), cwd, dict(env), log))
            listed = self.added if "--diff-filter=A" in argv else self.names
            log.write_text("".join(f"frontend/src/{n}\n" for n in sorted(listed)), encoding="utf-8")
            return 0
        if argv[:3] == ["npx", "prettier", "--check"]:
            self.calls.append((list(argv), cwd, dict(env), log))
            files = argv[3:]
            self.prettier_calls.append(files)
            log.write_text("prettier\n", encoding="utf-8")
            if self.prettier_code is not None:
                return self.prettier_code
            return 1 if any((cwd / f).read_text(encoding="utf-8").startswith("BAD") for f in files) else 0
        return super().__call__(argv, cwd, env, log)


def format_run(tree, monkeypatch, runner, files=None):
    for name, text in (files or {}).items():
        (tree / "frontend" / "src" / name).write_text(text, encoding="utf-8")
    fake_git_dir(monkeypatch, tree)
    return run(tree, runner)


def test_format_new_unformatted_file_fails(tree, monkeypatch):
    """Attack 4, branch 1: a file added by this branch must be formatted."""
    runner = FormatRunner(["a.vue"], added=["a.vue"])
    code, lines = format_run(tree, monkeypatch, runner, {"a.vue": BAD})
    assert (code, lines[-1]) == (1, "GATE FAIL frontend-format: exit 1")
    assert "src/a.vue: new file, not formatted" in lines


def test_format_file_formatted_at_base_now_unformatted_fails(tree, monkeypatch):
    """Attack 4, branch 2: the branch made a formatted file unformatted."""
    runner = FormatRunner(["a.vue"], base={"src/a.vue": GOOD})
    code, lines = format_run(tree, monkeypatch, runner, {"a.vue": BAD})
    assert (code, lines[-1]) == (1, "GATE FAIL frontend-format: exit 1")
    assert "src/a.vue: formatted at the merge base, unformatted now" in lines
    left = [n for n in os.listdir(tree / "frontend" / "src") if n.startswith(gate.COPY_PREFIX)]
    assert left == []  # the temp copies are removed


def test_format_old_debt_still_unformatted_passes_and_is_counted(tree, monkeypatch):
    """Attack 4, branch 3: a file already unformatted at base and still so is counted, not failed."""
    runner = FormatRunner(["a.vue", "b.vue"], base={"src/a.vue": BAD})
    code, lines = format_run(tree, monkeypatch, runner, {"a.vue": BAD, "b.vue": GOOD})
    assert code == 0
    assert "frontend-format: 2 checked, 1 already unformatted at base (not failed)" in lines
    assert lines[-1].startswith("GATE PASS")
    assert gate_log(tree, "frontend-format").endswith("1 already unformatted at base (not failed)")


def test_format_all_formatted_passes_with_one_prettier_run(tree, monkeypatch):
    runner = FormatRunner(["a.vue", "b.vue"], added=["b.vue"])
    code, lines = format_run(tree, monkeypatch, runner, {"a.vue": GOOD, "b.vue": GOOD})
    assert code == 0 and runner.prettier_calls == [["src/a.vue", "src/b.vue"]]
    assert "frontend-format: 2 checked, 0 already unformatted at base (not failed)" in lines


def test_format_zero_files_passes(tree, monkeypatch):
    """Attack 4, branch 4: nothing changed under src/ - no prettier run, no summary line."""
    runner = FormatRunner([])
    code, lines = format_run(tree, monkeypatch, runner)
    assert code == 0 and runner.prettier_calls == []
    assert not [ln for ln in lines if ln.startswith("frontend-format:")]


def test_format_unreadable_base_fails_closed(tree, monkeypatch):
    """Standing item (c): `git show` of the base version fails -> fail, never 'no base, so pass'."""
    code, lines = format_run(tree, monkeypatch, FormatRunner(["a.vue"], show_code=128), {"a.vue": BAD})
    assert (code, lines[-1]) == (1, "GATE FAIL frontend-format: exit 128")
    assert any("cannot read or check the base version of src/a.vue" in ln for ln in lines)


def test_format_unreadable_committed_version_fails_closed(tree, monkeypatch):
    """Standing item (d): `git show HEAD:<file>` fails -> fail, never judged by the work-tree copy."""
    code, lines = format_run(tree, monkeypatch, FormatRunner(["a.vue"], head_show_code=128), {"a.vue": BAD})
    assert (code, lines[-1]) == (1, "GATE FAIL frontend-format: exit 128")
    assert any("cannot read the committed version of src/a.vue" in ln for ln in lines)


def test_format_unreadable_merge_base_fails_closed(tree, monkeypatch):
    code, lines = format_run(tree, monkeypatch, FormatRunner(["a.vue"], merge_base_code=128), {"a.vue": BAD})
    assert (code, lines[-1]) == (1, "GATE FAIL frontend-format: exit 128")


@pytest.mark.parametrize("code_in", [2, 7, 127])
def test_format_prettier_error_exit_fails_closed(tree, monkeypatch, code_in):
    """Standing item (d): prettier answers 0 formatted, 1 unformatted; anything else (2 = error) is a failure."""
    runner = FormatRunner(["a.vue"], prettier_code=code_in)
    code, lines = format_run(tree, monkeypatch, runner, {"a.vue": GOOD})
    assert (code, lines[-1]) == (1, f"GATE FAIL frontend-format: exit {code_in}")
    assert runner.prettier_calls == [["src/a.vue"]]  # the batch answer is final: no per-file or base runs


def test_format_prettier_error_on_one_file_during_the_ratchet_fails_closed(tree, monkeypatch):
    """The batch said 1 (unformatted); the per-file answer 2 (error) is not 'formatted at base': it fails."""

    class Flaky(FormatRunner):
        def __call__(self, argv, cwd, env, log):
            if argv[:3] == ["npx", "prettier", "--check"] and self.prettier_calls:
                self.prettier_calls.append(argv[3:])
                log.write_text("boom\n", encoding="utf-8")
                return 2
            return super().__call__(argv, cwd, env, log)

    code, lines = format_run(tree, monkeypatch, Flaky(["a.vue"]), {"a.vue": BAD})
    assert (code, lines[-1]) == (1, "GATE FAIL frontend-format: exit 2")


# --- real git: the verdict follows the committed blobs, never the checkout (finding gate-output-read-by-eye) ---------
GOOD_TWO, BAD_TWO = "good two\n", "BAD two\n"


def git_bytes(repo, *args):
    """Raw stdout of one real git command (through the gate's own runner), failing the test on a non-zero exit."""
    log = repo.parent / "git.out"
    assert gate.default_runner(["git", *args], repo, dict(os.environ), log) == 0
    return log.read_bytes()


def git(repo, *args):
    return git_bytes(repo, *args).decode().strip()


def real_runner(argv, cwd, env, log):
    """Real git; a fake prettier that, like prettier's endOfLine=lf, calls a file unformatted for BAD text or a CR."""
    if argv[:3] != ["npx", "prettier", "--check"]:
        return gate.default_runner(argv, cwd, env, log)
    log.write_text("prettier\n", encoding="utf-8")
    texts = [(cwd / f).read_bytes().decode() for f in argv[3:]]
    return 1 if any("BAD" in t or "\r" in t for t in texts) else 0


def make_repo(tmp_path, base_files):
    repo = tmp_path / "real"
    (repo / "frontend" / "src").mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    for key, value in (("user.email", "c@x"), ("user.name", "c"), ("core.autocrlf", "true")):
        git(repo, "config", key, value)
    for name, text in base_files.items():
        (repo / "frontend" / "src" / name).write_bytes(text.encode())
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "base")
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    git(repo, "checkout", "-qb", "br")
    return repo


def commit_edit(repo, name, data):
    (repo / "frontend" / "src" / name).write_bytes(data)
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "edit")


def real_format(repo, tmp_path):
    step = gate.Step("frontend-format", ("npx", "prettier", "--check"), "frontend", "format")
    logs = tmp_path / "logs"
    logs.mkdir(exist_ok=True)
    code, _ = gate.run_format(step, repo, real_runner, logs, dict(os.environ))
    return code, (logs / "frontend-format.log").read_text(encoding="utf-8")


def test_format_crlf_checkout_of_a_formatted_file_passes(tmp_path):
    """Attack 1: a file formatted at base and in HEAD, with real CRLF bytes in the work tree, passes."""
    repo = make_repo(tmp_path, {"a.vue": "good\n"})
    commit_edit(repo, "a.vue", GOOD_TWO.replace("\n", "\r\n").encode())
    assert b"\r\n" in (repo / "frontend" / "src" / "a.vue").read_bytes()
    assert b"\r" not in git_bytes(repo, "show", "HEAD:frontend/src/a.vue")
    code, log = real_format(repo, tmp_path)
    assert code == 0, log
    assert "1 checked" in log


def test_format_formatted_at_base_made_unformatted_still_fails_with_real_git(tmp_path):
    """Attack 2: the same setup, but the committed text is unformatted -> fail naming the file."""
    repo = make_repo(tmp_path, {"a.vue": "good\n"})
    commit_edit(repo, "a.vue", BAD_TWO.encode())
    code, log = real_format(repo, tmp_path)
    assert code == 1
    assert "src/a.vue: formatted at the merge base, unformatted now" in log


def test_format_never_overwrites_or_leaves_a_file_named_like_a_copy(tmp_path):
    """Attack 3: real files named like the old fixed copy name and like the new prefix survive the step untouched."""
    names = ["gate-base-copy.vue", f"{gate.COPY_PREFIX}x.vue"]
    repo = make_repo(tmp_path, {"a.vue": "good\n", **dict.fromkeys(names, "mine\n")})
    commit_edit(repo, "a.vue", BAD_TWO.encode())
    code, _ = real_format(repo, tmp_path)
    assert code == 1
    src = repo / "frontend" / "src"
    assert sorted(os.listdir(src)) == sorted(["a.vue", *names])
    assert [(src / n).read_text() for n in names] == ["mine\n", "mine\n"]


def test_format_a_renamed_old_unformatted_file_counts_as_new(tmp_path):
    """Attack 4: --no-renames makes a moved file new, so an unformatted moved file fails (as a rename it would be
    old debt and pass)."""
    repo = make_repo(tmp_path, {"old.vue": BAD_TWO})
    git(repo, "mv", "frontend/src/old.vue", "frontend/src/moved.vue")
    git(repo, "commit", "-qm", "mv")
    assert git(repo, "diff", "--name-status", "origin/main...HEAD").startswith("R")  # git itself sees a rename
    code, log = real_format(repo, tmp_path)
    assert code == 1
    assert "src/moved.vue: new file, not formatted" in log
