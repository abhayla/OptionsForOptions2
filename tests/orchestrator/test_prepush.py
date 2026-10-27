"""prepush.py: step order, every step runs, exit code, marker only on all-pass + clean tracked tree.
Injected runner and a temp git repo; the real suites are never run here."""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "orchestrator"))
import prepush

NAMES = ["ci_local", "ruff_ratchet", "coverage", "alembic_guard"]


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)  # noqa: S603, S607


def make_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "t@t")
    git(repo, "config", "user.name", "t")
    (repo / "a.txt").write_text("a", encoding="utf-8")
    git(repo, "add", "a.txt")
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
    assert tails == ["tools/ci_local.py", "scripts/ruff_ratchet.py", "scripts/orchestrator/coverage.py . --check",
                     "scripts/alembic_migration_guard.py"]
    assert all(Path(c[1]) == repo for c in runner.calls)
    assert all(repo not in Path(c[2]).parents for c in runner.calls)
    out = capsys.readouterr().out
    assert out.count("PASS ") == len(NAMES) + 1  # four steps + TOTAL PASS
    assert "TOTAL PASS" in out


def test_full_is_passed_through_to_ci_local(tmp_path):
    repo = make_repo(tmp_path)
    runner = Runner()
    prepush.run_all(str(repo), full=True, runner=runner, log_dir=str(tmp_path / "l"))
    assert runner.calls[0][0][-1] == "--full"
    assert "--full" not in runner.calls[1][0]


def test_later_steps_still_run_after_a_failure_and_exit_is_1(tmp_path, capsys):
    repo = make_repo(tmp_path)
    runner = Runner(fail={"ci_local"})
    rc = prepush.run_all(str(repo), runner=runner, log_dir=str(tmp_path / "l"))
    assert rc == 1
    assert len(runner.calls) == len(NAMES)
    out = capsys.readouterr().out
    assert "FAIL ci_local" in out
    assert "TOTAL FAIL" in out
    assert "failed: ci_local" in out


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
