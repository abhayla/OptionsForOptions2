#!/usr/bin/env python
"""PreToolUse(Bash) guard: refuse `git checkout -- <path>` / `git restore <path>`
when that path has UNCOMMITTED changes.

WHY (Learn-or-block, 2nd occurrence in one day, 2026-09-10):
  - DEFECT-B14: a builder ran `git checkout -- scraper/src/services/company-host-source.ts`
    to undo a stray edit. It restored the file from HEAD and silently reverted the
    ENTIRE uncommitted security fix back to the vulnerable original. Caught only by
    a puzzling `ip.split is not a function` failure minutes later.
  - DEFECT-B18: the supervisor did the same thing while mutation-testing a CI guard,
    wiping ~200 lines of uncommitted hardening and invalidating four mutation results
    that were then measured against the wrong file.

The command is not wrong in general -- discarding a change is exactly what it is for.
It is wrong as a way to UNDO A MUTATION during testing, because the "known good" it
restores is the last COMMIT, not the state you had a second ago. The fix is to commit
first and restore from a backup copy.

Behaviour: blocks only when git itself reports the named path as modified or staged.
A path with no uncommitted changes passes through untouched, so the ordinary
"throw away this experiment" use is unaffected.

Tier A review round (2026-09-10), four findings fixed here:
  1. Quoted / spaced pathspecs (`"mod.txt"`, `'mod.txt'`, `"my file.txt"`) are now
     tokenized with shlex (falling back to a plain split on a parse error) so the
     quotes don't defeat the dirty-path match.
  2. `git restore --staged <path>` (unstaging only, never touches the worktree) is
     allowed even when the path is dirty -- UNLESS `--worktree`/`-W` or
     `--source`/`-s` is also present, in which case the worktree really is touched
     and the command still blocks.
  3. The checkout/restore matchers are anchored to the START of a shell segment
     (`^\s*(?:sudo\s+)?(?:ENV=val\s+)*git\b...`) instead of a bare `\bgit\b`
     substring search, so prose that merely MENTIONS `git checkout --` (e.g. inside
     an `echo "..."` or a comment) is never mistaken for the command itself.
     Segments are split on `&&`, `||`, `;`, `|` and newlines first, so
     `cd x && git checkout -- f`, `git -C x checkout -- f` and `sudo git ...` are
     still caught -- only the shell-quoted string a `git` invocation appears INSIDE
     of is exempt.
  4. `bash -c "git checkout -- mod.txt"` (or any nested-shell invocation) was
     DELIBERATELY left unblocked in the 2026-09-10 round: parsing a spawned
     sub-shell's grammar was out of scope and a naive substring match on the
     quoted string risked resurrecting finding 3's false positive.

Tier A mechanism fix (2026-09-16b), PROVEN GAP: both this guard and
git-stash-worktree-guard.py let a discard/stash through when the verb is
nested inside an interpreter argument instead of the top-level shell:
  (C) `powershell -NoProfile -c "git stash push -- f.txt; ..."` in a worktree.
  (D) `python -c "import subprocess; subprocess.run(['git','checkout','--','f.txt'])"`.
Root cause: the segment-based match only looks at verbs at the START of a
shell segment, so a verb inside a QUOTED interpreter argument (`-c`, `-Command`,
`-e`, `/c`, `-p` for powershell/pwsh/bash/sh/zsh/cmd/python/python3/node) is
invisible, and a Python/JS argv LIST (`['git', 'checkout', '--', path]`) never
looks like `git checkout` as text at all.

Fix (this file, `_nested_command_texts`): before the segment scan, pull out
(a) the string literal following an interpreter's `-c`/`-Command`/`-e`/`/c`/`-p`
flag, for `powershell|pwsh|bash|sh|zsh|cmd|python|python3|node`, and feed that
extracted text back through the SAME segment/regex machinery recursively; and
(b) detect a Python/JS list literal shaped `[... 'git' ... 'checkout'|'restore' ...]`
(quoted tokens in order) and treat it as an equivalent invocation text
(`git checkout -- <extracted path tokens>`) fed through the same path logic.
Deliberately still out of scope: verbs built from string CONCATENATION or
variable interpolation inside the nested interpreter (e.g. `"git " + "checkout"`,
or a shell variable holding the verb) — those require evaluating the nested
language, which this guard does not do.

Override (deliberate discard): GIT_DISCARD_GUARD_ALLOW=1 inline in the command.
Fail-open: any internal error exits 0 rather than blocking work.
"""
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _git_shell as gs  # noqa: E402

