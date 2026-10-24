"""dispatch.py: one command from a Measure JSON to a checked builder brief (ADR-181 item 2).

Usage: python scripts/orchestrator/dispatch.py <row> <measure.json> --kind build|fix|verify-r2 --out <brief.md>
           --worktree <builder worktree> (--in-flight <worktree>=<start-ref> [...] | --no-in-flight)
           [--ledger <path>] [--root <repo>]

Runs STEPS in order and stops at the first refusal. Exit 0 accepted (one line appended to the ledger, then
`DISPATCH OK ...`), 1 a step refused, 2 bad usage (including neither --in-flight nor --no-in-flight: nobody silently
skips the overlap check), 4 the builder worktree is not ready (the setup steps are printed). Every child runs as an argv
list without a shell and its exit code is read directly: only 0 passes; any other code, or a child that cannot be
started, refuses. The ledger (default `<git common dir>/ofo-dispatch-ledger.jsonl`, shared by every worktree) holds
accepted dispatches only; a third `fix` dispatch of one row is refused (ADR-106: park or redesign after round 2), and an
unreadable ledger line refuses instead of counting as empty. CI and the merge gate stay the authority (ADR-181).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
KINDS = ("build", "fix", "verify-r2")
STEPS = ("round-limit", "worktree-ready", "make-brief", "check-brief", "copy-from", "overlap", "ledger")
MAX_FIX_ROUNDS = 2
EXIT_REFUSED, EXIT_USAGE, EXIT_NOT_READY = 1, 2, 4
LEDGER_NAME = "ofo-dispatch-ledger.jsonl"
LEDGER_KEYS = ("row", "kind", "round", "brief", "brief_sha256", "at", "session")
MAIN_BRANCH = "main"
Runner = Callable[[list[str]], int]


class Refused(Exception):
    """A step refused the dispatch; the message is the reason."""


def norm(text: str) -> str:
    return str(text).strip().lower()


def _child(runner: Runner, argv: list[str]) -> int:
    sys.stdout.flush()  # keep our lines and the child's in order when output is redirected
    try:
        return runner(argv)
    except (OSError, ValueError):  # FileNotFoundError is an OSError: the child could not be started
        return -1


def _real_runner(argv: list[str]) -> int:
    return subprocess.run(argv, check=False).returncode  # noqa: S603 - argv list, no shell


def _script(name: str) -> str:
    return str(HERE / name)


def read_ledger(path: Path) -> list[dict]:
    """Every accepted dispatch. A missing file is an empty ledger; a line that is not a complete entry refuses."""
    if not path.exists():
        return []
    entries: list[dict] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise Refused(f"ledger {path} unreadable ({type(exc).__name__})") from exc
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except ValueError as exc:
            raise Refused(f"ledger {path} line {number} is not JSON - fix or remove it, not read as empty") from exc
        if not isinstance(entry, dict) or not all(isinstance(entry.get(k), str) for k in ("row", "kind")):
            raise Refused(f"ledger {path} line {number} has no row/kind - fix or remove it, not read as empty")
        entries.append(entry)
    return entries


def count_rounds(entries: list[dict], row: str, kind: str) -> int:
    return sum(1 for e in entries if norm(e["row"]) == norm(row) and norm(e["kind"]) == norm(kind))


def _git(worktree: Path, *args: str) -> str | None:
    try:
        done = subprocess.run(["git", "-C", str(worktree), *args], capture_output=True, text=True,  # noqa: S603, S607
                              check=False)
    except OSError:
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def setup_steps(root: Path, worktree: Path, row: str, kind: str) -> list[str]:
    suffix = worktree.name
    return [
        "powershell -NoProfile -File %USERPROFILE%\\.claude\\tools\\wt-new.ps1 "
        f"-Repo {root} -Name {suffix} -Branch build/{suffix} -Base origin/main -Purpose row-{norm(row)}-{kind}",
        f"cd {worktree}\\frontend && npm ci",
        "python scripts/orchestrator/gate.py",
    ]


def worktree_problem(worktree: Path) -> str | None:
    if not worktree.is_dir():
        return f"{worktree} does not exist"
    if _git(worktree, "rev-parse", "--is-inside-work-tree") != "true":
        return f"{worktree} is not a git worktree"
    branch = _git(worktree, "rev-parse", "--abbrev-ref", "HEAD")
    if not branch or branch in (MAIN_BRANCH, "HEAD"):
        return f"{worktree} is on '{branch}', not a builder branch"
    if not (worktree / "frontend" / "node_modules").is_dir():
        return f"{worktree} has no frontend/node_modules"
    return None


def _planned_files(measure: Path, kind: str) -> list[str]:
    key = "changed_files" if kind == "verify-r2" else "files"
    try:
        data = json.loads(measure.read_text(encoding="utf-8"))
        files = data[key]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise Refused(f"overlap: cannot read '{key}' from {measure} ({type(exc).__name__})") from exc
    if not isinstance(files, list) or not files or not all(isinstance(f, str) for f in files):
        raise Refused(f"overlap: '{key}' in {measure} is not a non-empty list of paths")
    return files


def _ledger_path(root: Path, given: str | None) -> Path:
    if given:
        return Path(given)
    common = _git(root, "rev-parse", "--git-common-dir")
    if not common:
        raise Refused(f"cannot find the git common dir of {root}; pass --ledger")
    return (root / common).resolve() / LEDGER_NAME


def _refuse(text: str) -> int:
    sys.stdout.write(f"DISPATCH REFUSED {text}\n")
    return EXIT_REFUSED


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("row")
    ap.add_argument("measure")
    ap.add_argument("--kind", choices=KINDS, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--worktree", required=True)
    ap.add_argument("--in-flight", action="append", default=[], metavar="WORKTREE=START_REF")
    ap.add_argument("--no-in-flight", action="store_true")
    ap.add_argument("--ledger", default=None)
    ap.add_argument("--root", default=str(HERE.parents[1]))
    return ap


def main(argv: Sequence[str] | None = None, runner: Runner = _real_runner,
         now: Callable[[], datetime] | None = None) -> int:
    ap = _parser()
    args = ap.parse_args(list(argv) if argv is not None else None)
    if bool(args.in_flight) == args.no_in_flight:
        ap.error("say which rows are in flight: --in-flight <worktree>=<start-ref> (repeatable) or --no-in-flight")
    pairs = []
    for spec in args.in_flight:
        where, sep, ref = spec.rpartition("=")
        if not sep or not where or not ref:
            ap.error(f"--in-flight needs <worktree>=<start-ref>, got {spec!r}")
        pairs.append((where, ref))
    root, worktree = Path(args.root).resolve(), Path(args.worktree).resolve()
    out, measure = Path(args.out), Path(args.measure)
    row, kind = args.row, args.kind

    try:
        ledger = _ledger_path(root, args.ledger)  # step round-limit
        done = read_ledger(ledger)
        if kind == "fix" and count_rounds(done, row, "fix") >= MAX_FIX_ROUNDS:
            return _refuse(f"row {norm(row)}: third fix round - park it (run-discipline B1) or get an independent "
                           "redesign (ADR-106)")
    except Refused as exc:
        return _refuse(f"row {norm(row)}: {exc}")

    steps = setup_steps(root, worktree, row, kind)  # step worktree-ready
    problem = worktree_problem(worktree)
    if problem:
        sys.stdout.write(f"DISPATCH NOT READY row {norm(row)}: {problem}\n")
    sys.stdout.write("Setup steps:\n" + "".join(f"  {i}. {s}\n" for i, s in enumerate(steps, 1)))
    if problem:
        return EXIT_NOT_READY

    py = sys.executable
    children = (  # (step, argv) for the three checks that need only the brief
        ("make-brief", [py, _script("make_brief.py"), row, str(measure), "--kind", kind, "--out", str(out),
                        "--root", str(root)]),
        ("check-brief", [py, _script("check_brief.py"), str(out), "--root", str(root)]),
        ("copy-from", [py, _script("copy_from_check.py"), str(root), str(out)]),
    )
    for step, argv_ in children:
        code = _child(runner, argv_)
        if code != 0:
            return _refuse(f"row {norm(row)}: step {step} exited {code}")

    try:  # step overlap
        files = _planned_files(measure, kind)
        with tempfile.TemporaryDirectory() as tmp:
            listing = Path(tmp) / "planned-files.txt"
            listing.write_text("\n".join(files) + "\n", encoding="utf-8")
            for other, ref in pairs:
                code = _child(runner, [py, _script("overlap_gate.py"), other, ref, str(worktree), str(listing)])
                if code != 0:
                    return _refuse(f"row {norm(row)}: step overlap exited {code} against {other}")
        return _record(ledger, row, kind, out, now)  # step ledger
    except Refused as exc:
        return _refuse(f"row {norm(row)}: {exc}")


def _record(ledger: Path, row: str, kind: str, out: Path, now: Callable[[], datetime] | None) -> int:
    entries = read_ledger(ledger)  # read again: another session may have dispatched since the first look
    if kind == "fix" and count_rounds(entries, row, "fix") >= MAX_FIX_ROUNDS:
        raise Refused("third fix round - park it (run-discipline B1) or get an independent redesign (ADR-106)")
    try:
        digest = hashlib.sha256(out.read_bytes()).hexdigest()
    except OSError as exc:
        raise Refused(f"brief {out} unreadable after the checks ({type(exc).__name__})") from exc
    number = count_rounds(entries, row, kind) + 1
    stamp = (now or (lambda: datetime.now(timezone.utc)))().isoformat()
    entry = dict(zip(LEDGER_KEYS, (norm(row), kind, number, str(out), digest, stamp,
                                   os.environ.get("CLAUDE_SESSION_ID") or "unknown"), strict=True))
    try:
        ledger.parent.mkdir(parents=True, exist_ok=True)
        with ledger.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError as exc:
        raise Refused(f"cannot write ledger {ledger} ({type(exc).__name__})") from exc
    sys.stdout.write(f"DISPATCH OK row {norm(row)} {kind} round {number} brief {out}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
