"""measure_process.py: each ADR-178 counter is read from a streamed transcript and judged against its limit; a miss
exits 1 and is printed first; a session within every limit exits 0. Fixtures are small hand-written JSONL files
built in tmp_path (no real transcript lives in the repo)."""

from __future__ import annotations

import io
import json
import pathlib
import subprocess
import sys
from contextlib import redirect_stdout

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "orchestrator"))
import measure_process as mp  # noqa: E402

MIN_MISS_LINES = 8
TRACKER_LIMITS = {1: "< 250k", 2: "<= 3", 3: "0", 4: "0", 5: "<= 15", 7: "<= 1", 10: "<= 15"}


def _ts(hh: int, mm: int = 0) -> str:
    return f"2026-10-23T{hh:02}:{mm:02}:00+05:30"


def _turn(ts: str, ctx: int, text: str = "", tools: list[dict] | None = None, role: str = "assistant") -> str:
    content: list[dict] = [{"type": "text", "text": text}] if text else []
    content.extend({"type": "tool_use", **t} for t in tools or [])
    msg = {"role": role, "content": content, "usage": {"input_tokens": 100, "cache_read_input_tokens": ctx - 100}}
    return json.dumps({"type": role, "timestamp": ts, "message": msg})


def _task_line(ts: str, role: str, text: str = "") -> str:
    content = text if role == "user" else []
    return json.dumps({"type": role, "timestamp": ts, "message": {"role": role, "content": content}})


TABLE = "| # | W | REQ |\n" + "\n".join(f"| {i} | W-{i} | REQ-{i:03} | x |" for i in range(1, 40))


def _write(folder: pathlib.Path, name: str, lines: list[str]) -> pathlib.Path:
    p = folder / name
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def _commits(tmp: pathlib.Path, items: list[dict]) -> pathlib.Path:
    p = tmp / "commits.json"
    p.write_text(json.dumps(items), encoding="utf-8")
    return p


def _run(argv: list[str]) -> tuple[int, str]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = mp.main(argv)
    return code, buf.getvalue()


