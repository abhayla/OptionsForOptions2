"""prepush.py [--full] [--repo PATH]: the whole pre-push list on one commit, and the marker that lets it be pushed.

Runs, in order, every step even when an earlier one fails (so one run shows everything that is red):
  ci_checks (ci_local on a copy of ci.yml without its pytest steps, --no-tests), domain_tests (the tests/ files the
  kit's own selection picks; --full or an unreadable diff = all of tests/), app_tests (the tests_app files
  select_app_tests picks; DB tests are CI's; cannot select = FAIL), ruff_ratchet, coverage --check, alembic guard
(the last three are checks app-tests.yml / coverage.yml run in CI that ci_local does not mirror: finding
local-ci-mirror-runs-a-subset). Why the split: kit defect Startup-Factory #186, any changed non-.py file makes
ci_local run the full suite incl. tests_app (egress allow-list leak, DB tests that must not run on this host).
Each step's output goes to a log file outside the repo; one line per step.

Marker: when every step passed AND the tracked tree is clean, <git-common-dir>/ofo-prepush/<full HEAD sha>.json is
written. scripts/hooks/prepush_gate.py refuses `git push` without the marker for the pushed HEAD, and land.py checks it
before its first push. A dirty tree still runs the checks but writes no marker (the result would not describe a commit).
Exit 0 only when every step passed. Every external command goes through an injected runner(cmd, cwd, log_path) -> rc.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
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


def _note(log_path: str, text: str) -> None:
    with open(log_path, "w", encoding="utf-8") as handle:
        handle.write(text + "\n")


class Plan:
    """The steps in run order; each step method takes its log path and returns a return code. A step that needs no
    command writes its reason to its log."""

    def __init__(self, repo, full, runner, log_dir, select_domain, select_app):  # noqa: PLR0913
        self.repo, self.full, self.runner, self.log_dir = repo, full, runner, log_dir
        self.select_domain, self.select_app = select_domain, select_app

    def run(self, *cmd, log):
        return self.runner(list(cmd), self.repo, log)

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
        py = sys.executable
        return [("ci_checks", self.ci_checks), ("domain_tests", self.domain_tests), ("app_tests", self.app_tests),
                ("ruff_ratchet", lambda log: self.run(py, "scripts/ruff_ratchet.py", log=log)),
                ("coverage", lambda log: self.run(py, "scripts/orchestrator/coverage.py", ".", "--check", log=log)),
                ("alembic_guard", lambda log: self.run(py, "scripts/alembic_migration_guard.py", log=log))]


def real_runner(cmd, cwd, log_path):
    from gate_env import no_graft_env  # noqa: PLC0415 - grafts off for every child, like land.py

    with open(log_path, "w", encoding="utf-8", errors="replace") as log:
        return subprocess.run(cmd, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, check=False,  # noqa: S603
                              env=no_graft_env()).returncode


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


def write_marker(repo, sha, results) -> str:
    path = marker_path(repo, sha)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    body = {"sha": sha, "at": datetime.now(UTC).isoformat(timespec="seconds"),
            "steps": [{"name": n, "rc": rc, "seconds": s} for n, rc, s, _ in results]}
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(body, handle, indent=1)
    os.replace(tmp, path)
    return path


def run_all(repo, full=False, runner=real_runner, log_dir=None, clock=time.monotonic,  # noqa: PLR0913
            select_domain=None, select_app=None) -> int:
    select_domain = select_domain or select_domain_tests
    select_app = select_app or select_app_tests
    repo = os.path.abspath(repo)
    log_dir = log_dir or tempfile.mkdtemp(prefix="prepush-")
    os.makedirs(log_dir, exist_ok=True)
    sha = head_sha(repo)
    results = []
    for name, step in Plan(repo, full, runner, log_dir, select_domain, select_app).steps():
        log_path = os.path.join(log_dir, f"{name}.log")
        t0 = clock()
        rc = step(log_path)
        seconds = round(clock() - t0, 1)
        results.append((name, rc, seconds, log_path))
        print(f"{'PASS' if rc == 0 else 'FAIL'} {name} {seconds}s {log_path}")
    ok = all(rc == 0 for _, rc, _, _ in results)
    note = "marker not written"
    if ok and sha is None:
        note += " (no HEAD sha)"
    elif ok and not tree_is_clean(repo):
        note += " (tracked tree is dirty: commit or stash, then run again)"
    elif ok:
        note = "marker " + write_marker(repo, sha, results)
    else:
        failed = ", ".join(n for n, rc, _, _ in results if rc != 0)
        note += f" (failed: {failed})"
    total = round(sum(s for _, _, s, _ in results), 1)
    print(f"TOTAL {'PASS' if ok else 'FAIL'} {total}s {note}")
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="run all of tests/ as the domain tests")
    ap.add_argument("--repo", default=ROOT, help="the checkout to check (default: this one)")
    a = ap.parse_args(argv)
    if not os.path.isdir(a.repo):
        print("repo not found: " + a.repo)
        return 2
    return run_all(a.repo, a.full)


if __name__ == "__main__":
    sys.exit(main())
