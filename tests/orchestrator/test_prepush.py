"""prepush.py: step order, every step runs, exit code, marker only on all-pass + clean tracked tree.
Injected runner and a temp git repo; the real suites are never run here."""
import importlib.util
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import ClassVar

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "orchestrator"))
import prepush

CHEAP = ["ruff_ratchet", "coverage", "alembic_guard"]
NAMES = [*CHEAP, "preflight", "ci_checks", "domain_tests", "app_tests"]  # run order (cheap checks first)
FRONT = ["frontend_lint", "frontend_unit", "frontend_build"]
REAL_FRONTEND_CHANGES = prepush.frontend_changes
CI_YML = """name: ci
on:
  pull_request:
jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    steps:
      - name: Install
        run: pip install pyyaml pytest
      - name: Lint things
        run: python tools/factory_lint.py .
      - name: Run tests on pull request
        run: |
          if [ ! -d tests ]; then exit 0; fi
          python -m pytest -q -p no:cacheprovider
      - name: Bare pytest
        run: pytest -q
      - name: Drift
        run: python tools/kit_drift.py . --ci
"""


@pytest.fixture(autouse=True)
def selectors(monkeypatch):
    """Default selection: one domain file, one app file, so every step calls the runner."""
    monkeypatch.setattr(prepush, "select_domain_tests", lambda repo, base="origin/main": ["tests/test_a.py"])
    monkeypatch.setattr(prepush, "select_app_tests", lambda repo: (0, ["tests_app/test_b.py"], "1 files"))
    monkeypatch.setattr(prepush, "frontend_changes", lambda repo, base="origin/main": [])  # backend-only by default


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)  # noqa: S603, S607


def make_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "t@t")
    git(repo, "config", "user.name", "t")
    (repo / "a.txt").write_text("a", encoding="utf-8")
    (repo / ".github" / "workflows").mkdir(parents=True)
    (repo / ".github" / "workflows" / "ci.yml").write_text(CI_YML, encoding="utf-8")
    git(repo, "add", "a.txt", ".github")
    git(repo, "commit", "-q", "-m", "one")
    return repo


class Runner:
    def __init__(self, fail=()):
        self.fail = set(fail)
        self.calls = []

    def __call__(self, cmd, cwd, log_path):
        self.calls.append((cmd, cwd, log_path))
        name = next(n for n in NAMES + FRONT if Path(log_path).name == n + ".log")
        return 1 if name in self.fail else 0


def sha_of(repo):
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True,  # noqa: S603, S607
                          check=True).stdout.strip()


def test_steps_run_in_order_in_the_repo_with_logs_outside_it(tmp_path, capsys):
    repo = make_repo(tmp_path)
    runner = Runner()
    rc = prepush.run_all(str(repo), runner=runner, log_dir=str(tmp_path / "logs"))
    assert rc == 0
    tails = [" ".join(c[0][1:]).replace("\\", "/") for c in runner.calls]
    # the seconds-long checks first (finding cheap-check-after-expensive-one), then the minutes-long ones
    assert tails[:3] == ["scripts/ruff_ratchet.py", "scripts/orchestrator/coverage.py . --check",
                         "scripts/alembic_migration_guard.py"]
    assert tails[3].startswith("scripts/orchestrator/merge_preflight.py . --log-dir ")
    assert tails[4].startswith("tools/ci_local.py --workflow ")
    assert tails[4].endswith("ci-no-pytest.yml --no-tests")
    assert tails[5:] == ["-m pytest -q -p no:cacheprovider tests/test_a.py",
                         "-m pytest -c pytest-app.ini -q -p no:cacheprovider tests_app/test_b.py"]
    assert all(Path(c[1]) == repo for c in runner.calls)
    assert all(repo not in Path(c[2]).parents for c in runner.calls)
    out = capsys.readouterr().out
    assert out.count("PASS ") == len(NAMES) + 1  # seven steps + TOTAL PASS
    assert "TOTAL PASS" in out


def test_a_red_preflight_stops_the_run_before_the_long_steps_and_writes_no_marker(tmp_path, capsys):
    """2026-11-01: a broken merge used to cost a whole ~25 min gate; the preflight catches it in minutes and the long
    steps are not started (they could only repeat the same red)."""
    repo = make_repo(tmp_path)
    runner = Runner(fail={"preflight"})
    rc = prepush.run_all(str(repo), runner=runner, log_dir=str(tmp_path / "l"))
    assert rc == 1
    assert len(runner.calls) == len(CHEAP) + 1  # the cheap checks and the preflight ran; nothing after it
    out = capsys.readouterr().out
    assert "FAIL preflight" in out and "STOP: preflight failed" in out and "failed: preflight" in out
    assert not prepush.has_marker(str(repo), sha_of(repo))


@pytest.mark.parametrize("failing", CHEAP)
def test_a_red_cheap_check_still_lets_the_preflight_and_every_later_step_run(tmp_path, capsys, failing):
    repo = make_repo(tmp_path)
    runner = Runner(fail={failing})
    assert prepush.run_all(str(repo), runner=runner, log_dir=str(tmp_path / "l")) == 1
    assert [Path(c[2]).stem for c in runner.calls] == NAMES  # all seven ran, in order, preflight included
    out = capsys.readouterr().out
    assert f"FAIL {failing} " in out and "STOP" not in out and f"failed: {failing}" in out
    assert not prepush.has_marker(str(repo), sha_of(repo))


def test_a_red_ruff_ratchet_runs_every_later_step_and_exits_1(tmp_path, capsys):
    repo = make_repo(tmp_path)
    runner = Runner(fail={"ruff_ratchet"})
    rc = prepush.run_all(str(repo), runner=runner, log_dir=str(tmp_path / "l"))
    assert rc == 1
    assert [Path(c[2]).stem for c in runner.calls][1:] == NAMES[1:]
    assert "TOTAL FAIL" in capsys.readouterr().out


def test_the_workflow_copy_drops_pytest_steps_keeps_the_rest_outside_the_repo(tmp_path, capsys):
    repo = make_repo(tmp_path)
    prepush.run_all(str(repo), runner=Runner(), log_dir=str(tmp_path / "logs"))
    copy = tmp_path / "logs" / "ci-no-pytest.yml"
    steps = yaml.safe_load(copy.read_text(encoding="utf-8"))["jobs"]["lint-and-test"]["steps"]
    names = [s["name"] for s in steps]
    assert names == ["Install", "Lint things", "Drift"]  # "pip install ... pytest" is kept: it does not run pytest
    assert steps[1]["run"] == "python tools/factory_lint.py ."
    assert "Run tests on pull request; Bare pytest" in capsys.readouterr().out
    assert repo not in copy.parents


def test_no_tests_flag_is_passed_to_ci_local(tmp_path):
    repo = make_repo(tmp_path)
    runner = Runner()
    prepush.run_all(str(repo), runner=runner, log_dir=str(tmp_path / "l"))
    assert runner.calls[4][0][-1] == "--no-tests"


def test_a_none_selection_runs_all_of_tests(tmp_path, monkeypatch):
    monkeypatch.setattr(prepush, "select_domain_tests", lambda repo, base="origin/main": None)
    repo = make_repo(tmp_path)
    runner = Runner()
    prepush.run_all(str(repo), runner=runner, log_dir=str(tmp_path / "l"))
    assert runner.calls[5][0][-1] == "tests/"
    assert runner.calls[5][0][1:3] == ["-m", "pytest"]


