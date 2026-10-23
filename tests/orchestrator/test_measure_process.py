"""measure_process.py: each ADR-178 counter is read from a streamed transcript and judged against its limit; a miss
exits 1 and is printed first; a session within every limit exits 0. Fixtures are small hand-written JSONL files
built in tmp_path (no real transcript lives in the repo)."""

from __future__ import annotations

import io
import json
import pathlib
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
    content.extend({"type": "tool_use", "name": t["name"], "input": t["input"]} for t in tools or [])
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
    argv = ["--sessions-dir", str(s), "--tasks-dir", str(t), "--commits-json", str(c)]
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
