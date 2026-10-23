"""row_actuals.py: expected values come from the row briefs' `Expected:` lines, wall-clock from dated commits, agent
tokens from transcripts; anything not derivable prints `unmeasured`, never a number. Fixtures are built in tmp_path."""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "orchestrator"))
import row_actuals as ra  # noqa: E402

BRIEFS = pathlib.Path("docs/process/builder-sequence-briefs")
HEADER_AND_TWO_ROWS = 4
USAGE_EXIT = 2


def _cli(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=False, encoding="utf-8")  # noqa: S603


def _git(repo: pathlib.Path, *args: str, when: str | None = None) -> None:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t"}
    if when:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = when
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env=env)  # noqa: S603, S607


@pytest.fixture
def repo(tmp_path) -> pathlib.Path:
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q")
    for n, (stamp, subject) in enumerate([("2026-10-23T10:00:00+05:30", "Row 11 build"),
                                          ("2026-10-23T10:20:00+05:30", "Row 11 fix"),
                                          ("2026-10-23T10:50:00+05:30", "Row 11 finish"),
                                          ("2026-10-23T11:00:00+05:30", "Row 110 other row"),
                                          ("2026-10-23T12:00:00+05:30", "Row 12 only one")]):
        (r / f"f{n}.txt").write_text(str(n), encoding="utf-8")
        _git(r, "add", ".")
        _git(r, "commit", "-q", "-m", subject, when=stamp)
    (r / BRIEFS).mkdir(parents=True)
    (r / BRIEFS / "row-11-build.md").write_text("x\nExpected (orchestrator): 45 min / ~220k.\n", encoding="utf-8")
    (r / BRIEFS / "row-11-fix-1.md").write_text("Expected (orchestrator): 20 min / ~80k.\n", encoding="utf-8")
    (r / BRIEFS / "row-12-build.md").write_text("no expected line here\n", encoding="utf-8")
    return r


def _transcript(tasks: pathlib.Path, name: str, head: str, usages: list[dict]) -> None:
    f = tasks / name / "tasks" / "a.output"
    f.parent.mkdir(parents=True)
    lines = [{"type": "user", "timestamp": "2026-10-23T10:00:00+05:30",
              "message": {"role": "user", "content": head}}]
    lines += [{"type": "assistant", "timestamp": "2026-10-23T10:01:00+05:30",
               "message": {"role": "assistant", "content": [], "usage": u}} for u in usages]
    f.write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")


def _row(text: str, n: int) -> list[str]:
    line = next(x for x in text.splitlines() if x.startswith(f"| {n} |"))
    return [c.strip() for c in line.strip("|").split("|")]


def test_wall_clock_from_three_dated_commits_and_expected_summed(repo, tmp_path):
    """First to last `Row 11` commit is 50 minutes (the `Row 110` commit is another row); expected is summed."""
    cells = _row(ra.table(repo, [11], tmp_path / "none"), 11)
    assert cells[1] == "65"  # 45 + 20 from the two row-11 briefs
    assert cells[2] == "300k"
    assert cells[3] == "50"
    assert cells[4] == "unmeasured (no transcript)"


def test_row_with_no_expected_line_is_unmeasured_never_zero(repo, tmp_path):
    """Attack 5: a row brief with no `Expected:` line -> `unmeasured`; one commit -> unmeasured, not 0."""
    cells = _row(ra.table(repo, [12], tmp_path / "none"), 12)
    assert cells[1:3] == ["unmeasured", "unmeasured"]
    assert cells[3] == "unmeasured (1 commits)"
    assert "| 0 |" not in "".join(cells)


def test_row_with_no_brief_and_no_commit(repo, tmp_path):
    """A row nothing mentions prints unmeasured in every column."""
    cells = _row(ra.table(repo, [13], tmp_path / "none"), 13)
    assert cells[1:] == ["unmeasured", "unmeasured", "unmeasured (0 commits)", "unmeasured (no transcript)"]


def test_tokens_from_transcript_exclude_cache_reads(repo, tmp_path):
    """Agent tokens = input + output + cache creation of the transcript naming the row; cache reads not counted."""
    tasks = tmp_path / "tasks"
    _transcript(tasks, "s1", "Your brief is row-11-fix-1.md", [
        {"input_tokens": 1000, "output_tokens": 500, "cache_creation_input_tokens": 500,
         "cache_read_input_tokens": 900000},
        {"input_tokens": 2000, "output_tokens": 1000, "cache_creation_input_tokens": 0}])
    _transcript(tasks, "s2", "unrelated row 4 work", [{"input_tokens": 99000, "output_tokens": 1}])
    assert _row(ra.table(repo, [11], tasks), 11)[4] == "5k (1 transcripts)"


def test_cli_prints_table_and_bad_rows_exit_2(repo, tmp_path):
    """The command prints a markdown table with the five columns; a malformed --rows exits 2."""
    cmd = [sys.executable, str(REPO / "scripts" / "orchestrator" / "row_actuals.py"), "--repo", str(repo),
           "--tasks-dir", str(tmp_path / "none")]
    ok = _cli([*cmd, "--rows", "11-12"])
    assert ok.returncode == 0
    assert ok.stdout.splitlines()[0] == "| " + " | ".join(ra.HEADERS) + " |"
    assert len(ok.stdout.strip().splitlines()) == HEADER_AND_TWO_ROWS
    assert _cli([*cmd, "--rows", "x"]).returncode == USAGE_EXIT


def test_transcript_reader_is_imported_not_copied():
    """One home for the reader: row_actuals uses measure_process's functions, defines no copy of them."""
    src = (REPO / "scripts" / "orchestrator" / "row_actuals.py").read_text(encoding="utf-8")
    assert "def _jsonl" not in src
    assert "def read_task" not in src
    assert "def git_commits" not in src
