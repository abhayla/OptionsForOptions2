"""land.py: push -> PR -> merge gate in one command, with a faked command runner (no network, no real git/gh)."""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "orchestrator"))
import gh_issue
import land

GATE = "merge_when_green.py"
TWICE = 2
SHA = "0123456789abcdef0123456789abcdef01234567"


class Fake:
    """Answers by command prefix; `gate` is a list of (rc, output) returned one per gate call."""

    def __init__(self, gate, close_rc=0, open_prs="[]", state="CLEAN", update_rc=0):
        self.gate = list(gate)
        self.close_rc = close_rc
        self.open_prs = open_prs
        self.state = state
        self.update_rc = update_rc
        self.calls = []

    def __call__(self, cmd, cwd=None):
        self.calls.append(cmd)
        joined = " ".join(cmd)
        if GATE in joined:
            return self.gate.pop(0)
        if "pr_close_check.py" in joined:
            return self.close_rc, "" if self.close_rc == 0 else "body line 1: closes #5"
        answers = {
            "rev-parse": (0, "feat/x\n"),
            "origin/main..HEAD": (0, "a commit\n---COMMIT---\n"),
            "list-pr": (0, self.open_prs),
            "create-pr": (0, "https://github.com/o/r/pull/77\n"),
            "view-pr": (0, self.state + "\n"),
            "update-pr": (self.update_rc, ""),
            "checks": (0, json.dumps([
                {"name": "app-tests", "state": "SUCCESS", "link": "https://github.com/o/r/actions/runs/111/job/1"},
                {"name": "lint-and-test", "state": "FAILURE", "link": "https://github.com/o/r/actions/runs/222/job/2"},
            ])),
        }
        by_prefix = {("gh", "pr", "list"): "list-pr", ("gh", "pr", "create"): "create-pr",
                     ("gh", "pr", "view"): "view-pr", ("gh", "pr", "update-branch"): "update-pr",
                     ("gh", "pr", "checks"): "checks"}
        key = by_prefix.get(tuple(cmd[:3]))
        key = key or next((k for k in ("rev-parse", "origin/main..HEAD") if k in cmd), None)
        return answers.get(key, (0, ""))

    def ran(self, *words):
        return [c for c in self.calls if all(w in " ".join(c) for w in words)]


def run(fake, tmp_path, capsys, reviewed_sha=SHA, **opts):
    """opts: marker (default True: the pre-push marker exists), skip_prepush (default: no skip)."""
    body = tmp_path / "body.md"
    body.write_text("body", encoding="utf-8")
    marker = opts.get("marker", True)
    env = land.Env(runner=fake, sleep=lambda s: None, tmp_dir=str(tmp_path), marker_check=lambda wt: marker)
    rc = land.land("wt", "title", str(body), env, reviewed_sha=reviewed_sha, skip_prepush=opts.get("skip_prepush", ""))
    return rc, capsys.readouterr().out


def test_no_pre_push_marker_stops_before_any_push(tmp_path, capsys):
    fake = Fake([(0, "merged")])
    rc, out = run(fake, tmp_path, capsys, marker=False)
    assert rc == 1
    assert not fake.ran("git", "push")
    assert not fake.ran("gh", "pr")
    assert "python scripts/orchestrator/prepush.py" in out
    assert "--skip-prepush REASON" in out
    assert "nothing was pushed" in out


def test_marker_present_pushes(tmp_path, capsys):
    fake = Fake([(0, "merged")])
    rc, _ = run(fake, tmp_path, capsys, marker=True)
    assert rc == 0
    assert fake.ran("git", "push", "-u", "origin", "feat/x")


def test_skip_prepush_with_a_reason_proceeds_and_prints_it(tmp_path, capsys):
    fake = Fake([(0, "merged")])
    rc, out = run(fake, tmp_path, capsys, marker=False, skip_prepush="docs-only, owner said so")
    assert rc == 0
    assert fake.ran("git", "push", "-u", "origin", "feat/x")
    assert "skipped (--skip-prepush): docs-only, owner said so" in out


def test_skip_prepush_without_a_reason_is_refused(tmp_path, capsys):
    repo, body = make_repo(tmp_path)
    for reason in ("", "   "):
        rc = land.main([str(repo), "--title", "t", "--body-file", str(body), "--reviewed-sha", SHA, "--dry-run",
                        "--skip-prepush", reason])
        assert rc == TWICE  # exit 2: bad input
        assert "non-empty reason" in capsys.readouterr().out


def test_the_behind_update_push_is_not_gated(tmp_path, capsys):
    """Only the first push needs the marker; the fallback push after merging origin/main is covered by CI."""
    checks = []
    fake = Fake([(1, "x"), (0, "merged")], state="BEHIND", update_rc=1)
    body = tmp_path / "body.md"
    body.write_text("body", encoding="utf-8")

    def marker(wt):
        checks.append(wt)
        return True

    env = land.Env(runner=fake, sleep=lambda s: None, tmp_dir=str(tmp_path), marker_check=marker)
    assert land.land("wt", "title", str(body), env, reviewed_sha=SHA) == 0
    assert len(fake.ran("git", "push", "origin", "feat/x")) == TWICE  # first push + fallback push
    assert checks == ["wt"]  # looked up once, for the first push only


