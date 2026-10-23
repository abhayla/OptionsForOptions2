"""ADR-178 process counters (docs/process/adr-178-tracker.md rows 1-7 and 10), each against its limit.

Usage: python scripts/orchestrator/measure_process.py [--repo <root>] [--sessions <n>] [--chunk-start <sha>]
           [--sessions-dir <dir>] [--tasks-dir <dir>] [--commits-json <file>] [--since YYYY-MM-DD]
Prints `MISS` lines first, then `OK` lines, then `UNMEASURED` lines; exit 1 on any MISS, else 0.
Rows and limits (the tracker is the source; the numbers here must match it):
  1 orchestrator context tokens per turn, average per session         < 250k
  2 rows closed per orchestrator session                             <= 3
  3 63-row table prints per session                                   0
  4 Opus dispatches naming no safety-set file and no `Why Opus:` line naming one   0
  5 minutes per round-2 checker (agent transcript first-last time)    <= 15
  6 local database runs per session (fresh_launch / db_run commands)  <= rows closed in that session (one per row)
  7 commits touching scripts/orchestrator or scripts/hooks since the chunk start   <= 1 (generator + this script exempt)
 10 minutes from a fix commit to the next checker dispatch            <= 15
Transcripts are streamed line by line (never loaded whole). Sessions = the main-session JSONL files under the Claude
projects folder for this repo (`--sessions-dir` overrides; `--sessions N` = the N newest). Agent transcripts =
`*/tasks/*.output` under the Claude temp folder for this repo (`--tasks-dir` overrides). Commits come from `git log`
(`--commits-json` overrides, for tests: a list of {sha, time (ISO), subject, files}).
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))
from brief_path import resolve_brief

LIMITS = {1: 250_000, 2: 3, 3: 0, 4: 0, 5: 15.0, 7: 1, 10: 15.0}
SAFETY_SET = (  # the files whose change makes a checker Opus (ADR-178; builder-brief.md "Safety set"); matched as a
    # path tail, so `ofo/broker/kite_http.py` in a brief counts like `backend/ofo/broker/kite_http.py`
    # (briefs name files as `outcome/service.py` or `kite_ws.py`, so the tails are module-level)
    "engine/", "scenario/", "table/", "outcome/", "marketdata/", "feed_", "feed/", "kite_ws", "broker/", "kite_",
    "routes/auth", "broker_sessions", "orders/", "execution/", "reconciliation/", "alembic/", "scripts/hooks/",
)
SAFETY_WORDS = re.compile(r"\b(engine|scenario|table|outcome|market ?data|feed|kite_ws|socket|broker|auth|token|"
                          r"session store|order|execution|reconcil|migration|alembic|hook)\b", re.I)
WHY_OPUS = re.compile(r"^\W*Why Opus:(.*)$", re.I | re.M)
PROCESS_DIRS = ("scripts/orchestrator/", "scripts/hooks/")
PROCESS_EXEMPT = ("scripts/orchestrator/make_brief.py", "scripts/orchestrator/measure_process.py")
TABLE_MIN_ROWS = 30
CLOSE_RE = re.compile(r"\bRow \d+\b.*\b(closed|PARKED)\b", re.I)
FIX_RE = re.compile(r"\bfix\b", re.I)
ROUND2_RE = re.compile(r"round[ -]?2|\br2\b", re.I)
CHECKER_RE = re.compile(r"verif|checker|review", re.I)
DB_RUN_RE = re.compile(r"fresh_launch\.py|db_run(?:_fresh)?\.py|pytest-app\.ini", re.I)
OPUS_RE = re.compile(r"opus", re.I)
CTX_KEYS = ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
GIT_FIELDS = 3


def _iso(ts: str) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _jsonl(path: Path):
    with path.open(encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if isinstance(obj, dict):
                yield obj


def _blocks(obj: dict) -> list[dict]:
    msg = obj.get("message") if isinstance(obj.get("message"), dict) else None
    content = msg.get("content") if msg else None
    return [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []


def _usage(obj: dict) -> dict | None:
    msg = obj.get("message") if isinstance(obj.get("message"), dict) else None
    u = msg.get("usage") if msg else None
    return u if isinstance(u, dict) else None


def names_safety_file(text: str) -> bool:
    return any(p in text.replace("\\", "/") for p in SAFETY_SET)


BRIEF_PATH_RE = re.compile(r"(?:[A-Za-z]:)?[\\/][^\s`'\"]+?\.md|docs[\\/]process[\\/][^\s`'\"]+?\.md")


def _with_briefs(prompt: str, repo: Path | None) -> str:
    """The prompt plus the text of every brief file it names (a dispatch usually says only `Your brief is <file>`)."""
    parts = [prompt]
    for raw in BRIEF_PATH_RE.findall(prompt):
        found = resolve_brief(raw, [repo] if repo else [])
        if found is not None:
            try:
                parts.append(found.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
    return "\n".join(parts)


def opus_dispatch_ok(prompt: str, model: str, repo: Path | None = None) -> bool:
    """An Opus dispatch is fine when its prompt (or the brief file it names) names a safety-set file, or its
    `Why Opus:` line names one."""
    if not OPUS_RE.search(model or ""):
        return True
    text = _with_briefs(prompt, repo)
    if names_safety_file(text):
        return True
    m = WHY_OPUS.search(text)
    return bool(m and (names_safety_file(m.group(1)) or SAFETY_WORDS.search(m.group(1))))


def _span(first, last, t):
    if t is None:
        return first, last
    first = t if first is None or t < first else first
    last = t if last is None or t > last else last
    return first, last


def _note_tool(b: dict, t, s: dict) -> None:
    name, inp = b.get("name", ""), b.get("input") or {}
    if name in ("Bash", "PowerShell") and DB_RUN_RE.search(str(inp.get("command", ""))):
        s["db_runs"] += 1
    if name not in ("Agent", "Task"):
        return
    prompt = str(inp.get("prompt", ""))
    if not opus_dispatch_ok(prompt, str(inp.get("model", "")), s.get("repo")):
        s["bad_opus"].append(prompt.strip().splitlines()[0][:90] if prompt.strip() else "(empty prompt)")
    if CHECKER_RE.search(prompt[:400]) and t:
        s["checkers"].append(t)


def read_session(path: Path, repo: Path | None = None) -> dict:
    """Stream one orchestrator session: turns, context, table prints, Opus dispatches, DB runs, checker dispatches."""
    s = {"path": str(path), "repo": repo, "turns": 0, "ctx": 0, "tables": 0, "db_runs": 0, "bad_opus": [],
         "checkers": [], "first": None, "last": None}
    for obj in _jsonl(path):
        t = _iso(obj.get("timestamp", ""))
        s["first"], s["last"] = _span(s["first"], s["last"], t)
        u = _usage(obj)
        if u:
            s["turns"] += 1
            s["ctx"] += sum(u.get(k, 0) or 0 for k in CTX_KEYS)
        for b in _blocks(obj):
            if b.get("type") == "text" and obj.get("type") == "assistant":
                txt = b.get("text", "")
                if txt.count("\n|") >= TABLE_MIN_ROWS and "REQ-" in txt:
                    s["tables"] += 1
            elif b.get("type") == "tool_use":
                _note_tool(b, t, s)
    s["avg_ctx"] = s["ctx"] // s["turns"] if s["turns"] else 0
    return s


def read_task(path: Path) -> dict | None:
    """One agent transcript: first user text, first-last minutes."""
    first = last = None
    head = ""
    for obj in _jsonl(path):
        first, last = _span(first, last, _iso(obj.get("timestamp", "")))
        if head or obj.get("type") != "user":
            continue
        texts = [b.get("text", "") for b in _blocks(obj) if b.get("type") == "text"]
        msg = obj.get("message") if isinstance(obj.get("message"), dict) else {}
        if not texts and isinstance(msg.get("content"), str):
            texts = [msg["content"]]
        head = texts[0][:400] if texts else ""
    if first is None or last is None:
        return None
    return {"path": str(path), "head": head, "minutes": (last - first).total_seconds() / 60, "first": first}


def git_commits(repo: Path, since: str) -> list[dict]:
    cmd = ["git", "-C", str(repo), "log", "--all", f"--since={since}", "--date=iso-strict",
           "--format=%x1e%H%x1f%ad%x1f%s", "--name-only"]
    out = subprocess.run(cmd, capture_output=True, text=True, check=False,  # noqa: S603
                         encoding="utf-8", errors="replace").stdout
    commits = []
    for rec in out.split("\x1e"):
        if not rec.strip():
            continue
        head, _, files = rec.partition("\n")
        parts = head.split("\x1f")
        if len(parts) != GIT_FIELDS:
            continue
        commits.append({"sha": parts[0], "time": parts[1], "subject": parts[2],
                        "files": [f for f in files.splitlines() if f.strip()]})
    return commits


def _default_dirs(repo: Path) -> tuple[Path, Path]:
    slug = re.sub(r"[^A-Za-z0-9]", "-", str(repo.resolve()))
    home = Path.home()
    sessions = home / ("." + "claude") / "projects" / slug
    temp = Path(os.environ.get("LOCALAPPDATA", str(home / "AppData" / "Local"))) / "Temp" / "claude" / slug
    return sessions, temp


class Report:
    def __init__(self) -> None:
        self.miss: list[str] = []
        self.ok: list[str] = []
        self.unm: list[str] = []

    def row(self, n: int, good: bool, text: str) -> None:
        (self.ok if good else self.miss).append(f"{'OK  ' if good else 'MISS'} row {n}: {text}")


def _in(s: dict, t) -> bool:
    return bool(s["first"] and t and s["first"] <= t <= s["last"])


def _session_rows(s: dict, dated: list[dict], rep: Report) -> None:
    name = Path(s["path"]).stem[:8]
    rep.row(1, s["avg_ctx"] < LIMITS[1],
            f"session {name} avg context {s['avg_ctx'] // 1000}k/turn over {s['turns']} turns (limit < 250k)")
    closed = [c for c in dated if _in(s, _iso(c["time"])) and CLOSE_RE.search(c["subject"])]
    rep.row(2, len(closed) <= LIMITS[2], f"session {name} closed {len(closed)} rows (limit <= 3)")
    rep.row(3, s["tables"] <= LIMITS[3], f"session {name} printed the 63-row table {s['tables']} times (limit 0)")
    bad = s["bad_opus"]
    rep.row(4, not bad, f"session {name} Opus dispatches without a safety-set file or `Why Opus:` reason: {len(bad)}"
            + (" - " + "; ".join(bad[:3]) if bad else ""))
    limit6 = max(len(closed), 1)
    rep.row(6, s["db_runs"] <= limit6,
            f"session {name} local database runs {s['db_runs']} (limit <= {limit6}: one per row closed)")
    fixes = [_iso(c["time"]) for c in dated if FIX_RE.search(c["subject"]) and _in(s, _iso(c["time"]))]
    gaps = []
    for f in fixes:
        later = [d for d in s["checkers"] if d >= f]
        if later:
            gaps.append((min(later) - f).total_seconds() / 60)
    if fixes and not gaps:
        rep.unm.append(f"UNMEASURED row 10: session {name} has {len(fixes)} fix commits and no checker dispatch after")
    elif gaps:
        rep.row(10, max(gaps) <= LIMITS[10], f"session {name} fix commit -> checker dispatch worst {max(gaps):.0f} min "
                f"over {len(gaps)} fixes (limit <= 15)")


def measure(dirs: tuple[Path, Path], commits: list[dict], n_sessions: int, chunk_start: str | None,
            repo: Path | None = None) -> Report:
    """`dirs` = (orchestrator sessions folder, agent tasks folder)."""
    sessions_dir, tasks_dir = dirs
    rep = Report()
    paths = []
    if sessions_dir.is_dir():
        paths = sorted(sessions_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)[-n_sessions:]
    sessions = [read_session(p, repo) for p in paths]
    if not sessions:
        rep.unm.append(f"UNMEASURED rows 1-4, 6: no session transcript under {sessions_dir}")
    dated = [c for c in commits if _iso(c["time"])]
    for s in sessions:
        _session_rows(s, dated, rep)

    tasks = []
    if tasks_dir.is_dir():
        tasks = [read_task(Path(p)) for p in glob.glob(str(tasks_dir / "*" / "tasks" / "*.output"))]
    r2 = [t for t in tasks if t and ROUND2_RE.search(t["head"]) and CHECKER_RE.search(t["head"])]
    if sessions and sessions[0]["first"]:
        r2 = [t for t in r2 if t["first"] >= sessions[0]["first"]]
    if not r2:
        rep.unm.append("UNMEASURED row 5: no round-2 checker transcript in the measured window")
    for t in r2:
        rep.row(5, t["minutes"] <= LIMITS[5],
                f"round-2 checker {Path(t['path']).stem[:12]} ran {t['minutes']:.0f} min (limit <= 15)")

    _chunk_row(commits, chunk_start, rep)
    return rep


def _chunk_row(commits: list[dict], chunk_start: str | None, rep: Report) -> None:
    if not chunk_start:
        rep.unm.append("UNMEASURED row 7: pass --chunk-start <sha of the chunk's first commit>")
        return
    chunk = []
    for c in commits:
        if c["sha"].startswith(chunk_start):
            break
        chunk.append(c)
    touching = [c for c in chunk if any(f.startswith(PROCESS_DIRS) and f not in PROCESS_EXEMPT for f in c["files"])]
    rep.row(7, len(touching) <= LIMITS[7], f"process-tool commits since {chunk_start[:8]}: {len(touching)} "
            "(limit <= 1)" + (" - " + "; ".join(c["subject"][:60] for c in touching[:3]) if touching else ""))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default=str(Path(__file__).resolve().parents[2]))
    ap.add_argument("--sessions", type=int, default=2, help="the N newest orchestrator sessions")
    ap.add_argument("--chunk-start", default=None)
    ap.add_argument("--sessions-dir", default=None)
    ap.add_argument("--tasks-dir", default=None)
    ap.add_argument("--commits-json", default=None)
    ap.add_argument("--since", default=(dt.datetime.now(dt.UTC) - dt.timedelta(days=3)).date().isoformat())
    args = ap.parse_args(argv)
    repo = Path(args.repo)
    d_sessions, d_tasks = _default_dirs(repo)
    sessions_dir = Path(args.sessions_dir) if args.sessions_dir else d_sessions
    tasks_dir = Path(args.tasks_dir) if args.tasks_dir else d_tasks
    if args.commits_json:
        commits = json.loads(Path(args.commits_json).read_text(encoding="utf-8"))
    else:
        commits = git_commits(repo, args.since)
    rep = measure((sessions_dir, tasks_dir), commits, args.sessions, args.chunk_start, repo)
    out = rep.miss + rep.ok + rep.unm
    out.append(f"{len(rep.miss)} MISS, {len(rep.ok)} OK, {len(rep.unm)} UNMEASURED (ADR-178 tracker rows 1-7, 10)")
    sys.stdout.write("\n".join(out) + "\n")
    return 1 if rep.miss else 0


if __name__ == "__main__":
    sys.exit(main())