def test_full_runs_all_of_tests_without_asking_the_selector(tmp_path, monkeypatch):
    def boom(repo, base="origin/main"):
        raise AssertionError("selector must not be asked")

    monkeypatch.setattr(prepush, "select_domain_tests", boom)
    repo = make_repo(tmp_path)
    runner = Runner()
    assert prepush.run_all(str(repo), full=True, runner=runner, log_dir=str(tmp_path / "l")) == 0
    assert runner.calls[5][0][-1] == "tests/"


def test_an_empty_selection_skips_the_domain_step_as_pass(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(prepush, "select_domain_tests", lambda repo, base="origin/main": [])
    monkeypatch.setattr(prepush, "select_app_tests", lambda repo: (0, [], "0 files"))
    repo = make_repo(tmp_path)
    runner = Runner()
    assert prepush.run_all(str(repo), runner=runner, log_dir=str(tmp_path / "l")) == 0
    assert len(runner.calls) == len(NAMES) - 2
    assert "PASS domain_tests" in capsys.readouterr().out
    assert "no domain tests needed" in (tmp_path / "l" / "domain_tests.log").read_text(encoding="utf-8")
    assert prepush.has_marker(str(repo), sha_of(repo))


def test_app_tests_cannot_select_fails_closed_with_the_message(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(prepush, "select_app_tests", lambda repo: (3, [], "route tests: diff not parsed"))
    repo = make_repo(tmp_path)
    runner = Runner()
    assert prepush.run_all(str(repo), runner=runner, log_dir=str(tmp_path / "l")) == 1
    assert "diff not parsed" in (tmp_path / "l" / "app_tests.log").read_text(encoding="utf-8")
    assert "FAIL app_tests" in capsys.readouterr().out
    assert not prepush.has_marker(str(repo), sha_of(repo))
    assert len(runner.calls) == len(NAMES) - 1  # the other steps still ran


def test_domain_selection_error_fails_closed(tmp_path, monkeypatch):
    def broken(repo, base="origin/main"):
        raise RuntimeError("diff unreadable")

    monkeypatch.setattr(prepush, "select_domain_tests", broken)
    repo = make_repo(tmp_path)
    assert prepush.run_all(str(repo), runner=Runner(), log_dir=str(tmp_path / "l")) == 1


def test_missing_ci_yml_fails_the_ci_checks_step_closed(tmp_path):
    repo = make_repo(tmp_path)
    (repo / ".github" / "workflows" / "ci.yml").unlink()
    git(repo, "commit", "-q", "-am", "drop ci")
    runner = Runner()
    assert prepush.run_all(str(repo), runner=runner, log_dir=str(tmp_path / "l")) == 1
    assert len(runner.calls) == len(NAMES) - 1


def test_later_steps_still_run_after_a_failure_and_exit_is_1(tmp_path, capsys):
    repo = make_repo(tmp_path)
    runner = Runner(fail={"ci_checks"})
    rc = prepush.run_all(str(repo), runner=runner, log_dir=str(tmp_path / "l"))
    assert rc == 1
    assert len(runner.calls) == len(NAMES)
    out = capsys.readouterr().out
    assert "FAIL ci_checks" in out
    assert "TOTAL FAIL" in out
    assert "failed: ci_checks" in out


def test_marker_is_written_on_all_pass_and_clean_tree(tmp_path):
    repo = make_repo(tmp_path)
    sha = sha_of(repo)
    assert not prepush.has_marker(str(repo), sha)
    assert prepush.run_all(str(repo), runner=Runner(), log_dir=str(tmp_path / "l")) == 0
    assert prepush.has_marker(str(repo), sha)
    body = json.loads(Path(prepush.marker_path(str(repo), sha)).read_text(encoding="utf-8"))
    assert body["sha"] == sha
    assert [s["name"] for s in body["steps"]] == NAMES
    assert all(s["rc"] == 0 for s in body["steps"])
    assert body["at"].endswith("+00:00")
    assert Path(prepush.marker_path(str(repo), sha)).parent.parent.name == ".git"


def test_no_marker_when_any_step_failed(tmp_path):
    repo = make_repo(tmp_path)
    for failing in NAMES:
        assert prepush.run_all(str(repo), runner=Runner(fail={failing}), log_dir=str(tmp_path / "l")) == 1
        assert not prepush.has_marker(str(repo), sha_of(repo)), failing


def test_no_marker_on_a_dirty_tracked_tree_but_checks_still_run(tmp_path, capsys):
    repo = make_repo(tmp_path)
    (repo / "a.txt").write_text("changed", encoding="utf-8")
    runner = Runner()
    rc = prepush.run_all(str(repo), runner=runner, log_dir=str(tmp_path / "l"))
    assert rc == 0
    assert len(runner.calls) == len(NAMES)
    assert not prepush.has_marker(str(repo), sha_of(repo))
    assert "tracked tree was dirty when the run started" in capsys.readouterr().out


def test_untracked_junk_outside_source_dirs_does_not_block_the_marker(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "scratch.txt").write_text("x", encoding="utf-8")
    (repo / "pid.txt").write_text("123", encoding="utf-8")
    (repo / "frontend").mkdir()
    (repo / "frontend" / "notes.md").write_text("x", encoding="utf-8")  # frontend/ but not frontend/src
    assert prepush.run_all(str(repo), runner=Runner(), log_dir=str(tmp_path / "l")) == 0
    assert prepush.has_marker(str(repo), sha_of(repo))


@pytest.mark.parametrize("rel", ["backend/x.py", "tests/test_new.py", "tests_app/conftest_extra.py",
                                 "scripts/helper.py", "frontend/src/New.vue"])
def test_an_untracked_source_file_blocks_the_marker_and_is_named(tmp_path, capsys, rel):
    # review F2: CI checks the committed tree; a committed import of a never-added module passes here only
    repo = make_repo(tmp_path)
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x = 1\n", encoding="utf-8")
    assert prepush.run_all(str(repo), runner=Runner(), log_dir=str(tmp_path / "l")) == 0
    assert not prepush.has_marker(str(repo), sha_of(repo))
    out = capsys.readouterr().out
    assert "untracked source files CI will not see: " + rel in out


def test_an_ignored_file_under_backend_does_not_block(tmp_path):
    repo = make_repo(tmp_path)
    (repo / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
    git(repo, "add", ".gitignore")
    git(repo, "commit", "-q", "-m", "ignore")
    (repo / "backend" / "__pycache__").mkdir(parents=True)
    (repo / "backend" / "__pycache__" / "x.pyc").write_bytes(b"x")
    assert prepush.run_all(str(repo), runner=Runner(), log_dir=str(tmp_path / "l")) == 0
    assert prepush.has_marker(str(repo), sha_of(repo))


class MovingRunner(Runner):
    """Does something to the repo while the last step runs (the run is long; a commit or a checkout can land)."""

    def __init__(self, repo, action):
        super().__init__()
        self.repo, self.action = repo, action

    def __call__(self, cmd, cwd, log_path):
        if Path(log_path).name == "alembic_guard.log":
            self.action(self.repo)
        return super().__call__(cmd, cwd, log_path)


def test_head_moving_during_the_run_writes_no_marker(tmp_path, capsys):
    # review F3: the sha is read at the start; a commit made mid-run must not get (or give) a marker
    repo = make_repo(tmp_path)
    start = sha_of(repo)
    runner = MovingRunner(repo, lambda r: git(r, "commit", "-q", "--allow-empty", "-m", "mid-run"))
    assert prepush.run_all(str(repo), runner=runner, log_dir=str(tmp_path / "l")) == 0
    assert sha_of(repo) != start
    assert not prepush.has_marker(str(repo), start)
    assert not prepush.has_marker(str(repo), sha_of(repo))
    assert "HEAD moved during the run" in capsys.readouterr().out


def test_dirty_at_start_clean_at_end_writes_no_marker(tmp_path, capsys):
    repo = make_repo(tmp_path)
    (repo / "a.txt").write_text("changed", encoding="utf-8")  # the tests ran on this, not on the commit
    runner = MovingRunner(repo, lambda r: git(r, "checkout", "--", "a.txt"))
    assert prepush.run_all(str(repo), runner=runner, log_dir=str(tmp_path / "l")) == 0
    assert not prepush.has_marker(str(repo), sha_of(repo))
    assert "dirty when the run started" in capsys.readouterr().out


class FakePopen:
    """Stands in for subprocess.Popen: records the keyword arguments, finishes at once with rc 0."""
    kwargs: ClassVar[dict] = {}

    def __init__(self, cmd, **kwargs):
        type(self).kwargs = kwargs
        self.pid = 1

    def wait(self, timeout=None):
        return 0


def test_the_child_run_never_carries_the_db_urls_and_gets_its_own_temp_root(tmp_path, monkeypatch):
    # review F4: under db_run.py these are set; the selected DB tests must still not reach the shared host
    for key in prepush.DB_ENV:
        monkeypatch.setenv(key, "postgresql://prod-host/x")
    monkeypatch.setenv("OFO_KEEP_ME", "1")
    monkeypatch.setattr(prepush.tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(prepush.subprocess, "Popen", FakePopen)
    runner = prepush.RealRunner(repo=str(tmp_path / "r"))
    assert runner(["python", "-V"], str(tmp_path), str(tmp_path / "x.log")) == 0
    env = FakePopen.kwargs["env"]
    assert set(prepush.DB_ENV) == {"TEST_DATABASE_URL", "TEST_ADMIN_DATABASE_URL", "ALEMBIC_DATABASE_URL"}
    assert not set(prepush.DB_ENV) & set(env)
    assert env["OFO_KEEP_ME"] == "1"
    root = prepush.step_temp_root(str(tmp_path / "r"), "x")
    assert env["TMPDIR"] == env["TEMP"] == env["TMP"] == root
    assert FakePopen.kwargs["start_new_session"] is True or prepush.IS_WINDOWS
    assert not set(prepush.DB_ENV) & set(prepush.child_env({"TEST_DATABASE_URL": "x", "ALEMBIC_DATABASE_URL": "y",
                                                             "TEST_ADMIN_DATABASE_URL": "z", "A": "1"}))
    assert prepush.child_env({"A": "1"}) == {"A": "1"}  # no tmp_root given: temp variables untouched


def test_the_temp_root_is_per_repo_per_step_and_stable(tmp_path, monkeypatch):
    monkeypatch.setattr(prepush.tempfile, "tempdir", str(tmp_path))
    one = prepush.step_temp_root(str(tmp_path / "a"), "domain_tests")
    assert one == prepush.step_temp_root(str(tmp_path / "a"), "domain_tests")  # stable across runs: caches stay warm
    assert one != prepush.step_temp_root(str(tmp_path / "a"), "app_tests")  # no two stages share a temp root
    assert one != prepush.step_temp_root(str(tmp_path / "b"), "domain_tests")
    rel = Path(one).relative_to(tmp_path)
    assert rel.parts[0] == "ofo-prepush-tmp" and len(rel.parts[1]) == 12 and rel.parts[2] == "domain_tests"  # noqa: PLR2004
    assert Path(one).is_dir()


def test_a_real_child_sees_the_step_temp_root_in_all_three_variables(tmp_path, monkeypatch):
    monkeypatch.setattr(prepush.tempfile, "tempdir", str(tmp_path))
    log = tmp_path / "ruff_ratchet.log"
    code = "import os; print(os.environ['TMPDIR'], os.environ['TEMP'], os.environ['TMP'], sep='|')"
    assert prepush.RealRunner(repo=str(tmp_path))([sys.executable, "-c", code], str(tmp_path), str(log)) == 0
    root = prepush.step_temp_root(str(tmp_path), "ruff_ratchet")
    assert log.read_text(encoding="utf-8").strip() == "|".join([root] * 3)


def test_a_timed_out_or_unstartable_step_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(prepush, "STEP_TIMEOUT_S", 0)
    monkeypatch.setattr(prepush, "POLL_S", 0.05)
    log = tmp_path / "t.log"
    sleeper = [sys.executable, "-c", "import time; time.sleep(60)"]
    assert prepush.RealRunner(repo=str(tmp_path))(sleeper, str(tmp_path), str(log)) == prepush.TIMEOUT_RC
    assert "timed out" in log.read_text(encoding="utf-8")

    def cannot_start(cmd, **kwargs):
        raise FileNotFoundError(cmd[0])

    monkeypatch.setattr(prepush.subprocess, "Popen", cannot_start)
    assert prepush.RealRunner(repo=str(tmp_path))(["npm"], str(tmp_path), str(log)) == 1
    assert "could not start" in log.read_text(encoding="utf-8")


def test_real_runner_stays_importable_and_callable():
    assert callable(prepush.real_runner) and isinstance(prepush.real_runner, prepush.RealRunner)


CHILD = """
import subprocess, sys, time
grand = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
open(sys.argv[1], "w").write(str(grand.pid))
time.sleep(60)
"""


def alive(pid):
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as handle:
            return handle.read().rsplit(")", 1)[1].split()[0] != "Z"  # a zombie is gone
    except OSError:
        return False


@pytest.mark.skipif(sys.platform == "win32", reason="process groups and killpg are POSIX; the Windows path is taskkill")
def test_stop_kills_the_whole_process_tree(tmp_path, monkeypatch):  # the timeout path calls the same kill_tree
    pid_file = tmp_path / "grand.pid"
    runner = prepush.RealRunner(repo=str(tmp_path))
    monkeypatch.setattr(prepush, "POLL_S", 0.05)
    result = {}
    thread = threading.Thread(target=lambda: result.update(rc=runner([sys.executable, "-c", CHILD, str(pid_file)],
                                                                      str(tmp_path), str(tmp_path / "s.log"))))
    thread.start()
    for _ in range(600):  # wait until the grandchild exists (a count, not a clock assert)
        if pid_file.exists() and pid_file.read_text(encoding="utf-8"):
            break
        time.sleep(0.05)
    grand = int(pid_file.read_text(encoding="utf-8"))
    assert alive(grand)
    runner.stop.set()
    thread.join(timeout=60)
    assert not thread.is_alive()
    assert result["rc"] == prepush.STOPPED_RC
    for _ in range(100):
        if not alive(grand):
            break
        time.sleep(0.05)
    assert not alive(grand)
    assert "stopped: preflight failed" in (tmp_path / "s.log").read_text("utf-8")


def test_the_windows_kill_is_taskkill_of_the_whole_tree(monkeypatch):
    calls = []
    monkeypatch.setattr(prepush, "IS_WINDOWS", True)
    monkeypatch.setattr(prepush.subprocess, "run", lambda cmd, **kw: calls.append(cmd))

    class Proc:
        pid = 4242

        def wait(self, timeout=None):
            return 1

    prepush.kill_tree(Proc())
    assert calls == [["taskkill", "/F", "/T", "/PID", "4242"]]
    assert prepush._spawn_kwargs() == {"creationflags": 0x200}  # CREATE_NEW_PROCESS_GROUP


def which(tool):
    return "/fake/bin/" + tool


def frontend_repo(tmp_path, node_modules=True):
    repo = make_repo(tmp_path)
    (repo / "frontend").mkdir()
    if node_modules:
        (repo / "frontend" / "node_modules").mkdir()  # untracked, outside frontend/src: does not block
    return repo


def run_front(repo, tmp_path, changes, runner, full=False):
    return prepush.run_all(str(repo), full=full, runner=runner, log_dir=str(tmp_path / "l"),
                           select_frontend=lambda r: changes, which=which)


def test_a_frontend_change_runs_lint_related_vitest_and_build_in_frontend(tmp_path, capsys):
    repo = frontend_repo(tmp_path)
    runner = Runner()
    assert run_front(repo, tmp_path, ["src/components/LegPicker.vue", "tests/leg-picker.test.js"], runner) == 0
    # lint (needs no build: eslint ignores dist/) and the build run before the preflight, which reads frontend/dist;
    # vitest runs last
    front = [*runner.calls[3:5], runner.calls[-1]]
    assert [c[0] for c in front] == [
        ["/fake/bin/npm", "run", "lint"],
        ["/fake/bin/npm", "run", "build"],
        ["/fake/bin/npx", "vitest", "related", "--run", "src/components/LegPicker.vue", "tests/leg-picker.test.js"]]
    assert all(Path(c[1]) == repo / "frontend" for c in front)
    out = capsys.readouterr().out
    assert all(f"PASS {n} " in out for n in FRONT)
    assert prepush.has_marker(str(repo), sha_of(repo))
    body = json.loads(Path(prepush.marker_path(str(repo), sha_of(repo))).read_text(encoding="utf-8"))
    assert [s["name"] for s in body["steps"]] == [*CHEAP, "frontend_lint", "frontend_build", "preflight", "ci_checks",
                                                       "domain_tests", "app_tests", "frontend_unit"]


@pytest.mark.parametrize("failing", FRONT)
def test_a_red_frontend_step_writes_no_marker_and_exits_1(tmp_path, capsys, failing):
    # orchestrator finding 1: a marker was written over 37 failing vitest tests
    repo = frontend_repo(tmp_path)
    assert run_front(repo, tmp_path, ["src/a.js"], Runner(fail={failing})) == 1
    assert not prepush.has_marker(str(repo), sha_of(repo))
    out = capsys.readouterr().out
    assert f"FAIL {failing} " in out
    assert f"failed: {failing}" in out


@pytest.mark.parametrize(("changes", "full"), [(["*"], False), (None, False), (["src/a.js"], True)])
def test_every_vitest_file_runs_on_full_a_wide_change_or_an_unreadable_diff(tmp_path, changes, full):
    repo = frontend_repo(tmp_path)
    runner = Runner()
    assert run_front(repo, tmp_path, changes, runner, full=full) == 0
    assert runner.calls[-1][0] == ["/fake/bin/npx", "vitest", "run"]  # vitest runs last
    assert len(runner.calls) == len(NAMES) + len(FRONT)


def test_missing_node_modules_is_a_fail_with_the_reason_never_a_skip(tmp_path, capsys):
    repo = frontend_repo(tmp_path, node_modules=False)
    runner = Runner()
    assert run_front(repo, tmp_path, ["src/a.js"], runner) == 1
    assert len(runner.calls) == len(NAMES)  # no frontend command was started
    assert not prepush.has_marker(str(repo), sha_of(repo))
    out = capsys.readouterr().out
    assert all(f"FAIL {n} " in out for n in FRONT)
    assert "node_modules is missing" in (tmp_path / "l" / "frontend_unit.log").read_text(encoding="utf-8")


def test_a_missing_npm_is_a_fail(tmp_path):
    repo = frontend_repo(tmp_path)
    rc = prepush.run_all(str(repo), runner=Runner(), log_dir=str(tmp_path / "l"),
                         select_frontend=lambda r: ["src/a.js"], which=lambda tool: None)
    assert rc == 1
    assert not prepush.has_marker(str(repo), sha_of(repo))
    assert "npm not found" in (tmp_path / "l" / "frontend_lint.log").read_text(encoding="utf-8")


def test_a_backend_only_change_runs_no_frontend_step(tmp_path, capsys):
    repo = frontend_repo(tmp_path, node_modules=False)  # would FAIL if a frontend step ran
    runner = Runner()
    assert run_front(repo, tmp_path, [], runner) == 0
    assert len(runner.calls) == len(NAMES)
    assert "frontend_" not in capsys.readouterr().out
    assert prepush.has_marker(str(repo), sha_of(repo))


def test_a_frontend_selector_error_fails_closed_into_running_every_step(tmp_path):
    def broken(repo):
        raise RuntimeError("diff unreadable")

    repo = frontend_repo(tmp_path)
    runner = Runner()
    prepush.run_all(str(repo), runner=runner, log_dir=str(tmp_path / "l"), select_frontend=broken, which=which)
    assert runner.calls[-1][0] == ["/fake/bin/npx", "vitest", "run"]  # vitest runs last


def commit_file(repo, rel, text="x"):
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    git(repo, "add", rel)
    git(repo, "commit", "-q", "-m", rel)


def test_frontend_changes_reads_the_diff_from_the_merge_base(tmp_path):
    changes = REAL_FRONTEND_CHANGES  # the autouse fixture stubs the module attribute; this is the real function
    repo = make_repo(tmp_path)
    assert changes(str(repo)) is None  # no origin/main: unreadable -> callers run every frontend step
    commit_file(repo, "frontend/src/old.js")
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    assert changes(str(repo)) == []
    commit_file(repo, "backend/x.py")
    assert changes(str(repo)) == []  # backend-only
    commit_file(repo, "frontend/src/a.js")
    commit_file(repo, "frontend/tests/a.test.js")
    assert changes(str(repo)) == ["src/a.js", "tests/a.test.js"]
    commit_file(repo, "frontend/src/old.js", "changed")
    assert sorted(changes(str(repo))) == ["src/a.js", "src/old.js", "tests/a.test.js"]
    commit_file(repo, "frontend/package.json", "{}")
    assert changes(str(repo)) == ["*"]
    git(repo, "reset", "-q", "--hard", "HEAD~1")
    git(repo, "rm", "-q", "frontend/src/old.js")
    git(repo, "commit", "-q", "-m", "delete")
    assert changes(str(repo)) == ["*"]  # a deletion can break any importer: every test file


def test_marker_belongs_to_one_sha_an_amend_loses_it(tmp_path):
    repo = make_repo(tmp_path)
    old = sha_of(repo)
    prepush.run_all(str(repo), runner=Runner(), log_dir=str(tmp_path / "l"))
    git(repo, "commit", "-q", "--amend", "-m", "reworded")
    new = sha_of(repo)
    assert new != old
    assert prepush.has_marker(str(repo), old)
    assert not prepush.has_marker(str(repo), new)


def test_a_marker_file_copied_to_another_sha_does_not_count(tmp_path):
    repo = make_repo(tmp_path)
    sha = sha_of(repo)
    prepush.run_all(str(repo), runner=Runner(), log_dir=str(tmp_path / "l"))
    fake_sha = "f" * 40
    Path(prepush.marker_path(str(repo), fake_sha)).write_bytes(Path(prepush.marker_path(str(repo), sha)).read_bytes())
    assert not prepush.has_marker(str(repo), fake_sha)


def test_linked_worktree_marker_lives_in_the_common_git_dir(tmp_path):
    repo = make_repo(tmp_path)
    wt = tmp_path / "wt"
    git(repo, "worktree", "add", "-q", "--detach", str(wt))
    sha = sha_of(wt)
    assert prepush.run_all(str(wt), runner=Runner(), log_dir=str(tmp_path / "l")) == 0
    assert prepush.has_marker(str(repo), sha)
    assert prepush.has_marker(str(wt), sha)


@pytest.mark.parametrize(("full", "skips"), [(True, True), (False, False)])
def test_the_preflight_skips_its_tests_repo_scan_only_when_all_of_tests_runs_next(tmp_path, full, skips):
    """Review 2026-11-01 MINOR 7: a selection run (no --full) does not run every repo_scan test, so it keeps the
    preflight's own repo_scan of tests/."""
    repo = make_repo(tmp_path)
    runner = Runner()
    prepush.run_all(str(repo), full=full, runner=runner, log_dir=str(tmp_path / "l"))
    preflight = next(c[0] for c in runner.calls if "merge_preflight.py" in " ".join(c[0]))
    assert ("--no-domain-scans" in preflight) is skips


# ---- parallel mode (--jobs N) ----

TWO_WORKERS = 2
USAGE_RC = 2
LONG = ["preflight", "ci_checks", "domain_tests", "app_tests"]


class ThreadRunner(Runner):
    """Runner for threads. Steps named in `block` wait on the stop event (like a real child that gets killed) and
    return STOPPED_RC when it is set; `raises` raise; the preflight waits until `ci_checks` has started."""

    def __init__(self, fail=(), block=(), raises=()):
        super().__init__(fail)
        self.stop = threading.Event()
        self.block, self.raises = set(block), set(raises)
        self.ci_started = threading.Event()
        self.lock = threading.Lock()

    def __call__(self, cmd, cwd, log_path):
        name = Path(log_path).stem
        with self.lock:
            self.calls.append((cmd, cwd, log_path))
        if name == "ci_checks":
            self.ci_started.set()
        if name in self.raises:
            raise RuntimeError("worker blew up")
        if name == "preflight" and name in self.fail:
            self.ci_started.wait(timeout=60)
        if name in self.block:
            return prepush.STOPPED_RC if self.stop.wait(timeout=60) else 0  # 0 when never stopped: the test fails
        return 1 if name in self.fail else 0


def step_lines(out):
    return [ln for ln in out.splitlines() if re.match(r"(PASS|FAIL) \w+ ", ln)]


def run_jobs(repo, tmp_path, runner, jobs, **kw):
    return prepush.run_all(str(repo), runner=runner, log_dir=str(tmp_path / "l"), jobs=jobs, **kw)


def test_parallel_mode_runs_the_same_commands_in_the_same_places_with_the_same_logs(tmp_path):
    repo = make_repo(tmp_path)
    serial, parallel = Runner(), ThreadRunner()
    assert run_jobs(repo, tmp_path, serial, 1) == 0
    assert run_jobs(repo, tmp_path, parallel, 4) == 0
    assert len(parallel.calls) == len(serial.calls) == len(NAMES)
    as_set = lambda calls: {(tuple(c[0]), c[1], c[2]) for c in calls}  # noqa: E731
    assert as_set(parallel.calls) == as_set(serial.calls)


@pytest.mark.parametrize("jobs", [1, 2, 4, 16])
def test_every_planned_step_gets_exactly_one_line(tmp_path, capsys, jobs):
    repo = frontend_repo(tmp_path)
    assert run_jobs(repo, tmp_path, ThreadRunner(), jobs, select_frontend=lambda r: ["src/a.js"], which=which) == 0
    names = [ln.split()[1] for ln in step_lines(capsys.readouterr().out)]
    planned = [*CHEAP, "frontend_lint", "frontend_build", *LONG, "frontend_unit"]
    assert sorted(names) == sorted(planned)
    if jobs == 1:
        assert names == planned  # the reference mode prints in plan order
    else:
        assert names[:5] == planned[:5]  # the serial prefix prints first, in order


@pytest.mark.parametrize("jobs", [2, 4])
def test_a_red_preflight_stops_the_others_and_writes_no_marker(tmp_path, capsys, jobs):
    repo = make_repo(tmp_path)
    runner = ThreadRunner(fail={"preflight"}, block={"ci_checks", "domain_tests", "app_tests"})
    assert run_jobs(repo, tmp_path, runner, jobs) == 1
    out = capsys.readouterr().out
    ran = [Path(c[2]).stem for c in runner.calls]
    assert ran[:3] == CHEAP and set(ran) >= {"preflight", "ci_checks"}
    if jobs == TWO_WORKERS:  # two workers: domain_tests and app_tests were queued and never started
        assert set(ran) == {*CHEAP, "preflight", "ci_checks"}
        assert "FAIL domain_tests 0.0s stopped: preflight failed" in out
        assert "FAIL app_tests 0.0s stopped: preflight failed" in out
        assert "stopped: preflight failed" in (tmp_path / "l" / "domain_tests.log").read_text(encoding="utf-8")
    assert "FAIL preflight " in out and "FAIL ci_checks " in out  # the killed one is a FAIL too
    assert "STOP: preflight failed" in out and "TOTAL FAIL" in out
    assert not any(ln.startswith("PASS ci_checks") for ln in out.splitlines())
    assert not prepush.has_marker(str(repo), sha_of(repo))


def test_a_red_non_preflight_step_in_parallel_lets_the_others_finish_and_writes_no_marker(tmp_path, capsys):
    repo = make_repo(tmp_path)
    runner = ThreadRunner(fail={"domain_tests"})
    assert run_jobs(repo, tmp_path, runner, 4) == 1
    assert sorted(Path(c[2]).stem for c in runner.calls) == sorted(NAMES)
    out = capsys.readouterr().out
    assert "FAIL domain_tests " in out and "PASS app_tests " in out and "PASS ci_checks " in out
    assert "STOP" not in out and "failed: domain_tests" in out
    assert not prepush.has_marker(str(repo), sha_of(repo))


def test_an_exception_inside_a_worker_is_a_fail_and_writes_no_marker(tmp_path, capsys):
    repo = make_repo(tmp_path)
    runner = ThreadRunner(raises={"app_tests"})
    assert run_jobs(repo, tmp_path, runner, 4) == 1
    out = capsys.readouterr().out
    assert "FAIL app_tests " in out and "PASS ci_checks " in out and "failed: app_tests" in out
    assert "worker blew up" in (tmp_path / "l" / "app_tests.log").read_text(encoding="utf-8")
    assert not prepush.has_marker(str(repo), sha_of(repo))


def test_jobs_1_prints_exactly_the_serial_loops_lines(tmp_path, capsys):
    repo = make_repo(tmp_path)
    assert run_jobs(repo, tmp_path, Runner(), 1) == 0
    lines = capsys.readouterr().out.splitlines()
    steps = [ln for ln in lines if ln.startswith("PASS ") and "TOTAL" not in ln]
    assert [ln.split()[1] for ln in steps] == NAMES
    assert all(re.fullmatch(r"PASS \w+ \d+\.\d+s \S+\.log", ln) for ln in steps)
    assert lines[-1].startswith("TOTAL PASS ")


@pytest.mark.parametrize(("option", "env", "want"), [("3", {}, 3), (None, {"PREPUSH_JOBS": "5"}, 5),
                                                      ("2", {"PREPUSH_JOBS": "9"}, 2),  # the option wins
                                                      (None, {}, os.cpu_count() or 1), (" 4 ", {}, 4)])
def test_resolve_jobs(option, env, want):
    assert prepush.resolve_jobs(option, env) == want


@pytest.mark.parametrize("bad", ["0", "-1", "abc", "1.5", "2x"])
def test_resolve_jobs_rejects_bad_values_and_main_exits_2(tmp_path, monkeypatch, capsys, bad):
    with pytest.raises(ValueError, match="jobs"):
        prepush.resolve_jobs(bad, {})
    with pytest.raises(ValueError, match="jobs"):
        prepush.resolve_jobs(None, {"PREPUSH_JOBS": bad})
    monkeypatch.delenv("PREPUSH_JOBS", raising=False)
    assert prepush.main(["--repo", str(tmp_path), "--jobs", bad]) == USAGE_RC
    monkeypatch.setenv("PREPUSH_JOBS", bad)
    assert prepush.main(["--repo", str(tmp_path)]) == USAGE_RC
    assert "usage error" in capsys.readouterr().out


def test_the_marker_records_the_mode_and_the_total_line_form(tmp_path, capsys):
    repo = make_repo(tmp_path)
    assert run_jobs(repo, tmp_path, ThreadRunner(), 3) == 0
    body = json.loads(Path(prepush.marker_path(str(repo), sha_of(repo))).read_text(encoding="utf-8"))
    assert body["mode"] == {"jobs": 3, "lane": "full"}
    last = capsys.readouterr().out.strip().splitlines()[-1]
    assert re.fullmatch(r"TOTAL PASS \d+\.\d+s \(steps sum \d+\.\d+s, jobs 3\) marker \S.*\.json", last), last
    assert [s["name"] for s in body["steps"]] == NAMES  # plan order whatever the finishing order


def test_a_step_that_never_ran_can_not_count_as_passed(tmp_path, monkeypatch, capsys):
    repo = make_repo(tmp_path)
    full = prepush._run_steps

    def partial(plan, log_dir, clock):
        return full(plan, log_dir, clock)[:-1]  # every rc 0, but app_tests has no result

    monkeypatch.setattr(prepush, "_run_steps", partial)
    assert run_jobs(repo, tmp_path, Runner(), 1) == 1
    assert not prepush.has_marker(str(repo), sha_of(repo))
    assert "TOTAL FAIL" in capsys.readouterr().out


def test_complete_is_a_structural_check():
    row = lambda n, rc=0: (n, rc, 0.0, "x.log")  # noqa: E731
    assert prepush.complete([row("a"), row("b")], ["b", "a"])
    assert not prepush.complete([row("a")], ["a", "b"])  # missing
    assert not prepush.complete([row("a"), row("b"), row("c")], ["a", "b"])  # unplanned
    assert not prepush.complete([row("a"), row("a")], ["a"])  # duplicate
    assert not prepush.complete([row("a"), row("b", prepush.STOPPED_RC)], ["a", "b"])  # stopped


# ---- proxy notice ----

def test_the_proxy_notice_names_the_variables_and_never_their_values(monkeypatch):
    for name in prepush.PROXY_VARS:
        monkeypatch.delenv(name, raising=False)
    assert prepush.proxy_notice() is None
    monkeypatch.setenv("HTTPS_PROXY", "http://user:secret@proxy.example:3128")
    monkeypatch.setenv("all_proxy", "socks5://other-secret@proxy.example:1080")
    monkeypatch.setenv("HTTP_PROXY", "")  # set but empty: not a proxy
    text = prepush.proxy_notice()
    assert text.startswith("NOTICE: proxy variables set (HTTPS_PROXY, all_proxy): tests that expect the egress gate")
    assert "secret" not in text and "proxy.example" not in text and "HTTP_PROXY" not in text.replace("HTTPS_PROXY", "")
    assert text.endswith("them unset (runbook, Before a push)")


def test_run_all_prints_the_proxy_notice_once_and_it_changes_no_verdict(tmp_path, monkeypatch, capsys):
    for name in prepush.PROXY_VARS:
        monkeypatch.delenv(name, raising=False)
    repo = make_repo(tmp_path)
    assert prepush.run_all(str(repo), runner=Runner(), log_dir=str(tmp_path / "a")) == 0
    assert "NOTICE" not in capsys.readouterr().out
    monkeypatch.setenv("HTTP_PROXY", "http://hidden-value:1")
    assert prepush.run_all(str(repo), runner=Runner(), log_dir=str(tmp_path / "b")) == 0  # still passes
    out = capsys.readouterr().out
    assert out.count("NOTICE: proxy variables set (HTTP_PROXY)") == 1 and "hidden-value" not in out
    assert prepush.has_marker(str(repo), sha_of(repo))


# ---- docs-only lane ----

REPO_ROOT = Path(__file__).resolve().parents[2]
SKIPPED_STEPS = ["ruff_ratchet", "alembic_guard"]


def docs_repo(tmp_path):
    """A repo with tools/change_scope.py (copied from this one) and origin/main at its first commits."""
    repo = make_repo(tmp_path)
    (repo / "tools").mkdir()
    (repo / "tools" / "change_scope.py").write_text((REPO_ROOT / "tools" / "change_scope.py").read_text("utf-8"),
                                                    encoding="utf-8")
    commit_file(repo, "docs/old.md", "old")
    commit_file(repo, "backend/old.py", "x = 1\n")
    git(repo, "add", "tools")
    git(repo, "commit", "-q", "-m", "tools")
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    return repo


def docs_count(repo):
    return prepush.docs_only_change(str(repo), sha_of(repo))


def test_a_docs_only_diff_counts_its_files_additions_modifications_and_deletions(tmp_path):
    repo = docs_repo(tmp_path)
    assert docs_count(repo) is None  # nothing changed: an empty diff is not a docs lane
    commit_file(repo, "spec/new.md", "n")
    commit_file(repo, "docs/old.md", "changed")
    commit_file(repo, "README.md", "root markdown")
    assert docs_count(repo) == 3  # noqa: PLR2004
    git(repo, "rm", "-q", "docs/old.md")
    git(repo, "commit", "-q", "-m", "delete a records file")
    assert docs_count(repo) == 3  # noqa: PLR2004  # a deleted records file is still one changed file


@pytest.mark.parametrize("rel", ["backend/x.py", "tools/x.py", ".github/x.yml", "notes.txt", "docs/script.py",
                                 "docs/test_x.md", "unknown/x.md"])
def test_an_unknown_path_anywhere_in_the_diff_is_the_full_lane(tmp_path, rel):
    repo = docs_repo(tmp_path)
    commit_file(repo, "docs/fine.md", "ok")
    assert docs_count(repo) == 1
    commit_file(repo, rel, "x")
    assert docs_count(repo) is None


def test_deleting_a_code_file_renaming_one_or_changing_a_mode_is_the_full_lane(tmp_path):
    repo = docs_repo(tmp_path)
    git(repo, "rm", "-q", "backend/old.py")
    git(repo, "commit", "-q", "-m", "delete code")
    assert docs_count(repo) is None
    git(repo, "reset", "-q", "--hard", "origin/main")
    git(repo, "mv", "backend/old.py", "docs/moved.md")
    git(repo, "commit", "-q", "-m", "rename code into docs")
    assert docs_count(repo) is None  # with --no-renames it is a deletion of a code path plus an addition
    git(repo, "reset", "-q", "--hard", "origin/main")
    git(repo, "update-index", "--chmod=+x", "docs/old.md")
    git(repo, "commit", "-q", "-m", "mode")
    assert docs_count(repo) is None


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privileges on Windows")
def test_a_symlink_is_the_full_lane(tmp_path):
    repo = docs_repo(tmp_path)
    (repo / "docs" / "ln.md").symlink_to("old.md")
    git(repo, "add", "docs/ln.md")
    git(repo, "commit", "-q", "-m", "symlink")
    assert docs_count(repo) is None


def test_no_merge_base_a_git_failure_or_an_import_failure_is_the_full_lane(tmp_path):
    repo = docs_repo(tmp_path)
    commit_file(repo, "docs/fine.md", "ok")
    assert docs_count(repo) == 1
    assert prepush.docs_only_change(str(repo), sha_of(repo), base="origin/missing") is None  # no merge base
    assert prepush.docs_only_change(str(tmp_path / "not-a-repo"), "HEAD") is None  # git fails
    (repo / "tools" / "change_scope.py").write_text("raise RuntimeError('broken')\n", encoding="utf-8")
    assert docs_count(repo) is None  # import failure
    (repo / "tools" / "change_scope.py").unlink()
    assert docs_count(repo) is None


def test_docs_only_entries_fails_closed_on_every_odd_shape():
    spec = importlib.util.spec_from_file_location("cs_for_test", REPO_ROOT / "tools" / "change_scope.py")
    scope = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = scope
    spec.loader.exec_module(scope)
    ok = ("A", ["docs/a.md"], ("000000", "100644"))
    assert prepush.docs_only_entries(scope.path_is_docs, [ok]) == 1
    assert prepush.docs_only_entries(scope.path_is_docs, []) is None
    odd = [("A", ["docs/../backend/x.py"], ("000000", "100644")),  # a path with ..
           ("A", ["../docs/x.md"], ("000000", "100644")),
           ("D", ["backend/x.py"], ("100644", "000000")),  # deleting a code file
           ("R", ["docs/a.md", "docs/b.md"], ("100644", "100644")),  # a rename
           ("T", ["docs/a.md"], ("100644", "120000")),
           ("M", ["docs/a.md"], ("100644", "100755")),  # mode change
           ("M", ["docs/a.md"], ("100755", "100755")),
           ("A", ["docs/a.md"], ("000000", "120000")),  # symlink
           ("A", ["docs/sub"], ("000000", "160000")),  # submodule
           ("M", ["docs/a.md", "docs/b.md"], ("100644", "100644")),
           ("A", [], ("000000", "100644"))]
    for entry in odd:
        assert prepush.docs_only_entries(scope.path_is_docs, [ok, entry]) is None, entry


def test_full_never_asks_for_the_docs_lane(tmp_path, capsys):
    def boom(repo, sha):
        raise AssertionError("must not be asked with --full")

    repo = make_repo(tmp_path)
    rc = prepush.run_all(str(repo), full=True, runner=Runner(), log_dir=str(tmp_path / "l"), select_docs_only=boom)
    assert rc == 0
    assert "SKIP" not in capsys.readouterr().out


def run_docs(repo, tmp_path, runner, count=3, jobs=1, **kw):
    kw.setdefault("select_docs_app", lambda r: (0, ["tests_app/test_reads_docs.py"], "1 files"))
    return prepush.run_all(str(repo), runner=runner, log_dir=str(tmp_path / "l"), jobs=jobs,
                           select_docs_only=lambda r, sha: count, **kw)


@pytest.mark.parametrize("jobs", [1, 4])
def test_a_docs_only_change_skips_nothing_and_runs_the_docs_reading_app_tests(tmp_path, capsys, jobs):
    repo = make_repo(tmp_path)
    runner = ThreadRunner()

    def no_code_selector(r):
        raise AssertionError("the code app-test selector must not be used in the docs lane")

    def frontend_would_fail(r):  # a frontend step would FAIL here (no node_modules): it must not even be planned
        return ["src/a.js"]

    assert run_docs(repo, tmp_path, runner, jobs=jobs, select_app=no_code_selector,
                    select_frontend=frontend_would_fail, which=which) == 0
    out = capsys.readouterr().out
    assert sorted(Path(c[2]).stem for c in runner.calls) == sorted(NAMES)  # all seven steps ran, ruff and alembic too
    assert "SKIP" not in out and "frontend_" not in out and "PASS ruff_ratchet" in out and "PASS alembic_guard" in out
    app = next(c[0] for c in runner.calls if Path(c[2]).stem == "app_tests")
    assert app[-1] == "tests_app/test_reads_docs.py"
    body = json.loads(Path(prepush.marker_path(str(repo), sha_of(repo))).read_text(encoding="utf-8"))
    assert body["mode"] == {"jobs": jobs, "lane": "docs-only (3 files)"}
    assert [s["name"] for s in body["steps"]] == NAMES
    assert all("skipped" not in s and s["rc"] == 0 for s in body["steps"])
    assert prepush.SKIPPABLE == ()


@pytest.mark.parametrize("failing", ["ruff_ratchet", "alembic_guard", "coverage"])
def test_a_red_step_in_the_docs_lane_blocks_the_marker(tmp_path, failing):
    # round 1: a local ruff version difference made the old gate refuse; the docs lane must refuse the same way
    repo = make_repo(tmp_path)
    assert run_docs(repo, tmp_path, Runner(fail={failing})) == 1
    assert not prepush.has_marker(str(repo), sha_of(repo))


def test_any_skip_row_blocks_the_marker(tmp_path, monkeypatch, capsys):
    repo = make_repo(tmp_path)
    sneaky = ("docs-only (3 files)", {"ruff_ratchet": "x"}, True)
    monkeypatch.setattr(prepush, "_lane", lambda repo, full, sel, sha: sneaky)
    assert run_docs(repo, tmp_path, Runner()) == 1
    assert not prepush.has_marker(str(repo), sha_of(repo))
    assert "TOTAL FAIL" in capsys.readouterr().out
    row = lambda n: (n, 0, 0.0, "x.log")  # noqa: E731
    everything = ["ruff_ratchet", "coverage"]
    assert not prepush.complete([row("coverage")], everything, skips=("ruff_ratchet",))  # SKIPPABLE is empty
    assert not prepush.complete([row("coverage")], everything, skips=())  # a step with no result and no skip
    assert prepush.complete([row("ruff_ratchet"), row("coverage")], everything)


def test_the_lane_is_decided_on_the_start_sha_not_on_a_moved_head(tmp_path):
    repo = docs_repo(tmp_path)
    commit_file(repo, "docs/fine.md", "ok")
    start = sha_of(repo)
    commit_file(repo, "backend/x.py", "x = 1\n")  # HEAD moves while the lane is being decided
    assert prepush.docs_only_change(str(repo), start) == 1
    assert prepush.docs_only_change(str(repo), sha_of(repo)) is None
    assert prepush.docs_only_change(str(repo)) is None  # no sha: symbolic HEAD


def test_run_all_hands_the_start_sha_to_the_lane_decision(tmp_path):
    repo = make_repo(tmp_path)
    seen = []
    run_all_sha = sha_of(repo)
    prepush.run_all(str(repo), runner=Runner(), log_dir=str(tmp_path / "l"),
                    select_docs_only=lambda r, sha: seen.append(sha))
    assert seen == [run_all_sha]


def test_a_change_to_change_scope_itself_is_the_full_lane(tmp_path):
    repo = docs_repo(tmp_path)
    commit_file(repo, "docs/fine.md", "ok")
    assert docs_count(repo) == 1
    scope_file = repo / "tools" / "change_scope.py"
    scope_file.write_text(scope_file.read_text("utf-8") + "\n# loosened\n", encoding="utf-8")
    git(repo, "commit", "-q", "-am", "edit the classifier")
    assert docs_count(repo) is None
    entries = [("A", ["docs/a.md"], ("000000", "100644")), ("M", ["tools/change_scope.py"], ("100644", "100644"))]
    assert prepush.docs_only_entries(lambda p: True, entries) is None  # even if a loosened classifier said docs


def test_a_real_docs_only_branch_runs_the_docs_lane_end_to_end(tmp_path, capsys):
    repo = docs_repo(tmp_path)
    (repo / "tests_app").mkdir()
    commit_file(repo, "tests_app/test_reads.py", 'P = ROOT / "spec" / "decisions" / "ADR-1.md"\n')
    commit_file(repo, "tests_app/test_plain.py", "x = 1\n")
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    commit_file(repo, "spec/decisions/ADR-1.md", "text")
    runner = Runner()
    assert prepush.run_all(str(repo), runner=runner, log_dir=str(tmp_path / "l")) == 0
    out = capsys.readouterr().out
    assert "LANE docs-only (1 files): nothing is skipped" in out and "SKIP" not in out
    app = next(c[0] for c in runner.calls if Path(c[2]).stem == "app_tests")
    assert app[-1] == "tests_app/test_reads.py" and "tests_app/test_plain.py" not in app
    body = json.loads(Path(prepush.marker_path(str(repo), sha_of(repo))).read_text(encoding="utf-8"))
    assert body["mode"]["lane"] == "docs-only (1 files)"


def test_the_app_selection_picks_the_files_that_read_docs_paths(tmp_path):
    repo = docs_repo(tmp_path)
    apps = repo / "tests_app"
    (apps / "sub").mkdir(parents=True)
    (apps / "test_joins.py").write_text('P = ROOT / "spec" / "decisions" / "ADR-210.md"\n', encoding="utf-8")
    (apps / "test_literal.py").write_text('P = Path("docs/api/openapi.json")\n', encoding="utf-8")
    (apps / "test_os_join.py").write_text('P = os.path.join(ROOT, "views", "spec-digest.md")\n', encoding="utf-8")
    (apps / "test_plain.py").write_text('opts.get("plans", "closed")\nX = "frontend/src/a.js"\n', encoding="utf-8")
    (apps / "_paths.py").write_text('DIGEST = "views/spec-digest.md"\n', encoding="utf-8")
    (apps / "test_via_helper.py").write_text("import _paths\n", encoding="utf-8")
    (apps / "sub" / "conftest.py").write_text('F = "knowledge/findings/x.json"\n', encoding="utf-8")
    (apps / "sub" / "test_under_conftest.py").write_text("x = 1\n", encoding="utf-8")
    rc, files, message = prepush.select_docs_app_tests(str(repo))
    assert rc == 0, message
    assert files == ["tests_app/sub/test_under_conftest.py", "tests_app/test_joins.py", "tests_app/test_literal.py",
                     "tests_app/test_os_join.py", "tests_app/test_via_helper.py"]
    assert "tests_app/test_plain.py" not in files


def test_the_app_selection_fails_closed(tmp_path):
    repo = docs_repo(tmp_path)
    rc, files, message = prepush.select_docs_app_tests(str(repo))  # no tests_app/
    assert rc == 1 and files == [] and "tests_app" in message
    (repo / "tests_app").mkdir()
    (repo / "tests_app" / "test_bad.py").write_bytes(b"\xff\xfe not utf-8 \x80")
    assert prepush.select_docs_app_tests(str(repo))[0] == 1  # unreadable file
    (repo / "tests_app" / "test_bad.py").unlink()
    assert prepush.select_docs_app_tests(str(repo))[0] == 0
    (repo / "tools" / "change_scope.py").unlink()
    assert prepush.select_docs_app_tests(str(repo))[0] == 1  # cannot load the docs folder names


def test_a_selection_error_in_the_docs_lane_is_a_fail(tmp_path):
    repo = make_repo(tmp_path)
    assert run_docs(repo, tmp_path, Runner(), select_docs_app=lambda r: (1, [], "cannot select")) == 1
    assert "cannot select" in (tmp_path / "l" / "app_tests.log").read_text(encoding="utf-8")
    assert not prepush.has_marker(str(repo), sha_of(repo))


# ---- Ctrl-C and the kill path ----

def test_a_keyboard_interrupt_kills_the_child_tree_and_is_reraised(tmp_path, monkeypatch):
    killed = []

    class Interrupted(FakePopen):
        def wait(self, timeout=None):
            raise KeyboardInterrupt

    monkeypatch.setattr(prepush.subprocess, "Popen", Interrupted)
    monkeypatch.setattr(prepush, "kill_tree", killed.append)
    with pytest.raises(KeyboardInterrupt):
        prepush.RealRunner(repo=str(tmp_path))(["x"], str(tmp_path), str(tmp_path / "s.log"))
    assert len(killed) == 1 and isinstance(killed[0], Interrupted)


@pytest.mark.skipif(sys.platform == "win32", reason="the test sends SIGINT to itself")
def test_a_keyboard_interrupt_in_the_main_thread_stops_the_workers_and_writes_no_marker(tmp_path):
    repo = make_repo(tmp_path)

    class Interrupting(ThreadRunner):
        def __call__(self, cmd, cwd, log_path):
            if Path(log_path).stem == "domain_tests":
                os.kill(os.getpid(), signal.SIGINT)  # a real Ctrl-C: the main thread is waiting on the workers
            return super().__call__(cmd, cwd, log_path)

    runner = Interrupting(block={"ci_checks", "domain_tests", "app_tests"})
    # A process started in the background from a non-interactive shell inherits SIGINT as ignored and Python then
    # installs no handler: the signal above would do nothing and this test failed ("DID NOT RAISE") only when the
    # gate was launched that way. Install the default handler for the test and put the old disposition back.
    previous = signal.signal(signal.SIGINT, signal.default_int_handler)
    try:
        with pytest.raises(KeyboardInterrupt):
            run_jobs(repo, tmp_path, runner, 4)
    finally:
        signal.signal(signal.SIGINT, previous)
    assert runner.stop.is_set()  # the workers saw it and ended (the pool was joined before the exception left)
    assert not prepush.has_marker(str(repo), sha_of(repo))


def test_a_missing_taskkill_falls_back_to_proc_kill_and_never_crashes(monkeypatch):
    monkeypatch.setattr(prepush, "IS_WINDOWS", True)

    def no_taskkill(cmd, **kwargs):
        raise FileNotFoundError(cmd[0])

    monkeypatch.setattr(prepush.subprocess, "run", no_taskkill)
    calls = []

    class Proc:
        pid = 7

        def kill(self):
            calls.append("kill")

        def wait(self, timeout=None):
            return 1

    prepush.kill_tree(Proc())
    assert calls == ["kill"]
