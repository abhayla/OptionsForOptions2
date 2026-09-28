"""Shared shell-word parsing for the git guards (issue #14 fix round 2).

RCA: matching raw command TEXT with regexes lets a quoted program path, bundled
short flags, an unambiguous prefix of a long option, a mixed-case config key or
an env-var config mechanism slip through, while text that merely CONTAINS the
watched words (an echo, a commit -m message, an unrelated subcommand's -n) gets
blocked by accident. The fix is to actually parse each segment into words and
reason about the PROGRAM and its ARGV, not about substrings.

This file is byte-identical in every guard directory that imports it
(git-discard-uncommitted-guard, git-hook-bypass-guard, git-stash-worktree-guard)
and in the kit's flat `.claude/hooks/` template directory, where all four
guards already live side by side.
"""
import os
import re

# A segment boundary: &&, ||, ;, |, a bare & (PowerShell call operator), and
# {, }, (, ) so `if ($?) { git ... }` reads as `git ...` on its own.
#
# finding segment-split-before-quotes: the previous version matched a regex like this over the
# raw command TEXT before any quote was recognised, so a separator character INSIDE a single-
# or double-quoted string (e.g. a `-m "a|b"` commit message, or a test loop's quoted case
# string holding `|`) split the string in two and the quoted words on either side were then
# read as their own command segments -- a quoted bypass word ("--no-verify") then reached
# `parse_invocation` as if it were a real, separate command. `split_segments` below is
# quote-aware: it scans the command character by character and only treats a separator as a
# boundary while it is NOT inside an open single or double quote. An unterminated quote fails
# safe (the rest of the command is kept as one segment) rather than being treated as closed.
_MULTI_CHAR_SEPARATORS = ("&&", "||")
_SINGLE_CHAR_SEPARATORS = frozenset(";|&{}()\n")

# A leading NAME=value / NAME="quoted value" / NAME='quoted value' env
# assignment at the start of what's left of a segment.
_ENV_ASSIGN_RE = re.compile(
    r"^\s*([A-Za-z_][A-Za-z0-9_]*)="
    r"(\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'|\S*)"
)


def collapse_backtick_continuation(command):
    """A PowerShell backtick immediately before a newline continues the
    logical line; collapse it to a space so the two halves read as one
    segment instead of being torn apart by the newline split."""
    return re.sub(r"`\r?\n", " ", command)


def _scan_segments(command):
    """Quote-aware segment scan shared by `split_segments` and
    `split_segments_with_start`. Returns a list of (segment_text, start_pos)
    pairs, positions relative to `command` as passed in (the caller collapses
    backtick continuations first, once, so positions stay meaningful to it)."""
    segments = []
    buf = []
    seg_start = 0
    quote = None  # "'" or '"' while inside a quoted run, else None
    i = 0
    n = len(command)
    while i < n:
        ch = command[i]
        if quote is not None:
            buf.append(ch)
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in ("'", '"'):
            quote = ch
            buf.append(ch)
            i += 1
            continue
        two = command[i:i + 2]
        if two in _MULTI_CHAR_SEPARATORS:
            segments.append(("".join(buf), seg_start))
            buf = []
            i += 2
            seg_start = i
            continue
        if ch in _SINGLE_CHAR_SEPARATORS:
            segments.append(("".join(buf), seg_start))
            buf = []
            i += 1
            seg_start = i
            continue
        buf.append(ch)
        i += 1
    segments.append(("".join(buf), seg_start))
    return segments


def split_segments(command):
    """Split a full command string into shell segments on &&, ||, ;, |, a
    bare &, {, }, (, ) and newlines -- but ONLY outside an open single or
    double quote (finding segment-split-before-quotes). Backtick
    line-continuations are collapsed first. An unterminated quote is a fail
    -safe: the remainder of the command is kept as one segment rather than
    guessing where it would have closed."""
    command = collapse_backtick_continuation(command)
    return [seg for seg, _start in _scan_segments(command)]


