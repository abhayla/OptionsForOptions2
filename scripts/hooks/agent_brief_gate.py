"""PreToolUse hook (Agent): refuse a dispatch whose prompt names a docs/process/brief-*.md file that fails check_brief.

Only the DESIGNATED brief is checked: a line `Your full brief: <path>` or `Brief: <path>` (any other mention of a
brief file, e.g. "for history see ...", passes). check_brief runs with UTF-8 output; the dispatch is refused
only when it exits non-zero AND printed a MISSING/FAIL line; a crash of the checker allows (one stderr line).
Finding brief-rule-from-memory + 2026-10-16: unchecked briefs cost 3 CI rounds. The brief path may be absolute
or relative (tried against CLAUDE_PROJECT_DIR, this repo, then the current directory).
A prompt naming no brief file passes.
Fails open: missing check_brief.py, unreadable/absent brief file, a timeout, malformed input -> allow.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

REPO = Path(__file__).resolve().parents[2]
BRIEF_RE = re.compile(r"^\s*(?:your full brief|brief)\s*:\s*(\S*?docs[/\\]process[/\\]brief-[\w.\-]+?\.md)",
                      re.IGNORECASE | re.MULTILINE)
LINE_RE = re.compile(r"^(MISSING|FAIL)\b")
TIMEOUT = 60


def _resolve(ref: str) -> Path | None:
    candidates = [Path(ref)]
    if not Path(ref).is_absolute():
        base = os.environ.get("CLAUDE_PROJECT_DIR")
        candidates = ([Path(base) / ref] if base else []) + [REPO / ref, Path.cwd() / ref]
    return next((c for c in candidates if c.is_file()), None)


def decide(tool_name: str, tool_input: dict) -> str | None:
    if tool_name.lower() not in ("agent", "task"):
        return None
    prompt = tool_input.get("prompt")
    checker = REPO / "scripts" / "orchestrator" / "check_brief.py"
    if not isinstance(prompt, str) or not checker.is_file():
        return None
    problems: list[str] = []
    for ref in dict.fromkeys(BRIEF_RE.findall(prompt)):
        brief = _resolve(ref)
        if brief is None:
            continue
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
        try:
            r = subprocess.run([sys.executable, str(checker), str(brief)], capture_output=True, text=True,  # noqa: S603
                               encoding="utf-8", errors="replace", timeout=TIMEOUT, cwd=REPO, env=env, check=False)
        except Exception:  # noqa: BLE001, S112 - timeout or spawn failure: fail open
            continue
        lines = [ln for ln in r.stdout.splitlines() if LINE_RE.match(ln)]
        if r.returncode != 0 and lines:
            problems.append(f"{brief.name}: " + "; ".join(lines))
        elif r.returncode != 0:
            sys.stderr.write(f"agent_brief_gate: check_brief exited {r.returncode} with no MISSING/FAIL line "
                             f"for {brief.name}; allowing (fail open)\n")
    if not problems:
        return None
    banner = "BLOCKED by agent_brief_gate: the brief fails scripts/orchestrator/check_brief.py. Fix it, dispatch again."
    return banner + "\n" + "\n".join(problems)


def main() -> int:
    try:
        from _route_common import run_hook  # noqa: PLC0415
    except Exception:  # noqa: BLE001 - a missing helper module fails open, silently
        return 0
    return run_hook(decide)


if __name__ == "__main__":
    sys.exit(main())
