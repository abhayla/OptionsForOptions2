"""Run the CI mirror in an agent worktree: atool.py <agent-id> [grep-word]"""
import os, subprocess, sys
wt = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "." + "claude", "worktrees", f"agent-{sys.argv[1]}")
word = sys.argv[2] if len(sys.argv) > 2 else "W-"
steps = [["tools/factory_lint.py", "."], ["tools/trace_check.py", "."], ["tools/build_findings_index.py", ".", "--check"],
         ["tools/check_spec_refs.py", "."], ["tools/kit_settings.py", ".", "--check"], ["-m", "pytest", "-q", "-p", "no:cacheprovider"]]
bad = 0
for s in steps:
    r = subprocess.run([sys.executable, *s], cwd=wt, capture_output=True, text=True)
    out = (r.stdout + r.stderr).strip().splitlines()
    keys = (word, "passed", "failed", "checked", "ERROR", "error", "stale", "valid", " ok")
    tail = [l for l in out if any(k in l for k in keys)][-4:] or out[-2:]
    print(s[0] if s[0] != "-m" else "pytest", "rc", r.returncode, "|", " / ".join(tail)[:600])
    bad |= r.returncode
sys.exit(bad)
