"""ADR-178 process counters (docs/process/adr-178-tracker.md rows 1-7 and 10), each against its limit.

Usage: python scripts/orchestrator/measure_process.py [--repo <root>] [--sessions <n> | --session <id-prefix> ...]
           [--chunk-start <sha>]
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
`--repo` may be a linked worktree: the folders are slugged from the MAIN checkout (git common dir), falling back to
`--repo` when git cannot answer. `--session <id-prefix>` (repeatable) picks sessions by file-name prefix; an id with no
file or several files prints an UNMEASURED line. Agent transcripts of a session = `<session>/subagents/*.jsonl` under
the sessions folder, plus (with `--session`) `<id>/tasks/*.output` under the temp folder, deduped by agent id.
The `read:` line (printed just before the summary) names what was read.
Transcripts are streamed line by line (never loaded whole). Sessions = the main-session JSONL files under the Claude
projects folder for this repo (`--sessions-dir` overrides; `--sessions N` = the N newest). Agent transcripts =
`*/tasks/*.output` under the Claude temp folder for this repo (`--tasks-dir` overrides). Commits come from `git log`
(`--commits-json` overrides, for tests: a list of {sha, time (ISO), subject, files}).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

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
CLOSE_RE = re.compile(r"\bRow (\d+)\b.*\b(closed|PARKED)\b", re.I)
REVIEW_FILE = "docs/process/row-review.md"
REVIEW_HEADING_RE = re.compile(r"^\+### Row (\d+)\b")
# a fix-round commit: `fix 1`, `fix1`, `fix round 2`, `round-1 fix`, or a subject that starts with fix; a subject that
# only mentions the word ("refuses a third fix round") is not one
FIX_RE = re.compile(r"\bfix(?:es)?[ -]?\d\b|\bfix round[ -]?\d\b|\bround[ -]?\d+ fix\b|^\s*fix\b", re.I)
DB_SCRIPTS = ("fresh_launch.py", "db_run.py", "db_run_fresh.py")
LEDGER_NAME = "ofo-dispatch-ledger.jsonl"  # written by dispatch.py (its LEDGER_NAME); one JSON object per line
VERIFY_KINDS = ("verify-r2", "checker")
PYTHON_RE = re.compile(r"python(?:3(?:\.\d+)?)?(?:\.exe)?", re.I)
CD_RE = re.compile(r"(cd|set-location|pushd)\b", re.I)
ENV_RE = re.compile(r"[A-Za-z_]\w*=")
ROUND2_RE = re.compile(r"round[ -]?2|\br2\b", re.I)
CHECKER_RE = re.compile(r"verif|checker|review", re.I)
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


class UsageOnce:
    """Usage of assistant messages, counted once per ``message.id``. Claude Code writes one transcript line per content
    block, each repeating the message's usage; the last line of an id wins, a line without an id counts once
    (finding transcript-usage-counted-per-line)."""

    def __init__(self) -> None:
        self._by_id: dict[str, dict] = {}
        self._anon: list[dict] = []

    def add(self, obj: dict) -> None:
        u = _usage(obj)
        if not u:
            return
        msg_id = obj["message"].get("id")
        if isinstance(msg_id, str) and msg_id:
            self._by_id[msg_id] = u
        else:
            self._anon.append(u)

    def usages(self) -> list[dict]:
        return [*self._by_id.values(), *self._anon]


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


def is_db_run(command: str) -> bool:
    """True when the command RUNS a database tool: its first program (after `cd ... &&` / `;` prefixes and env
    assignments) is python running fresh_launch.py, db_run.py or db_run_fresh.py. A grep, sed or edit that merely
    names one of them is not a run."""
    for raw in re.split(r"&&|;|\n", command.replace("\\", "/")):
        part = raw.strip()
        if not part or CD_RE.match(part):
            continue
        try:
            words = [w for w in shlex.split(part) if not ENV_RE.match(w)]
        except ValueError:
            return False
        if not words or not PYTHON_RE.fullmatch(words[0].rsplit("/", 1)[-1]):
            return False
        script = next((w for w in words[1:] if w.endswith(".py")), "")
        return script.rsplit("/", 1)[-1] in DB_SCRIPTS
    return False


def _note_tool(b: dict, t, s: dict) -> None:
    tool_id = b.get("id")
    if isinstance(tool_id, str) and tool_id:  # one transcript line per content block: the same tool_use repeats
        if tool_id in s["tool_ids"]:
            return
        s["tool_ids"].add(tool_id)
    name, inp = b.get("name", ""), b.get("input") or {}
    if name in ("Bash", "PowerShell") and is_db_run(str(inp.get("command", ""))):
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
         "checkers": [], "first": None, "last": None, "tool_ids": set()}
    once = UsageOnce()
    for obj in _jsonl(path):
        t = _iso(obj.get("timestamp", ""))
        s["first"], s["last"] = _span(s["first"], s["last"], t)
        once.add(obj)
        for b in _blocks(obj):
            if b.get("type") == "text" and obj.get("type") == "assistant":
                txt = b.get("text", "")
                if txt.count("\n|") >= TABLE_MIN_ROWS and "REQ-" in txt:
                    s["tables"] += 1
            elif b.get("type") == "tool_use":
                _note_tool(b, t, s)
    for u in once.usages():
        s["turns"] += 1
        s["ctx"] += sum(u.get(k, 0) or 0 for k in CTX_KEYS)
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


def attach_review_rows(repo: Path, since: str, commits: list[dict]) -> str:
    """Set `review_rows` (the N of every `### Row N` heading a commit ADDS to the row-review file) on each commit.
    Returns "" when git answered, else the reason (the caller prints it: row 2 then uses commit subjects only)."""
    cmd = ["git", "-C", str(repo), "log", "--all", f"--since={since}", "--format=%x1e%H", "-p", "--", REVIEW_FILE]
    try:
        run = subprocess.run(cmd, capture_output=True, text=True, check=False,  # noqa: S603
                             encoding="utf-8", errors="replace")
    except OSError as exc:
        return f"git log of {REVIEW_FILE} failed ({type(exc).__name__})"
    if run.returncode != 0:
        return f"git log of {REVIEW_FILE} failed (exit {run.returncode})"
    rows: dict[str, list[int]] = {}
    for rec in run.stdout.split("\x1e"):
        sha, _, body = rec.partition("\n")
        found = [int(m.group(1)) for ln in body.splitlines() if (m := REVIEW_HEADING_RE.match(ln))]
        if sha.strip() and found:
            rows[sha.strip()] = found
    for c in commits:
        c["review_rows"] = rows.get(c["sha"], [])
    return ""


def rows_closed(s: dict, dated: list[dict]) -> list[int]:
    """Distinct rows closed inside the session window: headings added to the row-review file, plus rows that only a
    `Row N ... closed|PARKED` subject names."""
    inside = [c for c in dated if _in(s, _iso(c["time"]))]
    closed = {n for c in inside for n in c.get("review_rows", [])}
    closed.update(int(m.group(1)) for c in inside if (m := CLOSE_RE.search(c["subject"])))
    return sorted(closed)


def read_ledger(path: Path | None) -> tuple[list[dict] | None, str]:
    """The dispatch ledger entries and a note: (None, why) when the file is missing or any line is unreadable."""
    if path is None or not path.is_file():
        return None, f"dispatch ledger missing ({path})"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        return None, f"dispatch ledger unreadable ({type(exc).__name__})"
    entries = []
    for number, raw in enumerate(lines, 1):
        if not raw.strip():
            continue
        try:
            e = json.loads(raw)
        except ValueError:
            return None, f"dispatch ledger line {number} is not JSON"
        if not isinstance(e, dict) or not all(isinstance(e.get(k), str) for k in ("row", "kind", "at")) \
                or not _iso(e["at"]):
            return None, f"dispatch ledger line {number} has no row/kind/at"
        entries.append(e)
    return entries, ""


def ledger_window(entries: list[dict], s: dict) -> list[tuple]:
    """The ledger entries inside the session window as (time, row, kind), oldest first."""
    inside = [(_iso(e["at"]), e["row"].strip().lower(), e["kind"].strip().lower()) for e in entries
              if _in(s, _iso(e["at"]))]
    return sorted(inside)


def ledger_gaps(inside: list[tuple]) -> tuple[int, list[float]]:
    """(fix dispatches, minutes from each fix to the next verify/checker dispatch of the same row)."""
    fixes = [x for x in inside if x[2] == "fix"]
    gaps = []
    for at, row, _ in fixes:
        later = [t for t, r, k in inside if r == row and k in VERIFY_KINDS and t >= at]
        if later:
            gaps.append((later[0] - at).total_seconds() / 60)
    return len(fixes), gaps


def _git_common_dir(repo: Path) -> str:
    """Absolute git common dir of `repo` as git prints it ('' when git fails)."""
    cmd = ["git", "-C", str(repo), "rev-parse", "--path-format=absolute", "--git-common-dir"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, check=False,  # noqa: S603
                             encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


def main_checkout(repo: Path, resolver=_git_common_dir) -> tuple[Path, str]:
    """The main checkout of `repo` (the parent of its git common dir) and where the answer came from. Any git answer
    that is not an existing absolute directory (error, empty, relative) falls back to `repo` itself."""
    answer = resolver(repo)
    common = Path(answer) if answer else None
    if common is not None and common.is_absolute() and common.is_dir():
        return common.parent, "main checkout via git"
    return repo, "--repo fallback (git gave no usable common dir)"


def _default_dirs(repo: Path, resolver=_git_common_dir) -> tuple[Path, Path]:
    root, _ = main_checkout(repo, resolver)
    slug = re.sub(r"[^A-Za-z0-9]", "-", str(root.resolve()))
    home = Path.home()
    sessions = home / ("." + "claude") / "projects" / slug
    temp = Path(os.environ.get("LOCALAPPDATA", str(home / "AppData" / "Local"))) / "Temp" / "claude" / slug
    return sessions, temp


def _choose_sessions(sessions_dir: Path, n: int, ids: list[str]) -> tuple[list[Path], list[str]]:
    """Session files: the N newest, or exactly those named by prefix. Returns (paths, UNMEASURED lines)."""
    files = sorted(sessions_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime) if sessions_dir.is_dir() else []
    if not ids:
        return files[-n:], []
    chosen, errors = [], []
    for sid in ids:
        hits = [p for p in files if p.name.startswith(sid)]
        if len(hits) == 1:
            chosen.append(hits[0])
        else:
            why = "no transcript" if not hits else "ambiguous: " + ", ".join(p.stem[:12] for p in hits)
            errors.append(f"UNMEASURED rows 1-6, 10: session {sid}: {why} under {sessions_dir}")
    return chosen, errors


def _agent_files(sessions_dir: Path, tasks_dir: Path, chosen: list[Path], explicit: bool) -> list[Path]:
    """Agent transcripts, deduped by agent id (file stem without `agent-`). Explicit sessions read only their own
    subagents and tasks folders; otherwise every tasks folder plus the chosen sessions' subagents."""
    found: dict[str, Path] = {}

    def add(files) -> None:
        for f in sorted(files):
            found.setdefault(f.stem.removeprefix("agent-"), f)

    for p in chosen:
        add((sessions_dir / p.stem / "subagents").glob("*.jsonl"))
        if explicit:
            add((tasks_dir / p.stem / "tasks").glob("*.output"))
    if not explicit:
        add(tasks_dir.glob("*/tasks/*.output"))
    return list(found.values())


