"""PreToolUse hook (Write|Edit|MultiEdit|NotebookEdit and Bash|PowerShell): while a verifier's tool call is running,
the main session must not change `work/`, `spec/` or `evidence/` of any worktree, nor run a git command that rewrites
a working tree.

Why: the kit's verifier write-guard snapshots the three folders of every worktree at the verifier's PreToolUse and
quarantines anything that appeared or changed by its PostToolUse, whoever wrote it. The orchestrator's own file written
in that window was moved away (finding verifier-guard-watches-every-worktree).

In flight = a `*.json` snapshot younger than INFLIGHT_SECONDS in <tempdir>/verifier-write-guard/snap/ (the kit guard
creates it at a verifier's PreToolUse and deletes it at PostToolUse). An older one is a left-behind snapshot of a
killed call and is ignored. The folder is overridable with OFO_VERIFIER_SNAP_DIR (tests).

Refused (exit 2) when in flight: a write whose resolved path has work/spec/evidence directly under a folder holding
`.git`; a git step with a subcommand from REWRITES, which is git's porcelain set that writes the working tree
(merge, pull, checkout, switch, rebase, reset, cherry-pick, revert, am, restore, stash, clone, worktree add).
Read-only git (status, log, diff, show, fetch, rev-parse, ls-files, branch, worktree list) passes.
A verifier's own calls (agent_type ends in `verifier`) pass through: the kit guard judges them. Fails open on any error.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
MAX_LEN = 100_000
INFLIGHT_SECONDS = 900
SNAP_ENV = "OFO_VERIFIER_SNAP_DIR"
WRITE_TOOLS = {"write", "edit", "multiedit", "notebookedit"}
SHELL_TOOLS = {"bash", "powershell"}
GUARDED_DIRS = {"work", "spec", "evidence"}
REWRITES = {"merge", "pull", "checkout", "switch", "rebase", "reset", "cherry-pick", "revert", "am", "restore",
            "stash", "clone"}
GIT_ARG_OPTS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--super-prefix", "--config-env"}
RULE = "verifier_inflight_gate"


def snap_dir() -> Path:
    env = os.environ.get(SNAP_ENV)
    return Path(env) if env else Path(tempfile.gettempdir()) / "verifier-write-guard" / "snap"


def inflight_age() -> float | None:
    """Age in seconds of the youngest fresh snapshot, or None when no verifier call is in flight."""
    d = snap_dir()
    if not d.is_dir():
        return None
    now = time.time()
    ages = []
    for p in d.glob("*.json"):
        try:
            ages.append(max(0.0, now - p.stat().st_mtime))
        except OSError:
            continue
    fresh = [a for a in ages if a < INFLIGHT_SECONDS]
    return min(fresh) if fresh else None


def _refusal(what: str, age: float) -> str:
    return (f"BLOCKED by {RULE}: {what}. A verifier tool call is running (snapshot {int(age)}s old); "
            "the kit write-guard would quarantine this change. Wait for the verifier to return, then retry.")


def guarded_path(file_path: str, cwd: str) -> bool:
    raw = file_path.replace("\\", "/") if os.sep == "/" else file_path
    parts = Path(os.path.realpath(os.path.join(cwd or os.getcwd(), raw))).parts
    for i in range(1, len(parts)):
        if parts[i].lower() in GUARDED_DIRS and os.path.exists(os.path.join(*parts[:i], ".git")):
            return True
    return False


def git_rewrite(words: list[str]) -> str | None:
    """The rewriting git subcommand of this step, or None."""
    from _route_common import head  # noqa: PLC0415

    if head(words) != "git":
        return None
    i = 1
    while i < len(words):
        w = words[i]
        if w in GIT_ARG_OPTS:
            i += 2
        elif w.startswith("-"):
            i += 1  # --opt=value, --no-pager, -p ...
        else:
            break
    if i >= len(words):
        return None
    sub = words[i].lower()
    if sub in REWRITES:
        return sub
    if sub == "worktree" and i + 1 < len(words) and words[i + 1].lower() == "add":
        return "worktree add"
    return None


def _decide_write(ti: dict, cwd: str, age: float) -> str | None:
    fp = ti.get("file_path") or ti.get("notebook_path")
    if isinstance(fp, str) and fp and guarded_path(fp, cwd):
        return _refusal(f"a write under work/, spec/ or evidence/ ({fp})", age)
    return None


def _decide_shell(ti: dict, powershell: bool, age: float) -> str | None:
    command = ti.get("command")
    if not isinstance(command, str) or not command or len(command) > MAX_LEN:
        return None
    from _route_common import core_steps  # noqa: PLC0415

    for step in core_steps(command, powershell):
        sub = git_rewrite(step)
        if sub:
            return _refusal(f"`git {sub}` rewrites the working tree", age)
    return None


def decide(data: dict) -> str | None:
    agent = str(data.get("agent_type") or "").split(":")[-1].strip().lower()
    tool = str(data.get("tool_name", "")).lower()
    ti = data.get("tool_input") or {}
    if agent == "verifier" or (tool not in WRITE_TOOLS and tool not in SHELL_TOOLS):
        return None
    age = inflight_age()
    if age is None:
        return None
    if tool in WRITE_TOOLS:
        return _decide_write(ti, str(data.get("cwd") or ""), age)
    return _decide_shell(ti, tool == "powershell", age)


def main() -> int:
    try:
        from _route_common import read_input  # noqa: PLC0415

        reason = decide(read_input())
    except Exception:  # noqa: BLE001 - a hook must never block on its own bug
        return 0
    if not reason:
        return 0
    sys.stderr.write(reason + "\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
