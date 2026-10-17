"""Process tooling: stage_scorecard.py derives the delivery scorecard from recorded gh/git output.

Fixtures are hand-made under fixtures/scorecard/; window used: 2026-10-16T17:52Z (inclusive) .. 2026-10-17T12:00Z
(exclusive). Expected values are computed by hand in each docstring.
"""
import importlib.util
import json
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
_SPEC = importlib.util.spec_from_file_location(
    "stage_scorecard", HERE.parents[1] / "scripts" / "orchestrator" / "stage_scorecard.py")
sc = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(sc)

PR_ROWS = 2  # the scorecard prints two PR rows (by kind, lines by area)
SINCE, UNTIL =sc.parse_time("2026-10-16T17:52:00Z"), sc.parse_time("2026-10-17T12:00:00Z")


def load(name):
    return json.loads((HERE / "fixtures" / "scorecard" / name).read_text())


def window(rows, key):
    return [r for r in rows if sc.in_window(r[key], SINCE, UNTIL)]


def test_pr_window_and_kinds():
    """PR #3 merged exactly at until and #4 one second before since are out; kinds: build 1, docs 1, other 1 (solo)."""
    prs = window(load("prs.json"), "mergedAt")
    assert [p["number"] for p in prs] == [1, 2, 5]
    assert dict(sc.pr_kinds(prs)) == {"build": 1, "docs": 1, "other": 1}


def test_lines_by_area_counts_each_file_once():
    """PR1 spans product (10+3=13) and tests (5+2=7); PR2 docs 7, spec 4, tooling 6, other 1; PR5 evidence 9."""
    lines = sc.lines_by_area(window(load("prs.json"), "mergedAt"))
    assert dict(lines) == {"product code": 13, "tests": 7, "docs/process": 7, "spec/work/findings/views": 4,
                           "tooling": 6, "other": 1, "evidence": 9}


def test_ci_window_edges_and_conclusions():
    """Since-edge run (17:52:00) is in; until-edge run (12:00:00) and 17:51:59 are out.
    CI: success, failure, success = 3 total, 1 failure, 2 success. App tests: failure, cancelled, empty = 3 total."""
    summary = sc.ci_summary(window(load("runs.json"), "createdAt"))
    assert dict(summary["CI"]) == {"total": 3, "success": 2, "failure": 1}
    assert dict(summary["App tests"]) == {"total": 3, "failure": 1, "cancelled": 1, "other": 1}


def test_merge_only_and_round_commits():
    """Two main-merges (branch 'main', remote-tracking origin/main); the PR merge and plain commits do not count.
    Round commits: 'round 3', 'Fix round 2', 'r2: x'; 'around the corner' and 'ground 4' do not."""
    subjects = ["Merge branch 'main' into build/x", "Merge remote-tracking branch 'origin/main'",
                "Merge pull request #5 from a/b", "W-1: add thing", "W-1 round 3 fixes", "Fix round 2",
                "r2: tighten", "around the corner", "ground 4"]
    assert sc.merge_only_commits(subjects) == subjects[:2]
    assert sc.round_commits(subjects) == ["W-1 round 3 fixes", "Fix round 2", "r2: tighten"]


def test_gh_unavailable_prints_unmeasured_not_zero(monkeypatch, capsys):
    """gh missing -> exit 0; PR (2 rows) and CI (1 row) say 'unmeasured'; no figure of zero runs is shown."""
    def fake_run(cmd):
        if cmd[0] == "gh":
            return None, "gh unavailable (FileNotFoundError)"
        return "Merge branch 'main' into x\nW-1 round 2\n", ""
    monkeypatch.setattr(sc, "_run", fake_run)
    assert sc.main(["--since", "2026-10-16T17:52:00Z", "--until", "2026-10-17T12:00:00Z"]) == 0
    out = capsys.readouterr().out
    assert out.count("unmeasured: gh unavailable") == 3
    assert "0 runs" not in out and "0 total" not in out
    assert "| Merge-only commits | 1 of 2 |" in out


def test_empty_gh_list_is_unmeasured(monkeypatch):
    """gh printing `[]` is unmeasured, not a measured zero."""
    monkeypatch.setattr(sc, "_run", lambda cmd: ("[]", ""))
    assert sc._gh_json(["run", "list"]) == (None, "gh returned an empty list")


