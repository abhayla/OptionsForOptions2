"""The local gate (ADR-181 item 1): every check CI runs for this tree, in one command, stopping at the first failure.

Usage: python scripts/orchestrator/gate.py [--root <worktree>] [--pre-push [--fixes-red]]

Output: one `GATE FAIL <step>: exit <n>` (after the failing log's last 30 lines) and exit 1 at the first failing step,
or `GATE REFUSED ...` and exit 2 when the gate may not run (dirty tree, push refused). Only a full pass prints
`GATE PASS <40-char HEAD sha>` as the LAST line and exits 0. CI and the merge gate stay the authority (ADR-181).

STEPS is the allow-list: one ordered tuple, each step an argv list run without a shell or a pipe, its output in
`<git dir>/ofo-gate/<step>.log` and its exit code read directly. Anything not understood (an exit code other than 0,
select_app_tests output that does not parse, a missing tool) fails closed. Standard library only.

--pre-push (run as `gate.py --pre-push && git push`): refuses while an `App tests` run of this branch is not completed;
--fixes-red lifts that only when the newest completed run failed and no newer run is queued or in progress (the push
would cancel it). A gh error or unreadable answer refuses. --pre-push also runs pr_close_check.py for the branch's open
PR (no PR: skipped with a printed line; a gh error refuses).
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
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

PYTHON = sys.executable
# Finding local-pytest-plugin-not-in-ci: a plugin only this PC has (hypothesis) ran at the end of a session under the
# egress hook and failed the run; no repo test imports it and CI does not install it, so every pytest step turns it off.
NO_HYPOTHESIS = ["-p", "no:hypothesispytest"]
PYTEST = [PYTHON, "-m", "pytest", "-q", "-p", "no:cacheprovider", *NO_HYPOTHESIS]
PYTEST_APP = [PYTHON, "-m", "pytest", "-c", "pytest-app.ini", "-q", "-p", "no:cacheprovider", *NO_HYPOTHESIS]
GUARD_GLOB = "tests/test_*.py"
MONEY_GUARD = "tests/test_money_outside_engine.py"
ROOT_ARG = "<root>"
FRONTEND = "frontend"
DOMAIN_SRC = "backend/ofo"
GATE_REFUSED = 2
GATE_FAILED = 1
TAIL_LINES = 30
WORKFLOW = "App tests"
GH_RUN_LIMIT = 10
# `npm run format:check` is `prettier --check src/` and is red on 93 files of main, so the gate checks only the
# files this branch changed under frontend/src/, with the extensions prettier handles there, and fails a file only when
# it is new or was formatted at the merge base (an old unformatted file the branch touches is counted, not failed).
FORMAT_DIR = "src/"
FORMAT_EXT = (".js", ".mjs", ".cjs", ".ts", ".vue", ".css", ".json", ".html", ".md")
# The database variables the app-selected child must not see (database tests then skip, tests_app/conftest.py).
DB_ENV = ("DATABASE_URL", "TEST_DATABASE_URL", "TEST_ADMIN_DATABASE_URL", "OFO_REQUIRE_DB_TESTS")
# app-tests.yml "Throwaway broker settings": placeholders set only when absent; BROKER_TOKEN_KEY is fresh per run.
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
PrReader = Callable[[str], int | None]
NO_PR_TEXT = "no pull requests found"


class Step(NamedTuple):
    name: str
    argv: tuple
    cwd: str  # "." (the root) or a folder under it
    kind: str  # plain | clean | select | app | node | format | domain | build


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
    Step("frontend-format", ("npx", "prettier", "--check"), FRONTEND, "format"),
    Step("frontend-vitest-changed", ("npx", "vitest", "run", "--changed", "origin/main"), FRONTEND, "node"),
    Step("coverage", (PYTHON, "scripts/orchestrator/coverage.py", ".", "--check"), ".", "plain"),
    Step("reach-check", (PYTHON, "scripts/orchestrator/reach_check.py", "--root", "."), ".", "plain"),
    Step("reference-register", (PYTHON, "scripts/orchestrator/reference_register.py", "--check"), ".", "plain"),
    Step("findings-index", (PYTHON, "tools/build_findings_index.py", ".", "--check"), ".", "plain"),
    # The kit spec checks `.github/workflows/ci.yml` runs, with the same argv (read from that file).
    Step("kit-settings", (PYTHON, "tools/kit_settings.py", ".", "--check"), ".", "plain"),
    Step("factory-lint", (PYTHON, "tools/factory_lint.py", "."), ".", "plain"),
    Step("trace-check", (PYTHON, "tools/trace_check.py", "."), ".", "plain"),
    Step("build-order", (PYTHON, "tools/build_order.py", ".", "--check"), ".", "plain"),
    Step("spec-index", (PYTHON, "tools/build_spec_index.py", ".", "--check"), ".", "plain"),
    Step("spec-digest", (PYTHON, "tools/build_spec_digest.py", ".", "--check"), ".", "plain"),
    Step("spec-dupes", (PYTHON, "tools/spec_dupes.py", "."), ".", "plain"),
    Step("spec-refs", (PYTHON, "tools/check_spec_refs.py", "."), ".", "plain"),
    # CI's domain job runs the whole tests/ tree; here only the packages whose backend/ofo/<pkg>/ changed.
    Step("domain-tests", (*PYTEST,), ".", "domain"),
    # app-tests.yml `npm run build`, only when something under frontend/ changed.
    Step("frontend-build", ("npm", "run", "build"), FRONTEND, "build"),
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
            return subprocess.run([exe, *argv[1:]], cwd=cwd, env=env, stdout=out, stderr=subprocess.STDOUT,  # noqa: S603
                                  check=False).returncode
        except OSError as exc:
            out.write(f"cannot start `{argv[0]}`: {exc}\n".encode())
            return 127


def gh_runs(branch: str) -> list:
    """The branch's recent `App tests` runs, newest first; raises RuntimeError on any gh failure or odd answer."""
    cmd = ["gh", "run", "list", "--branch", branch, "--workflow", WORKFLOW, "--limit", str(GH_RUN_LIMIT),
           "--json", "databaseId,status,conclusion,headSha"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=60,  # noqa: S603
                              check=False)
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


