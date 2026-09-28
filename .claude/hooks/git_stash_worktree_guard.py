#!/usr/bin/env python3
"""PreToolUse hook: deny `git stash` (mutating subcommands) inside a linked git worktree.

Fails open on any unexpected error (missing git, not a repo, bad JSON, etc.) —
never blocks a Bash call for a reason unrelated to the stash-in-worktree class.
Motivating incident: a worker ran `git stash` inside a linked worktree,
which silently misrouted its uncommitted work to the wrong branch's stash.

Tier A mechanism fix (2026-09-16b), PROVEN GAP: a stash issued through a nested
interpreter escaped this guard --
  (C) `powershell -NoProfile -c "git stash push -- f.txt; ..."` in a linked
      worktree succeeded although the top-level shell command has no `git`
      token at its start; the verb only appears inside the quoted PowerShell
      script string, which GIT_STASH_TOKEN_RE (anchored to shell-segment
      boundaries) never looks inside.

Fix (`nested_command_texts`): before the top-level regex scan, pull the
literal string handed to an interpreter's `-c`/`-Command`/`-e`/`/c`/`-p` flag
(powershell/pwsh/bash/sh/zsh/cmd/python/python3/node) and feed it back through
the SAME find_stash_matches()/resolve_target_dir() machinery, using the OUTER
command for any `cd`/`-C` resolution the nested text lacks. A Python/JS argv
list shaped `['git', 'stash', ...]` is also reconstructed into `git stash ...`
text and scanned the same way, mirroring git-discard-uncommitted-guard.py's
fix for the same class. Deliberately still out of scope: a verb assembled by
string concatenation or a shell variable inside the nested interpreter.
"""
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _git_shell as gs  # noqa: E402

# Read-only stash subcommands that never touch/misroute work. Any subcommand
# token that is itself a flag (--help, -h, ...) is also treated as read-only —
# it is informational, not one of the mutating verbs (push/pop/apply/drop/
# branch/clear/store).
READONLY_STASH_SUBCOMMANDS = {"list", "show", "create"}

# Matches a `git` invocation — optionally preceded by an env-assignment
# prefix, a `(`/`$(`/`\` prefix, or a `command ` prefix, and optionally
# carrying -C <path> / --git-dir=... / -c k=v / other flags before the
# subcommand — followed by `stash`, as a token, not merely the substring
# "git stash" anywhere (e.g. inside `echo "git stash"`). re.MULTILINE so the
# `^` anchor also matches after an embedded newline (multi-line commands).
# The git program, spelled any way the shell accepts it: bare `git`, `git.exe`,
# or a path ending in `/git(.exe)` or `\git(.exe)`, case-insensitive (issue #14).
_GIT_BIN = r"(?:\S*[\\/])?git(?:\.exe)?"

GIT_STASH_TOKEN_RE = re.compile(
    r"(?:^|[;&|]\s*|[{}]\s*|\bthen\b\s*|\bdo\b\s*)"
    r"(?:(?:[A-Za-z_][A-Za-z0-9_]*=\S+\s+)+)?"
    r"(?:\$\(|\(|\\)?"
    r"\s*(?:command\s+)?"
    + _GIT_BIN
    + r"\b"
    r"(?:\s+(?:"
    r"-C\s+(?:\"[^\"]*\"|'[^']*'|\S+)"
    r"|--git-dir=\S+"
    r"|-c\s+\S+"
    r"|-{1,2}[A-Za-z][\w-]*(?:=\S+)?"
    r"))*"
    r"\s+stash\b(\s+\S+)?",
    re.MULTILINE | re.IGNORECASE,
)


def env_bypass(command: str) -> bool:
    if os.environ.get("GIT_STASH_GUARD_ALLOW") == "1":
        return True
    # Inline env-var prefix form: GIT_STASH_GUARD_ALLOW=1 git stash ...
    if re.search(r"(?:^|[;&|]\s*)GIT_STASH_GUARD_ALLOW=1\b", command):
        return True
    return False


def _strip_quotes(token: str) -> str:
    """Strip one layer of matching quotes. Deliberately NOT shlex.split —
    shlex treats backslash as an escape char and mangles Windows paths
    (C:\\Users\\... -> CUsers...)."""
    if len(token) >= 2 and token[0] == token[-1] and token[0] in ("'", '"'):
        return token[1:-1]
    return token


def extract_c_path(matched_text: str):
    """Extract a `-C <path>` argument from the matched git-invocation text.
    `<path>` may be a bare token or a single/double-quoted string containing
    spaces; other flags (`-c key=val`, `--git-dir=...`) are ignored here since
    they either take no separate path argument or are handled by callers that
    don't need their value."""
    m = re.search(r"-C\s+(\"[^\"]*\"|'[^']*'|\S+)", matched_text or "")
    if not m:
        return None
    return _strip_quotes(m.group(1))


