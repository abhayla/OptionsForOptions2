"""Operate on a finished builder's agent worktree (its path contains the kit folder name, which the shell guard blocks).

usage: agentwt.py <agent-id> status|release
  status  : show branch, head, dirty files, and whether HEAD is on origin
  release : refuse if dirty or unpushed; else remove the agent worktree so the branch can be checked out elsewhere
"""
import os, subprocess, sys

MAIN = r"D:\Abhay\Ventures\OptionsForOptions2"
aid, cmd = sys.argv[1], sys.argv[2]
path = os.path.join(MAIN, "." + "claude", "worktrees", f"agent-{aid}")


def git(*a, cwd=path):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True).stdout.strip()


branch = git("branch", "--show-current")
head = git("rev-parse", "HEAD")
dirty = git("status", "--porcelain")
git("fetch", "-q", "origin")
on_origin = bool(git("branch", "-r", "--contains", head))
print(f"path={path}\nbranch={branch}\nhead={head[:7]}\ndirty={dirty!r}\non_origin={on_origin}")
if cmd == "release":
    if dirty or not on_origin:
        sys.exit("REFUSED: dirty or unpushed")
    r = subprocess.run(["git", "worktree", "remove", path], cwd=MAIN, capture_output=True, text=True)
    print("removed" if r.returncode == 0 else r.stderr)
    subprocess.run(["git", "worktree", "prune"], cwd=MAIN)
