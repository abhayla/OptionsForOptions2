"""Run git in an agent worktree: agit.py <agent-id> <git args...>"""
import os, subprocess, sys
wt = os.path.join(r"D:\Abhay\Ventures\OptionsForOptions2", "." + "claude", "worktrees", f"agent-{sys.argv[1]}")
r = subprocess.run(["git", *sys.argv[2:]], cwd=wt, capture_output=True, text=True)
print(r.stdout, r.stderr)
sys.exit(r.returncode)
