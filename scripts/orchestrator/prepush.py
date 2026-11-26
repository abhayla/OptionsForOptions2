"""prepush.py [--full] [--repo PATH]: the whole pre-push list on one commit, and the marker that lets it be pushed.

Runs, in order, every step even when an earlier one fails (so one run shows everything that is red), with ONE
exception: a red preflight stops the run (merge_preflight.py, 2026-11-01: a broken merge is caught in minutes, and the
long steps would only repeat it). Order: the seconds-long checks first (finding cheap-check-after-expensive-one,
2026-11-26: they ran after ~1985 s of long stages and 12 gate runs failed late): ruff_ratchet, coverage --check,
alembic guard (the checks app-tests.yml / coverage.yml run in CI that ci_local does not mirror: finding
local-ci-mirror-runs-a-subset); then, when frontend/ runs, frontend_lint (eslint ignores dist/, so it needs no build)
and frontend_build (still before everything that reads frontend/dist: the preflight's layer 0 and the domain tests'
bundle secret scan); then preflight (--no-domain-scans with --full, since all of tests/ runs next), ci_checks (ci_local
on a copy of ci.yml without its pytest steps, --no-tests), domain_tests (the tests/ files the kit's own selection
picks; --full or an unreadable diff = all of tests/), app_tests (the tests_app files select_app_tests picks: those a backend/ change can break PLUS every changed
tests_app test file, its conftest subtree and the tests naming a changed helper/data file; DB tests
are CI's; cannot select = FAIL), and frontend_unit last. Why the split: kit defect Startup-Factory #186, any changed
non-.py file makes ci_local run the full suite incl. tests_app (egress allow-list leak, DB tests that must not run on
this host).
When the change since the merge base with origin/main touches frontend/ (or that diff cannot be read: fail closed),
the frontend steps run in frontend/, as app-tests.yml does in CI: npm run lint, npm run build, and
npx vitest related --run <changed src/tests files> (every test file with --full or when a deletion / non-src file
changed). A missing frontend/node_modules or tool is a FAIL with the reason, never a skip (orchestrator finding 1,
2026-10-27: a marker was written over 37 red vitest tests).
Jobs (--jobs N or PREPUSH_JOBS, the option wins; default os.cpu_count(); N < 1 or not a number = usage error, exit
2): N == 1 is the reference mode, the serial loop above. N > 1 runs the same serial prefix (the cheap checks,
frontend_lint, frontend_build), then preflight, ci_checks, domain_tests, app_tests and frontend_unit side by side in
min(N, steps) threads, preflight submitted first; each keeps its own log, seconds and STEP_TIMEOUT_S. A red preflight
sets a stop event: steps not started are reported `FAIL <name> 0.0s stopped: preflight failed`, running ones are killed
with their whole process tree (POSIX: own session + killpg SIGTERM then SIGKILL after KILL_GRACE_S; Windows:
CREATE_NEW_PROCESS_GROUP + `taskkill /F /T`), then the STOP line. The same tree kill ends a step at STEP_TIMEOUT_S.
Docs-only lane (not with --full): when EVERY path changed between the merge base with origin/main and the START sha
(not symbolic HEAD, which can move) is a records file (tools/change_scope.py path_is_docs from the checked repo; status
A or M, or D of a records path; mode 100644; no rename, symlink or submodule; tools/change_scope.py itself among the
changes, or anything unreadable = the full lane), the marker and the report record lane "docs-only (<n> files)" and
app_tests also runs the tests_app files that READ a docs-folder path (select_docs_app_tests; a selection error =
FAIL). The lane SKIPS NOTHING (SKIPPABLE is empty, so the structural marker check rejects any skipped step): on a
docs-only change today's selectors already run no code-only stage (domain tests narrow to the records tests, the code
app selection is empty, no frontend step), so the lane removes nothing and only adds the docs-reading app tests.
ruff_ratchet and alembic_guard cost under a second and a red one (e.g. another local ruff version) must refuse.
KeyboardInterrupt kills every running child's process tree (serial and parallel; the parallel main thread sets the
stop event first), then propagates: no marker.
Isolation (both modes): every child gets its own TMPDIR/TEMP/TMP, <tempdir>/ofo-prepush-tmp/<sha1(repo)[:12]>/<step>
(stable across runs, so the preflight's mypy cache stays warm; no two stages share one).
Each step's output goes to a log file outside the repo; one line per step. A step that times out
(STEP_TIMEOUT_S) or cannot start is a FAIL. The child environment never carries TEST_DATABASE_URL,
TEST_ADMIN_DATABASE_URL or ALEMBIC_DATABASE_URL (this host's PostgreSQL serves production; DB tests are CI's).

Marker: written to <git-common-dir>/ofo-prepush/<full HEAD sha>.json only when every step passed (structurally: the
set of result step names equals the planned set and every rc is 0, so a step that never ran or was stopped cannot
count; body "mode": {"jobs": N, "lane": "full"}) AND the tracked tree
was clean at the start and at the end AND HEAD is the same sha at the end as at the start AND no untracked,
not-ignored file sits under backend/, tests*/, scripts/ or frontend/src/ (CI sees only the committed tree; such
files are named in the refusal). scripts/hooks/prepush_gate.py refuses `git push` without the marker for the pushed
HEAD, and land.py checks it before its first push. A dirty tree still runs the checks but writes no marker (the result
would not describe a commit).
Known gaps (not chased): Playwright e2e is CI's only; `vitest related` trusts vitest's import graph (a test that
reaches a changed file only at run time, e.g. a dynamic import by computed name, is not picked: use --full); an
untracked file that .gitignore hides is not counted; a change outside backend/, tests*/, scripts/, frontend/src/ left
untracked is not counted.
TOTAL line: `TOTAL PASS|FAIL <wall-clock>s (steps sum <s>s, jobs N) <note>`.
Exit 0 only when every step passed. Every external command goes through an injected runner(cmd, cwd, log_path) -> rc.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
MARKER_DIR = "ofo-prepush"


PYTEST_RUN = re.compile(r"(?:python\d*(?:\.\d+)?\s+-m\s+pytest\b|(?:^|[;&|]\s*)pytest\b)", re.M)


def ci_checks_workflow(repo: str, out_dir: str) -> tuple[str, list[str]]:
    """Write a copy of ci.yml without the steps whose `run:` invokes pytest; return (path, removed step names).
    The copy keeps every other step as loaded (kit defect Startup-Factory #186: the kit picks the full suite,
    tests_app included, as soon as a non-.py file changed; the tests run in their own steps below)."""
    import yaml  # noqa: PLC0415

    with open(os.path.join(repo, ".github", "workflows", "ci.yml"), encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    removed: list[str] = []
    for job in (data.get("jobs") or {}).values():
        kept = []
        for step in job.get("steps") or []:
            if PYTEST_RUN.search(str(step.get("run", ""))):
                removed.append(str(step.get("name") or step.get("run", "")[:40]))
            else:
                kept.append(step)
        job["steps"] = kept
    path = os.path.join(out_dir, "ci-no-pytest.yml")
    with open(path, "w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, sort_keys=False, width=10_000)
    return path, removed


def select_domain_tests(repo: str, base: str = "origin/main") -> list[str] | None:
    """tests/ files the kit's own selection picks (ci_local.select_tests, imported): None = whole tests/."""
    import importlib.util  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    spec = importlib.util.spec_from_file_location("ci_local_for_prepush", os.path.join(repo, "tools", "ci_local.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses in the module need it registered
    spec.loader.exec_module(module)
    picked, _reason = module.select_tests(Path(repo), base)
    if picked is None:
        return None
    return [p for p in picked if p.replace("\\", "/").startswith("tests/")]


def select_app_tests(repo: str) -> tuple[int, list[str], str]:
    """(rc, tests_app files, message) from scripts/orchestrator/select_app_tests.py; rc != 0 means cannot select."""
    r = subprocess.run([sys.executable, os.path.join("scripts", "orchestrator", "select_app_tests.py"), "."],  # noqa: S603
                       cwd=repo, capture_output=True, text=True, check=False)
    out = (r.stdout or "") + (r.stderr or "")
    files = [ln.strip() for ln in out.splitlines() if ln.strip().endswith(".py")]
    return r.returncode, files, out.strip()


SKIPPABLE: tuple[str, ...] = ()  # the steps a lane may skip: none (round 1: the docs-only lane skips nothing)
RECORDS_MODES = {"A": ("000000", "100644"), "M": ("100644", "100644"), "D": ("100644", "000000")}


def load_change_scope(repo: str):
    """tools/change_scope.py of the CHECKED repo (like select_domain_tests imports ci_local)."""
    import importlib.util  # noqa: PLC0415

    path = os.path.join(repo, "tools", "change_scope.py")
    spec = importlib.util.spec_from_file_location("change_scope_for_prepush", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CLASSIFIER = "tools/change_scope.py"


def docs_only_entries(path_is_docs, entries) -> int | None:
    """Number of entries when every one is an added / modified / deleted records file (mode 100644, one path), else
    None. entries: (status letter, [paths], (old mode, new mode)) as change_scope.parse_raw_z gives them."""
    if not entries:
        return None
    if any(CLASSIFIER in paths for _, paths, _ in entries):
        return None  # the classifier's own change must not vouch for itself
    for status, paths, modes in entries:
        if status not in RECORDS_MODES or len(paths) != 1 or tuple(modes) != RECORDS_MODES[status]:
            return None
        if not path_is_docs(paths[0]):
            return None
    return len(entries)


def docs_only_change(repo: str, sha: str | None = None, base: str = "origin/main") -> int | None:
    """Count of changed files when the whole change since the merge base is records files, else None (fail closed:
    no merge base, git error, empty diff, tools/change_scope.py not importable or changed, anything unexpected).
    The diff is merge-base..sha, sha being the start sha of the run (HEAD only when none is given)."""
    sha = sha or "HEAD"
    try:
        rc, merge_base = _git(repo, "merge-base", base, sha)
        if rc != 0 or not merge_base:
            return None
        scope = load_change_scope(repo)
        proc = subprocess.run(["git", "-C", repo, "--no-pager", "-c", "core.quotepath=off", "diff", "--raw", "-z",  # noqa: S603, S607
                               "--no-renames", "--no-abbrev", "--no-ext-diff", merge_base, sha, "--"],
                              capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
        if proc.returncode != 0:
            return None
        return docs_only_entries(scope.path_is_docs, scope.parse_raw_z(proc.stdout) or [])
    except Exception:  # noqa: BLE001 - any doubt is the full lane
        return None


def docs_readers_patterns(folders) -> tuple[re.Pattern[str], re.Pattern[str]]:
    """(string literal starting with a docs folder and '/', a Path / join operand naming a docs folder)."""
    names = "|".join(re.escape(f) for f in folders)
    literal = re.compile(rf"""["'`](?:\./)?(?:{names})/""")
    quoted = rf"""["'](?:{names})["']"""
    joined = re.compile(rf"/\s*{quoted}|{quoted}\s*/|(?:join|joinpath|Path|PurePath)\([^)\n]*{quoted}")
    return literal, joined


def select_docs_app_tests(repo: str) -> tuple[int, list[str], str]:
    """(rc, tests_app/**/test_*.py files that read a docs path, message); rc != 0 = cannot select (fail closed).
    A helper or conftest.py that names a docs path selects every test that imports it (conftest: every test beside or
    below it)."""
    try:
        literal, joined = docs_readers_patterns(load_change_scope(repo).DOCS_FOLDERS)
        root = os.path.join(repo, "tests_app")
        if not os.path.isdir(root):
            return 1, [], "tests_app/ not found"
        tests, helpers = [], []
        for here, dirs, files in os.walk(root):
            dirs[:] = sorted(d for d in dirs if d != "__pycache__")
            for name in sorted(files):
                if name.endswith(".py"):
                    path = os.path.join(here, name)
                    with open(path, encoding="utf-8") as handle:
                        text = handle.read()
                    rel = os.path.relpath(path, repo).replace(os.sep, "/")
                    (tests if name.startswith("test_") else helpers).append((rel, text))
        reads = lambda text: bool(literal.search(text) or joined.search(text))  # noqa: E731
        readers = [rel for rel, text in helpers if reads(text)]

        def uses(rel, text, helper):
            stem = os.path.splitext(os.path.basename(helper))[0]
            if stem == "conftest":
                return rel.startswith(os.path.dirname(helper) + "/")
            return re.search(rf"\b{re.escape(stem)}\b", text) is not None

        picked = sorted(rel for rel, text in tests if reads(text) or any(uses(rel, text, h) for h in readers))
        return 0, picked, f"{len(picked)} tests_app files read docs paths"
    except Exception as exc:  # noqa: BLE001 - cannot select: fail closed
        return 1, [], repr(exc)


FRONTEND = "frontend"
FRONTEND_TEST_DIRS = ("src/", "tests/")  # a change elsewhere in frontend/ (config, package.json) runs every test file


def frontend_changes(repo: str, base: str = "origin/main") -> list[str] | None:
    """frontend/ paths (relative to frontend/) changed since the merge base with origin/main, as
    [path] for an added/modified file and ["*"] when any frontend change needs every test file (a deletion, a rename,
    a non-src change). [] = no frontend change. None = the diff could not be read (callers fail closed: run it all)."""
    rc, mb = _git(repo, "merge-base", base, "HEAD")
    if rc != 0 or not mb:
        return None
    rc, out = _git(repo, "diff", "--name-status", "--no-renames", mb, "HEAD", "--", FRONTEND)
    if rc != 0:
        return None
    picked: list[str] = []
    for line in out.splitlines():
        status, _, path = line.partition("\t")
        rel = path.replace("\\", "/")[len(FRONTEND) + 1:]
        if not status.startswith(("A", "M")) or not rel.startswith(FRONTEND_TEST_DIRS):
            return ["*"]
        picked.append(rel)
    return picked


def _note(log_path: str, text: str) -> None:
    with open(log_path, "w", encoding="utf-8") as handle:
        handle.write(text + "\n")


class Plan:
    """The steps in run order; each step method takes its log path and returns a return code. A step that needs no
    command writes its reason to its log."""

    def __init__(self, repo, full, runner, log_dir, select_domain, select_app,  # noqa: PLR0913
                 frontend=(), which=shutil.which, skips=None):
        self.skips = dict(skips or {})  # step name -> reason it is not run (the docs-only lane)
        self.repo, self.full, self.runner, self.log_dir = repo, full, runner, log_dir
        self.select_domain, self.select_app = select_domain, select_app
        self.frontend, self.which = frontend, which  # frontend: frontend_changes() result

    def run(self, *cmd, log):
        return self.runner(list(cmd), self.repo, log)

    def front(self, tool, args, log):
        """One frontend step in frontend/. Missing node_modules or tool = FAIL with the reason, never a skip."""
        cwd = os.path.join(self.repo, FRONTEND)
        if not os.path.isdir(os.path.join(cwd, "node_modules")):
            _note(log, f"FAIL: {cwd}/node_modules is missing (run npm ci in frontend/); a frontend change cannot be "
                       "checked without it")
            return 1
        exe = self.which(tool)
        if not exe:
            _note(log, f"FAIL: {tool} not found on PATH")
            return 1
        return self.runner([exe, *args], cwd, log)

    def frontend_unit(self, log):
        changed = self.frontend
        if self.full or changed is None or "*" in changed:
            return self.front("npx", ["vitest", "run"], log)
        # the tests whose import graph reaches a changed file (orchestrator finding 3: every test that mounts it)
        return self.front("npx", ["vitest", "related", "--run", *changed], log)

    def ci_checks(self, log):
        try:
            workflow, removed = ci_checks_workflow(self.repo, self.log_dir)
        except Exception as exc:  # noqa: BLE001 - cannot build the workflow copy: fail closed
            _note(log, f"could not write the pytest-free ci.yml copy: {exc!r}")
            return 1
        print("ci_checks: pytest steps removed from the workflow copy: " + ("; ".join(removed) or "none"))
        return self.run(sys.executable, "tools/ci_local.py", "--workflow", workflow, "--no-tests", log=log)

    def domain_tests(self, log):
        try:
            files = None if self.full else self.select_domain(self.repo)
        except Exception as exc:  # noqa: BLE001 - selection failed: fail closed
            _note(log, f"could not select the domain tests: {exc!r}")
            return 1
        if files is not None and not files:
            _note(log, "no domain tests needed")
            return 0
        return self.run(sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *(files or ["tests/"]), log=log)

    def app_tests(self, log):
        try:
            rc, files, message = self.select_app(self.repo)
        except Exception as exc:  # noqa: BLE001
            rc, files, message = 1, [], repr(exc)
        if rc != 0:
            _note(log, "cannot select the app tests (fail closed): " + message)
            return 1
        if not files:
            _note(log, "no app tests selected (DB tests are CI's)")
            return 0
        _note(log, "DB tests are CI's; running the selected files under pytest-app.ini")
        return self.run(sys.executable, "-m", "pytest", "-c", "pytest-app.ini", "-q", "-p", "no:cacheprovider", *files,
                        log=log)

    def steps(self):
        """The steps to run, in order (skipped ones left out)."""
        return [(n, f) for n, f in self.all_steps() if n not in self.skips]

    def all_steps(self):
        py = sys.executable
        front = self.frontend != []  # None (diff unreadable) runs them too: fail closed
        # seconds-long checks first (finding cheap-check-after-expensive-one: they used to run after ~33 min of long
        # stages, and 12 gate runs failed late on them)
        steps = [("ruff_ratchet", lambda log: self.run(py, "scripts/ruff_ratchet.py", log=log)),
                 ("coverage", lambda log: self.run(py, "scripts/orchestrator/coverage.py", ".", "--check", log=log)),
                 ("alembic_guard", lambda log: self.run(py, "scripts/alembic_migration_guard.py", log=log))]
        if front:
            # lint needs no build (frontend/eslint.config.js ignores dist/); the build still comes before everything
            # that reads frontend/dist: the preflight's layer 0 and the domain tests' bundle secret scan (a build left
            # from before a merge failed that scan on right code, 2026-11-01, one ~35 min gate run lost)
            steps += [("frontend_lint", lambda log: self.front("npm", ["run", "lint"], log)),
                      ("frontend_build", lambda log: self.front("npm", ["run", "build"], log))]
        # then the minutes-long checks of a broken merge; a red preflight stops the run (run_all). With --full all of
        # tests/ runs next, so the preflight skips its tests/ repo_scan subset; a selection run keeps it (MINOR 7)
        skip = ["--no-domain-scans"] if self.full else []
        steps += [("preflight", lambda log: self.run(py, "scripts/orchestrator/merge_preflight.py", ".", "--log-dir",
                                                     self.log_dir, *skip, log=log)),
                  ("ci_checks", self.ci_checks), ("domain_tests", self.domain_tests), ("app_tests", self.app_tests)]
        if front:
            steps.append(("frontend_unit", self.frontend_unit))
        return steps


DB_ENV = ("TEST_DATABASE_URL", "TEST_ADMIN_DATABASE_URL", "ALEMBIC_DATABASE_URL")
STEP_TIMEOUT_S = 3600
TIMEOUT_RC = 124
STOPPED_RC = 125
KILL_GRACE_S = 10  # SIGTERM, then SIGKILL for the whole group after this long
POLL_S = 0.2
TMP_ROOT_NAME = "ofo-prepush-tmp"
STOP_REASON = "stopped: preflight failed"
#: steps that run side by side with jobs > 1 (preflight first); everything before preflight in the plan is the serial
#: prefix. Order here is the submit order.
LONG_STEPS = ("preflight", "ci_checks", "domain_tests", "app_tests", "frontend_unit")


def step_temp_root(repo, step) -> str:
    """<tempdir>/ofo-prepush-tmp/<sha1 of the abs repo path, 12 chars>/<step>, created. Stable across runs (the
    preflight's mypy cache lives under gettempdir()); one per step, so no two stages share a temp root."""
    key = hashlib.sha1(os.path.abspath(repo).encode("utf-8"), usedforsecurity=False).hexdigest()[:12]
    path = os.path.join(tempfile.gettempdir(), TMP_ROOT_NAME, key, step)
    os.makedirs(path, exist_ok=True)
    return path


def child_env(environ=None, tmp_root=None) -> dict:
    """The parent environment minus every DB URL, always (review F4): this host's PostgreSQL also serves production,
    so the selected DB tests must skip here even when the run sits under db_run.py; CI runs them. With tmp_root the
    child's TMPDIR, TEMP and TMP point at it."""
    env = dict(os.environ if environ is None else environ)
    for key in DB_ENV:
        env.pop(key, None)
    if tmp_root:
        for key in ("TMPDIR", "TEMP", "TMP"):
            env[key] = tmp_root
    return env


IS_WINDOWS = os.name == "nt"


def _spawn_kwargs() -> dict:
    """Own session (POSIX) or process group (Windows), so the whole tree can be killed."""
    if IS_WINDOWS:
        return {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200)}
    return {"start_new_session": True}


def _signal_group(pid, sig) -> None:
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(pid, sig)


def kill_tree(proc) -> None:
    """Kill the child and everything it started. POSIX: SIGTERM to the group, SIGKILL after KILL_GRACE_S (and always
    once the leader is gone: a grandchild may outlive it). Windows: taskkill /F /T."""
    if IS_WINDOWS:
        cmd = ["taskkill", "/F", "/T", "/PID", str(proc.pid)]
        try:
            subprocess.run(cmd, capture_output=True, check=False)  # noqa: S603
        except OSError:  # no taskkill on this PATH: kill the child itself, never crash the run
            proc.kill()
    else:
        _signal_group(proc.pid, signal.SIGTERM)
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=KILL_GRACE_S)
        _signal_group(proc.pid, signal.SIGKILL)
    proc.wait()


class RealRunner:
    """runner(cmd, cwd, log_path) -> rc, with a stop event: when it is set a running child is killed with its whole
    tree and the step is a FAIL (STOPPED_RC). The same tree kill ends a step at STEP_TIMEOUT_S."""

    def __init__(self, repo=None, stop=None):
        self.repo = repo
        self.stop = stop if stop is not None else threading.Event()

    def __call__(self, cmd, cwd, log_path):
        # otherwise the plain environment: gate_env.no_graft_env() would leak GIT_GRAFT_FILE into pytest and break
        # tests/orchestrator/test_gate_env.py (the graft test needs git to honour grafts)
        step = os.path.splitext(os.path.basename(log_path))[0]
        with open(log_path, "w", encoding="utf-8", errors="replace") as log:
            try:
                env = child_env(tmp_root=step_temp_root(self.repo or cwd, step))
                proc = subprocess.Popen(cmd, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, env=env,  # noqa: S603
                                        **_spawn_kwargs())
            except OSError as exc:  # the tool could not start: a FAIL, never a pass
                log.write(f"\nFAIL: could not start {cmd[0]}: {exc!r}\n")
                return 1
            try:
                return self._wait(proc, log)
            except BaseException:  # Ctrl-C, SystemExit: never leave the child tree running
                kill_tree(proc)
                raise

    def _wait(self, proc, log):
        deadline = time.monotonic() + STEP_TIMEOUT_S
        while True:
            try:
                return proc.wait(timeout=POLL_S)
            except subprocess.TimeoutExpired:
                pass
            if self.stop.is_set():
                kill_tree(proc)
                log.write(f"\nFAIL: {STOP_REASON}\n")
                return STOPPED_RC
            if time.monotonic() >= deadline:
                kill_tree(proc)
                log.write(f"\nFAIL: timed out after {STEP_TIMEOUT_S}s\n")
                return TIMEOUT_RC


real_runner = RealRunner()  # stays importable; run_all builds its own (repo-bound) instance


def _git(repo, *args):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, check=False)  # noqa: S603, S607
    return r.returncode, (r.stdout or "").strip()


def head_sha(repo) -> str | None:
    rc, out = _git(repo, "rev-parse", "HEAD")
    return out if rc == 0 and len(out) == 40 else None  # noqa: PLR2004


def marker_dir(repo) -> str | None:
    rc, out = _git(repo, "rev-parse", "--git-common-dir")
    if rc != 0 or not out:
        return None
    return os.path.join(os.path.abspath(os.path.join(repo, out)), MARKER_DIR)


def marker_path(repo, sha) -> str:
    base = marker_dir(repo)
    if base is None:
        raise ValueError(f"not a git repository: {repo}")
    return os.path.join(base, f"{sha}.json")


def has_marker(repo, sha) -> bool:
    """True when a marker for exactly this sha exists and names this sha (a copied/renamed file does not count)."""
    try:
        with open(marker_path(repo, sha), encoding="utf-8") as handle:
            return json.load(handle).get("sha") == sha
    except (OSError, ValueError, AttributeError):
        return False


def tree_is_clean(repo) -> bool:
    rc, out = _git(repo, "status", "--porcelain", "--untracked-files=no")
    return rc == 0 and out == ""


UNTRACKED_SHOWN = 10
UNTRACKED_SOURCE = ("backend/", "tests", "scripts/", "frontend/src/")  # "tests" = tests/, tests_app/, tests_*


def untracked_source(repo) -> list[str] | None:
    """Untracked, not-ignored files where code lives (review F2: CI checks the committed tree only, so a committed
    file importing a never-added module passes here and fails in CI). Junk elsewhere (pid.txt at the root) is
    ignored. None = git failed (callers treat it as not clean)."""
    rc, out = _git(repo, "ls-files", "--others", "--exclude-standard")
    if rc != 0:
        return None
    return [p for p in out.splitlines() if p.replace("\\", "/").startswith(UNTRACKED_SOURCE)]


def marker_rows(results, skips, order) -> list[dict]:
    """The marker's step rows in plan order: a run step is {name, rc, seconds}, a skipped one {name, skipped}."""
    rows = {n: {"name": n, "rc": rc, "seconds": s} for n, rc, s, _ in results}
    rows.update({n: {"name": n, "skipped": reason} for n, reason in skips.items()})
    return [rows[n] for n in order if n in rows]


def write_marker(repo, sha, rows, mode=None) -> str:
    path = marker_path(repo, sha)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    body = {"sha": sha, "at": datetime.now(UTC).isoformat(timespec="seconds"),
            "mode": mode or {"jobs": 1, "lane": "full"}, "steps": rows}
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(body, handle, indent=1)
    os.replace(tmp, path)
    return path


def _line(name, rc, seconds, log_path) -> str:
    return f"{'PASS' if rc == 0 else 'FAIL'} {name} {seconds}s {log_path}"


def _run_steps(plan: Plan, log_dir: str, clock) -> list:
    """Every step in order, one PASS/FAIL line each; a red preflight stops the run (a broken merge is caught in
    minutes, and the long steps would only repeat it). The reference mode (jobs == 1)."""
    results = []
    for name, step in plan.steps():
        log_path = os.path.join(log_dir, f"{name}.log")
        t0 = clock()
        rc = step(log_path)
        seconds = round(clock() - t0, 1)
        results.append((name, rc, seconds, log_path))
        print(_line(name, rc, seconds, log_path))
        if name == "preflight" and rc != 0:
            print("STOP: preflight failed; the long steps were not run (fix it, commit, run again)")
            break
    return results


def _run_parallel(plan: Plan, log_dir: str, clock, jobs: int, stop: threading.Event) -> list:
    """The serial prefix first (as _run_steps), then the long steps in min(jobs, count) threads, preflight submitted
    first. A red preflight sets `stop`: queued steps are not started (FAIL, 0.0s) and running ones are stopped by the
    runner. Results come back in plan order."""
    steps = plan.steps()
    prefix = [(n, f) for n, f in steps if n not in LONG_STEPS]
    long_steps = sorted(((n, f) for n, f in steps if n in LONG_STEPS), key=lambda nf: LONG_STEPS.index(nf[0]))
    results = []
    for name, step in prefix:
        log_path = os.path.join(log_dir, f"{name}.log")
        t0 = clock()
        rc = step(log_path)
        seconds = round(clock() - t0, 1)
        results.append((name, rc, seconds, log_path))
        print(_line(name, rc, seconds, log_path))
    lock = threading.Lock()

    def work(name, step):
        log_path = os.path.join(log_dir, f"{name}.log")
        if stop.is_set():
            _note(log_path, "FAIL: " + STOP_REASON)
            with lock:
                print(f"FAIL {name} 0.0s {STOP_REASON} {log_path}")
            return name, STOPPED_RC, 0.0, log_path
        t0 = clock()
        try:
            rc = step(log_path)
        except Exception as exc:  # noqa: BLE001 - an exception inside a worker is a FAIL, never a pass
            rc = 1
            with open(log_path, "a", encoding="utf-8") as handle:
                handle.write(f"\nFAIL: step raised {exc!r}\n")
        seconds = round(clock() - t0, 1)
        if name == "preflight" and rc != 0:
            stop.set()
        with lock:
            print(_line(name, rc, seconds, log_path))
        return name, rc, seconds, log_path

    if long_steps:
        with ThreadPoolExecutor(max_workers=max(1, min(jobs, len(long_steps)))) as pool:
            try:
                futures = [pool.submit(work, n, f) for n, f in long_steps]
                parallel = [fut.result() for fut in futures]
            except BaseException:  # Ctrl-C in the main thread: the workers kill their trees, then the pool is joined
                stop.set()
                raise
        by_name = {r[0]: r for r in parallel}
        results += [by_name[n] for n, _ in steps if n in by_name]
        if by_name.get("preflight", ("", 0))[1] != 0:
            print("STOP: preflight failed; steps not yet started were not run and running ones were stopped "
                  "(fix it, commit, run again)")
    return results


def complete(results, planned, skips=()) -> bool:
    """Structural check for the marker: the run results plus the skipped steps are exactly the planned names (each
    once), every rc is 0, and only steps in SKIPPABLE are skipped. A step that never ran or was stopped can never
    count as passed."""
    names = [n for n, _, _, _ in results] + list(skips)
    return (len(names) == len(set(names)) and set(names) == set(planned) and set(skips) <= set(SKIPPABLE)
            and all(rc == 0 for _, rc, _, _ in results))


def _blocker(repo, sha, clean_at_start) -> str | None:
    """Why no marker may be written for this finished run, or None."""
    untracked = untracked_source(repo)
    end_sha = head_sha(repo) if sha is not None and clean_at_start else None
    if sha is None:
        reason = "no HEAD sha"
    elif not clean_at_start:
        reason = "tracked tree was dirty when the run started: commit or stash, then run again"
    elif end_sha != sha:
        reason = f"HEAD moved during the run: started on {sha[:7]}, now {(end_sha or '?')[:7]}; run again"
    elif not tree_is_clean(repo):
        reason = "tracked tree is dirty: commit or stash, then run again"
    elif untracked is None:
        reason = "could not list untracked files"
    elif untracked:
        more = f" and {len(untracked) - UNTRACKED_SHOWN} more" if len(untracked) > UNTRACKED_SHOWN else ""
        reason = ("untracked source files CI will not see: " + ", ".join(untracked[:UNTRACKED_SHOWN]) + more
                  + "; add or remove them, then run again")
    else:
        reason = None
    return reason


def _marker_note(repo, start, rows, ok, mode) -> str:
    """Write the marker when every condition holds and say so; otherwise the reason it was not written.
    start = (sha, tree was clean at the start)."""
    note = "marker not written"
    if not ok:
        failed = ", ".join(r["name"] for r in rows if r.get("rc", 0) != 0)
        return note + (f" (failed: {failed})" if failed else " (a planned step has no passing result)")
    if (reason := _blocker(repo, *start)) is not None:
        return note + f" ({reason})"
    return "marker " + write_marker(repo, start[0], rows, mode)


PROXY_VARS = ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy", "ALL_PROXY", "all_proxy")


def proxy_notice(environ=None) -> str | None:
    """One NOTICE line naming (never showing the values of) the proxy variables set in this environment, else None.
    A notice only: it changes no verdict and no marker."""
    env = os.environ if environ is None else environ
    names = [n for n in PROXY_VARS if env.get(n)]
    if not names:
        return None
    return (f"NOTICE: proxy variables set ({', '.join(names)}): tests that expect the egress gate to refuse (e.g. "
            "tests_app/test_kite_broker_reader.py attack2) fail behind a proxy; in a cloud container run the gate with "
            "them unset (runbook, Before a push)")


def _lane(repo, full, select_docs_only, sha=None) -> tuple[str, dict, bool]:
    """(lane name, {step: reason it is skipped} (empty: SKIPPABLE is empty), is the docs-only lane). --full, no start
    sha and any doubt = the full lane."""
    try:
        count = None if full or sha is None else select_docs_only(repo, sha)
    except Exception:  # noqa: BLE001 - cannot tell: the full lane
        count = None
    if count is None:
        return "full", {}, False
    return f"docs-only ({count} files)", dict.fromkeys(SKIPPABLE, f"docs-only change ({count} files)"), True


def _frontend_changes_or_none(select_frontend, repo):
    try:
        return select_frontend(repo)
    except Exception:  # noqa: BLE001 - cannot tell: fail closed, run every frontend step
        return None


def run_all(repo, full=False, runner=None, log_dir=None, clock=time.monotonic,  # noqa: PLR0913
            select_domain=None, select_app=None, select_frontend=None, which=shutil.which, jobs=1,
            select_docs_only=None, select_docs_app=None) -> int:
    select_domain = select_domain or select_domain_tests
    select_app = select_app or select_app_tests
    select_frontend = select_frontend or frontend_changes
    repo = os.path.abspath(repo)
    runner = runner or RealRunner(repo=repo)
    stop = getattr(runner, "stop", None)
    if not isinstance(stop, threading.Event):
        stop = threading.Event()
    log_dir = log_dir or tempfile.mkdtemp(prefix="prepush-")
    os.makedirs(log_dir, exist_ok=True)
    started = clock()
    if (notice := proxy_notice()) is not None:
        print(notice)
    sha = head_sha(repo)
    clean_at_start = tree_is_clean(repo)  # review F3: the tree is the commit for the whole run, not only at the end
    lane, skips, docs_lane = _lane(repo, full, select_docs_only or docs_only_change, sha)
    if docs_lane:  # a docs-only change: no frontend step is planned; app_tests runs the files that read docs paths
        frontend, select_app = [], select_docs_app or select_docs_app_tests
        print(f"LANE {lane}: nothing is skipped; app_tests runs the tests_app files that read docs paths")
        for name, reason in skips.items():
            print(f"SKIP {name} skipped: {reason}")
    else:
        frontend = _frontend_changes_or_none(select_frontend, repo)
    plan = Plan(repo, full, runner, log_dir, select_domain, select_app, frontend, which, skips)
    order = [n for n, _ in plan.all_steps()]
    serial = jobs <= 1
    results = _run_steps(plan, log_dir, clock) if serial else _run_parallel(plan, log_dir, clock, jobs, stop)
    ok = complete(results, order, skips)
    rows = marker_rows(results, skips, order)
    note = _marker_note(repo, (sha, clean_at_start), rows, ok, {"jobs": jobs, "lane": lane})
    wall = round(clock() - started, 1)
    total = round(sum(s for _, _, s, _ in results), 1)
    print(f"TOTAL {'PASS' if ok else 'FAIL'} {wall}s (steps sum {total}s, jobs {jobs}) {note}")
    return 0 if ok else 1


def resolve_jobs(option=None, environ=None) -> int:
    """--jobs wins over PREPUSH_JOBS; default os.cpu_count() or 1. ValueError (a usage error) for N < 1 or text."""
    env = os.environ if environ is None else environ
    raw = option if option is not None else env.get("PREPUSH_JOBS")
    if raw is None or str(raw).strip() == "":
        return os.cpu_count() or 1
    try:
        jobs = int(str(raw).strip())
    except ValueError:
        raise ValueError(f"jobs must be a whole number >= 1, got {raw!r}") from None
    if jobs < 1:
        raise ValueError(f"jobs must be >= 1, got {jobs}")
    return jobs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="run all of tests/ as the domain tests, and every vitest file")
    ap.add_argument("--repo", default=ROOT, help="the checkout to check (default: this one)")
    ap.add_argument("--jobs", default=None, metavar="N",
                    help="long steps side by side (default: PREPUSH_JOBS, else the CPU count; 1 = serial reference)")
    a = ap.parse_args(argv)
    if not os.path.isdir(a.repo):
        print("repo not found: " + a.repo)
        return 2
    try:
        jobs = resolve_jobs(a.jobs)
    except ValueError as exc:
        print("usage error: " + str(exc))
        return 2
    return run_all(a.repo, a.full, jobs=jobs)


if __name__ == "__main__":
    sys.exit(main())
