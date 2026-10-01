#!/usr/bin/env python3
"""run_smoke.py — keep the walking skeleton working (REQ-006 AC-4; owner decisions OD-33, OD-34).

Usage:
    python tools/run_smoke.py [ROOT]

Runs every `smoke` command of every requirement marked `skeleton: true` under
ROOT/spec/requirements, in id order, each:
  - split with shlex (POSIX rules) and run WITHOUT a shell (no pipes, `&&`, redirects or globbing:
    a smoke command is one program and its arguments);
  - with cwd = ROOT and a timeout of 600 seconds;
  - a leading `python` / `python3` is run with the interpreter running this script, so the smoke
    run uses the same Python as the CI step that called it; any other program is resolved with
    shutil.which first (so `npm` finds `npm.cmd` on Windows). Use forward slashes in paths.
A smoke line containing a shell operator word (`&&`, `||`, `|`, `;`, `<`, `>`, ...) is REFUSED before
anything runs: with no shell it would silently become an argument (`a && b` never runs `b`).

Exit codes:
  0  every smoke command passed, or ROOT has no requirements at all (nothing to keep working yet);
  1  a smoke command failed, timed out or could not start (each named: requirement id + command),
     a smoke line contains a shell operator (nothing is run),
     or requirements exist but no smoke command does (no walking skeleton to keep working).
"""
from __future__ import annotations

import shlex
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from factory_lint import parse_frontmatter, smoke_line_problem  # noqa: E402  (shared with the lint)

TIMEOUT_SECONDS = 600
_TAIL_LINES = 20


def load_smoke(root: Path) -> tuple[int, list[tuple[str, str]]]:
    """(number of requirement files, [(requirement id, smoke command)]) in id order."""
    req_dir = root / "spec" / "requirements"
    if not req_dir.is_dir():
        return 0, []
    files = sorted(req_dir.glob("REQ-*.md"))
    commands: list[tuple[str, str]] = []
    for p in files:
        data, err = parse_frontmatter(p)
        if err is not None or not isinstance(data, dict) or data.get("skeleton") is not True:
            continue
        rid = data.get("id") if isinstance(data.get("id"), str) else p.stem
        for cmd in data.get("smoke") or []:
            if isinstance(cmd, str) and cmd.strip():
                commands.append((rid, cmd))
    return len(files), commands


def _argv(cmd: str) -> list[str]:
    argv = shlex.split(cmd)
    if argv and argv[0] in ("python", "python3"):
        argv[0] = sys.executable
    elif argv:
        argv[0] = shutil.which(argv[0]) or argv[0]
    return argv


def _tail(text: str | bytes | None) -> str:
    if not text:
        return ""
    if isinstance(text, bytes):
        text = text.decode("utf-8", "replace")
    return "\n".join(text.strip().splitlines()[-_TAIL_LINES:])


def run(root: Path, timeout: int = TIMEOUT_SECONDS) -> list[tuple[str, str, str]]:
    """Run every smoke command; return [(requirement id, command, reason)] for each failure."""
    _n, commands = load_smoke(root)
    failures: list[tuple[str, str, str]] = []
    for rid, cmd in commands:
        try:
            argv = _argv(cmd)
        except ValueError as exc:
            failures.append((rid, cmd, f"could not parse the command: {exc}"))
            continue
        if not argv:
            failures.append((rid, cmd, "empty command"))
            continue
        try:
            proc = subprocess.run(argv, cwd=str(root), shell=False, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            failures.append((rid, cmd, f"timed out after {timeout} s\n{_tail(exc.stdout)}"))
            continue
        except OSError as exc:
            failures.append((rid, cmd, f"could not start: {exc}"))
            continue
        if proc.returncode != 0:
            failures.append((rid, cmd, f"exit code {proc.returncode}\n{_tail(proc.stdout)}\n{_tail(proc.stderr)}"))
        else:
            print(f"PASS {rid}: {cmd}")
    return failures


def _safe_stdio() -> None:
    """Print UTF-8 with replacement, so a cp1252 pipe (Windows CI, a redirected shell) never raises
    UnicodeEncodeError on a command or output line."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv: list[str] | None = None) -> int:
    _safe_stdio()
    args = list(argv if argv is not None else sys.argv[1:])
    root = Path(args[0]) if args else Path(".")
    n_reqs, commands = load_smoke(root)
    if n_reqs == 0:
        print(f"run_smoke: no requirements under {root / 'spec' / 'requirements'}; nothing to run")
        return 0
    if not commands:
        print(f"run_smoke: FAIL {n_reqs} requirement(s) but no smoke command: mark the walking-skeleton "
              f"requirement `skeleton: true` with a `smoke:` list")
        return 1
    refused = [(rid, cmd, smoke_line_problem(cmd)) for rid, cmd in commands if smoke_line_problem(cmd)]
    if refused:
        for rid, cmd, problem in refused:
            print(f"REFUSED {rid}: {cmd}\n  {problem} (shell operator lines are never run)")
        print(f"run_smoke: FAIL {len(refused)} smoke line(s) refused; nothing was run")
        return 1
    failures = run(root)
    for rid, cmd, reason in failures:
        print(f"FAIL {rid}: {cmd}\n  {reason.strip()}")
    if failures:
        print(f"run_smoke: {len(failures)} of {len(commands)} smoke command(s) failed")
        return 1
    print(f"run_smoke: {len(commands)} smoke command(s) passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