class Report:
    def __init__(self) -> None:
        self.miss: list[str] = []
        self.ok: list[str] = []
        self.unm: list[str] = []
        self.read = ""
        self.ledger: tuple[list[dict] | None, str] = (None, "dispatch ledger not given")
        self.notes: list[str] = []

    def row(self, n: int, good: bool, text: str) -> None:
        (self.ok if good else self.miss).append(f"{'OK  ' if good else 'MISS'} row {n}: {text}")


def _in(s: dict, t) -> bool:
    return bool(s["first"] and t and s["first"] <= t <= s["last"])


def _session_rows(s: dict, dated: list[dict], rep: Report) -> None:
    name = Path(s["path"]).stem[:8]
    if not s["turns"]:
        rep.unm.append(f"UNMEASURED rows 1-4, 6: session {name} has no assistant turns")
        _row10(s, name, dated, rep)
        return
    rep.row(1, s["avg_ctx"] < LIMITS[1],
            f"session {name} avg context {s['avg_ctx'] // 1000}k/turn over {s['turns']} turns (limit < 250k)")
    closed = rows_closed(s, dated)
    rep.row(2, len(closed) <= LIMITS[2], f"session {name} closed {len(closed)} rows {closed} (limit <= 3)")
    rep.row(3, s["tables"] <= LIMITS[3], f"session {name} printed the 63-row table {s['tables']} times (limit 0)")
    bad = s["bad_opus"]
    rep.row(4, not bad, f"session {name} Opus dispatches without a safety-set file or `Why Opus:` reason: {len(bad)}"
            + (" - " + "; ".join(bad[:3]) if bad else ""))
    limit6 = max(len(closed), 1)
    rep.row(6, s["db_runs"] <= limit6,
            f"session {name} local database runs {s['db_runs']} (limit <= {limit6}: one per row closed)")
    _row10(s, name, dated, rep)