def _dirs(tmp: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
    s = tmp / "sessions"
    s.mkdir()
    (tmp / "tasks" / "abc" / "tasks").mkdir(parents=True)
    return s, tmp / "tasks"


def _argv(s, t, c, chunk: str | None = None) -> list[str]:
    # the default ledger is the real shared one: point at a missing file unless a test passes its own after
    argv = ["--sessions-dir", str(s), "--tasks-dir", str(t), "--commits-json", str(c),
            "--ledger", str(t / "no-ledger.jsonl")]
    return argv + (["--chunk-start", chunk] if chunk else [])


def test_good_session_passes_every_counter(tmp_path):
    s, t = _dirs(tmp_path)
    opus = {"name": "Agent", "input": {"model": "opus", "prompt": "Verify row 12.\nWhy Opus: backend/ofo/outcome/"
                                                                   "service.py is a safety-set file"}}
    _write(s, "good.jsonl", [_turn(_ts(9), 180_000, "status", [opus]), _turn(_ts(9, 20), 200_000, "row 12 done")])
    _write(t / "abc" / "tasks", "r2.output", [_task_line(_ts(9, 5), "user", "Round 2 verifier, findings only"),
                                              _task_line(_ts(9, 14), "assistant")])
    c = _commits(tmp_path, [
        {"sha": "b" * 40, "time": _ts(9, 10), "subject": "Row 12 (W-140) closed Done", "files": ["work/W-140.md"]},
        {"sha": "a" * 40, "time": _ts(8), "subject": "chunk start", "files": ["docs/x.md"]},
    ])
    code, out = _run(_argv(s, t, c, "a" * 8))
    assert code == 0, out
    assert out.startswith("OK") and "0 MISS" in out
    assert "OK   row 1" in out and "OK   row 5" in out and "OK   row 7" in out


def test_each_counter_over_its_limit_is_a_miss_printed_first(tmp_path):
    s, t = _dirs(tmp_path)
    db = {"name": "Bash", "input": {"command": "python D:/x/fresh_launch.py . python -m pytest tests_app/a.py"}}
    opus = {"name": "Agent", "input": {"model": "claude-opus", "prompt": "Review the wording of the tooltips"}}
    sonnet = {"name": "Agent", "input": {"model": "sonnet", "prompt": "Verifier for the fix"}}
    _write(s, "bad.jsonl", [_turn(_ts(9), 400_000, TABLE, [db] * 5 + [opus]), _turn(_ts(12), 500_000, "x", [sonnet])])
    _write(t / "abc" / "tasks", "r2.output", [_task_line(_ts(9, 5), "user", "You are the round 2 verifier"),
                                              _task_line(_ts(9, 35), "assistant")])
    rows = [{"sha": str(i) * 40, "time": _ts(9, 10 + i), "subject": f"Row {i} closed Done", "files": []}
            for i in range(1, 5)]
    rows += [
        {"sha": "f" * 40, "time": _ts(10), "subject": "Row 4 fix 1", "files": ["backend/a.py"]},
        {"sha": "c" * 40, "time": _ts(9, 30), "subject": "Process: gate", "files": ["scripts/orchestrator/x.py"]},
        {"sha": "d" * 40, "time": _ts(9, 31), "subject": "Process: hook", "files": ["scripts/hooks/x.py"]},
        {"sha": "e" * 40, "time": _ts(9, 32), "subject": "generator", "files": ["scripts/orchestrator/make_brief.py"]},
        {"sha": "9" * 40, "time": _ts(8), "subject": "chunk start", "files": []},
    ]
    c = _commits(tmp_path, rows)
    code, out = _run(_argv(s, t, c, "9" * 8))
    assert code == 1
    lines = out.splitlines()
    first_other = next(i for i, ln in enumerate(lines) if not ln.startswith("MISS"))
    assert first_other >= MIN_MISS_LINES  # every MISS line comes before any OK / UNMEASURED / summary line
    for n in (1, 2, 3, 4, 5, 6, 7, 10):
        assert f"MISS row {n}:" in out, (n, out)
    assert "process-tool commits since 99999999: 2" in out  # the generator is exempt
    assert "fix commit -> checker dispatch worst 120 min" in out


def test_opus_dispatch_rules():
    assert mp.opus_dispatch_ok("anything", "sonnet")
    assert mp.opus_dispatch_ok("check backend/ofo/engine/black_scholes.py", "opus")
    assert mp.opus_dispatch_ok("x\nWhy Opus: live feed liveness in kite_ws", "opus")
    assert not mp.opus_dispatch_ok("review the labels", "opus")
    assert not mp.opus_dispatch_ok("review the labels\nWhy Opus: it is important", "opus")


def test_opus_dispatch_reads_the_named_brief_file(tmp_path):
    brief = tmp_path / "docs" / "process" / "verify-row-99.md"
    brief.parent.mkdir(parents=True)
    brief.write_text("Check backend/ofo/engine/black_scholes.py\nBudget: 15 min\n", encoding="utf-8")
    prompt = f"Your full brief is the file {brief} - read it first."
    assert mp.opus_dispatch_ok(prompt, "opus")
    assert mp.opus_dispatch_ok("Your brief is docs/process/verify-row-99.md", "opus", tmp_path)
    assert not mp.opus_dispatch_ok("Your brief is docs/process/verify-row-98.md", "opus", tmp_path)  # missing file


def test_missing_dirs_are_unmeasured_not_a_crash(tmp_path):
    c = _commits(tmp_path, [])
    code, out = _run(_argv(tmp_path / "none", tmp_path / "none2", c))
    assert code == 0 and "UNMEASURED rows 1-4, 6" in out and "UNMEASURED row 7" in out


def test_garbage_lines_are_skipped(tmp_path):
    s, t = _dirs(tmp_path)
    _write(s, "g.jsonl", ["not json", "42", _turn(_ts(9), 1000, "fine")])
    c = _commits(tmp_path, [])
    code, out = _run(_argv(s, t, c))
    assert code == 0 and "OK   row 1: session g avg context 1k/turn over 1 turns" in out


@pytest.mark.parametrize("limit_row", sorted(TRACKER_LIMITS))
def test_limits_match_the_tracker_file(limit_row):
    text = (REPO / "docs" / "process" / "adr-178-tracker.md").read_text(encoding="utf-8")
    line = next(ln for ln in text.splitlines() if ln.startswith(f"| {limit_row} |"))
    assert TRACKER_LIMITS[limit_row] in line


def test_one_message_id_on_three_lines_counts_one_turn(tmp_path):
    """Finding transcript-usage-counted-per-line: turns and context count a message id once."""
    def line(msg_id: str | None) -> str:
        msg = {"role": "assistant", "content": [], "usage": {"input_tokens": 100, "cache_read_input_tokens": 900}}
        if msg_id:
            msg["id"] = msg_id
        return json.dumps({"type": "assistant", "timestamp": _ts(9), "message": msg})

    p = _write(tmp_path, "s.jsonl", [line("m1"), line("m1"), line("m1"), line("m2"), line(None)])
    s = mp.read_session(p)
    assert (s["turns"], s["ctx"]) == (3, 3000)


# ---- chunk 4 (#532 F): the right folders, --session, the read line, row 10 always printed ----

SID_A = "a43256ae-1cfc-4a9f-8c25-066f2fdf30c0"
SID_B = "b99999ff-0000-4000-8000-000000000000"


def _session(folder: pathlib.Path, sid: str, hour: int = 9) -> pathlib.Path:
    return _write(folder, f"{sid}.jsonl", [_turn(_ts(hour), 100_000, "hello")])


def _r2_agent(folder: pathlib.Path, name: str, minutes: int) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    _write(folder, name, [_task_line(_ts(9, 1), "user", "Round 2 verifier, findings only"),
                          _task_line(_ts(9, 1 + minutes), "assistant")])


def test_worktree_path_slugs_the_main_checkout(tmp_path):
    main = tmp_path / "main-repo"
    (main / ".git").mkdir(parents=True)
    wt = tmp_path / "main-repo-c4"
    sessions, temp = mp._default_dirs(wt, lambda _r: str(main / ".git"))
    assert sessions.name == mp.re.sub(r"[^A-Za-z0-9]", "-", str(main.resolve()))
    assert temp.name == sessions.name
    assert mp.main_checkout(wt, lambda _r: str(main / ".git")) == (main, "main checkout via git")


@pytest.mark.parametrize("answer", ["", "relative/.git", "nowhere-absolute-xxxxx"])
def test_unusable_git_answers_fall_back_to_repo(tmp_path, answer):
    root, how = mp.main_checkout(tmp_path, lambda _r: answer)
    assert root == tmp_path and "fallback" in how


def test_session_prefix_picks_the_named_file_even_when_a_newer_one_exists(tmp_path):
    s, t = _dirs(tmp_path)
    _session(s, SID_A)
    _session(s, SID_B)  # newer by mtime
    code, out = _run([*_argv(s, t, _commits(tmp_path, [])), "--session", "a43256ae"])
    assert code == 0 and "session a43256ae avg context" in out and "b99999ff" not in out
    assert "(1 files chosen: a43256ae)" in out


def test_session_without_a_match_or_with_two_matches_is_unmeasured_by_name(tmp_path):
    s, t = _dirs(tmp_path)
    _session(s, SID_A)
    _session(s, "a43256ae-ffff-4000-8000-000000000000")
    code, out = _run([*_argv(s, t, _commits(tmp_path, [])), "--session", "zzz", "--session", "a43256ae"])
    assert code == 0
    assert "UNMEASURED rows 1-6, 10: session zzz: no transcript" in out
    assert "UNMEASURED rows 1-6, 10: session a43256ae: ambiguous" in out
    assert "(0 files chosen: none)" in out


def test_session_subagents_and_tasks_are_read_and_deduped(tmp_path):
    s, t = _dirs(tmp_path)
    _session(s, SID_A)
    _r2_agent(s / SID_A / "subagents", "agent-a1.jsonl", 20)  # a slow round-2 checker
    _r2_agent(t / SID_A / "tasks", "a1.output", 2)  # same agent id: the subagents copy wins
    _r2_agent(t / SID_A / "tasks", "a2.output", 3)
    _r2_agent(s / SID_B / "subagents", "agent-other.jsonl", 40)  # another session's agent: never read
    code, out = _run([*_argv(s, t, _commits(tmp_path, [])), "--session", "a43256ae"])
    assert code == 1
    assert "MISS row 5: round-2 checker agent-a1 ran 20 min" in out
    assert "OK   row 5: round-2 checker a2 ran 3 min" in out
    assert "agent transcripts 2" in out and "other" not in out


def test_default_run_also_reads_the_chosen_sessions_subagents(tmp_path):
    s, t = _dirs(tmp_path)
    _session(s, SID_A)
    _r2_agent(s / SID_A / "subagents", "agent-a1.jsonl", 5)
    _, out = _run(_argv(s, t, _commits(tmp_path, [])))
    assert "OK   row 5: round-2 checker agent-a1 ran 5 min" in out


def test_session_without_assistant_turns_is_unmeasured(tmp_path):
    s, t = _dirs(tmp_path)
    _write(s, f"{SID_A}.jsonl", [_task_line(_ts(9), "user", "hi")])
    _, out = _run([*_argv(s, t, _commits(tmp_path, [])), "--session", "a43256ae"])
    assert "UNMEASURED rows 1-4, 6: session a43256ae has no assistant turns" in out
    assert "row 1:" not in out


def test_row_10_line_is_present_without_fix_commits(tmp_path):
    s, t = _dirs(tmp_path)
    _session(s, SID_A)
    _, out = _run(_argv(s, t, _commits(tmp_path, [])))
    assert "UNMEASURED row 10: session a43256ae has no fix commit in its window" in out


def test_read_line_names_folder_and_counts(tmp_path):
    s, t = _dirs(tmp_path)
    _session(s, SID_A)
    _, out = _run(_argv(s, t, _commits(tmp_path, [])))
    line = next(ln for ln in out.splitlines() if ln.startswith("read:"))
    assert f"sessions {s} (1 files chosen: a43256ae), agent transcripts 0" in line


# ---- chunk 4 fix round 1: tool_use ids, row 2 from the review file, row 6 runs only, row 10 from the ledger ----

def _git(repo: pathlib.Path, *args: str) -> None:
    cmd = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args]
    subprocess.run(cmd, check=True)  # noqa: S603


