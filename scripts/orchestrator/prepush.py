"""prepush.py [--full] [--repo PATH]: the project's whole pre-push list on one commit, and the marker that lets it be pushed.

Runs, in order, every step even when an earlier one fails (so one run shows everything that is red):
  ci_local (the kit's ci.yml mirror; --full is passed through), ruff_ratchet, coverage --check, alembic guard
(the last three are the checks app-tests.yml / coverage.yml run in CI that ci_local does not mirror: finding
local-ci-mirror-runs-a-subset). Each step's output goes to a log file outside the repo; one line per step.

Marker: when every step passed AND the tracked tree is clean, <git-common-dir>/ofo-prepush/<full HEAD sha>.json is
written. scripts/hooks/prepush_gate.py refuses `git push` without the marker for the pushed HEAD, and land.py checks it
before its first push. A dirty tree still runs the checks but writes no marker (the result would not describe a commit).
Exit 0 only when every step passed. Every external command goes through an injected runner(cmd, cwd, log_path) -> rc.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
MARKER_DIR = "ofo-prepush"


def steps_for(full: bool) -> list[tuple[str, list[str]]]:
    py = sys.executable
    ci = [py, "tools/ci_local.py"] + (["--full"] if full else [])
    return [
        ("ci_local", ci),
        ("ruff_ratchet", [py, "scripts/ruff_ratchet.py"]),
        ("coverage", [py, "scripts/orchestrator/coverage.py", ".", "--check"]),
        ("alembic_guard", [py, "scripts/alembic_migration_guard.py"]),
    ]


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
    body = {"sha": sha, "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "steps": [{"name": n, "rc": rc, "seconds": s} for n, rc, s, _ in results]}
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(body, handle, indent=1)
    os.replace(tmp, path)
    return path


def run_all(repo, full=False, runner=real_runner, log_dir=None, clock=time.monotonic) -> int:
    repo = os.path.abspath(repo)
    log_dir = log_dir or tempfile.mkdtemp(prefix="prepush-")
    sha = head_sha(repo)
    results = []
    for name, cmd in steps_for(full):
        log_path = os.path.join(log_dir, f"{name}.log")
        t0 = clock()
        rc = runner(cmd, repo, log_path)
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
    ap.add_argument("--full", action="store_true", help="pass --full to ci_local")
    ap.add_argument("--repo", default=ROOT, help="the checkout to check (default: this one)")
    a = ap.parse_args(argv)
    if not os.path.isdir(a.repo):
        print("repo not found: " + a.repo)
        return 2
    return run_all(a.repo, a.full)


if __name__ == "__main__":
    sys.exit(main())
