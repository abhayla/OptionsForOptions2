"""PreToolUse hook (Write|Edit|MultiEdit|NotebookEdit and Bash|PowerShell): while a verifier's tool call is running,
the main session must not change `work/`, `spec/` or `evidence/` under the folders that verifier's guard watches, nor
run a git command that is not read-only.

Why: the kit's verifier write-guard snapshots the three folders of every worktree at the verifier's PreToolUse and
quarantines anything that appeared or changed by its PostToolUse, whoever wrote it. The orchestrator's own file written
in that window was moved away (finding verifier-guard-watches-every-worktree).

In flight = a `*.json` snapshot younger than INFLIGHT_SECONDS in <tempdir>/verifier-write-guard/snap/ (the kit guard
creates it at a verifier's PreToolUse and deletes it at PostToolUse). An older one is a left-behind snapshot of a
killed call and is ignored. The folder is overridable with OFO_VERIFIER_SNAP_DIR (tests). Each snapshot lists the roots
its guard watches; a write is judged only under those roots and a git step only when its directory (cwd, `-C`) is
under one. A snapshot that cannot be parsed or lists no root counts as watching everything (fail closed).

Refused (exit 2) when in flight: a write whose resolved path has work/spec/evidence directly under a watched folder
holding `.git`; any git step whose subcommand is NOT in the closed READ_ONLY allow-list (apply, rm, mv, the
delete-untracked command, checkout-index, read-tree, submodule, unknown subcommands, `-c` config, ...), and any git
step whose subcommand cannot be read (`xargs git ...`, `$g ...`, `eval`, ...) - fail closed while in flight; outside a
flight nothing is judged. A verifier's own calls (agent_type ends in `verifier`) pass: the kit guard judges them.
Fails open on any error of its own.

The orchestrator's writer scripts (record_evidence.py, record_evidence_fp.py, ev_agent.py, gh_issue.py --stage) call
`inflight_block_reason` below, so they refuse to write while in flight. NOT covered: arbitrary shell writes
(`echo >`, `cp`, `sed -i`, `Set-Content`) and other scripts that run git (land.py, aregen.py).
"""
from __future__ import annotations

import json
import os
import re
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
# Closed allow-list: everything else is refused while a verifier call is in flight.
READ_ONLY = {"status", "log", "diff", "show", "fetch", "rev-parse", "ls-files", "ls-tree", "cat-file", "describe",
             "blame", "shortlog", "grep", "merge-base", "for-each-ref", "remote", "branch", "worktree", "stash",
             "config", "version"}
BRANCH_FLAGS = {"--list", "-a", "-r", "--show-current", "-v", "-vv", "--contains"}
GIT_ARG_OPTS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--super-prefix", "--config-env"}
OPAQUE_HEADS = {"xargs", "find", "parallel", "eval", "iex", "invoke-expression", "cmd", "start", "start-process",
                "watch", "script", "ssh", "su", "runas"}
CD_HEADS = {"cd", "pushd", "popd", "chdir", "set-location", "sl"}
GIT_WORD = re.compile(r"(^|[\s/\\\"'`(;|&])git(\.exe)?(\s|$|[\"'`)])", re.IGNORECASE)
RULE = "verifier_inflight_gate"


def snap_dir() -> Path:
    env = os.environ.get(SNAP_ENV)
    return Path(env) if env else Path(tempfile.gettempdir()) / "verifier-write-guard" / "snap"


def _norm(p: str) -> str:
    return os.path.normcase(os.path.realpath(p))


def _under(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip("/\\") + os.sep)


def _snapshot_roots(p: Path) -> "list[str] | None":
    """The roots one snapshot's guard watches; None (everything) when it cannot be read or names none."""
    try:
        m = json.loads(p.read_text(encoding="utf-8"))
        roots = [_norm(r["root"]) for r in m["roots"] if isinstance(r.get("root"), str) and r["root"]]
    except Exception:  # noqa: BLE001 - unreadable = watch everything
        return None
    return roots or None