def _long_session(folder: pathlib.Path) -> pathlib.Path:
    return _write(folder, f"{SID_A}.jsonl", [_turn(_ts(9), 100_000, "a"), _turn(_ts(12), 100_000, "b")])


def _commit(hour: int, minute: int, subject: str, sha: str, rows: list[int] | None = None) -> dict:
    return {"sha": sha * 40, "time": _ts(hour, minute), "subject": subject, "files": [], "review_rows": rows or []}


def _ledger(tmp: pathlib.Path, entries: list, raw: str | None = None) -> pathlib.Path:
    p = tmp / "ledger.jsonl"
    lines = [json.dumps({"row": r, "kind": k, "at": _ts(h, m)}) for r, k, h, m in entries]
    p.write_text(raw if raw is not None else "\n".join(lines) + "\n", encoding="utf-8")
    return p


def _out(tmp: pathlib.Path, commits: list[dict], *extra: str) -> str:
    s, t = _dirs(tmp)
    _long_session(s)
    return _run([*_argv(s, t, _commits(tmp, commits)), "--session", "a43256ae", *extra])[1]


def test_a_tool_use_repeated_on_two_lines_counts_once_for_rows_4_and_6(tmp_path):
    opus = {"id": "toolu_1", "name": "Agent", "input": {"model": "opus", "prompt": "Review the tooltips"}}
    db = {"id": "toolu_2", "name": "Bash", "input": {"command": "python scripts/orchestrator/db_run.py . python x.py"}}
    p = _write(tmp_path, "s.jsonl", [_turn(_ts(9), 1000, "", [opus]), _turn(_ts(9, 1), 1000, "", [opus]),
                                     _turn(_ts(9, 2), 1000, "", [db]), _turn(_ts(9, 3), 1000, "", [db, db])])
    s = mp.read_session(p)
    assert (len(s["bad_opus"]), s["db_runs"]) == (1, 1)


