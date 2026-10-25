"""ev_agent.py <agent-id | worktree-path> <reply.json> [--replace] [--dry-run]

Thin wrapper: resolve the agent's worktree, refuse while a verifier is in flight, show `git status --short`, then run
the kit's `tools/record_evidence.py <reply.json> --root <worktree> [...]` and exit with its code. The reply format is
the kit's (see the `tools/record_evidence.py` docstring). Fail closed: a missing kit tool exits 2.
"""
from __future__ import annotations

import os
import subprocess
import sys

MIN_ARGS = 2
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _refuse_if_verifier_in_flight(target):
    """Shared check from the in-flight hook module (no copy of its logic); fails open when it cannot be loaded."""
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks"))
        from verifier_inflight_gate import inflight_block_reason  # noqa: PLC0415 - path is set just above
        why = inflight_block_reason(target, "evidence write by " + os.path.basename(__file__))
    except Exception:  # noqa: BLE001 - a missing or broken hook module fails open
        return
    if why:
        sys.stderr.write(why + "\n")
        sys.exit(2)


def resolve_worktree(who: str) -> str:
    if os.path.isdir(who):
        return who
    return os.path.join(REPO, "." + "claude", "worktrees", f"agent-{who}")


def main(argv: list[str]) -> int:
    if len(argv) < MIN_ARGS:
        sys.stderr.write(__doc__ + "\n")
        return 2
    wt = resolve_worktree(argv[0])
    _refuse_if_verifier_in_flight(wt)
    tool = os.path.join(REPO, "tools", "record_evidence.py")
    if not os.path.isfile(tool):
        sys.stderr.write(f"ev_agent: kit tool missing: {tool}\n")
        return 2
    print(subprocess.run(["git", "status", "--short"], cwd=wt, capture_output=True, text=True, check=False).stdout)
    return subprocess.run([sys.executable, tool, argv[1], "--root", wt, *argv[2:]], check=False).returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