def inflight() -> "list[tuple[float, Path, list[str] | None]] | None":
    """(age seconds, file, watched roots or None) of every fresh snapshot, or None when no call is in flight."""
    d = snap_dir()
    if not d.is_dir():
        return None
    now = time.time()
    ages = []
    for p in d.glob("*.json"):
        try:
            ages.append((max(0.0, now - p.stat().st_mtime), p))
        except OSError:
            continue
    fresh = [(a, p) for a, p in ages if a < INFLIGHT_SECONDS]
    return [(a, p, _snapshot_roots(p)) for a, p in fresh] or None


def inflight_age() -> float | None:
    f = inflight()
    return min(a for a, _, _ in f) if f else None


def _hit(flight, path: str | None) -> "tuple[float, Path] | None":
    """The youngest snapshot that watches `path` (None path = unknown place, watched by all)."""
    hits = [(a, p) for a, p, roots in flight
            if roots is None or path is None or any(_under(path, r) for r in roots)]
    return min(hits, key=lambda h: h[0]) if hits else None


def _refusal(what: str, hit: "tuple[float, Path]") -> str:
    age, snap = hit
    return (f"BLOCKED by {RULE}: {what}. A verifier tool call is running (snapshot {int(age)}s old); "
            "the kit write-guard would quarantine this change. Wait for the verifier to return, then retry. "
            f"If no verifier is running this is a left-behind snapshot of a killed call: delete {snap} "
            "or wait until it is 15 minutes old.")


def inflight_block_reason(target_dir: str, what: str) -> str | None:
    """For writer scripts: the refusal text if a verifier call that watches `target_dir` is in flight, else None.
    Fails open on any error."""
    try:
        flight = inflight()
        hit = _hit(flight, _norm(target_dir)) if flight else None
        return _refusal(what, hit) if hit else None
    except Exception:  # noqa: BLE001
        return None


def guarded_holder(file_path: str, cwd: str) -> str | None:
    """The folder holding `.git` that has work/spec/evidence directly under it on the resolved path, or None."""
    raw = file_path.replace("\\", "/") if os.sep == "/" else file_path
    parts = Path(os.path.realpath(os.path.join(cwd or os.getcwd(), raw))).parts
    for i in range(1, len(parts)):
        if parts[i].lower() in GUARDED_DIRS and os.path.exists(os.path.join(*parts[:i], ".git")):
            return os.path.normcase(os.path.join(*parts[:i]))
    return None


def guarded_path(file_path: str, cwd: str) -> bool:
    return guarded_holder(file_path, cwd) is not None


def _branch_ok(rest: list[str]) -> bool:
    listing = "--list" in rest
    i = 0
    while i < len(rest):
        a = rest[i]
        if a in BRANCH_FLAGS:
            i += 2 if a == "--contains" else 1
        elif listing and not a.startswith("-"):
            i += 1
        else:
            return False
    return True


def _read_only_ok(sub: str, rest: list[str]) -> bool:
    if any(a == "--output" or a.startswith("--output=") or a.startswith("--open-files-in-pager") for a in rest):
        return False
    if sub == "grep" and any(a.startswith("-O") for a in rest):
        return False
    if sub == "remote":
        return rest in ([], ["-v"])
    if sub == "branch":
        return _branch_ok(rest)
    if sub in ("worktree", "stash"):
        return bool(rest) and rest[0].lower() == "list"
    if sub == "config":
        return bool(rest) and rest[0] in ("--get", "--list")
    return True