@pytest.mark.parametrize("command,expected", [
    ("python scripts/orchestrator/db_run_fresh.py . python -m pytest -c pytest-app.ini tests_app/a.py", True),
    ("cd D:/x/repo && PYTHONUTF8=1 python D:\\x\\scripts\\orchestrator\\fresh_launch.py . python -m pytest", True),
    ("cd /d/x && python3 scripts/orchestrator/db_run.py . python -m alembic upgrade head", True),
    ("grep -n db_run_fresh.py scripts/orchestrator/*.py", False),
    ("sed -i s/a/b/ scripts/orchestrator/db_run_fresh.py", False),
    ("cat scripts/orchestrator/fresh_launch.py | head", False),
    ("python -m pytest -c pytest-app.ini tests_app/a.py", False),
    ("git add scripts/orchestrator/db_run.py && git commit -m 'db_run.py'", False),
    ("python scripts/other.py db_run.py", False),
])
def test_only_a_command_that_runs_a_database_tool_counts(command, expected):
    assert mp.is_db_run(command) is expected


def test_rows_closed_are_the_distinct_headings_added_inside_the_window(tmp_path):
    commits = [_commit(9, 10, "Review row 27", "1", [27]), _commit(9, 20, "Reviews 28 and 29", "2", [28, 29]),
               _commit(9, 30, "Edit row 28 again", "3", [28]), _commit(8, 0, "an earlier session's row", "4", [24])]
    out = _out(tmp_path, commits)
    assert "OK   row 2: session a43256ae closed 3 rows [27, 28, 29] (limit <= 3)" in out


