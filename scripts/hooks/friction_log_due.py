#!/usr/bin/env python3
"""Stop hook: remind ONCE, at the end of a long session, to log friction (rule improve-proactively).

Reads the hook's JSON from stdin ({session_id, transcript_path, stop_hook_active, ...}). Exits 0 silently unless ALL:
  1. the session lasted more than 60 minutes (first timestamp in the transcript to now);
  2. docs/process/friction-log.md has no row dated today (IST) that was written in this session (the file changed
     after the session started);
  3. this session has not been reminded yet (marker under the git common dir: <common-dir>/ofo-friction/<session>).
Then it writes the marker, prints ONE reminder to stderr and exits 2 (the session continues once). Never blocks twice;
exits 0 when `stop_hook_active` is true; fails open (exit 0) on any error; needs no network and reads only the first
lines of the transcript, so it finishes in well under a second.
Test hooks: FRICTION_NOW (ISO time) replaces the clock; CLAUDE_PROJECT_DIR is the repository root.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

MINUTES = 60
HEAD_LINES = 200
IST = timezone(timedelta(hours=5, minutes=30))
LOG = Path("docs/process/friction-log.md")
REMINDER = (
    "Friction log due: this session ran over 60 minutes and added no row to docs/process/friction-log.md today. "
    "If anything cost time (a wait, a repeat by hand, the same mistake twice, a missing tool or feature, an unclear "
    "rule), add one row now (see .claude/skills/improve/SKILL.md); if nothing did, say so in one line and stop. "
    "This reminder is shown once."
)


def parse_time(s: str) -> datetime | None:
    try:
        t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=UTC)


def session_start(transcript: Path) -> datetime | None:
    with transcript.open(encoding="utf-8", errors="replace") as fh:
        for n, line in enumerate(fh):
            if n >= HEAD_LINES:
                break
            m = re.search(r'"timestamp"\s*:\s*"([^"]+)"', line)
            if m and (t := parse_time(m.group(1))):
                return t
    return None


def marker_path(root: Path, session: str) -> Path | None:
    cmd = ["git", "-C", str(root), "rev-parse", "--git-common-dir"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=3, check=False)  # noqa: S603
    if r.returncode != 0:
        return None
    common = Path(r.stdout.strip())
    common = common if common.is_absolute() else root / common
    return common / "ofo-friction" / re.sub(r"[^A-Za-z0-9_.-]", "_", session)


def row_today_in_session(root: Path, start: datetime, today: str) -> bool:
    f = root / LOG
    if not f.is_file():
        return False
    if datetime.fromtimestamp(f.stat().st_mtime, UTC) < start:
        return False  # the log was not touched since the session began
    return any(ln.startswith(f"| {today} |") for ln in f.read_text(encoding="utf-8", errors="replace").split("\n"))


def decide(payload: dict, root: Path, now: datetime) -> bool:
    """True when the reminder is due (and the marker has been written)."""
    if payload.get("stop_hook_active"):
        return False
    tp = payload.get("transcript_path")
    if not tp or not Path(tp).is_file():
        return False
    start = session_start(Path(tp))
    if start is None or now - start <= timedelta(minutes=MINUTES):
        return False
    if row_today_in_session(root, start, now.astimezone(IST).strftime("%Y-%m-%d")):
        return False
    marker = marker_path(root, str(payload.get("session_id") or Path(tp).stem))
    if marker is None or marker.exists():
        return False
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(now.isoformat(), encoding="utf-8")
    return True


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
        now = parse_time(os.environ["FRICTION_NOW"]) if os.environ.get("FRICTION_NOW") else datetime.now(UTC)
        if now is not None and decide(payload, root, now):
            print(REMINDER, file=sys.stderr)
            return 2
    except Exception:  # noqa: BLE001  (fail open: a broken reminder must never stop a session)
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