ALLOW_ENV = "GIT_DISCARD_GUARD_ALLOW"

# An interpreter flag that takes an inline script/command STRING as its value:
# powershell/pwsh -c|-Command, bash/sh/zsh -c, cmd /c, python/python3 -c, node -e,
# python also accepts -p in some wrappers (kept permissive; false-positive cost
# is just re-scanning a string that happens not to contain "git").
_NESTED_INTERPRETER_RE = re.compile(
    r"\b(?:powershell(?:\.exe)?|pwsh(?:\.exe)?|bash|sh|zsh|cmd(?:\.exe)?|python3?|node)\b"
    r"[^\n]*?"
    r"(?:-{1,2}[Cc](?:ommand)?|-[Ee]|/[Cc]|-[Pp])\s+"
    r"(\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*')",
)

# A Python/JS argv-LIST literal: 'git' followed (within the same bracketed
# list) by a guarded verb as its own quoted element, e.g.
#   ['git', 'checkout', '--', 'f.txt']   or   ["git","restore","f.txt"]
# Captures the verb and the remainder of the list text so paths can be pulled
# from it the same way as a normal `-- <paths>` segment.
_ARGV_LIST_RE = re.compile(
    r"\[\s*(['\"])git\1\s*,\s*(['\"])(checkout|restore)\2(?P<rest>[^\]]*)\]",
)


def _unquote_literal(text):
    """Strip one layer of matching quotes from an extracted interpreter-arg string."""
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        return text[1:-1]
    return text


def nested_command_texts(command):
    """Yield command-shaped text pulled out of nested-interpreter invocations
    and argv-list literals, so the normal segment/regex scan below can treat
    them exactly like a top-level shell command.

    This is deliberately shallow: it extracts the literal string an
    interpreter flag is handed, or reconstructs a `git <verb> -- <paths>`
    string from a Python/JS list literal. It does NOT evaluate the nested
    language, so a verb built by string concatenation or a shell variable is
    still out of scope (documented in the module docstring).
    """
    for m in _NESTED_INTERPRETER_RE.finditer(command):
        inner = _unquote_literal(m.group(1))
        # Unescape the common escaping a shell/PS applies to a quoted arg so
        # `\"` / `\\` inside it read as plain text for our regexes.
        inner = inner.replace('\\"', '"').replace("\\'", "'")
        if "git" in inner:
            yield inner

    for m in _ARGV_LIST_RE.finditer(command):
        verb = m.group(3)
        rest = m.group("rest") or ""
        # Pull every quoted element out of the remainder of the list (skips
        # the verb itself, which is already captured) and rebuild as if it
        # were `git <verb> <elem1> <elem2> ...` — paths_after_separator()
        # already knows how to find `--` / trailing bare paths in that shape.
        elems = re.findall(r"['\"]([^'\"]*)['\"]", rest)
        rebuilt = "git %s %s" % (verb, " ".join(elems))
        yield rebuilt


def find_cwd(command, segment=None):
    """Work out which tree the command acts on, so `git status` asks the right repo.

    `git -C <dir>` wins over a leading `cd <dir>`: it is per-command and beats
    the shell's directory. Missing this form was a real hole — the test suite's
    case 10 caught `git -C <repo> checkout -- <dirty file>` passing straight
    through, and `git -C` is a form this project actually uses (DEFECT-B13).
    """
    for source in (segment, command):
        if not source:
            continue
        m = re.search(r"\bgit\s+-C\s+([^\s;&|]+)", source)
        if m:
            candidate = m.group(1).strip("'\"")
            if os.path.isdir(candidate):
                return candidate
    m = re.search(r"\bcd\s+([^\s;&|]+)", command)
    if m:
        candidate = m.group(1).strip("'\"")
        if os.path.isdir(candidate):
            return candidate
    return None


def paths_after_separator(sub_argv, sub):
    """Extract the pathspecs a checkout/restore's own argv (the tokens AFTER
    the subcommand, already shell-word-tokenized and quote-stripped by
    `_git_shell.parse_invocation`/`find_subcommand`) targets.

    `--` disambiguates explicitly; without it, every non-flag token is taken
    as a candidate pathspec (a branch name like `main`, or `-b feature`'s
    argument, simply never shows up as dirty in `git status`, so treating it
    as a candidate costs nothing -- `dirty_paths` is the real filter).
    """
    if "--" in sub_argv:
        idx = sub_argv.index("--")
        return [t for t in sub_argv[idx + 1:] if not t.startswith("-")]
    return [t for t in sub_argv if not t.startswith("-")]


