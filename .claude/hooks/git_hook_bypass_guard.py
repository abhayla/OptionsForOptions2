#!/usr/bin/env python3
"""PreToolUse hook: block git commands that bypass the repo's commit hooks.

Why (2026-09-11): a lane session committed all night with
`git -c core.hooksPath=/dev/null commit`, which is `--no-verify` wearing a
different hat. Four of those commits reached main having skipped the staged
secret scan, the workflow ASCII check and lint-staged tsc. git-collaboration.md
forbids `--no-verify`; this guard makes the rule a refusal instead of a memory.

Blocked when a `git commit` / `git merge` / `git push` / `git rebase` /
`git cherry-pick` / `git am` segment carries any of:
  --no-verify (or any unambiguous prefix of it, e.g. --no-verif, --no-v)
  -c core.hooksPath=<anything> (key matched case-insensitively)
  GIT_CONFIG_PARAMETERS / GIT_CONFIG_KEY_n set to core.hooksPath (inline or real env)
  HUSKY=0 (inline or real env)
  -n alone, or bundled into a short-flag group (-nm, -anm) -- COMMIT ONLY: -n is
    --no-verify's short form for commit; it means something else entirely for
    other subcommands (e.g. merge's -n is --no-stat) and is never a bypass there.

Tier A fix round 2 (issue #14, RCA: regexing raw command TEXT let a quoted
program path, bundled short flags, an unambiguous long-option prefix, a
mixed-case config key or an env-var config mechanism slip through, while text
that merely CONTAINS the watched words -- an echo, a commit -m message, an
unrelated subcommand's -n -- got blocked by accident). Fix: segments are
tokenized into real shell words (see _git_shell.py, shared with the sibling
git guards) and reasoned about as PROGRAM + ARGV, never as a text search.

Fails open on any unexpected error. Bypass: GIT_HOOK_BYPASS_GUARD_ALLOW=1
(real env var, or as an inline prefix) -- for the owner, with a reason in the
ledger, never for a worker.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _git_shell as gs  # noqa: E402

SUBS = {"commit", "merge", "push", "rebase", "cherry-pick", "am"}


def _is_no_verify_prefix(token):
    """`--no-verify` or any unambiguous prefix of it git itself would accept
    (from `--no-v` up -- shorter than that collides with nothing else here,
    but we don't need to go shorter since no proof case does)."""
    return (
        token.startswith("--")
        and len(token) >= len("--no-v")
        and "--no-verify".startswith(token)
    )


def _has_bundled_no_verify_short_flag(token):
    """`-n` alone, or `-n` bundled with other short flags (`-nm`, `-anm`).
    Never matches a long option (`--...`) or a bare `-`."""
    if not token.startswith("-") or token.startswith("--") or token == "-":
        return False
    return "n" in token[1:]


def offending_segment(command):
    for seg in gs.split_segments(command):
        seg = seg.strip()
        if not seg:
            continue
        parsed = gs.parse_invocation(seg, os.environ)
        if parsed is None:
            continue
        env = parsed["env"]
        sub, sub_argv, c_values = gs.find_subcommand(parsed["argv"])
        if sub not in SUBS:
            continue

        for t in sub_argv:
            if _is_no_verify_prefix(t):
                return seg, "--no-verify"

        if sub == "commit":
            for t in sub_argv:
                if _has_bundled_no_verify_short_flag(t):
                    return seg, "-n"

        if gs.config_value(c_values, "core.hookspath") is not None:
            return seg, "-c core.hooksPath="

        if gs.env_sets_hooks_path(env):
            return seg, "GIT_CONFIG_PARAMETERS/GIT_CONFIG_KEY_* core.hooksPath"

        if str(env.get("HUSKY")) == "0":
            return seg, "HUSKY=0"
    return None


def env_bypass(command: str) -> bool:
    if os.environ.get("GIT_HOOK_BYPASS_GUARD_ALLOW") == "1":
        return True
    return bool(re.search(r"(^|\s)GIT_HOOK_BYPASS_GUARD_ALLOW=1(\s|$)", command))


def main():
    try:
        data = json.loads(sys.stdin.read())
    except Exception:
        sys.exit(0)
    try:
        if data.get("tool_name") not in ("Bash", "PowerShell"):
            sys.exit(0)
        command = (data.get("tool_input") or {}).get("command") or ""
        if "git" not in command.lower():
            sys.exit(0)
        hit = offending_segment(command)
        if not hit:
            sys.exit(0)
        if env_bypass(command):
            sys.stderr.write("git-hook-bypass guard: bypassed by GIT_HOOK_BYPASS_GUARD_ALLOW\n")
            sys.exit(0)
        seg, why = hit
        sys.stderr.write(
            "BLOCKED: this git command bypasses the commit hooks (%s in `%s`). "
            "The hooks are the gate (git-collaboration.md); if the hook itself is "
            "broken, fix the hook or hold the commit -- never skip it.\n" % (why, seg[:120])
        )
        sys.exit(2)
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)


if __name__ == "__main__":
    main()