def _row10(s: dict, name: str, dated: list[dict], rep: Report) -> None:
    """Row 10: from the dispatch ledger (a fix dispatch to the next verify of the same row) when it has entries inside
    the session window, else from fix-round commits to the next checker dispatch in the transcript; says which."""
    entries, note = rep.ledger
    inside = ledger_window(entries, s) if entries is not None else []
    if inside:
        count, gaps = ledger_gaps(inside)
        src, what = "source: dispatch ledger", "fix dispatch"
        miss_why = f"{count} fix dispatches and no verify dispatch after"
    else:
        why = note or "dispatch ledger has no entries in the session window"
        src, what = f"source: fix-round commit subjects ({why})", "fix commit"
        times = [_iso(c["time"]) for c in dated if FIX_RE.search(c["subject"]) and _in(s, _iso(c["time"]))]
        count, gaps = len(times), []
        for f in times:
            later = [d for d in s["checkers"] if d >= f]
            if later:
                gaps.append((min(later) - f).total_seconds() / 60)
        miss_why = f"{count} fix commits and no checker dispatch after"
    if not count:
        rep.unm.append(f"UNMEASURED row 10: session {name} has no {what} in its window ({src})")
    elif not gaps:
        rep.unm.append(f"UNMEASURED row 10: session {name} has {miss_why} ({src})")
    else:
        rep.row(10, max(gaps) <= LIMITS[10], f"session {name} {what} -> checker dispatch worst {max(gaps):.0f} min "
                f"over {len(gaps)} fixes (limit <= 15; {src})")


