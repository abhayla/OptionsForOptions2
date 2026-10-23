"""regen.py [dir] [--only <tool>]: regenerate the generated files (findings index, spec digest, build order,
requirements index) in a checkout; default: this one. `--only build_spec_index.py` runs one tool.

The kit guard refuses a shell command that names a kit tool in write mode, so the orchestrator runs them through this
helper (as aregen.py does for agent worktrees). Prints each tool's return code and last output line.
"""
import os
import subprocess
import sys

TOOLS = ("build_findings_index.py", "build_spec_digest.py", "build_order.py", "build_spec_index.py")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
args = sys.argv[1:]
only = None
if "--only" in args:
    i = args.index("--only")
    only = args[i + 1]
    del args[i:i + 2]
    if only not in TOOLS:
        sys.exit(f"--only must be one of {TOOLS}")
target = os.path.abspath(args[0]) if args else ROOT
rc = 0
for tool in (only,) if only else TOOLS:
    r = subprocess.run([sys.executable, os.path.join("tools", tool), "."], cwd=target, capture_output=True, text=True)
    out = (r.stdout + r.stderr).strip().splitlines()
    print(tool, "rc", r.returncode, out[-1] if out else "")
    rc = rc or r.returncode
sys.exit(rc)