def test_a_closed_subject_adds_only_rows_the_review_file_did_not_name(tmp_path):
    commits = [_commit(9, 10, "Row 27 closed Done", "1", [27]), _commit(9, 20, "Row 40 PARKED (#600)", "2")]
    assert "closed 2 rows [27, 40]" in _out(tmp_path, commits)


def test_review_headings_come_from_a_real_git_log(tmp_path):
    repo = tmp_path / "repo"
    (repo / "docs" / "process").mkdir(parents=True)
    _git(repo, "init", "-q")
    review = repo / "docs" / "process" / "row-review.md"
    review.write_text("### Row 1 - old\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "first")
    review.write_text("### Row 1 - old\n### Row 2 - new\nbody\n### Rowan - not a row\n", encoding="utf-8")
    _git(repo, "commit", "-qam", "second")
    commits = mp.git_commits(repo, "2000-01-01")
    assert mp.attach_review_rows(repo, "2000-01-01", commits) == ""
    assert [c["subject"] for c in commits if c["review_rows"] == [2]] == ["second"]
    assert [c["review_rows"] for c in commits if c["subject"] == "first"] == [[1]]
    assert "failed" in mp.attach_review_rows(tmp_path / "not-a-repo", "2000-01-01", commits)


def test_row_10_commit_fallback_counts_fix_rounds_not_a_passing_mention(tmp_path):
    commits = [_commit(9, 5, "dispatch.py: refuses a third fix round (ADR-181)", "1"),
               _commit(9, 6, "Row 28f fix 2: a helper", "2"), _commit(9, 7, "Fix the label", "3"),
               _commit(9, 8, "c1 fix round 1: guard", "4"), _commit(9, 9, "Row 24 CI fix: fakes", "5")]
    out = _out(tmp_path, commits)
    assert "3 fix commits and no checker dispatch after" in out
    assert "source: fix-round commit subjects (dispatch ledger missing" in out


@pytest.mark.parametrize("rows,expect", [
    ([("28", "fix", 9, 0), ("28", "verify-r2", 9, 10), ("29", "fix", 10, 0)], "worst 10 min over 1 fixes"),
    ([("28", "fix", 9, 0), ("29", "verify-r2", 9, 5), ("28", "verify-r2", 9, 50)], "worst 50 min over 1 fixes"),
    ([("28", "verify-r2", 9, 0), ("28", "fix", 9, 5), ("28", "verify-r2", 9, 35)], "worst 30 min over 1 fixes"),
    ([("28", "fix", 9, 0), ("29", "verify-r2", 9, 5)], "1 fix dispatches and no verify dispatch after"),
    ([("28", "build", 9, 0)], "has no fix dispatch in its window (source: dispatch ledger)"),
])
def test_row_10_pairs_a_fix_with_its_own_rows_verify_in_the_ledger(tmp_path, rows, expect):
    out = _out(tmp_path, [_commit(9, 5, "Row 28f fix 1: not used", "1")], "--ledger", str(_ledger(tmp_path, rows)))
    assert expect in out and "source: dispatch ledger" in out and "fix-round commit" not in out


@pytest.mark.parametrize("case,note", [
    ("empty-window", "dispatch ledger has no entries in the session window"),
    ("missing", "dispatch ledger missing"),
    ("bad-line", "dispatch ledger line 2 is not JSON"),
    ("no-keys", "dispatch ledger line 1 has no row/kind/at"),
])
def test_row_10_falls_back_to_commits_and_says_why(tmp_path, case, note):
    bad = json.dumps({"row": "1", "kind": "fix", "at": _ts(9)}) + "\n{oops\n"
    ledger = {"empty-window": lambda: _ledger(tmp_path, [("28", "fix", 3, 0)]),
              "missing": lambda: tmp_path / "none.jsonl",
              "bad-line": lambda: _ledger(tmp_path, [], raw=bad),
              "no-keys": lambda: _ledger(tmp_path, [], raw='{"row": 1}\n')}[case]()
    out = _out(tmp_path, [_commit(9, 5, "Row 28f fix 1: x", "1")], "--ledger", str(ledger))
    assert f"source: fix-round commit subjects ({note}" in out


def test_a_linked_worktree_resolves_to_the_main_checkouts_slug(tmp_path):
    main = tmp_path / "main-repo"
    main.mkdir()
    _git(main, "init", "-q")
    (main / "a.txt").write_text("a", encoding="utf-8")
    _git(main, "add", "-A")
    _git(main, "commit", "-qm", "one")
    wt = tmp_path / "linked-wt"
    _git(main, "worktree", "add", "-q", str(wt))
    sessions, _ = mp._default_dirs(wt)
    assert sessions.name == mp.re.sub(r"[^A-Za-z0-9]", "-", str(main.resolve()))
    assert mp.main_checkout(wt)[1] == "main checkout via git"
    # in the main checkout git prints a relative `.git` unless asked for --path-format=absolute
    assert mp.main_checkout(main)[1] == "main checkout via git"


def test_read_line_names_the_project_root(tmp_path):
    s, t = _dirs(tmp_path)
    _session(s, SID_A)
    _, out = _run([*_argv(s, t, _commits(tmp_path, [])), "--repo", str(tmp_path)])
    line = next(ln for ln in out.splitlines() if ln.startswith("read:"))
    assert f"; project root {tmp_path} (--repo fallback" in line


def test_sessions_zero_is_refused():
    for bad in ("0", "-1", "x"):
        with pytest.raises(SystemExit):
            mp.main(["--sessions", bad])


def test_a_session_with_no_turns_still_prints_row_10_unmeasured_by_name(tmp_path):
    s, t = _dirs(tmp_path)
    _write(s, f"{SID_A}.jsonl", [_task_line(_ts(9), "user", "hi")])
    _, out = _run([*_argv(s, t, _commits(tmp_path, [])), "--session", "a43256ae"])
    assert "UNMEASURED rows 1-4, 6: session a43256ae has no assistant turns" in out
    assert "UNMEASURED row 10: session a43256ae has no fix commit in its window" in out


def test_measure_takes_session_ids_in_their_own_keyword(tmp_path):
    s, t = _dirs(tmp_path)
    _session(s, SID_A)
    _session(s, SID_B)
    rep = mp.measure(mp.Sources(s, t), [], 2, None, session_ids=["b99999ff"])
    assert "(1 files chosen: b99999ff)" in rep.read