CD_TOKEN_RE = re.compile(
    r"(?:^|[;&|\n]\s*|\bthen\b\s*|\bdo\b\s*)"
    r"(?:cd|pushd|Set-Location|sl|chdir)\s+(\"[^\"]*\"|'[^']*'|[^\s;&|]+)",
    re.MULTILINE | re.IGNORECASE,
)


def find_last_cd_before(command: str, before_pos: int, base_cwd: str):
    """Chain every `cd <path>` / `pushd <path>` that starts before
    `before_pos` (the position of the git-stash match), resolving each
    (possibly relative) target against the running directory — starting at
    `base_cwd` — so `cd a && cd b` resolves to `base_cwd/a/b`, and an
    absolute target resets the chain. Returns None if no cd/pushd precedes
    the match (caller falls back to `base_cwd` directly)."""
    current = None
    for m in CD_TOKEN_RE.finditer(command):
        if m.start() >= before_pos:
            break
        raw = _strip_quotes(m.group(1))
        base = current if current is not None else base_cwd
        current = raw if os.path.isabs(raw) else os.path.normpath(os.path.join(base or "", raw))
    return current


# An interpreter flag that takes an inline script/command STRING as its value:
# powershell/pwsh -c|-Command, bash/sh/zsh -c, cmd /c, python/python3 -c, node -e.
_NESTED_INTERPRETER_RE = re.compile(
    r"\b(?:powershell(?:\.exe)?|pwsh(?:\.exe)?|bash|sh|zsh|cmd(?:\.exe)?|python3?|node)\b"
    r"[^\n]*?"
    r"(?:-{1,2}[Cc](?:ommand)?|-[Ee]|/[Cc]|-[Pp])\s+"
    r"(\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*')",
)

# A Python/JS argv-LIST literal: 'git' followed by 'stash' as its own quoted
# element within the same bracketed list, e.g. ['git', 'stash', 'push', ...].
_ARGV_LIST_RE = re.compile(
    r"\[\s*(['\"])git\1\s*,\s*(['\"])stash\2(?P<rest>[^\]]*)\]",
)


def _unquote_literal(text):
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        return text[1:-1]
    return text


def nested_command_texts(command: str):
    """Yield command-shaped text pulled out of nested-interpreter invocations
    and argv-list literals (see module docstring, Tier A fix 2026-09-16b).
    Deliberately shallow: does not evaluate the nested language."""
    for m in _NESTED_INTERPRETER_RE.finditer(command):
        inner = _unquote_literal(m.group(1))
        inner = inner.replace('\\"', '"').replace("\\'", "'")
        if "stash" in inner:
            yield inner

    for m in _ARGV_LIST_RE.finditer(command):
        rest = m.group("rest") or ""
        elems = re.findall(r"['\"]([^'\"]*)['\"]", rest)
        yield "git stash %s" % " ".join(elems)


def find_stash_matches(command: str):
    return list(GIT_STASH_TOKEN_RE.finditer(command))


def is_readonly_stash(match: "re.Match") -> bool:
    sub = (match.group(1) or "").strip()
    if not sub:
        return False  # bare `git stash` == push, mutating
    if sub in READONLY_STASH_SUBCOMMANDS:
        return True
    # ONLY -h/--help is informational. Tier A round 2 (issue #14) fix: every
    # OTHER flag (`-u`, `--include-untracked`, `-m`, `--message`, ...) is a
    # `stash push` OPTION -- `git stash -u` / `git stash -m wip` mutate the
    # stash exactly like a bare `git stash`, and the previous rule (any
    # leading `-` is read-only) let both straight through.
    return sub in ("-h", "--help")


def _segments_with_start(text):
    """Like `_git_shell.split_segments`, but also returns each segment's
    start offset in `text` (post backtick-collapse), so the cd-chain lookup
    can still ask 'what preceded this invocation'. Quote-aware (finding
    segment-split-before-quotes): delegates to the shared parser so a
    separator character inside a quoted string is never mistaken for a
    segment boundary here either."""
    return gs.split_segments_with_start(text)


def is_readonly_stash_argv(sub_argv):
    if not sub_argv:
        return False  # bare `git stash` == push, mutating
    first = sub_argv[0]
    if first in READONLY_STASH_SUBCOMMANDS:
        return True
    return first in ("-h", "--help")


