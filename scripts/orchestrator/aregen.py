"""Regenerate the findings index inside an agent worktree and continue a paused rebase: aregen.py <agent-id>"""
import os, subprocess, sys
wt = os.path.join(r"D:\Abhay\Ventures\OptionsForOptions2", "." + "claude", "worktrees", f"agent-{sys.argv[1]}")
def run(*a):
    r = subprocess.run(list(a), cwd=wt, capture_output=True, text=True, env={**os.environ, "GIT_EDITOR": "true"})
    print(" ".join(a[:3]), "rc", r.returncode, (r.stdout + r.stderr).strip()[-400:])
    return r.returncode
run(sys.executable, "tools/build_findings_index.py", ".")
run("git", "add", "knowledge/findings/INDEX.md")
rc = run("git", "rebase", "--continue")
sys.exit(rc)
