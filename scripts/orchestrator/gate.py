"""The local gate (ADR-181 item 1): every check CI runs for this tree, in one command, stopping at the first failure.

Usage: python scripts/orchestrator/gate.py [--root <worktree>] [--pre-push [--fixes-red]]

Output: one `GATE FAIL <step>: exit <n>` (after the failing log's last 30 lines) and exit 1 at the first failing step,
or `GATE REFUSED ...` and exit 2 when the gate may not run (dirty tree, push refused). Only a full pass prints
`GATE PASS <40-char HEAD sha>` as the LAST line and exits 0. CI and the merge gate stay the authority (ADR-181).

STEPS is the allow-list: one ordered tuple, each step an argv list run without a shell or a pipe, its output in
`<git dir>/ofo-gate/<step>.log` and its exit code read directly. Anything not understood (an exit code other than 0,
select_app_tests output that does not parse, a missing tool) fails closed. Standard library only.

--pre-push (run as `gate.py --pre-push && git push`): refuses while an `App tests` run of this branch is not completed;
--fixes-red lifts that only when the newest completed run failed. A gh error or unreadable answer refuses.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, NamedTuple

PYTHON = sys.executable
PYTEST = [PYTHON, "-m", "pytest", "-q", "-p", "no:cacheprovider"]
PYTEST_APP = [PYTHON, "-m", "pytest", "-c", "pytest-app.ini", "-q", "-p", "no:cacheprovider"]
GUARD_GLOB = "tests/test_*.py"
MONEY_GUARD = "tests/test_money_outside_engine.py"
ROOT_ARG = "<root>"
FRONTEND = "frontend"
GATE_REFUSED = 2
GATE_FAILED = 1
TAIL_LINES = 30
WORKFLOW = "App tests"
GH_RUN_LIMIT = 10
# The database variables the app-selected child must not see (database tests then skip themselves, tests_app/conftest.py).
DB_ENV = ("DATABASE_URL", "TEST_DATABASE_URL", "TEST_ADMIN_DATABASE_URL", "OFO_REQUIRE_DB_TESTS")
# app-tests.yml "Throwaway broker settings": placeholders, set only when absent; BROKER_TOKEN_KEY is fresh per run.
BROKER_ENV = {
    "KITE_API_KEY": "ci_placeholder_key",
    "KITE_API_SECRET": "ci_placeholder_secret",
    "KITE_REDIRECT_URL": "http://127.0.0.1:8000/kite/callback",
    "FRONTEND_ORIGIN": "http://127.0.0.1:4173",
    "KITE_EXPECTED_USER_ID": "ZZ0000",
}
SELECTED_COUNT = re.compile(r"(\d+) files")
SELECTED_FILE = re.compile(r"tests_app/test_[A-Za-z0-9_]+\.py")
SHA = re.compile(r"[0-9a-f]{40}")

Runner = Callable[[list, Path, dict, Path], int]
GhReader = Callable[[str], list]


class Step(NamedTuple):
    name: str
    argv: tuple
    cwd: str  # "." (the root) or a folder under it
    kind: str  # plain | clean | select | app | node


STEPS: tuple = (
    Step("clean-tree", ("git", "status", "--porcelain"), ".", "clean"),
    Step("ruff-ratchet", (PYTHON, "scripts/ruff_ratchet.py"), ".", "plain"),
    Step("guard-tests", (*PYTEST, GUARD_GLOB), ".", "plain"),
    Step("money-guard", (*PYTEST, MONEY_GUARD), ".", "plain"),
    Step("repo-scan", (*PYTEST, "-m", "repo_scan", "tests"), ".", "plain"),
    Step("tests-errors", (*PYTEST, "tests/errors"), ".", "plain"),
    Step("tests-orchestrator", (*PYTEST, "tests/orchestrator"), ".", "plain"),
    Step("app-selected", (PYTHON, "scripts/orchestrator/select_app_tests.py", ROOT_ARG), ".", "select"),
    Step("openapi-drift", (*PYTEST_APP, "tests_app/test_openapi_drift.py"), ".", "app"),
    Step("frontend-lint", ("npm", "run", "lint"), FRONTEND, "node"),
    Step("frontend-format", ("npm", "run", "format:check"), FRONTEND, "node"),
    Step("frontend-vitest-changed", ("npx", "vitest", "run", "--changed", "origin/main"), FRONTEND, "node"),
    Step("coverage", (PYTHON, "scripts/orchestrator/coverage.py", ".", "--check"), ".", "plain"),
    Step("reach-check", (PYTHON, "scripts/orchestrator/reach_check.py", "--root", "."), ".", "plain"),
    Step("reference-register", (PYTHON, "scripts/orchestrator/reference_register.py", "--check"), ".", "plain"),
    Step("findings-index", (PYTHON, "tools/build_findings_index.py", ".", "--check"), ".", "plain"),
)
APP_SELECTED_RUN = [*PYTEST_APP, "-rs"]  # + the selected files, run by the `app-selected` step after its selection


def default_runner(argv: list, cwd: Path, env: dict, log: Path) -> int:
    """Run argv (no shell, no pipe) with its output in `log`; return its exit code, 127 when it cannot start."""
    exe = argv[0] if Path(argv[0]).is_absolute() else shutil.which(argv[0], path=env.get("PATH"))
    with log.open("wb") as out:
        if exe is None:
            out.write(f"cannot find `{argv[0]}` on PATH\n".encode())
            return 127
        try:
            return subprocess.run([exe, *argv[1:]], cwd=cwd, env=env, stdout=out, stderr=subprocess.STDOUT).returncode
        except OSError as exc:
            out.write(f"cannot start `{argv[0]}`: {exc}\n".encode())
            return 127


def gh_runs(branch: str) -> list:
    """The branch's recent `App tests` runs, newest first; raises RuntimeError on any gh failure or odd answer."""
    cmd = ["gh", "run", "list", "--branch", branch, "--workflow", WORKFLOW, "--limit", str(GH_RUN_LIMIT),
           "--json", "databaseId,status,conclusion,headSha"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"gh did not run: {exc}") from exc
    if proc.returncode != 0:
        raise RuntimeError(f"gh exited {proc.returncode}: {proc.stderr.strip()[:300]}")
    try:
        runs = json.loads(proc.stdout)
    except ValueError as exc:
        raise RuntimeError(f"gh answer is not JSON: {exc}") from exc
    if not isinstance(runs, list):
        raise RuntimeError("gh answer is not a list")
    return runs


