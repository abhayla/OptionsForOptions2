"""land.py <worktree> --title T --body-file F [--dry-run]

Take a committed branch from push to merged in one command:
  1. close-keyword check (pr_close_check.py) on the body and the branch's commit messages - before any push
  2. git push -u origin <branch>
  3. gh pr create, or reuse the open PR for the branch
  4. the kit's merge gate (merge_when_green.py), foreground, never reimplemented here
     - if the PR is BEHIND main (or the merge is refused for that reason): gh pr update-branch, or merge
       origin/main in the worktree and push, then call the gate again (max 3 retries)
     - red CI: stop, name the failed job, print `gh run view <id> --log-failed`
  5. print the merge time

Exit 0 merged, 1 stopped (the message says why), 2 bad input. --dry-run prints the commands and runs nothing.
Every external command goes through an injected runner(cmd, cwd) -> (returncode, output); no shell, no pipes.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
MAX_RETRIES = 3
BEHIND_WORDS = ("behind", "not up to date", "required status checks are expected", "base branch policy")


def real_runner(cmd, cwd=None):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)  # noqa: S603
    return r.returncode, (r.stdout or "") + (r.stderr or "")


class Stop(Exception):
    """The landing stopped; the message says why."""


class Env:
    """Everything a test replaces: the command runner, the clock, the sleep, the temp folder, the dry-run flag."""

    def __init__(self, runner=real_runner, dry_run=False, now=None, sleep=time.sleep, tmp_dir=None):
        self.runner = runner
        self.dry_run = dry_run
        self.now = now
        self.sleep = sleep
        self.tmp_dir = tmp_dir or tempfile.gettempdir()


def looks_behind(text):
    low = text.lower()
    return any(w in low for w in BEHIND_WORDS)


def failed_jobs(text):
    tail = text.split("failing check:", 1)[1]
    parts = [p.strip() for p in tail.split(",")]
    return [p.rsplit("=", 1)[0].strip() for p in parts if p.endswith(("=fail", "=cancel"))]


class Lander:
    def __init__(self, worktree, title, body_file, env):
        self.worktree = worktree
        self.title = title
        self.body_file = body_file
        self.env = env
        self.branch = ""
        self.pr = None

    def run(self, cmd, cwd=None):
        return self.env.runner(cmd, cwd)

    def git(self, *args):
        return self.run(["git", "-C", self.worktree, *args])

    def read_branch(self):
        _, text = self.git("rev-parse", "--abbrev-ref", "HEAD")
        self.branch = text.strip() or "<branch>"
        if self.branch in ("main", "HEAD"):
            raise Stop(f"worktree is on {self.branch}; land a feature branch")

    def close_check(self):
        rc, log = self.git("log", "--format=%B%n---COMMIT---", "origin/main..HEAD")
        if rc != 0:
            raise Stop(f"could not read commit messages: {log.strip()}")
        commits_file = os.path.join(self.env.tmp_dir, f"land-commits-{os.getpid()}.txt")
        if not self.env.dry_run:
            with open(commits_file, "w", encoding="utf-8") as handle:
                handle.write(log)
        rc, text = self.run([sys.executable, os.path.join(HERE, "pr_close_check.py"), "--body-file", self.body_file,
                             "--commits-file", commits_file], self.worktree)
        if rc != 0:
            raise Stop("before push: closing-reference check failed\n" + text.strip())

    def push(self):
        rc, text = self.git("push", "-u", "origin", self.branch)
        if rc != 0:
            raise Stop("push failed\n" + text.strip())

    def open_pr_number(self):
        rc, text = self.run(["gh", "pr", "list", "--head", self.branch, "--state", "open", "--json", "number"],
                            self.worktree)
        if rc != 0 or not text.strip():
            return None
        with contextlib.suppress(json.JSONDecodeError, KeyError, IndexError, TypeError):
            return json.loads(text)[0]["number"]
        return None

    def find_or_create_pr(self):
        self.pr = self.open_pr_number()
        if self.pr is not None:
            print(f"reusing open PR #{self.pr}")
            return
        rc, text = self.run(["gh", "pr", "create", "--head", self.branch, "--base", "main", "--title", self.title,
                             "--body-file", self.body_file], self.worktree)
        if rc != 0:
            raise Stop("gh pr create failed\n" + text.strip())
        tail = text.strip().rsplit("/", 1)[-1]
        if tail.isdigit():
            self.pr = int(tail)
        elif self.env.dry_run:
            self.pr = "<pr>"
        else:
            raise Stop("could not read the PR number from: " + text.strip())
        print(f"created PR #{self.pr}")

    def red_ci(self, text):
        _, runs = self.run(["gh", "run", "list", "--branch", self.branch, "--limit", "1", "--json", "databaseId"],
                           self.worktree)
        run_id = "<id>"
        with contextlib.suppress(json.JSONDecodeError, KeyError, IndexError, TypeError):
            run_id = json.loads(runs)[0]["databaseId"]
        jobs = ", ".join(failed_jobs(text)) or "see PR checks"
        raise Stop(f"CI red; failed job(s): {jobs}\nnext: gh run view {run_id} --log-failed")

    def update_branch(self):
        rc, text = self.run(["gh", "pr", "update-branch", str(self.pr)], self.worktree)
        if rc == 0:
            return
        print("gh pr update-branch failed; merging origin/main locally and pushing\n" + text.strip())
        for args in (("fetch", "origin", "main"), ("merge", "--no-edit", "origin/main"),
                     ("push", "origin", self.branch)):
            rc, text = self.git(*args)
            if rc != 0:
                raise Stop("fallback update failed at: git " + " ".join(args) + "\n" + text.strip())

    def is_behind(self, gate_output):
        _, state = self.run(["gh", "pr", "view", str(self.pr), "--json", "mergeStateStatus", "--jq",
                             ".mergeStateStatus"], self.worktree)
        return looks_behind(gate_output) or state.strip() == "BEHIND"

    def merge_loop(self):
        gate = [sys.executable, os.path.join(ROOT, "tools", "merge_when_green.py"), str(self.pr)]
        for attempt in range(MAX_RETRIES + 1):
            rc, text = self.run(gate, self.worktree)
            if text.strip():
                print(text.strip())
            if rc == 0:
                return
            if "failing check:" in text:
                self.red_ci(text)
            if not self.is_behind(text):
                raise Stop("merge gate refused for a reason other than BEHIND (output above)")
            if attempt == MAX_RETRIES:
                raise Stop(f"still BEHIND main after {MAX_RETRIES} update-branch retries")
            print(f"PR #{self.pr} is BEHIND main: updating the branch (retry {attempt + 1}/{MAX_RETRIES})")
            self.update_branch()
            self.env.sleep(5)

    def land(self):
        self.read_branch()
        self.close_check()
        self.push()
        self.find_or_create_pr()
        self.merge_loop()
        if self.env.dry_run:
            print("dry run: nothing was run")
            return
        stamp = (self.env.now() if self.env.now else datetime.now().astimezone()).strftime("%Y-%m-%d %H:%M:%S")
        print(f"MERGED PR #{self.pr} at {stamp}")


def land(worktree, title, body_file, env=None):
    """Return 0 when merged, 1 when stopped."""
    try:
        Lander(worktree, title, body_file, env or Env()).land()
    except Stop as stop:
        print("STOPPED: " + str(stop))
        return 1
    return 0


class DryRunner:
    """Reads (branch name, commit log) are real so the dry run shows real values; everything else is printed."""

    def __init__(self, worktree):
        self.worktree = worktree

    def __call__(self, cmd, cwd=None):
        if cmd[:3] == ["git", "-C", self.worktree] and cmd[3] in ("rev-parse", "log"):
            return real_runner(cmd, cwd)
        print("would run:", " ".join(cmd) + (f"   (in {cwd})" if cwd else ""))
        return 0, ""


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("worktree")
    ap.add_argument("--title", required=True)
    ap.add_argument("--body-file", required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    if not os.path.isdir(a.worktree) or not os.path.isfile(a.body_file):
        print("worktree or body file not found")
        return 2
    env = Env(runner=DryRunner(a.worktree), dry_run=True) if a.dry_run else Env()
    return land(a.worktree, a.title, a.body_file, env)


if __name__ == "__main__":
    sys.exit(main())
