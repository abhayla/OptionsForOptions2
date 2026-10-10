"""Run the CI mirror in a worktree: atool.py <agent-id | worktree-dir> [grep-word] [--no-tests]

--no-tests skips the full domain suite (on the VPS, whose PostgreSQL serves IPODhan production, CI runs it).
"""
import os, subprocess, sys
show = sys.argv[sys.argv.index("--show") + 1] if "--show" in sys.argv else None  # print one step's full output
args = [a for i, a in enumerate(sys.argv[1:], 1)
        if a not in ("--no-tests", "--show") and not (i > 1 and sys.argv[i - 1] == "--show")]
wt = args[0] if os.path.isdir(args[0]) else os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "." + "claude", "worktrees", f"agent-{args[0]}")
word = args[1] if len(args) > 1 else "W-"
steps = [["tools/factory_lint.py", "."], ["tools/trace_check.py", "."], ["tools/build_findings_index.py", ".", "--check"],
         ["tools/check_spec_refs.py", "."], ["tools/kit_settings.py", ".", "--check"],
         ["tools/build_order.py", ".", "--check"], ["tools/run_smoke.py", "."],
         ["tools/build_spec_index.py", ".", "--check"], ["tools/build_spec_digest.py", ".", "--check"],
         ["tools/spec_dupes.py", "."], ["tools/kit_selftest.py", "."], ["tools/kit_drift.py", ".", "--ci"],
         ["-m", "pytest", "-q", "-p", "no:cacheprovider"]]  # the ci.yml lint-and-test steps, in its order
if "--no-tests" in sys.argv:  # the full suite runs in CI; the repo-wide guard tests (~25 s) still run here
    import glob
    guards = sorted(os.path.relpath(p, wt) for p in glob.glob(os.path.join(wt, "tests", "test_*.py")))
    steps = steps[:-1] + [["-m", "pytest", "-q", "-p", "no:cacheprovider", *guards]]
bad = 0
for s in steps:
    r = subprocess.run([sys.executable, *s], cwd=wt, capture_output=True, text=True)
    out = (r.stdout + r.stderr).strip().splitlines()
    keys = (word, "passed", "failed", "checked", "ERROR", "error", "stale", "valid", " ok")
    tail = [l for l in out if any(k in l for k in keys)][-4:] or out[-2:]
    print(s[0] if s[0] != "-m" else "pytest", "rc", r.returncode, "|", " / ".join(tail)[:600])
    if show and show in s[0]:
        print("\n".join(out))
    bad |= r.returncode

# A changed migration can break any test that walks the migration chain, whatever its name (finding
# targeted-tests-miss-dependent-files, 2nd occurrence: 0010 broke 0009's round-trip test, found only in CI). With
# --no-tests, run every tests_app file that touches migrations against the real test database (light: targeted files).
if "--no-tests" in sys.argv:
    changed = subprocess.run(["git", "diff", "--name-only", "origin/main...HEAD"], cwd=wt, capture_output=True,
                             text=True).stdout.splitlines()
    if any("/alembic/versions/" in f for f in changed):
        import glob
        files = sorted(os.path.relpath(p, wt) for p in glob.glob(os.path.join(wt, "tests_app", "test_*.py"))
                       if any(k in open(p, encoding="utf-8").read() for k in ("alembic", "_migration_replay")))
        runner = os.path.join(os.path.dirname(os.path.abspath(__file__)), "db_run.py")
        main_checkout = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        r = subprocess.run([sys.executable, runner, wt, sys.executable, "-m", "pytest", "-q", "-rs", "-p",
                            "no:cacheprovider", "-c", "pytest-app.ini", *files], cwd=main_checkout,
                           capture_output=True, text=True)
        out = (r.stdout + r.stderr).strip().splitlines()
        print("migration tests", f"({len(files)} files)", "rc", r.returncode, "|", " / ".join(out[-2:])[:600])
        bad |= r.returncode
sys.exit(bad)