def push_verdict(runs: list, fixes_red: bool) -> str:
    """'' when a push may go ahead, else the reason it is refused. Every run state has an outcome (see the tests)."""
    try:
        ordered = sorted(runs, key=lambda r: int(r["databaseId"]), reverse=True)
        pending = [r for r in ordered if r["status"] != "completed"]
        completed = [r for r in ordered if r["status"] == "completed"]
        newest = completed[0] if completed else None
        newest_conclusion = newest["conclusion"] if newest else None
        newest_id = newest["databaseId"] if newest else None
        pending_text = [f"App tests run {r['databaseId']} is {r['status']}" for r in pending]
    except (KeyError, TypeError, ValueError) as exc:
        return f"gh answer has an unexpected shape ({exc!r})"
    if fixes_red and newest_conclusion != "failure":
        return f"--fixes-red but the newest completed App tests run {newest_id} is {newest_conclusion}, not failure"
    if pending and not fixes_red:
        return pending_text[0]
    return ""


def tail(path: Path, count: int = TAIL_LINES) -> list:
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()[-count:]
    except OSError:
        return []


def git_text(runner: Runner, root: Path, log_dir: Path, name: str, args: list) -> tuple:
    log = log_dir / f"{name}.log"
    code = runner(["git", *args], root, dict(os.environ), log)
    return code, "\n".join(tail(log, 1000)).strip()