def restore_is_staged_only(sub_argv):
    """True when a `git restore` invocation only unstages (never touches the
    worktree). `--staged`/`-S` moves changes out of the index back to the
    worktree copy -- the worktree file itself is untouched. `--worktree`/`-W`
    (default when `--staged` is absent) or an explicit `--source`/`-s` DOES
    write the worktree file, so either of those still blocks."""
    staged = any(t in ("--staged", "-S") for t in sub_argv)
    worktree = any(t in ("--worktree", "-W") for t in sub_argv)
    source = any(
        t in ("--source", "-s") or t.startswith("--source=") or t.startswith("-s=")
        for t in sub_argv
    )
    return staged and not worktree and not source


def dirty_paths(paths, cwd):
    """Return the subset git reports as having uncommitted changes."""
    if not paths:
        return []
    cmd = ["git", "status", "--porcelain", "--"] + paths
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        return []  # not a repo / bad pathspec -> not our business
    dirty = []
    for line in proc.stdout.splitlines():
        if len(line) < 4:
            continue
        status, name = line[:2], line[3:].strip()
        if status.strip() and not status.startswith("??"):
            dirty.append((status, name))
    return dirty


def find_dirty_hit(text, outer_command, payload_cwd):
    """Scan `text` (a full command, or a nested command string extracted from
    inside an interpreter arg / argv-list) for a checkout/restore-of-a-dirty-path
    hit. `outer_command` is used for `find_cwd`'s `cd`-chain lookup so a nested
    text with no cd/-C of its own still resolves against the real invocation's
    directory. Returns the dirty list on a hit, else None."""
    for segment in gs.split_segments(text):
        segment = segment.strip()
        if not segment:
            continue
        parsed = gs.parse_invocation(segment, os.environ)
        if parsed is None:
            continue
        sub, sub_argv, _c_values = gs.find_subcommand(parsed["argv"])
        if sub not in ("checkout", "restore"):
            continue
        if sub == "restore" and restore_is_staged_only(sub_argv):
            continue
        try:
            cwd = find_cwd(outer_command, segment) or payload_cwd or None
        except Exception:
            cwd = find_cwd(outer_command, segment)
        paths = paths_after_separator(sub_argv, sub)
        # `git checkout -f` / `--force` with no explicit path discards EVERY
        # dirty file in the tree, exactly like `git checkout -- .` (issue #14
        # Tier A round 2).
        if sub == "checkout" and not paths and any(t in ("-f", "--force") for t in sub_argv):
            paths = ["."]
        dirty = dirty_paths(paths, cwd)
        if dirty:
            return dirty
    return None


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    if payload.get("tool_name") not in ("Bash", "PowerShell"):
        sys.exit(0)
    command = payload.get("tool_input", {}).get("command", "") or ""
    if not command:
        sys.exit(0)
    if ALLOW_ENV in command:
        sys.exit(0)

    try:
        dirty = find_dirty_hit(command, command, payload.get("cwd"))
        if dirty is None:
            for nested in nested_command_texts(command):
                if ALLOW_ENV in nested:
                    continue
                dirty = find_dirty_hit(nested, command, payload.get("cwd"))
                if dirty is not None:
                    break
        if dirty is not None:
            listed = "\n".join("    %s  %s" % (s, n) for s, n in dirty)
            sys.stderr.write(
                "BLOCKED: this would DISCARD uncommitted changes, restoring from the last "
                "COMMIT rather than from the state you had a moment ago:\n"
                + listed
                + "\n\nThis exact command silently reverted a whole uncommitted security fix "
                "(DEFECT-B14) and ~200 lines of uncommitted CI hardening (DEFECT-B18) on "
                "2026-09-10.\n\nIf you are undoing a test mutation: commit the good state "
                "FIRST, keep a backup copy (cp <file> <file>.bak), and restore from that.\n"
                "If you genuinely mean to throw this work away: prefix the command with "
                + ALLOW_ENV
                + "=1\n"
            )
            sys.exit(2)
    except Exception:
        sys.exit(0)

    sys.exit(0)


if __name__ == "__main__":
    main()
