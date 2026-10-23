"""Mutation gate: run every listed guard mutant in a scratch copy and fail unless each one is killed.

Usage: python scripts/orchestrator/mutation_gate.py <checkout> <mutants.json> <results.jsonl>
           [--timeout SECS] [--config pytest-app.ini] [--launcher "<command prefix>"]

The mutants file is an allow-list: a JSON list of exactly `{id, file, find, replace, test}` objects. `find` must occur
exactly once in `file` (inside the checkout), else the mutant is `unresolved` and the gate fails (fail closed). The
checkout is never edited: it is copied once to a scratch folder and each mutant is applied there, then undone.
Per mutant `python -m pytest -q -p no:cacheprovider <test>` runs in the copy (prefixed by --launcher, e.g. the
throwaway-database runner) and one line `{id, result, secs, summary}` is appended to the results file at once.
A mutant is killed only when its named test PASSES on the unmutated copy and FAILS on the mutant: each distinct test
runs on the clean copy first; a test that does not pass clean makes its mutants `unresolved` (a hang there = timeout).
pytest answer -> result (one table, PYTEST_ANSWERS): failed or error at collection (exit 1/2) = killed; passed (0) =
survived; timeout = timeout (named, counts as NOT killed); internal error (3), usage error (4), no tests collected (5),
anything else = unresolved. A file that is not UTF-8 makes its mutant unresolved and the run continues.
`find` is matched byte for byte after UTF-8 decoding, so it must match the file's line endings (CRLF on a Windows
checkout: a multi-line `find` needs CR+LF line breaks).
Finally the union of the named tests runs once on the unmutated copy (line id `__clean__`, must pass).
Exit 0 only when every mutant is killed and the clean run passed; otherwise 1 naming each failing mutant.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import NamedTuple

DEFAULT_TIMEOUT = 180
KEYS = frozenset({"id", "file", "find", "replace", "test"})
IGNORE = shutil.ignore_patterns(".git", "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache")
PYTEST_ANSWERS = {0: "passed", 1: "failed", 2: "error", 3: "internal", 4: "usage", 5: "none"}
CLEAN_ID = "__clean__"
SUMMARY_CHARS = 300


def load_mutants(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise ValueError("the mutants file must be a non-empty JSON list")
    ids: set[str] = set()
    for m in data:
        if not isinstance(m, dict) or set(m) != KEYS or not all(isinstance(v, str) for v in m.values()):
            raise ValueError(f"each mutant must be exactly {sorted(KEYS)} as strings: {m!r}")
        if not m["id"] or not m["find"] or not m["test"] or m["id"] in ids or m["id"] == CLEAN_ID:
            raise ValueError(f"mutant id/find/test must be non-empty and the id unique: {m['id']!r}")
        ids.add(m["id"])
    return data


def kill_tree(proc: subprocess.Popen) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, check=False)  # noqa: S603, S607
    proc.kill()


def run_pytest(copy: Path, tests: list[str], config: str | None, launcher: list[str], timeout: int) -> tuple[str, str]:
    """(state, summary): state is passed|failed|error|none|usage|timeout|other."""
    cmd = [*launcher, sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]
    if config:
        cmd += ["-c", config]
    cmd += tests
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    proc = subprocess.Popen(  # noqa: S603
        cmd,
        cwd=copy,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        kill_tree(proc)
        proc.communicate()
        return "timeout", f"no answer within {timeout}s"
    tail = [x for x in out.strip().splitlines() if x.strip()]
    summary = (tail[-1] if tail else "")[:SUMMARY_CHARS]
    return PYTEST_ANSWERS.get(proc.returncode, "other"), summary


def classify(state: str) -> str:
    return {"failed": "killed", "error": "killed", "passed": "survived", "timeout": "timeout"}.get(state, "unresolved")


def append(results: Path, row: dict) -> None:
    with results.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def resolve(copy: Path, m: dict) -> tuple[Path | None, str | None, str]:
    """(path, original text, problem). The edit target must sit inside the copy and hold `find` exactly once."""
    target = (copy / m["file"]).resolve()
    if copy.resolve() not in target.parents or not target.is_file():
        return None, None, f"file {m['file']!r} is not a file inside the checkout"
    try:
        text = target.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        return None, None, f"file {m['file']!r} is not UTF-8 text"
    count = text.count(m["find"])
    if count != 1:
        return None, None, f"find text occurs {count} times in {m['file']} (must be exactly 1)"
    return target, text, ""


class Options(NamedTuple):
    timeout: int
    config: str | None
    launcher: list[str]


def run_gate(checkout: Path, mutants: list[dict], results: Path, opts: Options) -> int:
    results.write_text("", encoding="utf-8")
    bad: list[str] = []
    scratch = Path(tempfile.mkdtemp(prefix="mutgate-"))
    try:
        copy = scratch / "copy"
        shutil.copytree(checkout, copy, ignore=IGNORE)
        clean: dict[str, tuple[str, str]] = {}
        for m in mutants:
            t0 = time.monotonic()
            target, original, problem = resolve(copy, m)
            if target is not None and m["test"] not in clean:
                clean[m["test"]] = run_pytest(copy, [m["test"]], opts.config, opts.launcher, opts.timeout)
            clean_state, clean_summary = clean.get(m["test"], ("passed", ""))
            if target is None or original is None:
                row = {"id": m["id"], "result": "unresolved", "secs": 0.0, "summary": problem}
            elif clean_state != "passed":
                result = "timeout" if clean_state == "timeout" else "unresolved"
                summary = f"the named test does not pass on the clean copy ({clean_state}: {clean_summary})"
                row = {"id": m["id"], "result": result, "secs": round(time.monotonic() - t0, 1), "summary": summary}
            else:
                target.write_bytes(original.replace(m["find"], m["replace"], 1).encode("utf-8"))
                try:
                    state, summary = run_pytest(copy, [m["test"]], opts.config, opts.launcher, opts.timeout)
                finally:
                    target.write_bytes(original.encode("utf-8"))
                row = {
                    "id": m["id"],
                    "result": classify(state),
                    "secs": round(time.monotonic() - t0, 1),
                    "summary": f"{state}: {summary}",
                }
            append(results, row)
            if row["result"] != "killed":
                bad.append(f"{m['id']} ({row['result']}: {row['summary']})")
        t0 = time.monotonic()
        state, summary = run_pytest(
            copy, sorted({m["test"] for m in mutants}), opts.config, opts.launcher, opts.timeout
        )
        append(results, {"id": CLEAN_ID, "result": state, "secs": round(time.monotonic() - t0, 1), "summary": summary})
        if state != "passed":
            bad.append(f"{CLEAN_ID} (the unmutated copy did not pass: {state}: {summary})")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    if bad:
        sys.stdout.write("MUTATION GATE FAILED:\n" + "\n".join(f"  - {b}" for b in bad) + "\n")
        return 1
    sys.stdout.write(f"MUTATION GATE PASSED: {len(mutants)} mutants killed, clean run passed ({results})\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("checkout", type=Path)
    ap.add_argument("mutants", type=Path)
    ap.add_argument("results", type=Path)
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    ap.add_argument("--config", help="pytest -c file inside the checkout (tests_app: pytest-app.ini)")
    ap.add_argument("--launcher", default="", help="command prefix, e.g. the throwaway-database runner")
    a = ap.parse_args(argv)
    try:
        mutants = load_mutants(a.mutants)
    except (OSError, ValueError) as exc:
        sys.stdout.write(f"MUTATION GATE FAILED: bad mutants file: {exc}\n")
        return 1
    if not a.checkout.is_dir():
        sys.stdout.write(f"MUTATION GATE FAILED: {a.checkout} is not a directory\n")
        return 1
    launcher = [w.strip('"') for w in shlex.split(a.launcher, posix=False)]
    return run_gate(a.checkout.resolve(), mutants, a.results, Options(a.timeout, a.config, launcher))


if __name__ == "__main__":
    sys.exit(main())
