"""gate_env.py: the merge path's children ignore .git/info/grafts (Tier A review of PR #546, 2026-10-25).

Real git on a throwaway repository: one graft line empties the three-dot file list the kit 1.12.0 gate reads for a
truncated pull request; the helper's environment brings the changed file back.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "orchestrator"))
import gate_env
import land


def git(repo, *args, env=None):
    # the same flag the kit gate passes (merge_when_green.py, local git helper)
    r = subprocess.run(["git", "--no-replace-objects", *args], cwd=repo, capture_output=True, text=True,  # noqa: S603, S607
                       env=env, check=False)
    return r.stdout.strip()


@pytest.fixture
def grafted_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "t@example.invalid")
    git(repo, "config", "user.name", "t")
    (repo / "a.txt").write_text("a\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "base")
    base = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "-qb", "pr")
    (repo / "b.txt").write_text("b\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "pr change")
    head = git(repo, "rev-parse", "HEAD")
    assert git(repo, "diff", "--name-only", f"{base}...{head}") == "b.txt"
    (repo / ".git" / "info" / "grafts").write_text(head + "\n", encoding="utf-8")  # head loses its parent
    return repo, base, head


def test_a_graft_hides_the_change_without_the_helper(grafted_repo):
    repo, base, head = grafted_repo
    assert git(repo, "diff", "--name-only", f"{base}...{head}") == ""


def test_the_helper_env_brings_the_change_back(grafted_repo):
    repo, base, head = grafted_repo
    assert git(repo, "diff", "--name-only", f"{base}...{head}", env=gate_env.no_graft_env()) == "b.txt"


def test_the_graft_path_cannot_exist_and_differs_per_call():
    first, second = gate_env.no_graft_env()["GIT_GRAFT_FILE"], gate_env.no_graft_env()["GIT_GRAFT_FILE"]
    assert first != second
    assert not os.path.exists(first) and not os.path.exists(os.path.dirname(first))


def test_land_real_runner_passes_the_helper_env(monkeypatch):
    seen = {}

    def fake_run(cmd, **kw):
        seen.update(kw)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(land.subprocess, "run", fake_run)
    land.real_runner(["git", "--version"])
    assert not os.path.exists(seen["env"]["GIT_GRAFT_FILE"])