def gh_pr_number(branch: str) -> int | None:
    """The open PR number of `branch`; None when gh says there is no PR; RuntimeError on any other gh failure."""
    cmd = ["gh", "pr", "view", branch, "--json", "number"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=60,  # noqa: S603
                              check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"gh did not run: {exc}") from exc
    if proc.returncode != 0:
        if NO_PR_TEXT in proc.stderr.lower():
            return None
        raise RuntimeError(f"gh exited {proc.returncode}: {proc.stderr.strip()[:300]}")
    try:
        number = json.loads(proc.stdout)["number"]
    except (ValueError, KeyError, TypeError) as exc:
        raise RuntimeError(f"gh answer has no PR number: {exc!r}") from exc
    if not isinstance(number, int) or isinstance(number, bool) or number < 1:
        raise RuntimeError(f"gh answer has an odd PR number: {number!r}")
    return number


class Io(NamedTuple):
    """The injected side effects of a run: child runner, App tests reader, PR reader, output line."""

    runner: Runner
    reader: GhReader
    pr_reader: PrReader
    out: Callable[[str], None]


def check_close_keywords(root: Path, branch: str, log_dir: Path, io: Io) -> int:
    """--pre-push: run pr_close_check.py for the branch's open PR. No PR = skipped (printed); a gh error refuses."""
    try:
        number = io.pr_reader(branch)
    except RuntimeError as exc:
        io.out(f"GATE REFUSED push: cannot read the PR of {branch} ({exc})")
        return GATE_REFUSED
    if number is None:
        io.out(f"pr-close-check: skipped, {branch} has no open PR")
        return 0
    log = log_dir / "pr-close-check.log"
    argv = [PYTHON, "scripts/orchestrator/pr_close_check.py", "--pr", str(number)]
    code = io.runner(argv, root, dict(os.environ), log)
    if code != 0:
        for line in tail(log):
            io.out(line)
        io.out(f"GATE FAIL pr-close-check: exit {code}")
        return GATE_FAILED
    return 0


