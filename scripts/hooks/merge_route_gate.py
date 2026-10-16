"""PreToolUse hook (Bash|PowerShell): refuse running the kit merge gate directly; merges go through
scripts/orchestrator/merge.py (close check + update-branch + gate) or land.py (which does the same itself).

Finding: BEHIND merges cost 4 rounds on 2026-10-16. Judged per step, quote-aware: python / py / uv run python on the
gate script, with any spacing or path separator, `cd <kit tools> && python <gate>`, and `bash -c "..."`.
Text that merely mentions the file (echo, git add, pytest paths, grep) passes. Fails open on any problem.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
MAX_LEN = 100_000

PYTHON = re.compile(r"^(python|py|pypy)[\d.]*$")
SKIP_ARG = {"-X", "-W", "-Q", "-s"}  # python options that take a separate value
NAME = "merge_when_green"
MESSAGE = ("BLOCKED by merge_route_gate: do not run the kit merge gate directly (a PR that is BEHIND main fails it). "
           "Use `python scripts/orchestrator/merge.py <pr>` (close check + update-branch + gate) or land.py.")


def _runs_gate(words: list[str]) -> bool:
    from _route_common import head  # noqa: PLC0415

    h = head(words)
    if NAME in h:
        return True
    if not PYTHON.match(h):
        return False
    args = words[1:]
    i = 0
    while i < len(args):
        a = args[i]
        if a == "-c":
            return False  # inline code that only mentions the name is not a run of the gate
        if a == "-m":
            return i + 1 < len(args) and NAME in args[i + 1]
        if a in SKIP_ARG:
            i += 2
        elif a.startswith("-"):
            i += 1
        else:
            return NAME in a  # script path; backslashes may have been eaten by the shell scan
    return False


def decide(tool_name: str, tool_input: dict) -> str | None:
    if tool_name.lower() not in ("bash", "powershell"):
        return None
    command = tool_input.get("command")
    if not isinstance(command, str) or not command or len(command) > MAX_LEN:
        return None
    from _route_common import core_steps  # noqa: PLC0415

    ps = tool_name.lower() == "powershell"
    return MESSAGE if any(_runs_gate(s) for s in core_steps(command, ps)) else None


def main() -> int:
    try:
        from _route_common import run_hook  # noqa: PLC0415
    except Exception:  # noqa: BLE001 - a missing helper module fails open, silently
        return 0
    return run_hook(decide)


if __name__ == "__main__":
    sys.exit(main())
