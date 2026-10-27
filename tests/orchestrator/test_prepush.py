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
        name = next(n for n in NAMES if Path(log_path).name == n + ".log")
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
    assert "tracked tree is dirty" in capsys.readouterr().out


def test_untracked_files_do_not_block_the_marker(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "scratch.txt").write_text("x", encoding="utf-8")
    assert prepush.run_all(str(repo), runner=Runner(), log_dir=str(tmp_path / "l")) == 0
    assert prepush.has_marker(str(repo), sha_of(repo))


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
