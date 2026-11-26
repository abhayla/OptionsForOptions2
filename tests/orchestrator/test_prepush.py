"""prepush.py: step order, every step runs, exit code, marker only on all-pass + clean tracked tree.
Injected runner and a temp git repo; the real suites are never run here."""
import json
import os
import re
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