def test_truncated_fetch_is_unmeasured():
    """A fetch at its limit with oldest row newer than since may lack rows; below limit or reaching back is fine."""
    rows = [{"createdAt": "2026-10-17T00:00:00Z"}] * sc.RUN_LIMIT
    assert sc._truncated(rows, "createdAt", SINCE, sc.RUN_LIMIT)
    assert not sc._truncated(rows[:-1], "createdAt", SINCE, sc.RUN_LIMIT)
    older = [*rows, {"createdAt": "2026-10-16T00:00:00Z"}]
    assert not sc._truncated(older, "createdAt", SINCE, sc.RUN_LIMIT)


def test_merge_only_matches_all_main_merge_shapes():
    """Four main-into-branch shapes count; 'Merge pull request #N from ...' and look-alike names do not."""
    yes = ["Merge remote-tracking branch 'origin/main' into build/x", "Merge branch 'main' into build/x",
           "Merge origin/main into build/x", "Merge main into build/x"]
    no = ["Merge pull request #5 from abhayla/build/x", "Merge branch 'maintenance' into x",
          "Merge origin/mainline into x"]
    assert sc.merge_only_commits([*yes, *no]) == yes


def _drive(monkeypatch, capsys, prs, runs):
    def fake_run(cmd):
        if cmd[:2] == ["gh", "pr"]:
            return json.dumps(prs), ""
        if cmd[:2] == ["gh", "run"]:
            return json.dumps(runs), ""
        return "W-1: x\n", ""
    monkeypatch.setattr(sc, "_run", fake_run)
    assert sc.main(["--since", "2026-10-16T17:52:00Z", "--until", "2026-10-17T12:00:00Z"]) == 0
    return capsys.readouterr().out


def test_main_runs_at_limit_newer_than_since_is_unmeasured(monkeypatch, capsys):
    """1000 runs all created after --since: the CI row says unmeasured with the limit, no totals."""
    runs = [{"conclusion": "success", "createdAt": "2026-10-17T05:00:00Z", "workflowName": "CI"}] * sc.RUN_LIMIT
    out = _drive(monkeypatch, capsys, load("prs.json"), runs)
    assert f"| CI | unmeasured: gh run list hit the {sc.RUN_LIMIT} limit before the window start |" in out
    assert "CI runs" not in out


def test_main_prs_at_limit_newer_than_since_is_unmeasured(monkeypatch, capsys):
    """400 PRs merged after --since: both PR rows say unmeasured."""
    prs = [{"number": 1, "mergedAt": "2026-10-17T05:00:00Z", "headRefName": "a/b", "files": []}] * sc.LIMIT
    out = _drive(monkeypatch, capsys, prs, load("runs.json"))
    assert out.count("unmeasured: gh pr list hit the 400 limit") == PR_ROWS


def test_main_edge_timestamps(monkeypatch, capsys):
    """PR merged exactly at --since counts, exactly at --until does not; same for runs: 1 PR, 1 run."""
    prs = [{"number": 1, "mergedAt": "2026-10-16T17:52:00Z", "headRefName": "build/a", "files": []},
           {"number": 2, "mergedAt": "2026-10-17T12:00:00Z", "headRefName": "docs/b", "files": []}]
    runs = [{"conclusion": "success", "createdAt": "2026-10-16T17:52:00Z", "workflowName": "CI"},
            {"conclusion": "failure", "createdAt": "2026-10-17T12:00:00Z", "workflowName": "CI"}]
    out = _drive(monkeypatch, capsys, prs, runs)
    assert "| Merged PRs by kind | 1 total: build 1 |" in out
    assert "| CI runs (all workflows) | 1 runs: 1 success, 0 failure, 0 cancelled, 0 other |" in out


def test_main_limit_with_no_timestamps_is_unmeasured_no_traceback(monkeypatch, capsys):
    """400 PRs whose mergedAt is null: min() of nothing must not raise; the PR rows say unmeasured."""
    prs = [{"number": 1, "mergedAt": None, "headRefName": "a/b", "files": []}] * sc.LIMIT
    out = _drive(monkeypatch, capsys, prs, load("runs.json"))
    assert out.count("unmeasured: gh pr list hit the 400 limit") == PR_ROWS


def test_naive_time_rejected():
    """A time without timezone is refused rather than assumed UTC."""
    with pytest.raises(ValueError):
        sc.parse_time("2026-10-16T17:52:00")