def pre_push(root: Path, log_dir: Path, fixes_red: bool, io: Io) -> int:
    code, branch = git_text(io.runner, root, log_dir, "branch", ["rev-parse", "--abbrev-ref", "HEAD"])
    refused = check_push(branch if code == 0 else "", io.reader, fixes_red, io.out)
    return refused or check_close_keywords(root, branch, log_dir, io)


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
    if fixes_red:  # a run newer than the red is a push that is still being tested: this push would cancel it
        newer = [r for r in pending if int(r["databaseId"]) > int(newest_id)]
        if newer:
            return (f"--fixes-red but App tests run {newer[0]['databaseId']} is {newer[0]['status']}, newer than the "
                    f"red run {newest_id}: this push would cancel it")
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


PRETTIER_OK, PRETTIER_UNFORMATTED = 0, 1  # any other prettier exit code (2 = error) fails closed
FORMAT_PREFIX = "frontend-format:"


class Ctx(NamedTuple):
    """What one step needs to run commands: its definition, checkout, runner, log folder and environment."""

    step: Step
    root: Path
    runner: Runner
    log_dir: Path
    env: dict


def diff_args(kinds: str) -> list:
    """git diff of the frontend files of kind `kinds` (A added, C copied, M modified, R renamed) against origin/main;
    --no-renames turns a rename into delete + add, so a moved file counts as new."""
    return ["diff", "--name-only", "--no-renames", f"--diff-filter={kinds}", "origin/main...HEAD", "--", f"{FRONTEND}/"]


def git_lines(ctx: Ctx, log_name: str, args: list) -> tuple:
    """(exit code, output lines) of one git command run without a shell; the log keeps its output."""
    log = ctx.log_dir / log_name
    code = ctx.runner(["git", *args], ctx.root, ctx.env, log)
    return code, [ln.strip() for ln in tail(log, 100000) if ln.strip()]


COPY_PREFIX = ".gate-copy-"


def committed_answer(ctx: Ctx, rev: str, rel: str) -> tuple:
    """(git exit code, prettier exit code) for the version of `rel` committed at `rev`. The blob (`git show`, so the
    checkout's line endings never count) is written to a fresh temp file in the file's own folder with its extension
    (same prettier config, same line endings for both sides) and removed after; a non-zero git code = "cannot tell"."""
    show_log = ctx.log_dir / "frontend-format-show.log"
    code = ctx.runner(["git", "show", f"{rev}:{FRONTEND}/{rel}"], ctx.root, ctx.env, show_log)
    if code != 0:
        return code, PRETTIER_OK
    folder = ctx.root / FRONTEND / Path(rel).parent
    with tempfile.NamedTemporaryFile(dir=folder, prefix=COPY_PREFIX, suffix=Path(rel).suffix, delete=False) as copy:
        copy.write(show_log.read_bytes())
    try:
        name = (Path(rel).parent / Path(copy.name).name).as_posix()
        return 0, ctx.runner([*ctx.step.argv, name], ctx.root / ctx.step.cwd, ctx.env,
                             ctx.log_dir / "frontend-format-file.log")
    finally:
        Path(copy.name).unlink(missing_ok=True)


