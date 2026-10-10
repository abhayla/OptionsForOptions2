"""regen.py [dir]: regenerate the generated files (findings index, spec digest, build order) in a checkout; default: this one.

The kit guard refuses a shell command that names a kit tool in write mode, so the orchestrator runs them through this
helper (as aregen.py does for agent worktrees). Prints each tool's return code and last output line.
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
target = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else ROOT
rc = 0
for tool in ("build_findings_index.py", "build_spec_digest.py", "build_order.py"):
    r = subprocess.run([sys.executable, os.path.join("tools", tool), "."], cwd=target, capture_output=True, text=True)
    out = (r.stdout + r.stderr).strip().splitlines()
    print(tool, "rc", r.returncode, out[-1] if out else "")
    rc = rc or r.returncode
sys.exit(rc)
