"""PreToolUse hook (Bash|PowerShell): refuse a bare `gh issue create`; issues are created through
`python scripts/orchestrator/gh_issue.py app <label> <title> <body-file> --stage <stage>`
(which writes the coverage stage).

Finding: a stage-less issue failed the coverage check and cost a PR (2026-10-16).
Any spelling: `gh  issue create`,
`gh.exe issue create`, `gh -R o/r issue create`, behind env/time/bash -c. `gh issue comment|close|view|list` pass.
Fails open on any problem.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
MAX_LEN = 100_000

MESSAGE = ("BLOCKED by issue_route_gate: do not run `gh issue create` directly (the issue gets no coverage stage). Use "
           "`python scripts/orchestrator/gh_issue.py app <label> <title> <body-file> --stage <stage>`.")


def _is_issue_create(words: list[str]) -> bool:
    from _route_common import head  # noqa: PLC0415

    if head(words) != "gh":
        return False
    rest = words[1:]
    return any(rest[i] == "issue" and rest[i + 1] in ("create", "new") for i in range(len(rest) - 1))


def decide(tool_name: str, tool_input: dict) -> str | None:
    if tool_name.lower() not in ("bash", "powershell"):
        return None
    command = tool_input.get("command")
    if not isinstance(command, str) or not command or len(command) > MAX_LEN:
        return None
    from _route_common import core_steps  # noqa: PLC0415

    ps = tool_name.lower() == "powershell"
    return MESSAGE if any(_is_issue_create(s) for s in core_steps(command, ps)) else None


def main() -> int:
    try:
        from _route_common import run_hook  # noqa: PLC0415
    except Exception:  # noqa: BLE001 - a missing helper module fails open, silently
        return 0
    return run_hook(decide)


if __name__ == "__main__":
    sys.exit(main())