def ratchet(ctx: Ctx, files: list, added: set) -> tuple:
    """(exit code, log lines): which of `files` fail the ratchet. Each file's prettier answer is read on its own."""
    code, base = git_lines(ctx, "frontend-format-base-sha.log", ["merge-base", "origin/main", "HEAD"])
    if code != 0 or len(base) != 1 or not SHA.fullmatch(base[0]):
        return code or GATE_FAILED, ["cannot read the merge base: failing closed"]
    failed: list = []
    old_debt = 0
    for rel in files:
        code, answer = committed_answer(ctx, "HEAD", rel)
        if code != 0:
            return code, [f"cannot read the committed version of {rel} (exit {code}): failing closed"]
        if answer == PRETTIER_OK:
            continue
        if answer != PRETTIER_UNFORMATTED:
            return answer, [f"prettier exited {answer} on {rel}: failing closed"]
        if rel in added:
            failed.append(f"{rel}: new file, not formatted")
            continue
        code, base_answer = committed_answer(ctx, base[0], rel)
        if code != 0:
            return code, [f"cannot read or check the base version of {rel} (exit {code}): failing closed"]
        if base_answer not in (PRETTIER_OK, PRETTIER_UNFORMATTED):
            return base_answer, [f"prettier exited {base_answer} on the base version of {rel}: failing closed"]
        if base_answer == PRETTIER_UNFORMATTED:
            old_debt += 1
        else:
            failed.append(f"{rel}: formatted at the merge base, unformatted now")
    summary = [f"{FORMAT_PREFIX} {len(files)} checked, {old_debt} already unformatted at base (not failed)"]
    return (GATE_FAILED if failed else 0), [*failed, *summary]


def run_format(step: Step, root: Path, runner: Runner, log_dir: Path, env: dict) -> tuple:
    """prettier --check on the frontend files changed against origin/main, as a ratchet: a file fails when it is
    unformatted now AND (new on this branch OR formatted at the merge base). None changed = pass, `0 files`."""
    ctx = Ctx(step, root, runner, log_dir, env)
    log = log_dir / f"{step.name}.log"
    code, names = git_lines(ctx, f"{step.name}-files.log", diff_args("ACMR"))
    if code != 0:
        return code, f"{step.name}-files.log"
    code, added = git_lines(ctx, f"{step.name}-new.log", diff_args("A"))
    if code != 0:
        return code, f"{step.name}-new.log"
    prefix = f"{FRONTEND}/"
    files = [n[len(prefix):] for n in names
             if n.startswith(prefix + FORMAT_DIR) and n.endswith(FORMAT_EXT) and (root / n).is_file()]
    if not files:
        log.write_text("0 files\n", encoding="utf-8")
        return 0, None
    code = runner([*step.argv, *files], root / step.cwd, env, log)  # the common case: every file is formatted
    if code == PRETTIER_OK:
        log.write_text(f"{FORMAT_PREFIX} {len(files)} checked, 0 already unformatted at base (not failed)\n",
                       encoding="utf-8")
        return 0, None
    if code != PRETTIER_UNFORMATTED:
        return code, None
    code, summary = ratchet(ctx, files, {a[len(prefix):] for a in added})
    log.write_text("\n".join(summary) + "\n", encoding="utf-8")
    return code, None


def print_format_summary(log_dir: Path, step: Step, out: Callable[[str], None]) -> None:
    """After a passing format step: its `N checked, M already unformatted at base` line (nothing for `0 files`)."""
    for line in tail(log_dir / f"{step.name}.log", 1):
        if line.startswith(FORMAT_PREFIX):
            out(line)


def changed_names(runner: Runner, root: Path, env: dict, list_log: Path, folder: str) -> tuple:
    """(exit code, names) of the files under `folder` that differ from origin/main; a git failure is the code."""
    code = runner(["git", "diff", "--name-only", "origin/main...HEAD", "--", folder], root, env, list_log)
    return code, tail(list_log, 100000)


def run_domain(step: Step, root: Path, runner: Runner, log_dir: Path, env: dict) -> tuple:
    """pytest on tests/<pkg> for each backend/ofo/<pkg>/ with a changed file; none changed = pass, `0 packages`."""
    log = log_dir / f"{step.name}.log"
    code, names = changed_names(runner, root, env, log_dir / f"{step.name}-files.log", f"{DOMAIN_SRC}/")
    if code != 0:
        return code, f"{step.name}-files.log"
    prefix = f"{DOMAIN_SRC}/"
    pkgs = sorted({n[len(prefix):].split("/")[0] for n in names if n.startswith(prefix) and "/" in n[len(prefix):]})
    folders = [f"tests/{p}" for p in pkgs if (root / "tests" / p).is_dir()]
    if not folders:
        log.write_text("0 packages\n", encoding="utf-8")
        return 0, None
    return runner([*step.argv, *folders], root, env, log), None


