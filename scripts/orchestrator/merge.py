"""merge.py <pr>: the one way an orchestrator merges a PR.

Chain, each step stopping the chain on failure:
  1. pr_close_check.py --pr N      (no accidental issue-closing reference in the body or commits)
  2. gh pr update-branch N         ("already up to date" is fine; any other failure stops)
  3. the kit merge gate (merge_when_green.py in the kit tools folder), foreground; the only step that merges, so a
     red PR is never merged
Finding: a PR that is BEHIND main cost 4 merge rounds on 2026-10-16. Hook merge_route_gate refuses the
gate called directly.
Exit code: that of the first failing step, else 0.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
UP_TO_DATE = re.compile(r"\balready up[ -]to[ -]date\b", re.IGNORECASE)
GATE = ROOT / "tools" / "merge_when_green.py"


def run(cmd: list[str]) -> tuple[int, str]:
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8",  # noqa: S603
                       errors="replace", check=False)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def merge(pr: str, runner=run) -> int:
    rc, out = runner([sys.executable, str(HERE / "pr_close_check.py"), "--pr", pr])
    print(out, end="")
    if rc != 0:
        print(f"merge.py: close check failed (exit {rc}); not merging")
        return rc
    rc, out = runner(["gh", "pr", "update-branch", pr])
    print(out, end="")
    if rc != 0 and not UP_TO_DATE.search(out):
        print(f"merge.py: gh pr update-branch failed (exit {rc}); not merging")
        return rc
    rc, out = runner([sys.executable, str(GATE), pr])
    print(out, end="")
    return rc


def main(argv: list[str]) -> int:
    # gh prints a check mark; a cp1252 Windows console cannot encode it (UnicodeEncodeError, GC-1 2026-10-16)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    if len(argv) != 1 or not argv[0].isdigit():
        print("usage: python scripts/orchestrator/merge.py <pr-number>")
        return 2
    return merge(argv[0])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
