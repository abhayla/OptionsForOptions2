"""prepush.py: step order, every step runs, exit code, marker only on all-pass + clean tracked tree.
Injected runner and a temp git repo; the real suites are never run here."""
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "orchestrator"))
import prepush

NAMES = ["ci_checks", "domain_tests", "app_tests", "ruff_ratchet", "coverage", "alembic_guard"]
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
    assert tails[0].startswith("tools/ci_local.py --workflow ")
    assert tails[0].endswith("ci-no-pytest.yml --no-tests")
    assert tails[1:] == ["-m pytest -q -p no:cacheprovider tests/test_a.py",
                         "-m pytest -c pytest-app.ini -q -p no:cacheprovider tests_app/test_b.py",
                         "scripts/ruff_ratchet.py", "scripts/orchestrator/coverage.py . --check",
                         "scripts/alembic_migration_guard.py"]
    assert all(Path(c[1]) == repo for c in runner.calls)
    assert all(repo not in Path(c[2]).parents for c in runner.calls)
    out = capsys.readouterr().out
    assert out.count("PASS ") == len(NAMES) + 1  # six steps + TOTAL PASS
    assert "TOTAL PASS" in out


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
    assert runner.calls[0][0][-1] == "--no-tests"


def test_a_none_selection_runs_all_of_tests(tmp_path, monkeypatch):
    monkeypatch.setattr(prepush, "select_domain_tests", lambda repo, base="origin/main": None)
    repo = make_repo(tmp_path)
    runner = Runner()
    prepush.run_all(str(repo), runner=runner, log_dir=str(tmp_path / "l"))
    assert runner.calls[1][0][-1] == "tests/"
    assert runner.calls[1][0][1:3] == ["-m", "pytest"]


def test_full_runs_all_of_tests_without_asking_the_selector(tmp_path, monkeypatch):
    def boom(repo, base="origin/main"):
        raise AssertionError("selector must not be asked")

    monkeypatch.setattr(prepush, "select_domain_tests", boom)
    repo = make_repo(tmp_path)
    runner = Runner()
    assert prepush.run_all(str(repo), full=True, runner=runner, log_dir=str(tmp_path / "l")) == 0
    assert runner.calls[1][0][-1] == "tests/"


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


class FakeRun:
    def __init__(self, exc=None):
        self.exc, self.kwargs = exc, None

    def __call__(self, cmd, **kwargs):
        self.kwargs = kwargs
        if self.exc:
            raise self.exc
        return subprocess.CompletedProcess(cmd, 0)


def test_the_child_run_never_carries_the_db_urls(tmp_path, monkeypatch):
    # review F4: under db_run.py these are set; the selected DB tests must still not reach the shared host
    for key in prepush.DB_ENV:
        monkeypatch.setenv(key, "postgresql://prod-host/x")
    monkeypatch.setenv("OFO_KEEP_ME", "1")
    fake = FakeRun()
    monkeypatch.setattr(prepush.subprocess, "run", fake)
    assert prepush.real_runner(["python", "-V"], str(tmp_path), str(tmp_path / "x.log")) == 0
    env = fake.kwargs["env"]
    assert set(prepush.DB_ENV) == {"TEST_DATABASE_URL", "TEST_ADMIN_DATABASE_URL", "ALEMBIC_DATABASE_URL"}
    assert not set(prepush.DB_ENV) & set(env)
    assert env["OFO_KEEP_ME"] == "1"


def test_a_timed_out_or_unstartable_step_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(prepush.subprocess, "run", FakeRun(subprocess.TimeoutExpired("x", 1)))
    log = tmp_path / "t.log"
    assert prepush.real_runner(["x"], str(tmp_path), str(log)) == prepush.TIMEOUT_RC
    assert "timed out" in log.read_text(encoding="utf-8")
    monkeypatch.setattr(prepush.subprocess, "run", FakeRun(FileNotFoundError("npm")))
    assert prepush.real_runner(["npm"], str(tmp_path), str(log)) == 1
    assert "could not start npm" in log.read_text(encoding="utf-8")


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
    front = runner.calls[len(NAMES):]
    assert [c[0] for c in front] == [
        ["/fake/bin/npm", "run", "lint"],
        ["/fake/bin/npx", "vitest", "related", "--run", "src/components/LegPicker.vue", "tests/leg-picker.test.js"],
        ["/fake/bin/npm", "run", "build"]]
    assert all(Path(c[1]) == repo / "frontend" for c in front)
    out = capsys.readouterr().out
    assert all(f"PASS {n} " in out for n in FRONT)
    assert prepush.has_marker(str(repo), sha_of(repo))
    body = json.loads(Path(prepush.marker_path(str(repo), sha_of(repo))).read_text(encoding="utf-8"))
    assert [s["name"] for s in body["steps"]] == NAMES + FRONT


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
    assert runner.calls[len(NAMES) + 1][0] == ["/fake/bin/npx", "vitest", "run"]
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
    assert runner.calls[len(NAMES) + 1][0] == ["/fake/bin/npx", "vitest", "run"]


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