def run_build(step: Step, root: Path, runner: Runner, log_dir: Path, env: dict) -> tuple:
    """npm run build only when a file under frontend/ changed (deletions count); none = pass, `0 files`."""
    log = log_dir / f"{step.name}.log"
    code, names = changed_names(runner, root, env, log_dir / f"{step.name}-files.log", f"{FRONTEND}/")
    if code != 0:
        return code, f"{step.name}-files.log"
    if not [n for n in names if n.startswith(f"{FRONTEND}/")]:
        log.write_text("0 files\n", encoding="utf-8")
        return 0, None
    if not (root / step.cwd / "node_modules").is_dir():
        log.write_text("frontend/node_modules is missing: run npm ci in frontend/\n", encoding="utf-8")
        return GATE_FAILED, None
    return runner(expand(step, root), root / step.cwd, env, log), None


SPECIAL_KINDS = {"format": run_format, "domain": run_domain, "build": run_build}  # steps that pick their own files


def run_step(step: Step, root: Path, runner: Runner, log_dir: Path) -> tuple:
    """Return (exit code, extra log name or None). A step that cannot be understood returns non-zero."""
    log = log_dir / f"{step.name}.log"
    cwd = root / step.cwd
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    if step.kind in ("node", "format") and not (cwd / "node_modules").is_dir():
        log.write_text("frontend/node_modules is missing: run npm ci in frontend/\n", encoding="utf-8")
        return GATE_FAILED, None
    if step.kind == "app":
        env = app_env(env)
    special = SPECIAL_KINDS.get(step.kind)
    if special is not None:
        return special(step, root, runner, log_dir, env)
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
    gate_began = time.monotonic()
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
        if step.kind == "format":
            print_format_summary(log_dir, step, out)
    code, dirty = git_text(runner, root, log_dir, "clean-tree-after", ["status", "--porcelain"])
    code2, head_after = git_text(runner, root, log_dir, "head-after", ["rev-parse", "HEAD"])
    if code != 0 or dirty or code2 != 0 or head_after != head:
        out("GATE REFUSED: the steps changed the tree or HEAD, so no sha is certified")
        return GATE_REFUSED
    for line in timings:
        out(line)
    out(f"  total: {time.monotonic() - gate_began:.1f}s")
    out(f"GATE PASS {head}")
    return 0


def check_push(branch: str, reader: GhReader, fixes_red: bool, out: Callable[[str], None]) -> int:
    if not branch or branch == "HEAD":
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


def git_out(cwd: Path, *args: str) -> str:
    cmd = ["git", *args]
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()  # noqa: S603


def main(argv: list | None = None, runner: Runner = default_runner, reader: GhReader = gh_runs,
         out: Callable[[str], None] = print, pr_reader: PrReader = gh_pr_number) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=None)
    ap.add_argument("--pre-push", action="store_true")
    ap.add_argument("--fixes-red", action="store_true")
    args = ap.parse_args(argv)
    if args.fixes_red and not args.pre_push:
        out("GATE REFUSED: --fixes-red only goes with --pre-push")
        return GATE_REFUSED
    try:
        root = (args.root or Path(git_out(Path.cwd(), "rev-parse", "--show-toplevel"))).resolve()
        git_dir = Path(git_out(root, "rev-parse", "--absolute-git-dir"))
    except (OSError, subprocess.CalledProcessError):
        out("GATE REFUSED: not a git checkout")
        return GATE_REFUSED
    log_dir = git_dir / "ofo-gate"
    log_dir.mkdir(parents=True, exist_ok=True)
    if args.pre_push:
        refused = pre_push(root, log_dir, args.fixes_red, Io(runner, reader, pr_reader, out))
        if refused:
            return refused
    return run_gate(root, log_dir, runner, out)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    sys.exit(main())
