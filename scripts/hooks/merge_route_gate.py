"""PreToolUse hook (Bash|PowerShell): refuse running the kit merge gate directly; merges go through
scripts/orchestrator/merge.py (close check + update-branch + gate) or land.py (which does the same itself).

Finding: BEHIND merges cost 4 rounds on 2026-10-16. Judged per step, quote-aware: python / py / uv run python on the
gate script, with any spacing or path separator, `cd <kit tools> && python <gate>`, and `bash -c "..."`.
Text that merely mentions the file (echo, git add, pytest paths, grep) passes. Fails open on any problem.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _route_common import MAX_LEN, core_steps, head, run_hook

PYTHONS = {"python", "python3", "py", "pypy"}
NAME = "merge_when_green"
MESSAGE = ("BLOCKED by merge_route_gate: do not run the kit merge gate directly (a PR that is BEHIND main fails it). "
           "Use `python scripts/orchestrator/merge.py <pr>` (close check + update-branch + gate) or land.py.")


def _runs_gate(words: list[str]) -> bool:
    h = head(words)
    if NAME in h:
        return True
    if h in PYTHONS:
        script = next((w for w in words[1:] if not w.startswith("-")), "")
        return NAME in script  # backslashes may have been eaten by the shell scan; substring still matches
    return False


def decide(tool_name: str, tool_input: dict) -> str | None:
    if tool_name.lower() not in ("bash", "powershell"):
        return None
    command = tool_input.get("command")
    if not isinstance(command, str) or not command or len(command) > MAX_LEN:
        return None
    ps = tool_name.lower() == "powershell"
    return MESSAGE if any(_runs_gate(s) for s in core_steps(command, ps)) else None


def main() -> int:
    return run_hook(decide)


if __name__ == "__main__":
    sys.exit(main())