class Sources(NamedTuple):
    """Where the measure reads from: the orchestrator sessions folder, the agent tasks folder, the dispatch ledger
    file (row 10; None = not given) and the checkout (briefs named by dispatches are resolved against it)."""

    sessions_dir: Path
    tasks_dir: Path
    ledger: Path | None = None
    repo: Path | None = None


def measure(src: Sources, commits: list[dict], n_sessions: int, chunk_start: str | None, *,
            session_ids: list[str] | None = None) -> Report:
    """`n_sessions` = the N newest sessions, unless `session_ids` (session file-name prefixes) names them."""
    sessions_dir, tasks_dir, ledger, repo = src
    rep = Report()
    rep.ledger = read_ledger(ledger)
    ids = list(session_ids or [])
    paths, errors = _choose_sessions(sessions_dir, n_sessions, ids)
    rep.unm.extend(errors)
    sessions = [read_session(p, repo) for p in paths]
    if not sessions and not ids:
        rep.unm.append(f"UNMEASURED rows 1-4, 6: no session transcript under {sessions_dir}")
    dated = [c for c in commits if _iso(c["time"])]
    for s in sessions:
        _session_rows(s, dated, rep)

    agent_files = _agent_files(sessions_dir, tasks_dir, paths, bool(ids))
    rep.read = (f"read: sessions {sessions_dir} ({len(paths)} files chosen: "
                f"{', '.join(p.stem[:8] for p in paths) or 'none'}), agent transcripts {len(agent_files)}"
                )
    tasks = [read_task(f) for f in agent_files]
    r2 = [t for t in tasks if t and ROUND2_RE.search(t["head"]) and CHECKER_RE.search(t["head"])]
    if sessions and sessions[0]["first"] and not ids:
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