def test_dry_run_prints_the_missing_marker_and_does_not_fail(tmp_path, capsys):
    repo, body = make_repo(tmp_path)
    rc = land.main([str(repo), "--title", "t", "--body-file", str(body), "--reviewed-sha", SHA, "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "would stop here" in out
    assert "prepush.py" in out


def test_the_gate_gets_the_reviewed_sha(tmp_path, capsys):
    """Kit 1.8.0 item 5: the merge gate refuses without --reviewed-sha, so every gate call carries it."""
    fake = Fake([(1, "REFUSED: head branch is not up to date"), (0, "merged")], state="BEHIND")
    rc, _ = run(fake, tmp_path, capsys)
    assert rc == 0
    gates = fake.ran(GATE)
    assert len(gates) == TWICE
    assert all(g[-2:] == ["--reviewed-sha", SHA] for g in gates)


def test_final_gate_refusals_stop_without_updating_even_when_behind(tmp_path, capsys):
    """Opus review MAJOR-1: RE-REVIEW NEEDED arrives while the PR is BEHIND and "updates exhausted" contains
    "behind"; neither may trigger land.py's own update-branch retries, which would hide the cause."""
    for refusal in ("RE-REVIEW NEEDED: backend/ofo/execution/basket.py",
                    "REFUSED: PR 77 is still behind its base after 3 updates (updates exhausted)",
                    "REFUSED: reviewed sha 0123456789ab is not an ancestor of head fedcba987654"):
        fake = Fake([(1, refusal)], state="BEHIND")
        rc, out = run(fake, tmp_path, capsys)
        assert rc == 1
        assert len(fake.ran(GATE)) == 1
        assert not fake.ran("update-branch")
        assert not fake.ran("merge", "--no-edit")
        assert "not updating the branch again" in out


def test_a_missing_or_short_reviewed_sha_stops_before_anything_runs(tmp_path, capsys):
    for bad in ("", SHA[:12], SHA[:-1] + "g", "HEAD"):
        fake = Fake([(0, "merged")])
        rc, out = run(fake, tmp_path, capsys, reviewed_sha=bad)
        assert rc == 1
        assert fake.calls == []
        assert "--reviewed-sha must be the full 40-character sha" in out


def test_an_agent_id_resolves_to_its_builder_worktree(tmp_path):
    """A real directory is used as given; anything else is a builder agent id under the builder-worktree folder."""
    assert land.resolve_worktree(str(tmp_path)) == str(tmp_path)
    resolved = Path(land.resolve_worktree("abc123"))
    assert resolved.name == "agent-abc123"
    assert resolved.parent.name == "worktrees"
    assert resolved.parent.parent == Path(land.ROOT) / ("." + "claude")


def test_a_push_behind_origin_fast_forwards_then_pushes_again(tmp_path, capsys):
    """GC-2e W-102: an earlier run's update-branch left a merge commit on origin only; the next push is refused as
    non-fast-forward. The tool takes origin's commits with --ff-only and pushes again; a refused fast-forward stops."""
    fake = Fake(gate=[(0, "merged")])
    pushes = []
    plain = fake.__call__

    def runner(cmd, cwd=None):
        if "push" in cmd:
            pushes.append(cmd)
            if len(pushes) == 1:
                fake.calls.append(cmd)
                return 1, " ! [rejected] feat/x -> feat/x (non-fast-forward)"
        return plain(cmd, cwd)

    rc, _ = run(runner, tmp_path, capsys)
    assert rc == 0
    assert len(pushes) == 2
    assert fake.ran("pull", "--ff-only", "origin", "feat/x")


def test_new_pr_is_created_then_merged(tmp_path, capsys):
    fake = Fake([(0, "merged")])
    rc, out = run(fake, tmp_path, capsys)
    assert rc == 0
    assert fake.ran("git", "push", "-u", "origin", "feat/x")
    assert fake.ran("gh", "pr", "create")
    assert fake.ran(GATE, "77")
    assert "MERGED PR #77 at " in out


def test_existing_open_pr_is_reused(tmp_path, capsys):
    fake = Fake([(0, "merged")], open_prs=json.dumps([{"number": 55}]))
    rc, out = run(fake, tmp_path, capsys)
    assert rc == 0
    assert not fake.ran("gh", "pr", "create")
    assert fake.ran(GATE, "55")
    assert "reusing open PR #55" in out


def test_close_check_failure_stops_before_push(tmp_path, capsys):
    fake = Fake([], close_rc=1)
    rc, out = run(fake, tmp_path, capsys)
    assert rc == 1
    assert not fake.ran("git", "push")
    assert not fake.ran("gh", "pr")
    assert "closing-reference check failed" in out


def test_behind_updates_branch_then_retries(tmp_path, capsys):
    fake = Fake([(1, "REFUSED: head branch is not up to date"), (0, "merged")], state="BEHIND")
    rc, _ = run(fake, tmp_path, capsys)
    assert rc == 0
    assert len(fake.ran("gh", "pr", "update-branch", "77")) == 1
    assert len(fake.ran(GATE)) == TWICE


def test_behind_falls_back_to_local_merge_when_update_branch_fails(tmp_path, capsys):
    fake = Fake([(1, "x"), (0, "merged")], state="BEHIND", update_rc=1)
    rc, _ = run(fake, tmp_path, capsys)
    assert rc == 0
    assert fake.ran("merge", "--no-edit", "origin/main")
    assert len(fake.ran("git", "push", "origin", "feat/x")) == TWICE  # first push + fallback push


def test_behind_gives_up_after_three_retries(tmp_path, capsys):
    fake = Fake([(1, "not up to date")] * 4, state="BEHIND")
    rc, out = run(fake, tmp_path, capsys)
    assert rc == 1
    assert len(fake.ran("gh", "pr", "update-branch")) == land.MAX_RETRIES
    assert "after 3 update-branch retries" in out


def test_red_ci_names_failed_job_and_log_hint(tmp_path, capsys):
    fake = Fake([(1, "REFUSED: PR 77 has a failing check: app-tests=pass, lint-and-test=fail")])
    rc, out = run(fake, tmp_path, capsys)
    assert rc == 1
    assert "failed job(s): lint-and-test" in out
    assert "gh run view 222 --log-failed" in out  # the failed job's own run, not the first run found
    assert "111" not in out
    assert not fake.ran("update-branch")


def test_other_refusal_does_not_loop(tmp_path, capsys):
    fake = Fake([(1, "REFUSED: not green within 20 min (x=pending)")])
    rc, _ = run(fake, tmp_path, capsys)
    assert rc == 1
    assert len(fake.ran(GATE)) == 1


def make_repo(tmp_path, detach=False):
    repo = tmp_path / "repo"
    repo.mkdir()
    base = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run([*base, "init", "-q", "-b", "feat/y"], check=True)  # noqa: S603
    subprocess.run([*base, "commit", "-q", "--allow-empty", "-m", "c"], check=True)  # noqa: S603
    if detach:
        subprocess.run([*base, "checkout", "-q", "--detach"], check=True)  # noqa: S603
    body = tmp_path / "b.md"
    body.write_text("b", encoding="utf-8")
    return repo, body


def test_dry_run_runs_nothing_and_prints_commands(tmp_path, capsys):
    repo, body = make_repo(tmp_path)
    rc = land.main([str(repo), "--title", "t", "--body-file", str(body), "--reviewed-sha", SHA, "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "push -u origin feat/y" in out
    assert "would run: gh pr create" in out
    assert "dry run: nothing was run" in out


def test_detached_head_without_branch_stops_clearly(tmp_path, capsys):
    repo, body = make_repo(tmp_path, detach=True)
    rc = land.main([str(repo), "--title", "t", "--body-file", str(body), "--reviewed-sha", SHA, "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "detached HEAD" in out
    assert "--branch" in out


def test_detached_head_with_branch_pushes_head_to_that_branch(tmp_path, capsys):
    repo, body = make_repo(tmp_path, detach=True)
    rc = land.main([str(repo), "--title", "t", "--body-file", str(body), "--reviewed-sha", SHA, "--dry-run",
                    "--branch", "feat/z"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "push -u origin HEAD:refs/heads/feat/z" in out
    assert "--head feat/z" in out


def test_add_stage_inserts_inside_issues_block_and_keeps_crlf(tmp_path):
    f = tmp_path / "s.yaml"
    f.write_bytes(b'issues:\r\n  "#1": 4a  # one\r\n\r\nwork_items:\r\n  W-1: x\r\n')
    assert gh_issue.add_stage("294", "4a", "A  title", path=str(f))
    text = f.read_bytes().decode()
    assert text.index('"#294": 4a  # A title') < text.index("work_items:")
    assert "\r\n" in text and "\n" not in text.replace("\r\n", "")
    assert not gh_issue.add_stage("294", "4a", "again", path=str(f))


def test_gh_issue_stage_adds_staged_label_and_plain_does_not():
    """Dies if --stage stops adding the `staged` label that gives the issue its 24 h coverage grace."""
    staged = gh_issue.create_cmd("app", "bug", "t", "b.md", stage="S1")
    plain = gh_issue.create_cmd("app", "bug", "t", "b.md")
    i = staged.index("staged")
    assert staged[i - 1] == "--label"
    assert "staged" not in plain and staged.count("--label") == 2 and plain.count("--label") == 1