def split_segments_with_start(command):
    """Like `split_segments`, but also returns each segment's start offset in
    the backtick-collapsed command text, so a caller doing a `cd`-chain
    lookup can still ask 'what preceded this invocation'. Returns
    (collapsed_command, [(segment, start_pos), ...])."""
    collapsed = collapse_backtick_continuation(command)
    return collapsed, _scan_segments(collapsed)


def _strip_quotes(token):
    if len(token) >= 2 and token[0] == token[-1] and token[0] in ("'", '"'):
        return token[1:-1]
    return token


def tokenize(segment):
    """Split a segment into words, Windows-path-safe (backslashes are kept
    literally, never treated as escapes), with one layer of quotes stripped
    per token. Falls back to a plain whitespace split on anything shlex
    can't handle (unbalanced quotes etc.)."""
    import shlex

    try:
        raw = shlex.split(segment, posix=False)
    except ValueError:
        raw = segment.split()
    return [_strip_quotes(t) for t in raw]


def basename_lower(token):
    return re.split(r"[\\/]+", token)[-1].lower()


def is_git_program(token):
    return basename_lower(token) in ("git", "git.exe")


def parse_invocation(segment, os_environ=None):
    """Parse a segment as a possible git invocation.

    Returns None if the segment's program (after any leading NAME=value env
    assignments) is not git. Otherwise returns a dict:
      {"env": {name: value, ...}, "argv": [tokens after the program]}
    `env` merges any inline NAME=value prefix over `os_environ` (inline wins),
    so an env-based hooksPath override can be detected whether it was set as
    a real environment variable or as an inline prefix on the command.
    """
    text = segment
    env = {}
    while True:
        m = _ENV_ASSIGN_RE.match(text)
        if not m:
            break
        env[m.group(1)] = _strip_quotes(m.group(2))
        text = text[m.end():]

    tokens = tokenize(text)
    if not tokens:
        return None
    program = tokens[0]
    if not is_git_program(program):
        return None

    merged_env = dict(os_environ or {})
    merged_env.update(env)
    return {"env": merged_env, "argv": tokens[1:]}


# Global git options that consume the NEXT token as a value (so it is never
# mistaken for the subcommand).
_GLOBAL_OPTS_WITH_SEPARATE_VALUE = ("-c", "-C")


def find_subcommand(argv):
    """Walk past git's global options to find the subcommand token and the
    argv that follows it. Also collects every `-c key=value` seen along the
    way (inline `-ckey=value` is not supported by real git and is not
    handled here). Returns (subcommand_or_None, sub_argv, c_values)."""
    i = 0
    c_values = []
    while i < len(argv):
        t = argv[i]
        if t in _GLOBAL_OPTS_WITH_SEPARATE_VALUE:
            if t == "-c" and i + 1 < len(argv):
                c_values.append(argv[i + 1])
            i += 2
            continue
        if t.startswith("--"):
            i += 1
            continue
        if t.startswith("-") and t != "-":
            i += 1
            continue
        break
    if i < len(argv):
        return argv[i], argv[i + 1:], c_values
    return None, [], c_values


def config_value(pairs, key):
    """Return the value for `key` (case-insensitive) from a list of
    `key=value` strings, or None."""
    key_l = key.lower()
    for pair in pairs:
        k, sep, v = pair.partition("=")
        if sep and k.strip().lower() == key_l:
            return v
    return None


def env_sets_hooks_path(env):
    """True when the env (inline prefix merged over the real environment)
    configures core.hooksPath via GIT_CONFIG_PARAMETERS or the
    GIT_CONFIG_COUNT/GIT_CONFIG_KEY_n/GIT_CONFIG_VALUE_n mechanism."""
    gcp = env.get("GIT_CONFIG_PARAMETERS", "")
    if "core.hookspath" in gcp.lower():
        return True
    for k, v in env.items():
        if k.startswith("GIT_CONFIG_KEY_") and (v or "").lower() == "core.hookspath":
            return True
    return False