def _positive(text: str) -> int:
    if not text.isdigit() or int(text) < 1:
        raise argparse.ArgumentTypeError(f"{text!r} is not a positive number of sessions")
    return int(text)


def _ledger_path(repo: Path, root: Path, given: str | None) -> Path:
    if given:
        return Path(given)
    common = _git_common_dir(repo)
    return (Path(common) if common else root / ".git") / LEDGER_NAME


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default=str(Path(__file__).resolve().parents[2]))
    ap.add_argument("--sessions", type=_positive, default=2, help="the N newest orchestrator sessions")
    ap.add_argument("--session", action="append", default=[], help="session file-name prefix (repeatable)")
    ap.add_argument("--chunk-start", default=None)
    ap.add_argument("--sessions-dir", default=None)
    ap.add_argument("--tasks-dir", default=None)
    ap.add_argument("--commits-json", default=None)
    ap.add_argument("--ledger", default=None, help=f"dispatch ledger file (default: <git common dir>/{LEDGER_NAME})")
    ap.add_argument("--since", default=(dt.datetime.now(dt.UTC) - dt.timedelta(days=3)).date().isoformat())
    args = ap.parse_args(argv)
    repo = Path(args.repo)
    root, how = main_checkout(repo)
    d_sessions, d_tasks = _default_dirs(repo)
    sessions_dir = Path(args.sessions_dir) if args.sessions_dir else d_sessions
    tasks_dir = Path(args.tasks_dir) if args.tasks_dir else d_tasks
    review_note = "row-review headings not read (--commits-json)"
    if args.commits_json:
        commits = json.loads(Path(args.commits_json).read_text(encoding="utf-8"))
    else:
        commits = git_commits(repo, args.since)
        review_note = attach_review_rows(repo, args.since, commits)
    src = Sources(sessions_dir, tasks_dir, _ledger_path(repo, root, args.ledger), repo)
    rep = measure(src, commits, args.sessions, args.chunk_start, session_ids=args.session)
    rep.read += f"; project root {root} ({how})"
    rep.read += "; row 2 from " + (f"{REVIEW_FILE} headings + commit subjects" if not review_note else
                                   f"commit subjects only ({review_note})")
    out = rep.miss + rep.ok + rep.unm + [rep.read]
    out.append(f"{len(rep.miss)} MISS, {len(rep.ok)} OK, {len(rep.unm)} UNMEASURED (ADR-178 tracker rows 1-7, 10)")
    sys.stdout.write("\n".join(out) + "\n")
    return 1 if rep.miss else 0


if __name__ == "__main__":
    sys.exit(main())