def app_env(base: dict) -> dict:
    env = {k: v for k, v in base.items() if k not in DB_ENV}
    for key, value in BROKER_ENV.items():
        env.setdefault(key, value)
    env.setdefault("BROKER_TOKEN_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode())
    env["PYTHONUTF8"] = "1"
    return env


def expand(step: Step, root: Path) -> list:
    argv: list = []
    for part in step.argv:
        if part == ROOT_ARG:
            argv.append(str(root))
        elif part == GUARD_GLOB:
            argv += sorted(p.relative_to(root).as_posix() for p in (root / "tests").glob("test_*.py")
                           if p.name != Path(MONEY_GUARD).name)
        else:
            argv.append(part)
    return argv


def parse_selection(lines: list) -> list | None:
    """The files select_app_tests printed, or None when the output is not exactly `N files` + N test paths."""
    if not lines:
        return None
    head = SELECTED_COUNT.fullmatch(lines[0].strip())
    files = [ln.strip() for ln in lines[1:] if ln.strip()]
    if head is None or int(head.group(1)) != len(files) or not all(SELECTED_FILE.fullmatch(f) for f in files):
        return None
    return files


def run_step(step: Step, root: Path, runner: Runner, log_dir: Path) -> tuple:
    """Return (exit code, extra log name or None). A step that cannot be understood returns non-zero."""
    log = log_dir / f"{step.name}.log"
    cwd = root / step.cwd
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    if step.kind == "node" and not (cwd / "node_modules").is_dir():
        log.write_text("frontend/node_modules is missing: run npm ci in frontend/\n", encoding="utf-8")
        return GATE_FAILED, None
    if step.kind == "app":
        env = app_env(env)
    code = runner(expand(step, root), cwd, env, log)
    if step.kind != "select" or code != 0:
        return code, None
    files = parse_selection(tail(log, 100000))
    if files is None:
        with log.open("a", encoding="utf-8") as fh:
            fh.write("select_app_tests output not understood: failing closed\n")
        return GATE_FAILED, None
    if not files:
        with log.open("a", encoding="utf-8") as fh:
            fh.write("0 selected\n")
        return 0, None
    run_log = log_dir / f"{step.name}-tests.log"
    return runner([*APP_SELECTED_RUN, *files], root, app_env(dict(os.environ)), run_log), run_log.name


def run_gate(root: Path, log_dir: Path, runner: Runner, out: Callable[[str], None]) -> int:
    log_dir.mkdir(parents=True, exist_ok=True)
    code, dirty = git_text(runner, root, log_dir, "clean-tree", ["status", "--porcelain"])
    if code != 0 or dirty:
        out("GATE REFUSED: uncommitted changes" if code == 0 else f"GATE REFUSED: git status exited {code}")
        return GATE_REFUSED
    code, head = git_text(runner, root, log_dir, "head", ["rev-parse", "HEAD"])
    if code != 0 or not SHA.fullmatch(head):
        out("GATE REFUSED: cannot read the HEAD sha")
        return GATE_REFUSED
    timings: list = []
    for step in STEPS[1:]:  # step 0 (clean-tree) ran above, before anything else
        began = time.monotonic()
        code, extra = run_step(step, root, runner, log_dir)
        timings.append(f"  {step.name}: {time.monotonic() - began:.1f}s")
        if code != 0:
            shown = log_dir / (extra or f"{step.name}.log")
            for line in tail(shown):
                out(line)
            out(f"GATE FAIL {step.name}: exit {code}")
            return GATE_FAILED
    code, dirty = git_text(runner, root, log_dir, "clean-tree-after", ["status", "--porcelain"])
    code2, head_after = git_text(runner, root, log_dir, "head-after", ["rev-parse", "HEAD"])
    if code != 0 or dirty or code2 != 0 or head_after != head:
        out("GATE REFUSED: the steps changed the tree or HEAD, so no sha is certified")
        return GATE_REFUSED
    for line in timings:
        out(line)
    out(f"GATE PASS {head}")
    return 0


def check_push(root: Path, log_dir: Path, runner: Runner, reader: GhReader, fixes_red: bool,
               out: Callable[[str], None]) -> int:
    code, branch = git_text(runner, root, log_dir, "branch", ["rev-parse", "--abbrev-ref", "HEAD"])
    if code != 0 or not branch or branch == "HEAD":
        out("GATE REFUSED push: cannot name the current branch")
        return GATE_REFUSED
    try:
        why = push_verdict(reader(branch), fixes_red)
    except RuntimeError as exc:
        why = f"cannot read the App tests runs ({exc})"
    if why:
        out(f"GATE REFUSED push: {why}")
        return GATE_REFUSED
    return 0


def main(argv: list | None = None, runner: Runner = default_runner, reader: GhReader = gh_runs,
         out: Callable[[str], None] = print) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=None)
    ap.add_argument("--pre-push", action="store_true")
    ap.add_argument("--fixes-red", action="store_true")
    args = ap.parse_args(argv)
    if args.fixes_red and not args.pre_push:
        out("GATE REFUSED: --fixes-red only goes with --pre-push")
        return GATE_REFUSED
    try:
        top = args.root or Path(subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                                               check=True).stdout.strip())
        root = top.resolve()
        git_dir = Path(subprocess.run(["git", "rev-parse", "--absolute-git-dir"], cwd=root, capture_output=True,
                                      text=True, check=True).stdout.strip())
    except (OSError, subprocess.CalledProcessError):
        out("GATE REFUSED: not a git checkout")
        return GATE_REFUSED
    log_dir = git_dir / "ofo-gate"
    log_dir.mkdir(parents=True, exist_ok=True)
    if args.pre_push:
        refused = check_push(root, log_dir, runner, reader, args.fixes_red, out)
        if refused:
            return refused
    return run_gate(root, log_dir, runner, out)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    sys.exit(main())
