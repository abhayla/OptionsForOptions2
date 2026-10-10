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
if "--no-tests" in sys.argv:
    steps = steps[:-1]
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
sys.exit(bad)
