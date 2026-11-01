"""merge_preflight.py [repo] [--base REF]: the fast checks that catch a broken merge in minutes, before the long gate.

Why (measured, 2026-11-01 GC-MU integration and GC-MU close): the full gate (``prepush.py --full``, ~25 min) was the
first thing to see three classes of break, and each one cost a whole gate run:
- a clean TEXTUAL merge whose code no longer runs: five calls in a file with no conflict used the other branch's old
  function shapes (a deleted constant, a newly required ``quality`` / ``windows`` / ``config`` / ``gap_until``);
- tests calling old shapes (``read_snapshot`` without ``quality``, ``Context`` without ``view``, ``apply_update``
  without ``max_delist_percent``);
- repo-wide scans no per-item builder runs (import allow-lists, OpenAPI, coverage stages, generated views, the reply
  inventory): 8 findings on one gate run, 3 more on the next.

Four layers, cheapest first; the first red layer stops the run (its log names every finding):
0. build: a frontend/dist that exists must carry its manifest and be newer than every frontend input (the bundle secret
   scan reads it; a build left from before the merge failed that scan on 2026-11-01). No dist: pass (the scan skips).
1. interface: mypy over every changed Python file under backend/, tests/ and tests_app/, reporting ONLY the codes
   that mean "this call no longer matches its definition" (``call-arg``, ``name-defined``, and ``attr-defined`` on a
   module: ``Module "x" has no attribute "y"``). The rest of mypy's output is old noise in this repo and is ignored;
   reviewed false positives of those codes are listed in ``merge_preflight_known.json`` (file + message, with a
   reason) and only a finding NOT on that list fails. Measured 2026-11-01: on the raw textual merge the layer flags
   every break the gate found one at a time; on the fixed tree it flags none.
2. collect: ``pytest --collect-only`` over tests/ and tests_app/ (pytest-app.ini); any collection error fails.
3. repo scans: the ruff ratchet, the coverage stage check, the migration guard, every generated view in ``--check``
   mode, the reply inventory ``--check``, and the ``repo_scan``-marked tests plus the generated-file guard tests,
   with the database variables removed (database tests skip, as in prepush).

Changed files = ``git diff --name-only <merge-base(base, HEAD)>...HEAD`` plus uncommitted and untracked files; for a
merge commit HEAD that is everything either side changed since the base. Fail closed: an unreadable diff checks every
Python file; a missing tool (mypy) fails the layer with the reason, never a skip.

Exit 0 = every layer passed; 1 = a layer failed (named on the last line); 2 = bad usage.
Usage: python scripts/orchestrator/merge_preflight.py [repo] [--base origin/main]
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

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PY_ROOTS = ("backend/", "tests/", "tests_app/")
FRONTEND_INPUTS = ("frontend/src", "frontend/vite.config.js", "frontend/package-lock.json", "frontend/index.html")
KNOWN_FILE = "scripts/orchestrator/merge_preflight_known.json"  # reviewed mypy false positives (file + message)
DB_ENV = ("TEST_DATABASE_URL", "TEST_ADMIN_DATABASE_URL", "ALEMBIC_DATABASE_URL")
#: mypy findings that mean a call no longer matches its definition (the merge-break class); everything else is noise
INTERFACE_CODES = ("[call-arg]", "[name-defined]")
MODULE_ATTR = re.compile(r'Module "[^"]+" has no attribute ')
#: guard tests over generated files that are not marked repo_scan (run when present)
GUARD_FILES = ("tests_app/test_openapi_drift.py", "tests_app/test_reply_inventory.py",
               "tests_app/test_order_closure_all_routes.py")
#: generated-file checks: (script, args); a script that is not in this tree is skipped with a note
CHECKS = (("tools/build_findings_index.py", (".", "--check")), ("tools/build_spec_digest.py", (".", "--check")),
          ("tools/build_order.py", (".", "--check")), ("tools/build_spec_index.py", (".", "--check")),
          ("scripts/reply_inventory.py", ("--check",)), ("scripts/ruff_ratchet.py", ()),
          ("scripts/orchestrator/coverage.py", (".", "--check")), ("scripts/alembic_migration_guard.py", ()))


def _git(repo: str, *args: str) -> tuple[int, str]:
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, check=False)  # noqa: S603, S607
    return r.returncode, r.stdout


def changed_python(repo: str, base: str) -> list[str] | None:
    """Changed .py files under PY_ROOTS that exist now, or None when the diff cannot be read (fail closed)."""
    rc, mb = _git(repo, "merge-base", base, "HEAD")
    if rc != 0 or not mb.strip():
        return None
    rc1, committed = _git(repo, "diff", "--name-only", f"{mb.strip()}...HEAD")
    rc2, dirty = _git(repo, "diff", "--name-only", "HEAD")
    rc3, untracked = _git(repo, "ls-files", "--others", "--exclude-standard")
    if rc1 or rc2 or rc3:
        return None
    names = {n.strip().replace("\\", "/") for n in (committed + dirty + untracked).splitlines() if n.strip()}
    return sorted(n for n in names if n.endswith(".py") and n.startswith(PY_ROOTS)
                  and os.path.isfile(os.path.join(repo, n)))


def every_python(repo: str) -> list[str]:
    rc, out = _git(repo, "ls-files", "*.py")
    return sorted(n for n in out.splitlines() if n.startswith(PY_ROOTS)) if rc == 0 else []


def interface_findings(mypy_output: str) -> list[str]:
    """The mypy lines of the merge-break class (``INTERFACE_CODES`` or a missing module attribute)."""
    out = []
    for line in mypy_output.splitlines():
        if ": error:" not in line:
            continue
        if any(code in line for code in INTERFACE_CODES) or ("[attr-defined]" in line and MODULE_ATTR.search(line)):
            out.append(line.strip())
    return out


def _env(no_db: bool = True) -> dict:
    env = dict(os.environ)
    if no_db:
        for key in DB_ENV:
            env.pop(key, None)
    return env


def _run(cmd: list[str], repo: str, log: str, env: dict | None = None, extra_env: dict | None = None) -> int:
    full_env = dict(env or _env())
    full_env.update(extra_env or {})
    with open(log, "a", encoding="utf-8") as handle:
        handle.write("$ " + " ".join(cmd) + "\n")
        handle.flush()
        return subprocess.run(cmd, cwd=repo, stdout=handle, stderr=subprocess.STDOUT, env=full_env,  # noqa: S603
                              check=False).returncode


def layer_interface(repo: str, base: str, log: str) -> tuple[int, str]:
    files = changed_python(repo, base)
    scope = "changed"
    if files is None:
        files, scope = every_python(repo), "every (the diff could not be read)"
    if not files:
        return 0, "no changed Python files"
    try:
        import mypy  # noqa: F401, PLC0415 - presence check only
    except ImportError:
        return 1, "mypy is not installed (pip install mypy): the interface layer cannot run (fail closed)"
    found: list[str] = []
    # one mypy run per root, each with only backend/ on the path, so every file has exactly ONE module name (a test
    # imported both as ``test_x`` and ``tests_app.test_x`` stops mypy: "Source file found twice", rc 2)
    for root in PY_ROOTS:
        group = [f for f in files if f.startswith(root)]
        if not group:
            continue
        in_backend = root == "backend/"
        cwd = os.path.join(repo, "backend") if in_backend else repo
        targets = [f[len(root):] if in_backend else f for f in group]
        cmd = [sys.executable, "-m", "mypy", "--ignore-missing-imports", "--follow-imports=silent",
               "--no-error-summary", "--explicit-package-bases", "--check-untyped-defs", "--hide-error-context",
               "--show-error-codes",
               "--cache-dir", os.path.join(tempfile.gettempdir(), "merge_preflight_mypy", root.strip("/")), *targets]
        env = {**_env(), "MYPYPATH": "" if in_backend else os.path.join(repo, "backend")}
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False, env=env)  # noqa: S603
        if r.returncode not in (0, 1):  # 2 = mypy itself failed (bad config, crash): fail closed
            with open(log, "a", encoding="utf-8") as handle:
                handle.write(r.stdout + r.stderr)
            return 1, f"mypy could not run on {root} (rc {r.returncode}); see the log"
        found += [f"{root}{line}" if in_backend else line for line in interface_findings(r.stdout)]
    known = load_known(repo)
    new = [f for f in found if finding_key(f) not in known]
    gone = sorted(known - {finding_key(f) for f in found} - {k for k in known if k[0] not in files})
    with open(log, "a", encoding="utf-8") as handle:
        handle.write(f"{scope} files: {len(files)}; findings {len(found)}, known {len(found) - len(new)}, "
                     f"NEW {len(new)}\n" + "\n".join(new) + "\n")
        if gone:  # listed, its file was checked, and the finding is gone: drop the entry (never silently kept)
            handle.write("known entries no longer found (remove from " + KNOWN_FILE + "):\n"
                         + "\n".join(f"{k[0]}: {k[1]}" for k in gone) + "\n")
    note = (f"{len(new)} new call/import mismatch(es) in {len(files)} {scope} file(s) "
            f"({len(found) - len(new)} known false positives)")
    return (1 if new else 0), note + (f"; {len(gone)} known entries are gone (see log)" if gone else "")


def finding_key(line: str) -> tuple[str, str]:
    """(file with forward slashes, message without the line number) of one mypy finding line."""
    path, _, rest = line.partition(":")
    return path.replace("\\", "/"), re.sub(r"^\s*\d+:\s*error:\s*", "", rest).strip()


def load_known(repo: str) -> set[tuple[str, str]]:
    """The reviewed false positives (``KNOWN_FILE``); none when the file is absent. A malformed file raises (an
    unreadable list must never turn into "nothing is known" silently passing, nor into "everything is known")."""
    path = os.path.join(repo, KNOWN_FILE)
    if not os.path.isfile(path):  # a checkout older than the list: the list that ships with this script
        path = os.path.join(ROOT, KNOWN_FILE)
    if not os.path.isfile(path):
        return set()
    with open(path, encoding="utf-8") as handle:
        doc = json.load(handle)
    return {(e["file"], e["message"]) for e in doc["known"]}


def layer_collect(repo: str, log: str) -> tuple[int, str]:
    bad = []
    for label, args in (("tests", ["tests"]), ("tests_app", ["-c", "pytest-app.ini", "tests_app"])):
        rc = _run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", *args], repo, log)
        if rc not in (0, 5):  # 5 = nothing collected (an empty suite is not a collection error)
            bad.append(f"{label} rc {rc}")
    return (1 if bad else 0), ("collection errors: " + ", ".join(bad)) if bad else "both suites collect"


def newest_input(repo: str) -> tuple[float, str] | None:
    """(mtime, path) of the newest file the frontend build reads (``FRONTEND_INPUTS``), or None when there is none."""
    newest = None
    for rel in FRONTEND_INPUTS:
        path = os.path.join(repo, rel)
        files = ([os.path.join(d, f) for d, _, fs in os.walk(path) for f in fs] if os.path.isdir(path)
                 else [path] if os.path.isfile(path) else [])
        for f in files:
            m = os.path.getmtime(f)
            if newest is None or m > newest[0]:
                newest = (m, os.path.relpath(f, repo).replace("\\", "/"))
    return newest


def layer_build(repo: str, log: str) -> tuple[int, str]:
    """The bundle the secret scan reads is a build of THIS tree (2026-11-01: a build made before the merge, with the old
    config and no manifest, failed the scan on code that was right). No build at all: the scan skips locally, so
    pass."""
    dist = os.path.join(repo, "frontend", "dist")
    if not os.path.isdir(dist):
        return 0, "no frontend/dist: the bundle scan skips locally (CI builds first)"
    manifest = os.path.join(dist, ".vite", "manifest.json")
    fix = "run `npm run build` in frontend/ (the bundle scan reads frontend/dist)"
    if not os.path.isfile(manifest):
        note = f"frontend/dist has no .vite/manifest.json (a build from another config): {fix}"
    else:
        newest = newest_input(repo)
        if newest is None or newest[0] <= os.path.getmtime(manifest):
            return 0, "frontend build is newer than every input"
        note = f"frontend/dist is older than {newest[1]}: {fix}"
    with open(log, "a", encoding="utf-8") as handle:
        handle.write(note + "\n")
    return 1, note


def layer_scans(repo: str, log: str, domain_scans: bool = True) -> tuple[int, str]:
    failed, skipped = [], []
    for script, args in CHECKS:
        if not os.path.isfile(os.path.join(repo, script)):
            skipped.append(script)
            continue
        if _run([sys.executable, script, *args], repo, log) != 0:
            failed.append(script)
    # prepush runs all of tests/ as its next step, so it passes --no-domain-scans (measured: this part alone 385 s)
    if domain_scans and _run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-m", "repo_scan",
                              "tests"], repo, log) not in (0, 5):
        failed.append("tests -m repo_scan")
    guards = [g for g in GUARD_FILES if os.path.isfile(os.path.join(repo, g))]
    if _run([sys.executable, "-m", "pytest", "-c", "pytest-app.ini", "-q", "-p", "no:cacheprovider", "-m",
             "repo_scan", "tests_app"], repo, log) not in (0, 5):
        failed.append("tests_app -m repo_scan")
    if guards and _run([sys.executable, "-m", "pytest", "-c", "pytest-app.ini", "-q", "-p", "no:cacheprovider",
                        *guards], repo, log) != 0:
        failed.append("generated-file guard tests")
    note = ("failed: " + ", ".join(failed)) if failed else "every scan passed"
    if skipped:
        note += " (not in this tree: " + ", ".join(skipped) + ")"
    return (1 if failed else 0), note


def run(repo: str, base: str, log_dir: str, domain_scans: bool = True) -> int:
    # cheapest first: the build check takes milliseconds, the interface check ~20-120 s, collect ~20 s, scans minutes
    layers = (("build", lambda log: layer_build(repo, log)),
              ("interface", lambda log: layer_interface(repo, base, log)),
              ("collect", lambda log: layer_collect(repo, log)),
              ("scans", lambda log: layer_scans(repo, log, domain_scans)))
    for name, layer in layers:
        log = os.path.join(log_dir, f"preflight-{name}.log")
        t0 = time.monotonic()
        rc, note = layer(log)
        print(f"{'PASS' if rc == 0 else 'FAIL'} preflight-{name} {round(time.monotonic() - t0, 1)}s {note} {log}",
              flush=True)
        if rc != 0:
            print(f"PREFLIGHT FAIL at {name}: fix it before the long gate (log: {log})", flush=True)
            return 1
    print("PREFLIGHT PASS", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("repo", nargs="?", default=ROOT)
    ap.add_argument("--base", default="origin/main", help="the branch the change will land on (merge-base side)")
    ap.add_argument("--log-dir", default=None)
    ap.add_argument("--no-domain-scans", action="store_true",
                    help="skip the tests/ repo_scan subset (prepush runs all of tests/ right after)")
    a = ap.parse_args(argv)
    if not os.path.isdir(a.repo):
        print("repo not found: " + a.repo)
        return 2
    log_dir = a.log_dir or tempfile.mkdtemp(prefix="preflight-")
    os.makedirs(log_dir, exist_ok=True)
    return run(os.path.abspath(a.repo), a.base, log_dir, domain_scans=not a.no_domain_scans)


if __name__ == "__main__":
    raise SystemExit(main())