def find_stash_hits_via_parser(command):
    """Identify the git program ONLY through `_git_shell.py` (Tier A round 3,
    issue #14 -- the previous version of this file kept its own quote
    stripping / regex program match, which missed a quoted program path like
    `& "C:\\Program Files\\Git\\bin\\git.exe" stash` even though the sibling
    bypass guard, using the shared parser, already caught the same form).

    Returns a list of (segment_text, start_pos, sub_argv) for every segment
    whose PROGRAM is git (per `_git_shell.is_git_program`) and whose
    SUBCOMMAND is `stash`."""
    collapsed, segs = _segments_with_start(command)
    hits = []
    for seg, start in segs:
        stripped = seg.strip()
        if not stripped:
            continue
        parsed = gs.parse_invocation(stripped, os.environ)
        if parsed is None:
            continue
        sub, sub_argv, _c_values = gs.find_subcommand(parsed["argv"])
        if sub != "stash":
            continue
        hits.append((seg, start, sub_argv))
    return collapsed, hits


def resolve_target_dir(command: str, cwd: str, start_pos: int, seg_text: str) -> str:
    base = cwd or os.getcwd()
    c_path = extract_c_path(seg_text)
    if c_path:
        return c_path if os.path.isabs(c_path) else os.path.normpath(os.path.join(base, c_path))
    cd_path = find_last_cd_before(command, start_pos, base)
    if cd_path:
        return cd_path
    return base


def is_linked_worktree(path: str):
    """Return absolute worktree path string if `path` is a linked worktree, else None.

    Any failure (git missing, not a repo, timeout, bad output) returns None
    (fail-open — caller treats None as "not a worktree, allow").
    """
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--git-dir", "--git-common-dir"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=3,
        )
        if proc.returncode != 0:
            return None
        lines = [l.strip() for l in proc.stdout.splitlines() if l.strip()]
        if len(lines) < 2:
            return None
        git_dir, git_common_dir = lines[0], lines[1]

        def norm(p):
            if not os.path.isabs(p):
                p = os.path.join(path, p)
            return os.path.normcase(os.path.normpath(os.path.abspath(p)))

        if norm(git_dir) != norm(git_common_dir):
            return os.path.normpath(os.path.abspath(path))
        return None
    except Exception:
        return None


def main():
    try:
        raw = sys.stdin.read()
        data = json.loads(raw)
    except Exception:
        sys.exit(0)  # malformed JSON -> allow

    try:
        if data.get("tool_name") not in ("Bash", "PowerShell"):
            sys.exit(0)

        tool_input = data.get("tool_input") or {}
        command = tool_input.get("command") or ""
        if not command or "stash" not in command.lower():
            sys.exit(0)

        cwd = data.get("cwd") or os.getcwd()

        # Determine whether this command would actually be denied BEFORE
        # printing anything — the bypass notice is only relevant when a deny
        # was the alternative. Scan the top-level command text first, then
        # any nested-interpreter / argv-list text extracted from inside it
        # (Tier A fix 2026-09-16b) — a nested match resolves its target dir
        # against the OUTER command since the nested text usually carries no
        # cd/-C of its own. The git PROGRAM itself is identified only via
        # `_git_shell.py` (Tier A round 3, issue #14) -- never by this
        # guard's own regex/quote-stripping.
        denied_worktree = None

        collapsed, hits = find_stash_hits_via_parser(command)
        mutating_hits = [h for h in hits if not is_readonly_stash_argv(h[2])]
        for seg, start, _sub_argv in mutating_hits:
            target_dir = resolve_target_dir(collapsed, cwd, start, seg)
            worktree_path = is_linked_worktree(target_dir)
            if worktree_path:
                denied_worktree = worktree_path
                break

        if denied_worktree is None:
            for nested in nested_command_texts(command):
                if env_bypass(nested):
                    continue
                _nested_collapsed, nested_hits = find_stash_hits_via_parser(nested)
                nested_mutating = [h for h in nested_hits if not is_readonly_stash_argv(h[2])]
                for seg, start, _sub_argv in nested_mutating:
                    target_dir = resolve_target_dir(collapsed, cwd, 0, seg)
                    worktree_path = is_linked_worktree(target_dir)
                    if worktree_path:
                        denied_worktree = worktree_path
                        break
                if denied_worktree:
                    break

        if not denied_worktree:
            sys.exit(0)

        if env_bypass(command):
            sys.stderr.write("git-stash guard: bypassed by GIT_STASH_GUARD_ALLOW\n")
            sys.exit(0)

        sys.stderr.write(
            "BLOCKED: git stash inside a linked worktree (%s) is not allowed "
            "(a stash in a worktree has misrouted work before); commit on the "
            "branch or use a scratch copy instead.\n" % denied_worktree
        )
        sys.exit(2)
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)  # fail-open on any unexpected error


if __name__ == "__main__":
    main()
