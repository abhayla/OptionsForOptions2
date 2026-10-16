"""land.py: push -> PR -> merge gate in one command, with a faked command runner (no network, no real git/gh)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "orchestrator"))
import gh_issue
import land

GATE = "merge_when_green.py"
TWICE = 2


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
            "list-run": (0, json.dumps([{"databaseId": 4242}])),
        }
        by_prefix = {("gh", "pr", "list"): "list-pr", ("gh", "pr", "create"): "create-pr",
                     ("gh", "pr", "view"): "view-pr", ("gh", "pr", "update-branch"): "update-pr",
                     ("gh", "run", "list"): "list-run"}
        key = by_prefix.get(tuple(cmd[:3]))
        key = key or next((k for k in ("rev-parse", "origin/main..HEAD") if k in cmd), None)
        return answers.get(key, (0, ""))

    def ran(self, *words):
        return [c for c in self.calls if all(w in " ".join(c) for w in words)]


def run(fake, tmp_path, capsys):
    body = tmp_path / "body.md"
    body.write_text("body", encoding="utf-8")
    env = land.Env(runner=fake, sleep=lambda s: None, tmp_dir=str(tmp_path))
    rc = land.land("wt", "title", str(body), env)
    return rc, capsys.readouterr().out


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
    fake = Fake([(1, "REFUSED: PR 77 has a failing check: lint=pass, app-tests=fail")])
    rc, out = run(fake, tmp_path, capsys)
    assert rc == 1
    assert "failed job(s): app-tests" in out
    assert "gh run view 4242 --log-failed" in out
    assert not fake.ran("update-branch")


def test_other_refusal_does_not_loop(tmp_path, capsys):
    fake = Fake([(1, "REFUSED: not green within 20 min (x=pending)")])
    rc, _ = run(fake, tmp_path, capsys)
    assert rc == 1
    assert len(fake.ran(GATE)) == 1


def test_dry_run_runs_nothing_and_prints_commands(tmp_path, capsys):
    body = tmp_path / "b.md"
    body.write_text("b", encoding="utf-8")
    rc = land.main([str(Path(__file__).resolve().parents[2]), "--title", "t", "--body-file", str(body), "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "would run: git -C" in out and "push -u origin" in out
    assert "would run: gh pr create" in out
    assert "dry run: nothing was run" in out


def test_add_stage_inserts_inside_issues_block_and_keeps_crlf(tmp_path):
    f = tmp_path / "s.yaml"
    f.write_bytes(b'issues:\r\n  "#1": 4a  # one\r\n\r\nwork_items:\r\n  W-1: x\r\n')
    assert gh_issue.add_stage("294", "4a", "A  title", path=str(f))
    text = f.read_bytes().decode()
    assert text.index('"#294": 4a  # A title') < text.index("work_items:")
    assert "\r\n" in text and "\n" not in text.replace("\r\n", "")
    assert not gh_issue.add_stage("294", "4a", "again", path=str(f))