def git_refusal(words: list[str], cwd: str, dir_unknown: bool = False) -> "tuple[str | None, str | None]":
    """(why this git step is refused or None, the directory it runs in or None when unknown).
    Allow-list: only READ_ONLY subcommands with read-only arguments pass."""
    workdir: str | None = None if dir_unknown else (cwd or os.getcwd())
    unsafe = None
    i = 1
    while i < len(words):
        w = words[i]
        if w in GIT_ARG_OPTS:
            nxt = words[i + 1] if i + 1 < len(words) else ""
            if w == "-C":
                workdir = os.path.join(workdir, nxt) if workdir is not None else None
                if workdir is not None and not os.path.isdir(workdir):
                    workdir = None  # unreadable path (mangled quoting, missing folder): place unknown
            elif w in ("-c", "--config-env"):
                unsafe = unsafe or "git -c (config can define a command)"
            else:
                workdir = None
            i += 2
        elif w.startswith("-"):
            if w.startswith(("--git-dir=", "--work-tree=", "--namespace=", "--super-prefix=")):
                workdir = None
            if w.startswith(("--config-env=", "--exec-path")):
                unsafe = unsafe or f"git {w.split('=')[0]}"
            i += 1  # --no-pager, -p, -P ...
        else:
            break
    if unsafe:
        return unsafe, workdir
    if i >= len(words):
        return None, workdir
    sub = words[i].lower()
    if sub == "--version":
        sub = "version"
    if sub not in READ_ONLY or not _read_only_ok(sub, words[i + 1:]):
        return f"`git {sub}` is not on the read-only list", workdir
    return None, workdir


def _step_verdict(step: list[str], cwd: str, dir_unknown: bool) -> "tuple[str | None, str | None] | None":
    """(why refused, directory or None) for a step that runs git or cannot be read, else None."""
    from _route_common import head  # noqa: PLC0415

    h = head(step)
    if h == "git":
        return git_refusal(step, cwd, dir_unknown)
    if h in ("python", "python3", "py", "uv"):
        for k, w in enumerate(step):
            if os.path.basename(w.replace("\\", "/")) == "agit.py":  # helper that passes its args to git
                return git_refusal(["git", *step[k + 2:]], cwd, True)
    joined = " ".join(step[1:])
    if h in OPAQUE_HEADS and GIT_WORD.search(joined):
        return f"git reached through `{h}` cannot be read", None
    if h.startswith(("$", "`")):
        return "the command name is a variable, so a git call cannot be ruled out", None
    return None


def _decide_write(ti: dict, cwd: str, flight) -> str | None:
    fp = ti.get("file_path") or ti.get("notebook_path")
    if not (isinstance(fp, str) and fp):
        return None
    holder = guarded_holder(fp, cwd)
    if holder is None:
        return None
    hit = _hit(flight, _norm(holder))
    return _refusal(f"a write under work/, spec/ or evidence/ ({fp})", hit) if hit else None


def _decide_shell(ti: dict, powershell: bool, cwd: str, flight) -> str | None:
    command = ti.get("command")
    if not isinstance(command, str) or not command or len(command) > MAX_LEN:
        return None
    from _route_common import core_steps, head  # noqa: PLC0415

    dir_unknown = False
    for step in core_steps(command, powershell):
        if head(step) in CD_HEADS:
            dir_unknown = True  # a later step runs somewhere we cannot resolve
            continue
        verdict = _step_verdict(step, cwd, dir_unknown)
        if verdict is None or verdict[0] is None:
            continue
        why, wd = verdict
        hit = _hit(flight, _norm(wd) if wd else None)
        if hit:
            return _refusal(why, hit)
    return None


def decide(data: dict) -> str | None:
    agent = str(data.get("agent_type") or "").split(":")[-1].strip().lower()
    tool = str(data.get("tool_name", "")).lower()
    ti = data.get("tool_input") or {}
    if agent == "verifier" or (tool not in WRITE_TOOLS and tool not in SHELL_TOOLS):
        return None
    flight = inflight()
    if not flight:
        return None
    cwd = str(data.get("cwd") or "")
    if tool in WRITE_TOOLS:
        return _decide_write(ti, cwd, flight)
    return _decide_shell(ti, tool == "powershell", cwd, flight)


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
