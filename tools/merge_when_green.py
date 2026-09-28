"""Merge a pull request only when CI has really run and every check passed.

    python tools/merge_when_green.py <pr-number> [--timeout-min 20]

Why: `gh pr checks --watch && gh pr merge` merged PR #11 while CI had not started, because "no checks reported"
exited 0 (finding check-validates-nothing-reports-pass, third occurrence). Here zero checks means WAIT, never pass.
"""
import argparse
import json
import subprocess
import sys
import time

PASSING = {"pass", "skipping"}
FAILING = {"fail", "cancel"}

CONFLICT_MESSAGE = "CONFLICTING: GitHub runs no CI on this PR; merge the base branch in first"


def check_pr_state(pr_state):
    """Return ('already_merged', None), ('refuse', message) or ('poll', None) for gh pr view's
    {"state", "mergeable", "mergeStateStatus"} JSON.

    A CONFLICTING/DIRTY PR gets zero CI runs from GitHub, so waiting on checks would wait forever
    (the same "no checks reported" trap decide() already guards against, one layer up). mergeable
    is UNKNOWN right after a push, since GitHub computes it lazily — that case keeps polling.
    """
    if pr_state.get("state") == "MERGED":
        return ("already_merged", None)
    if pr_state.get("mergeable") == "CONFLICTING" or pr_state.get("mergeStateStatus") == "DIRTY":
        return ("refuse", CONFLICT_MESSAGE)
    return ("poll", None)


def read_pr_state(pr):
    out = subprocess.run(["gh", "pr", "view", str(pr), "--json", "state,mergeable,mergeStateStatus"],
                         capture_output=True, text=True)
    if out.returncode != 0 or not out.stdout.strip():
        return {}
    try:
        return json.loads(out.stdout)
    except json.JSONDecodeError:
        return {}


def decide(checks):
    """Return 'merge', 'wait' or 'refuse' for a list of {"name", "bucket"} dicts from gh."""
    if not checks:
        return "wait"
    buckets = [c.get("bucket", "") for c in checks]
    if any(b in FAILING for b in buckets):
        return "refuse"
    if all(b in PASSING for b in buckets):
        return "merge"
    return "wait"


def read_checks(pr):
    out = subprocess.run(["gh", "pr", "checks", str(pr), "--json", "name,bucket"],
                         capture_output=True, text=True)
    if out.returncode not in (0, 8) or not out.stdout.strip():  # gh exits 8 while checks are pending
        return []
    try:
        return json.loads(out.stdout)
    except json.JSONDecodeError:
        return []


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("pr")
    ap.add_argument("--timeout-min", type=float, default=20)
    ap.add_argument("--interval-s", type=float, default=20)
    a = ap.parse_args(argv)
    verdict, message = check_pr_state(read_pr_state(a.pr))
    if verdict == "already_merged":
        print("already merged")
        return 0
    if verdict == "refuse":
        print(message)
        return 1
    deadline = time.time() + a.timeout_min * 60
    while True:
        checks = read_checks(a.pr)
        verdict = decide(checks)
        names = ", ".join(f"{c.get('name')}={c.get('bucket')}" for c in checks) or "no checks reported yet"
        if verdict == "refuse":
            print(f"REFUSED: PR {a.pr} has a failing check: {names}")
            return 1
        if verdict == "merge":
            print(f"all {len(checks)} checks passed: {names}")
            merge_result = subprocess.run(
                ["gh", "pr", "merge", str(a.pr), "--merge", "--delete-branch"],
                capture_output=True, text=True,
            )
            # gh-merge-delete-branch-fails-in-worktree: --delete-branch tries to switch the
            # worktree to the base branch, which the main checkout already holds, so gh can exit
            # non-zero after the merge itself succeeded on GitHub. Re-read the PR's real state
            # instead of trusting gh's local exit code.
            post_state = read_pr_state(a.pr)
            if post_state.get("state") == "MERGED":
                print("merged")
                if merge_result.returncode != 0:
                    note = (merge_result.stderr or merge_result.stdout).strip()
                    print(f"note: local branch cleanup failed: {note}")
                return 0
            sys.stderr.write((merge_result.stderr or merge_result.stdout))
            return merge_result.returncode or 1
        if time.time() > deadline:
            print(f"REFUSED: PR {a.pr} not green within {a.timeout_min} min ({names})")
            return 1
        time.sleep(a.interval_s)


if __name__ == "__main__":
    sys.exit(main())
