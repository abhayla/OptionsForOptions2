"""merge.py <pr> --reviewed-sha <sha>: the one way an orchestrator merges a PR.

<sha> is the full 40-character sha of the commit the reviewer or verifier passed; it is checked before any step runs.
Chain, each step stopping the chain on failure:
  1. pr_close_check.py --pr N      (no accidental issue-closing reference in the body or commits)
  2. gh pr update-branch N         ("already up to date" is fine; any other failure stops)
  3. the kit merge gate (merge_when_green.py in the kit tools folder) with --reviewed-sha, foreground; the only step
     that merges, so a red PR is never merged, and (kit 1.8.0) never a head the reviewed sha does not cover
Finding: a PR that is BEHIND main cost 4 merge rounds on 2026-10-16. Hook merge_route_gate refuses the
gate called directly.
Exit code: that of the first failing step, else 0; 2 for bad usage.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
UP_TO_DATE = re.compile(r"\balready up[ -]to[ -]date\b", re.IGNORECASE)
GATE = ROOT / "tools" / "merge_when_green.py"
FULL_SHA = re.compile(r"[0-9a-fA-F]{40}")  # the kit gate's own rule (merge_when_green._HEX40)
USAGE = "usage: python scripts/orchestrator/merge.py <pr-number> --reviewed-sha <full 40-character sha>"


def child_env() -> dict[str, str]:
    # The kit gate decodes gh output with the platform default; on cp1252 Windows a byte like 0x90 in a compare reply
    # crashed its reader thread and the gate refused with "staleness unreadable" (PR 473, 2026-10-20). UTF-8 mode
    # for every child fixes the class without editing the kit file.
    return {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}


def run(cmd: list[str]) -> tuple[int, str]:
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8",  # noqa: S603
                       errors="replace", check=False, env=child_env())
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def merge(pr: str, reviewed_sha: str, runner=run) -> int:
    if not FULL_SHA.fullmatch(reviewed_sha or ""):
        print("merge.py: --reviewed-sha must be the full 40-character sha of the reviewed commit, "
              f"not {reviewed_sha!r}")
        return 2
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
    rc, out = runner([sys.executable, str(GATE), pr, "--reviewed-sha", reviewed_sha])
    print(out, end="")
    return rc


def main(argv: list[str]) -> int:
    # gh prints a check mark; a cp1252 Windows console cannot encode it (UnicodeEncodeError, GC-1 2026-10-16)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    if len(argv) != len(("<pr>", "--reviewed-sha", "<sha>")) or not argv[0].isdigit() or argv[1] != "--reviewed-sha":
        print(USAGE)
        return 2
    return merge(argv[0], argv[2])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
