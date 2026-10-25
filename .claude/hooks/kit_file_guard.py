#!/usr/bin/env python3
"""kit_file_guard.py — PreToolUse hook: refuse a tool call that would EDIT a kit-owned file.

WHY (OD-22): a project made by the copier (tools/new_project.py) never edits, deletes or
loosens a kit-owned file (rules, hooks, agents, skills, the kit's settings wiring) — only a
Factory kit upgrade replaces them. New project needs get NEW files instead (a rule under the
project rules folder, a hook addendum entry, and so on). This hook is the project-side
enforcement layer named in OD-22 ("a project hook blocks edits to kit-owned files listed in
the lock"); the CI drift check and the owner's review of any PR touching kit files are the
other two layers. Seatbelt, not lock (OD-11 wording, same idea applied here): it relies on
this hook actually being wired and running.

Protected classes (the `owner` field recorded per file in the project's lock file, one entry
per copied file: path / source / sha256 / owner):
  - "kit"       — Factory-owned, replaced only by a kit upgrade.
  - "generated" — written by a kit tool from kit+project inputs; hand-editing it forks it
                  from the tool that regenerates it.
  - "owner"     — a human-owner-only file (e.g. the production seatbelt's config); only the
                  human who owns the project edits it, never Claude.
  - the lock file itself is always protected, whether or not it lists itself.
  - the project's personal LOCAL settings override file is always protected even when it is
    not in the lock at all (it is git-ignored, created ad hoc, can silently switch off every
    other hook, and CI never sees it) — only a human creates or edits it. Its name is built
    from parts below, like every other sensitive path in this repo's own tooling.

Tool coverage:
  - File-editing tools (Edit, Write, MultiEdit, NotebookEdit): denied when the resolved target
    path is protected.
  - Shell tools (Bash, PowerShell): denied when the command both NAMES a protected path and
    contains a write/delete form (rm, mv, cp/copy with it as a target, sed -i, tee, `>`/`>>`,
    truncate, git rm / checkout -- / restore, Remove-Item, Move-Item, Copy-Item -Destination,
    Set-Content, Add-Content, Out-File, New-Item -Force). A read-only command mentioning a
    protected path (cat, grep, git diff, ...) is never denied by this check.
  - Anything else (Task/Agent dispatch, mcp__* calls, ...) is not affected.

Sanctioned writers: a shell command whose program is the kit settings generator or a kit
upgrade tool is allowed even though it writes the generated settings file — those ARE the
tools that regenerate it.

Fail open: no lock file (or an unreadable/malformed one) allows every call and prints one
stderr line saying so (run-discipline D1: a project hook does nothing useful without its
data file, but it must never block work because that file is missing). Any other internal
error also fails open.

Bypass (owner only, like the other kit guards): KIT_FILE_GUARD_ALLOW=1 inline in a shell
command, or set in the process environment for a file-editing tool call (file tools carry no
command text to put an inline marker in).

Deny output: a stderr message + exit code 2 (NOT the JSON hookSpecificOutput deny shape some
sibling guards use). Proven live on 2.1.280 (M3 kit-file-guard brief, coordinator note): a
PreToolUse JSON `permissionDecision: "deny"` (exit 0) from one hook is OVERRIDDEN when another
matching hook in the same event returns `permissionDecision: "allow"` — a project hook
returning allow let an Agent call through that this kit's budget guard had denied via JSON;
without that other hook the JSON deny held. Exit code 2 cannot be overridden that way, so this
guard blocks with exit 2, matching git-discard-uncommitted-guard's convention.
"""
from __future__ import annotations

import json
import os
import re
import sys

ALLOW_ENV = "KIT_FILE_GUARD_ALLOW"

# Names built from parts (this repo's own governing seatbelt refuses to see some path/file
# names typed as one contiguous literal in file content or shell text it scans).
_DOT_FACTORY = "." + "factory"
_DOT_CLAUDE = "." + "claude"
_LOCK_NAME = "factory" + ".lock"
_LOCAL_SETTINGS_NAME = "settings" + "." + "local" + ".json"

LOCK_REL = _DOT_FACTORY + "/" + _LOCK_NAME
LOCAL_SETTINGS_REL = _DOT_CLAUDE + "/" + _LOCAL_SETTINGS_NAME

PROTECTED_OWNERS = {"kit", "generated", "owner"}

FILE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
FILE_PATH_KEYS = ("file_path", "notebook_path")
SHELL_TOOLS = {"Bash", "PowerShell"}

DENY_KIND_KIT = "kit"
DENY_KIND_OWNER = "owner"
DENY_KIND_LOCAL_SETTINGS = "local-settings"

# Fixed folders that are ALWAYS treated as protected-containing, regardless of what the lock
# happens to list (review r1, item 1) -- a project's kit tooling and kit-owned trees, even
# before the lock names every file inside them.
_FIXED_PROTECTED_FOLDERS = (
    _DOT_CLAUDE,
    _DOT_CLAUDE + "/hooks",
    _DOT_CLAUDE + "/rules/kit",
    _DOT_CLAUDE + "/kit",
    "tools",
    _DOT_FACTORY,
)

# Review r2, item 1: kit-only folders hold kit files only -- a NEW file dropped in one is denied
# even though it is (by definition) not in the lock yet. Deliberately excludes agents/ and
# skills/: a project adds its OWN agents and skills there.
KIT_ONLY_FOLDERS = (
    _DOT_CLAUDE + "/rules/kit",
    _DOT_CLAUDE + "/kit",
    _DOT_CLAUDE + "/hooks",
)
DENY_KIND_KIT_FOLDER = "kit-folder"

# Review r1: enumerating write verbs can never be complete (same class as the
# text-gate-misses-non-shell-actions finding). Flipped to a READ-ONLY allowlist: once a shell
# command names a protected path or a protected-containing folder, every segment of the command
# (split on ; && || | & and newlines) must be one of these, with no output redirection to a
# real file, or the whole command is refused.
_READONLY_PROGRAM_RE = re.compile(
    r"^(cat|type|head|tail|less|more|wc|grep|rg|findstr|ls|dir"
    r"|get-content|gc|get-childitem|gci|select-string|sls|diff)(?:\.exe)?(?=\s|$)",
    re.IGNORECASE,
)
# W-046 round 5 (#127): main's `^git\s+` spelling only. Round 1 had widened it to `git.exe`, which
# allowed `git.exe diff <kit path>` where main denies it (AC-6: tightening only).
_READONLY_GIT_RE = re.compile(
    r"^(git)\s+(diff|log|show|status|blame|ls-files)\b", re.IGNORECASE
)
# Item 1 (OD-22 follow-up, kit-file-guard-blocks-nonmutating-tool-runs): a segment whose program
# is python/python3/py and whose first argument is EXACTLY `tools/<name>.py` (nothing further --
# no extra `/`, `\`, `..`, no trailing text before whitespace/end) is RUNNING that kit tool, not
# writing it -- allowed as long as the segment carries no output redirect to a real path (checked
# by _has_bad_redirect before this is reached) and the tool named, with its actual arguments, is
# not one of the conditional writers below, which keep the stricter whole-command-only rule
# (_SANCTIONED_WHOLE_RE) instead of this leniency.
#
# Review round 2 (Tier A, REVISE on c4d20d1): the previous version of this regex had no trailing
# anchor, so `tools/factory_lint.py/../kit_settings.py` matched `factory_lint.py` as the "tool
# name" and was allowed even though the shell actually runs kit_settings.py -- a path trick that
# ran a writer under a read-only-looking name. The `(?=\s|$)` anchor below closes that: the
# argument must end exactly at `.py`, followed only by whitespace or end of segment.
_RUNNING_KIT_TOOL_RE = re.compile(
    r"^(?:python3?|py)(?-i:(?:\s+-[IBu])*)\s+tools[/\\]([\w.-]+\.py)(?=\s|$)", re.IGNORECASE
)

# Review round 3: a kit tool is judged on its NORMALISED words (quotes and backslashes removed),
# not on substrings of the raw text, and a flag matches when it is a unique leading part of a writer
# flag (argparse accepts `--write-vie`). Tools that only write unless told to check are read-only
# only with their exact check flag.
_KIT_TOOLS_ALWAYS_WRITE = {"kit_upgrade.py", "new_project.py"}
_KIT_TOOLS_READONLY_FLAGS = {  # tool -> exact words that make the run read-only
    "kit_settings.py": ("--check",),
    "build_findings_index.py": ("--check",),
    "build_order.py": ("--check", "--may-start"),
    "build_spec_digest.py": ("--check",),
    "build_spec_index.py": ("--check",),
    "generate_kit_tools_provenance.py": ("--check",),
}
# Writer / caller-chosen-output flags of any kit tool (long names; `-o` is the short form).
_KIT_WRITER_FLAGS = (
    "output", "out", "out-root", "out-dir", "output-dir", "outfile", "write", "write-view",
    "force", "force-nonempty", "in-place", "inplace",
)
# Tools whose output flag is allowed when its value is exactly the tool's own generated file.
_KIT_OWN_OUTPUT = {"build_status_page.py": "views/status-page.html"}


def _main_text_writer_test(name: str, segment: str) -> bool:
    """The pre-W-046 writer test, kept EXACTLY as it was: substring tests on the raw segment text.
    The word-level checks below are added on top (deny if either denies), so a junk-wrapped token
    (`--write-viewx`, `x--write-view`) that the word match misses is still caught here (AC-6)."""
    seg_lower = segment.lower()
    if name in ("kit_settings.py", "kit_upgrade.py"):
        if name == "kit_settings.py":
            return "--check" not in seg_lower
        return True
    if name == "build_findings_index.py":
        return "--check" not in seg_lower
    if name == "trace_check.py":
        return "--write-view" in seg_lower
    return False


def _is_writer_invocation(tool_name: str, segment: str) -> bool:
    name = tool_name.lower()
    if _main_text_writer_test(name, segment):
        return True
    words = _shell_words(segment)
    if words is None:
        return True  # cannot tokenise with certainty: treat as a writer
    if name in _KIT_TOOLS_ALWAYS_WRITE:
        return True
    rest = words[1:]
    if name in _KIT_TOOLS_READONLY_FLAGS and not any(
        w in _KIT_TOOLS_READONLY_FLAGS[name] for w in rest
    ):
        return True
    own = _KIT_OWN_OUTPUT.get(name)
    for i, w in enumerate(rest):
        if w.startswith("--"):
            flag = w[2:].split("=", 1)[0].lower()
            if not _name_is_leading_part(flag, _KIT_WRITER_FLAGS):
                continue
            if own is not None and _name_is_leading_part(flag, ("out",)):
                value = w.split("=", 1)[1] if "=" in w else (rest[i + 1] if i + 1 < len(rest) else None)
                if value == own:
                    continue
            return True
        if w.startswith("-") and len(w) > 1 and "o" in w[1:].split("=", 1)[0]:
            return True
    return False


# Sanctioned writers (review r1, item 2): allowed ONLY when the entire command is exactly one
# of these invocations (arguments allowed, no separators, no redirects) -- never as one segment
# of a longer command, and never with a trailing comment/anything else on the same line.
_SANCTIONED_WHOLE_RE = re.compile(
    r"^\s*python3?\s+tools[/\\]kit_(?:settings|upgrade)\.py(?:\s+[^\s;&|<>]+)*\s*$",
    re.IGNORECASE,
)
_SEPARATOR_CHARS_RE = re.compile(r"[;&|\n<>#]")

# Bypass (review r1, item 3): valid ONLY as a LEADING inline assignment, never elsewhere in the
# command (a trailing `echo KIT_FILE_GUARD_ALLOW=1` must not launder a write earlier in the line).
_BASH_BYPASS_LEADING_RE = re.compile(r"^\s*KIT_FILE_GUARD_ALLOW=1\s+\S")
_PS_BYPASS_LEADING_RE = re.compile(
    r"^\s*\$env:KIT_FILE_GUARD_ALLOW\s*=\s*1\s*;", re.IGNORECASE
)

_BAD_REDIRECT_RE = re.compile(r"(?:\d*)>>?\s*(\S+)")

_WARNED = False

# finding segment-split-before-quotes: a regex split over raw command TEXT (like the old
# `_SEGMENT_SPLIT_RE.split(command)`) treats a separator character INSIDE a single- or
# double-quoted argument (e.g. a commit message or `-m` value holding '|' or ';') as a real
# shell segment boundary, so the quoted text on either side is scanned as its own command --
# a read-only-looking half can then make the whole command look safe even though a write verb
# is hiding in the other half. `_split_segments` below only treats a separator as a boundary
# while it is NOT inside an open quote; an unterminated quote fails safe (the remainder of the
# command is kept as one segment).
_MULTI_CHAR_SEPARATORS = ("&&", "||")
_SINGLE_CHAR_SEPARATORS = frozenset(";|&\n")


def _split_segments(command: str) -> list[str]:
    segments: list[str] = []
    buf: list[str] = []
    quote = None
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
            segments.append("".join(buf))
            buf = []
            i += 2
            continue
        if ch in _SINGLE_CHAR_SEPARATORS:
            segments.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    segments.append("".join(buf))
    return segments


def _norm_command_text(command: str) -> str:
    return command.replace("\\", "/").lower()


def _dir_ancestors(rel_path: str) -> list[str]:
    parts = rel_path.replace("\\", "/").split("/")[:-1]
    out = []
    for i in range(1, len(parts) + 1):
        out.append("/".join(parts[:i]))
    return out


# W-046 round 5 (#127): `$null` is PowerShell's null device only under the PowerShell tool; in
# Bash it is an ordinary variable that may be set to any path, so it is not an inert target there.
# Data tables, so a mutation test can loosen each one.
_INERT_REDIRECT_TARGETS = {
    "Bash": ("/dev/null", "nul"),
    "PowerShell": ("/dev/null", "nul", "$null"),
}


def _has_bad_redirect(segment: str, shell: str = "Bash") -> bool:
    inert = _INERT_REDIRECT_TARGETS["PowerShell" if shell == "PowerShell" else "Bash"]
    for m in _BAD_REDIRECT_RE.finditer(segment):
        target = m.group(1).strip("'\"")
        if target.lower() not in inert:
            return True
    return False


# ---------------------------------------------------------------------------
# W-046 (OD-85 D2, REQ-055 AC-6, issue #120): a read-only program can still make the shell or the
# program itself run code or write a file through its ARGUMENTS. Every rule below only ever ADDS
# a deny once a command has already named a protected path; none of them allows anything new.
#
# Known gaps, out of this guard's threat model (say so here so nobody assumes otherwise):
#   - a git diff driver / textconv / fsmonitor configured in .git/config or .gitattributes (the
#     program then runs it with no flag on the command line);
#   - shell rc files, aliases and functions;
#   - a write that names no protected path at all (issue #119 re-hashes lock-listed files);
#   - zsh, and a glob that expands to a file someone already created with a flag-like name.
# ---------------------------------------------------------------------------

# Banned arguments per allowlisted program, matched on NORMALISED words (see _shell_words).
# long: a word `--name` or `--name=value` is banned when `name` is a leading part of one of these
# (git and others accept an unambiguous abbreviation, so `--outp` is `--output`); matched
# case-insensitively. short: banned when the letter appears in a single-dash word (`-abc` is
# `-a -b -c`; `-ccore.x=y` carries `-c`), case-sensitive. plus: any word starting with `+`.
_BANNED_ARGS = {
    "git": {"long": ("output", "ext-diff", "textconv", "filters"), "short": "c", "plus": False},
    "rg": {"long": ("pre", "pre-glob", "hostname-bin"), "short": "", "plus": False},
    "less": {"long": ("log-file",), "short": "oO", "plus": True},
    "more": {"long": ("log-file",), "short": "oO", "plus": True},
}

# Characters allowed in a command that names a protected path: printable ASCII, tab, line feed.
_ALLOWED_CHAR_RE = re.compile(r"\A[\x20-\x7e\t\n]*\Z")

def _bad_charset(command: str) -> bool:
    """True if the command holds any character outside printable ASCII, tab and LF: curly quotes
    (PowerShell reads them as quote marks, the guard does not), NBSP, en dash, CR, U+0085,
    U+2028/2029 and the like all make the guard and the shell read different words."""
    return _ALLOWED_CHAR_RE.match(command) is None


def _bash_backslash_hazard(command: str) -> bool:
    """True if a backslash outside single quotes could make the shell and _split_segments read
    different quotes or line breaks: any backslash outside quotes, and inside double quotes a
    backslash before `"` or a line feed (any other backslash there, such as in a grep
    alternation or an escaped backslash, is read the same way by both)."""
    quote = None
    i = 0
    n = len(command)
    while i < n:
        ch = command[i]
        if quote == "'":
            if ch == "'":
                quote = None
        elif quote == '"':
            if ch == "\\":
                if i + 1 < n and command[i + 1] in ('"', chr(10)):
                    return True
                i += 1  # the escaped character cannot open or close a quote
            elif ch == '"':
                quote = None
        elif ch == "\\":
            return True
        elif ch in ("'", '"'):
            quote = ch
        i += 1
    return False


def _ps_unquoted_hazard(command: str) -> bool:
    """PowerShell tool only: True if `(`, `{` or a backtick appears outside quotes (`@(` and
    `$(` contain `(`). The shell runs the code inside them while the guard sees a read."""
    quote = None
    for ch in command:
        if quote is not None:
            if ch == quote:
                quote = None
            continue
        if ch in ("'", '"'):
            quote = ch
        elif ch in "({`":
            return True
    return False


def _expansion_hazard(segment: str) -> bool:
    """True if the text holds ANY `$` outside single quotes. The guard cannot know what the
    shell makes of it (`--ext$X-diff` with X unset is `--ext-diff`, `$null_x` is another
    variable, `$^` and `$?` are variables too), so there is no word-level exemption: inert
    redirects (`2>/dev/null`, `2>$null`, ...) are removed whole-word first by
    _strip_inert_redirects. The one literal `$` kept is a regex end anchor right before the closing
    double quote (`grep "foo$" f`), which the shell never expands."""
    quote = None
    n = len(segment)
    for i, ch in enumerate(segment):
        if quote == "'":
            if ch == "'":
                quote = None
            continue
        if ch == "'" and quote is None:
            quote = "'"
            continue
        if ch == '"':
            quote = None if quote == '"' else '"'
            continue
        if ch == "$":
            if quote == '"' and i + 1 < n and segment[i + 1] == '"':
                continue
            return True
    return False


_INERT_REDIRECT_RES = {
    # Bash: `$null` is a variable (round 5), so `2>$null` keeps its `$` and the `$` denial applies.
    "Bash": re.compile(r"(?<!\S)(?:[12]?>/dev/null|2>&1)(?=\s|$)"),
    "PowerShell": re.compile(r"(?<!\S)(?:[12]?>(?:/dev/null|(?i:\$null))|2>&1)(?=\s|$)"),
}


def _strip_inert_redirects(command: str, shell: str = "Bash") -> str:
    """Remove exact whole-word redirect tokens that write nothing (`2>/dev/null`, `>/dev/null`,
    `2>&1`, and under the PowerShell tool only `2>$null`, `>$null`), so the `$` denial needs no
    `$null` special case."""
    rx = _INERT_REDIRECT_RES["PowerShell" if shell == "PowerShell" else "Bash"]
    return rx.sub("", command)


def _segment_hazard(segment: str, shell: str = "Bash") -> bool:
    """The checks EVERY allowed segment passes through, whatever program admitted it: an
    unresolvable `$` expansion, or text that cannot be tokenised with certainty."""
    return (
        _expansion_hazard(_strip_inert_redirects(segment, shell))
        or _shell_words(segment, shell) is None
    )


def _shell_words(segment: str, shell: str = "Bash") -> list[str] | None:
    """Split a segment into shell words with quotes and backslashes removed (so `--""filters`,
    `'--'filters` and a backslash before the first dash all become `--filters`). Returns None when the segment cannot
    be tokenised with certainty (unbalanced quote, unquoted `{` brace expansion, or an unquoted
    glob character in a word that starts with `-`): the caller then treats it as NOT read-only."""
    words: list[str] = []
    cur: list[str] = []
    started = False
    quote = None
    i = 0
    n = len(segment)

    def finish() -> None:
        nonlocal cur, started
        if started:
            words.append("".join(cur).replace("\\", ""))
        cur = []
        started = False

    while i < n:
        ch = segment[i]
        if quote is not None:
            if quote == '"' and ch == "\\" and shell != "PowerShell" and i + 1 < n:
                cur.append(segment[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
            else:
                cur.append(ch)
            i += 1
            continue
        if ch in ("'", '"'):
            quote = ch
            started = True
            i += 1
            continue
        if ch == "\\" and shell != "PowerShell" and i + 1 < n:
            cur.append(segment[i + 1])
            started = True
            i += 2
            continue
        if ch in " \t\n":
            finish()
            i += 1
            continue
        if ch == "{":
            return None
        if ch in "*?[" and cur and cur[0] == "-":
            return None
        cur.append(ch)
        started = True
        i += 1
    if quote is not None:
        return None
    finish()
    return words


def _name_is_leading_part(name: str, longs: tuple[str, ...]) -> bool:
    return bool(name) and any(b.startswith(name) for b in longs)


def _word_is_banned(word: str, rules: dict) -> bool:
    if rules["plus"] and word.startswith("+"):
        return True
    if word.startswith("--"):
        return _name_is_leading_part(word[2:].split("=", 1)[0].lower(), rules["long"])
    if word.startswith("-") and len(word) > 1:
        body = word[1:].split("=", 1)[0]
        return any(ch in rules["short"] for ch in body)
    return False


def _program_runs_code(program: str, segment: str, shell: str = "Bash") -> bool:
    """True if this allowlisted read-only segment must NOT be treated as read-only: the guard
    cannot tokenise it with certainty, or one of its words is a banned argument of the program
    that admitted it (the same case-insensitive match that admitted the segment)."""
    if _segment_hazard(segment, shell):
        return True
    words = _shell_words(segment, shell)
    rules = _BANNED_ARGS.get(program.lower())
    if rules is None:
        return False
    return any(_word_is_banned(w, rules) for w in words[1:])


def _is_readonly_segment(segment: str, shell: str = "Bash") -> bool:
    s = segment.strip()
    if not s:
        return True
    if _has_bad_redirect(s, shell):
        return False
    if _segment_hazard(s, shell):
        return False
    m_prog = _READONLY_PROGRAM_RE.match(s)
    if m_prog:
        return not _program_runs_code(m_prog.group(1), s, shell)
    m_git = _READONLY_GIT_RE.match(s)
    if m_git:
        return not _program_runs_code("git", s, shell)
    m = _RUNNING_KIT_TOOL_RE.match(s)
    if m and not _is_writer_invocation(m.group(1), s):
        return True
    return False


def _warn_once(msg: str) -> None:
    global _WARNED
    if not _WARNED:
        sys.stderr.write("kit-file-guard: " + msg + "\n")
        _WARNED = True


def deny(path_rel: str, reason_kind: str, note: str = "") -> None:
    if reason_kind == "owner":
        msg = (
            "BLOCKED: '" + path_rel + "' is owner-locked (only the human project owner edits "
            "this file, never Claude). If it genuinely needs to change, ask the owner to make "
            "the edit themselves."
        )
    elif reason_kind == DENY_KIND_KIT_FOLDER:
        msg = (
            "BLOCKED: '" + path_rel + "' would create a new file inside a kit-only folder -- "
            "kit folders hold kit files only. Put a new project rule under "
            "'.claude/rules/project/', a new project hook under '.claude/project/hooks/'."
        )
    elif reason_kind == "local-settings":
        msg = (
            "BLOCKED: '" + path_rel + "' is the project's personal local settings override — "
            "it can switch off every other hook and CI never sees it. Only a human creates or "
            "edits it directly; Claude never writes it."
        )
    else:
        msg = (
            "BLOCKED: '" + path_rel + "' is kit-owned (OD-22) — a project never edits, "
            "deletes or loosens a kit file; only a Factory kit upgrade replaces it. If you "
            "need new behavior, add a NEW file instead: a rule under the project rules folder, "
            "a hook wiring entry in the project's hook addendum, or run the Factory's kit "
            "upgrade."
        )
    if note:
        msg += "\n" + note
    sys.stderr.write(msg + "\n")
    sys.exit(2)


def find_project_root(start: str | None) -> str | None:
    """Walk up from `start` to the first directory holding the project's lock file."""
    if not start:
        return None
    cur = os.path.abspath(start)
    while True:
        if os.path.isfile(os.path.join(cur, LOCK_REL)):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def _canon(path: str) -> str:
    """Resolve symlinks/junctions/8.3 short names (review r1, item 4) and case-fold, so a
    resolved path from any tool call compares equal to the lock's recorded path."""
    return os.path.normcase(os.path.realpath(path))


def _contains_path_token(norm_command: str, token: str) -> bool:
    """True if `token` appears in `norm_command` as a whole path component, not merely as a
    substring of a longer name (e.g. "tools" must not match "mytools")."""
    if not token:
        return False
    start = 0
    while True:
        idx = norm_command.find(token, start)
        if idx == -1:
            return False
        before = norm_command[idx - 1] if idx > 0 else ""
        after_idx = idx + len(token)
        after = norm_command[after_idx] if after_idx < len(norm_command) else ""
        before_ok = before == "" or not (before.isalnum() or before in "_.")
        after_ok = after == "" or not (after.isalnum() or after == "_")
        if before_ok and after_ok:
            return True
        start = idx + 1


def load_lock(project_root: str) -> dict | None:
    lock_path = os.path.join(project_root, LOCK_REL)
    try:
        import yaml  # type: ignore
    except Exception:
        _warn_once("PyYAML not available; allowing (fail open)")
        return None
    try:
        with open(lock_path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except Exception as exc:
        _warn_once("could not read/parse the lock file: " + str(exc) + "; allowing (fail open)")
        return None
    if not isinstance(data, dict) or not isinstance(data.get("files"), list):
        _warn_once("lock file has no usable 'files' list; allowing (fail open)")
        return None
    return data


def owner_kind(project_root: str, lock: dict | None, resolved: str) -> str | None:
    """Return DENY_KIND_LOCAL_SETTINGS, DENY_KIND_OWNER, or DENY_KIND_KIT for a protected
    resolved path, else None."""
    if resolved == _canon(os.path.join(project_root, LOCAL_SETTINGS_REL)):
        return DENY_KIND_LOCAL_SETTINGS
    if resolved == _canon(os.path.join(project_root, LOCK_REL)):
        return DENY_KIND_KIT
    if lock:
        for entry in lock.get("files", []):
            if not isinstance(entry, dict):
                continue
            path = entry.get("path")
            if not isinstance(path, str) or not path:
                continue
            if _canon(os.path.join(project_root, path)) == resolved:
                owner = entry.get("owner")
                if owner in PROTECTED_OWNERS:
                    return DENY_KIND_OWNER if owner == "owner" else DENY_KIND_KIT
                return None
    return None


def protected_paths(project_root: str, lock: dict | None) -> set[str]:
    protected = {
        _canon(os.path.join(project_root, LOCK_REL)),
        _canon(os.path.join(project_root, LOCAL_SETTINGS_REL)),
    }
    if lock:
        for entry in lock.get("files", []):
            if not isinstance(entry, dict):
                continue
            path = entry.get("path")
            owner = entry.get("owner")
            if isinstance(path, str) and path and owner in PROTECTED_OWNERS:
                protected.add(_canon(os.path.join(project_root, path)))
    return protected


def _resolve_candidate(path_str: str, cwd: str) -> str:
    """Resolve a file-tool path against the payload's cwd (review r1, item 4), not the project
    root, since a relative path in a tool call is relative to where the tool is invoked.
    Backslashes are separators on every OS here (finding path-rules-differ-between-dev-os-and-ci-os):
    on Linux `\\tmp\\p\\.claude\\rules\\kit\\x.md` would otherwise be one odd file name, not the kit file."""
    path_str = path_str.replace("\\", "/")
    if os.path.isabs(path_str) or (len(path_str) > 1 and path_str[1] == ":"):
        candidate = path_str
    else:
        candidate = os.path.join(cwd, path_str)
    return _canon(candidate)


def _in_kit_only_folder(project_root: str, resolved: str) -> bool:
    for folder in KIT_ONLY_FOLDERS:
        folder_canon = _canon(os.path.join(project_root, folder))
        if resolved == folder_canon or resolved.startswith(folder_canon + os.sep):
            return True
    return False


def check_file_tool(
    tool_input: dict, project_root: str, cwd: str, lock: dict | None
) -> tuple[str, str] | None:
    protected = protected_paths(project_root, lock)
    for key in FILE_PATH_KEYS:
        raw = tool_input.get(key)
        if isinstance(raw, str) and raw:
            resolved = _resolve_candidate(raw, cwd)
            if resolved in protected:
                kind = owner_kind(project_root, lock, resolved) or DENY_KIND_KIT
                return raw, kind
            if _in_kit_only_folder(project_root, resolved):
                return raw, DENY_KIND_KIT_FOLDER
    return None


def _protected_rel_names(project_root: str, lock: dict | None) -> list[tuple[str, str]]:
    """(rel_path_or_folder, kind) for every protected file, protected-containing folder, and the
    fixed kit-tooling folders (review r1, item 1: enumerating write verbs can never be complete,
    so this now drives a default-deny once ANY of these is named, not a verb match)."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(rel: str, kind: str) -> None:
        key = _norm_command_text(rel)
        if key in seen:
            return
        seen.add(key)
        out.append((rel, kind))

    add(LOCAL_SETTINGS_REL, DENY_KIND_LOCAL_SETTINGS)
    add(LOCK_REL, DENY_KIND_KIT)
    for folder in _FIXED_PROTECTED_FOLDERS:
        add(folder, DENY_KIND_KIT)

    if lock:
        for entry in lock.get("files", []):
            if not isinstance(entry, dict):
                continue
            path = entry.get("path")
            owner = entry.get("owner")
            if isinstance(path, str) and path and owner in PROTECTED_OWNERS:
                kind = DENY_KIND_OWNER if owner == "owner" else DENY_KIND_KIT
                add(path, kind)
                for ancestor in _dir_ancestors(path):
                    add(ancestor, DENY_KIND_KIT)
    return sorted(out, key=lambda t: -len(t[0]))


def check_shell_tool(
    command: str, project_root: str, lock: dict | None, shell: str = "Bash"
) -> tuple[str, str] | None:
    if not command:
        return None

    # Bypass (review r1, item 3): valid ONLY as a leading inline assignment.
    if _BASH_BYPASS_LEADING_RE.match(command) or _PS_BYPASS_LEADING_RE.match(command):
        return None

    norm_command = _norm_command_text(command)
    hit = None
    for rel, kind in _protected_rel_names(project_root, lock):
        token = _norm_command_text(rel)
        if _contains_path_token(norm_command, token):
            hit = (rel, kind)
            break
    if hit is None:
        return None

    # W-046 r2: from here a protected path IS named, so an internal error must DENY, never allow.
    # (An error before this point -- bad JSON, missing lock, no project -- still fails open, as
    # main() documents: nothing is known to be protected yet.)
    try:
        return _check_named_command(command, shell, hit)
    except Exception:
        return hit


def _check_named_command(command: str, shell: str, hit: tuple[str, str]) -> tuple[str, str] | None:
    # Review round 2, item B: command substitution / process substitution can hide an arbitrary
    # write inside what otherwise looks like a read-only segment (e.g. a `cat`/`python` call whose
    # argument is `$(rm tools/pathsafe.py)`); refuse outright rather than try to parse into it.
    if "$(" in command or "`" in command or "<(" in command:
        return hit

    # W-046 r3: ANY `$` outside single quotes denies (both shells, sanctioned writers included).
    # Inert redirects are removed for THIS scan only; every other check sees the command exactly
    # as before (tightening only: nothing main denies may become allowed).
    if _expansion_hazard(_strip_inert_redirects(command, shell)):
        return hit

    # W-046: characters the guard and the shell read differently (curly quotes, NBSP, CR, ...).
    if _bad_charset(command):
        return hit

    # W-046 r2: in Bash a backslash outside single quotes escapes the next character (a quote
    # included), which _split_segments does not model: `cat \" ; rm tools/x ; echo \"` is three
    # commands to the shell and one quoted segment to the splitter. Fail closed.
    if shell != "PowerShell" and _bash_backslash_hazard(command):
        return hit

    # W-046: PowerShell runs the code inside ( ), @( ), { } and backtick escapes.
    if shell == "PowerShell" and _ps_unquoted_hazard(command):
        return hit

    # Sanctioned writer (review r1, item 2): allowed ONLY when it IS the entire command --
    # no separators, no redirects, nothing trailing (a comment or another command). Checked
    # after the rules above so a sanctioned program cannot carry a hidden sub-expression.
    if not _SEPARATOR_CHARS_RE.search(command) and _SANCTIONED_WHOLE_RE.match(command):
        return None

    # Review r1, item 1: default-deny once a protected path/folder is named, UNLESS every
    # segment of the command is provably read-only.
    segments = _split_segments(command)
    if all(_is_readonly_segment(seg, shell) for seg in segments):
        return None

    return hit


# ---------------------------------------------------------------------------
# W-041 (REQ-055 AC-1, OD-85 D1): a second, strictly narrower allow path for the Bash tool.
#
# check_shell_tool above is main's verdict, tightened only by W-046 (OD-85 D2; its denies are a
# superset of commit 43aa7d8's, proven by the W-046 differential) and NOT edited here (its source
# is pinned by a test, re-taken deliberately at W-046 round 5).
# check_shell_command takes that verdict first; a command it denies is allowed ONLY when it came
# from the Bash tool AND passes a strict simple-command grammar AND every program's shell-
# normalised words pass that program's allowlist. Anything this code cannot resolve for certain
# (an unknown program, a lexer disagreement with shlex, an unparsable loop, any exception) keeps
# main's deny. An allow is a SILENT exit 0 (never a JSON "allow", which would override other
# hooks' denies).
#
# Findings this answers: guard-matches-raw-text-not-shell-words (judge normalised words, not raw
# text), guard-matches-one-spelling-of-a-program (the program word must be a bare table name; no
# path, no extension, exact case), readonly-allowlist-runs-code-in-arguments (per-program bans on
# every flag that runs a helper or writes a file, in every spelling: prefixes, `=`, clusters).
#
# W-049 (REQ-056 AC-2) adds three more exemptions to this same narrow path, each a data table:
#   - DATA tokens ("d"): a whole-word single-quoted string, or exactly
#     "$(cat <<'WORD' <newline> body <newline> WORD <newline> )"  (quoted delimiter only; the FIRST
#     line equal to WORD ends the body; the next characters must be `)"`). Bash expands nothing in
#     either spelling, so the text reaches the program as one literal argument. A d token is accepted
#     ONLY as the value of a flag marked data-ok in _GH_WRITER_FLAGS / _GIT_COMMIT_FLAGS, and only for
#     the programs in _DATA_PROGRAMS (gh, git): `gh pr|issue create|comment|edit` and `git commit`,
#     which never write a local file by themselves. Any other d token, and any near-miss spelling of
#     either form, fails closed. Newlines stay banned everywhere outside a d token. The shlex
#     differential check runs on a skeleton where each d token is replaced by a fixed word.
#   - sed: print-only. Flags only from _SED_FLAG_LETTERS, exactly one script (_SED_SCRIPT_RE, the
#     first non-flag word), then files; any later word starting with "-" is refused.
#   - a leading `cd <one plain dir> &&` (_CD_PREFIX_OPS); the rest must pass the existing rules.
#
# W-051 (REQ-057 AC-2) adds three more, same path, each a data table:
#   - generator regenerates (_GENERATOR_RUNS / _GENERATOR_PROGRAMS): the WHOLE command is
#     `python tools/<generator> <dir> [exact trailing words]`, plain words only, run from a folder
#     holding a lock file; <dir> is `.` or one plain absolute path to a folder holding a lock file,
#     not inside a protected folder of either project (_GENERATOR_DIR_BANNED_FOLDERS);
#   - `cd <dir> && X` (_cd_kit_tool_allows): <dir> is absolute or starts with `.` (no CDPATH lookup)
#     and holds a lock file; X is ONE `python tools/<name>.py ...` run that main's read-only kit tool
#     rule allows, judged against the current project's lock AND the cd target's, or X is the
#     generator shape with `.` meaning the cd target; nothing may follow X; never an always-writer;
#   - a bare flag word (_BARE_FLAG_RE) is not a path mention: allowed when every protected-name
#     mention in the command is such a word (main would see no protected path without them).
# Known gap (W-051, main's too): a short flag with a glued value (`tar -Ctools`) is not seen as a
# mention by main's name match, so main already allows it; this path adds nothing there.
#
# KNOWN GAPS (out of scope by the W-041 threat model; reported, not defended here):
#   - a `git commit` runs the project's own git hooks (pre-commit, commit-msg, ...) and, for
#     `gh pr create`, a push runs pre-push: a hook is code the repo owner chose, outside this text;
#   - the heredoc form assumes bash 5.x (Git Bash) parses a quoted heredoc inside $( ) as a real
#     command; very old bash (3.2) does not and is not a supported shell here;
#   - a git config key that names a program (core.fsmonitor, diff/filter drivers,
#     remote.<name>.uploadpack, core.sshCommand, gpg.program, core.pager) is run by an
#     allowlisted git subcommand without appearing in the command text;
#   - shell rc aliases/functions (the Bash tool's shell is assumed to run no user rc that
#     redefines cat, git, ...);
#   - zsh as the Bash tool's shell: the grammar is proven against bash / Git Bash only;
#   - writes that name no kit path at all (issue 119);
#   - a launched owner script (-File, outside every kit root) receives relative arguments such
#     as `.`; what that owner script does with them is the owner's script's business.
# ---------------------------------------------------------------------------
import shlex as _shlex

_SIMPLE_WORD_CHARS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_./:@%+=,~*-"
)
# Inside quotes: printable ASCII except the characters that expand or escape inside quotes,
# and both quote characters.
_SIMPLE_QUOTED_BANNED = frozenset("$`\\!\"'")
_SIMPLE_REDIRECTS = {
    "2>/dev/null": ["2", ">", "/dev/null"],
    ">/dev/null": [">", "/dev/null"],
    "2>&1": ["2", ">&", "1"],
}
_SIMPLE_LIST_OPS = ("&&", "||", ";")
_SIMPLE_VAR_RE = re.compile(r"^[a-z][a-z0-9_]*$")
# A glob word must start with a literal folder: its text before the first star holds a slash,
# and it starts with a letter, digit, underscore, dot or tilde (never a dash).
_SIMPLE_GLOB_PREFIX_RE = re.compile(r"^[A-Za-z0-9_.~][^*]*/")

# Per-program allowlist (anything not a key of _PROGRAM_RULES is not allowed). Bans are data so a
# mutation test can remove each one and show an attack test going red.
_SIMPLE_ANY_ARGS = {"cat", "head", "tail", "wc", "ls", "cmp", "diff"}
_GREP_BANNED_SHORT = "f"
_GREP_BANNED_LONG = ("file",)
_RG_BANNED_SHORT = "z"
_RG_BANNED_LONG = ("pre", "pre-glob", "hostname-bin", "search-zip")
_SORT_BANNED_SHORT = "oT"
_SORT_BANNED_LONG = ("output", "compress-program", "temporary-directory")
_UNIQ_MAX_POSITIONALS = 1
_GIT_SUBCOMMANDS = {
    "status", "log", "show", "diff", "ls-files", "blame", "rev-parse", "merge-base",
    "ls-remote", "cat-file",
}
_GIT_BANNED_LONG = ("ext-diff", "textconv", "output", "filters", "upload-pack", "exec")
# W-046 round 5 merge: REQ-055 AC-6 bans git `-c` in every spelling (`-ccore.x=y`, `-nc`); main's
# verdict denies it, so this allow path must not re-allow it after the subcommand either.
_GIT_BANNED_SHORT = "c"
_GIT_LS_REMOTE_FLAGS = {
    "--heads", "--tags", "--refs", "-q", "--quiet", "--exit-code", "--get-url", "--symref",
    "-h", "-t", "-b", "--branches",
}
_GIT_LS_REMOTE_SORT_RE = re.compile(r"^--sort=[A-Za-z0-9:_-]+$")
_GIT_REMOTE_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_GIT_CAT_FILE_FLAGS = {"-t", "-s", "-p", "-e"}
_GH_GROUPS = {"issue", "pr", "run", "repo"}
_GH_ACTIONS = {"view", "list"}
_GH_REPO_VALUE_RE = re.compile(
    r"^(?:[A-Za-z0-9][A-Za-z0-9.-]*/)?[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*$"
)
# W-051 (REQ-057 AC-2): the generator regenerates a project is told to run. Generalises the old
# findings-index special case (`python tools/build_findings_index.py .`). The whole command must be
# `<program> tools/<name> <dir> <exact trailing words>`, every token a plain word, run from a folder
# holding a lock file; <dir> is `.` or one plain absolute path to a folder holding a lock file, not
# inside a protected folder of either project. Data tables, so a mutation test can loosen each one.
_GENERATOR_PROGRAMS = ("python",)
_GENERATOR_RUNS = {  # tool file -> the exact words that must follow the directory argument
    "build_spec_digest.py": (),
    "build_spec_index.py": (),
    "build_order.py": (),
    "build_findings_index.py": (),
    "trace_check.py": ("--write-view",),
}
_GENERATOR_DIR_BANNED_FOLDERS = KIT_ONLY_FOLDERS + _FIXED_PROTECTED_FOLDERS
# W-051: a bare flag word (one or two dashes, then only letters, digits and dashes) is not a path
# mention. Main's name match needs a non-alphanumeric character before a protected name, so inside
# such a word a name can only follow a dash: a glued short-flag value (`-Ctools`) is never matched
# here (main does not see it either), and a word with `=`, `/`, `\`, `.` keeps today's verdict.
_BARE_FLAG_RE = re.compile(r"^--?[A-Za-z0-9][A-Za-z0-9-]*\Z")
# W-051: a kit tool run after a leading `cd <dir> &&`: the program words and the tool word shape.
_CD_TOOL_PROGRAMS = ("python", "python3", "py")
_CD_TOOL_WORD_RE = re.compile(r"^tools/[A-Za-z0-9_][A-Za-z0-9_.-]*\.py\Z")
_LAUNCHER_PROGRAMS = {"powershell", "pwsh"}
_LAUNCHER_FLAG_NOVALUE = {"-noprofile"}
_LAUNCHER_FLAG_VALUE = {"-executionpolicy"}
_LAUNCHER_VALUE_RE = re.compile(r"^[A-Za-z]+$")
_LAUNCHER_ARG_BANNED_PREFIXES = ("-c", "-e")

# W-049 tables. Every exemption below is data so a mutation test can loosen each one.
_DATA_PLACEHOLDER = "DATA"
_HEREDOC_OPEN = "\"$(cat <<'"
_HEREDOC_WORD_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\Z")
_AFTER_WORD_CHARS = " ;|&"
# Programs that may receive a d token (and only inside their writer flag tables below).
_DATA_PROGRAMS = {"gh", "git"}
_SED_FLAG_LETTERS = "nEr"
_SED_SCRIPT_RE = re.compile(r"^[0-9]+(,[0-9]+)?p\Z")
_CD_PROGRAM = "cd"
_CD_PREFIX_OPS = ("&&",)
_GH_WRITER_ACTIONS = {
    "pr": {"create", "comment", "edit"},
    "issue": {"create", "comment", "edit"},
}
# flag -> (canonical name, takes a value, a d token may be the value)
_GH_WRITER_FLAGS = {
    "-t": ("title", True, True), "--title": ("title", True, True),
    "-b": ("body", True, True), "--body": ("body", True, True),
    "-B": ("base", True, False), "--base": ("base", True, False),
    "-H": ("head", True, False), "--head": ("head", True, False),
    "-d": ("draft", False, False), "--draft": ("draft", False, False),
    "-l": ("label", True, False), "--label": ("label", True, False),
    "-a": ("assignee", True, False), "--assignee": ("assignee", True, False),
    "--add-label": ("label", True, False), "--remove-label": ("label", True, False),
    "-R": ("repo", True, False), "--repo": ("repo", True, False),
    "--fill": ("fill", False, False),
}
_GH_WRITER_POSITIONAL_RE = re.compile(r"^[0-9]+\Z")
_GH_WRITER_POSITIONALS = {"create": 0, "comment": 1, "edit": 1}
_GIT_COMMIT_FLAGS = {
    "-m": ("message", True, True), "--message": ("message", True, True),
    "-q": ("quiet", False, False), "--quiet": ("quiet", False, False),
    "-s": ("signoff", False, False), "--signoff": ("signoff", False, False),
}


class _SimpleFail(Exception):
    """Any shape the grammar cannot resolve for certain: the caller keeps main's deny."""


def _check_plain_word(word: str) -> None:
    for k, c in enumerate(word):
        if c == "~":
            if k == 0:
                if not (word == "~" or word.startswith("~/")):
                    raise _SimpleFail("~user or ~+ / ~- expansion")
            elif not word[k - 1].isalnum():
                raise _SimpleFail("~ after = or : expands in bash")
    if "*" in word and not _SIMPLE_GLOB_PREFIX_RE.match(word):
        raise _SimpleFail("glob without a literal dir/ prefix")


# Round 3 (independent review): this lexer reads a Python str, bash reads bytes after its reader
# drops NUL (and MSYS drops CR), so a delimiter split by such a character is `EOF)` to bash and
# `E?OF)` to us. One whitelist on the WHOLE command, before any token is cut: every character is
# printable (str.isprintable) or in _DATA_EXTRA_CHARS. Tab and newline stay legal here, but the
# grammar still refuses them outside a data token.
_DATA_EXTRA_CHARS = "\t\n"


def _command_chars_ok(command: str) -> bool:
    return all(c.isprintable() or c in _DATA_EXTRA_CHARS for c in command)


def _q_body_ok(body: str) -> bool:
    return all(" " <= c <= "~" and c not in _SIMPLE_QUOTED_BANNED for c in body)


def _delimiter_ends_line(command: str, q: int) -> bool:
    """The closing quote of the delimiter word is followed by a newline and nothing else."""
    return command[q + 1:q + 2] == "\n"


def _close_paren_follows(command: str, nl: int) -> bool:
    """The delimiter line is followed (after its newline) by the lone `)"`."""
    return nl != -1 and command.startswith(')"', nl + 1)


def _line_names_delimiter(line: str, word: str) -> bool:
    """A body line that contains the delimiter word anywhere: bash and this lexer may disagree on
    where the heredoc ends, so refuse (stricter than bash's own rule)."""
    return word in line


def _scan_heredoc(command: str, i: int) -> tuple[str, int]:
    """The one heredoc data spelling, starting at command[i]: -> (body, index after the closing
    `)"`). Anything else that looks like it raises _SimpleFail."""
    k = i + len(_HEREDOC_OPEN)
    q = command.find("'", k)
    if q == -1:
        raise _SimpleFail("heredoc delimiter not closed")
    word = command[k:q]
    if not word or not _HEREDOC_WORD_RE.match(word):
        raise _SimpleFail("heredoc delimiter shape")
    if not _delimiter_ends_line(command, q):
        raise _SimpleFail("text after the heredoc delimiter")
    start = pos = q + 2
    while True:
        nl = command.find("\n", pos)
        line = command[pos:] if nl == -1 else command[pos:nl]
        if line == word:
            if not _close_paren_follows(command, nl):
                raise _SimpleFail("heredoc not closed by a lone )\"")
            return command[start:pos], nl + 3
        if _line_names_delimiter(line, word):
            # bash 5.2 inside $( ) ends a heredoc at `EOF)`, `EOF )`, `EOF;)` and runs the rest
            raise _SimpleFail("a body line contains the delimiter")
        if nl == -1:
            raise _SimpleFail("heredoc not closed")
        pos = nl + 1


def _simple_lex(command: str) -> list[tuple[str, str]]:
    """Tokens of a command in the strict grammar: ("w", text) plain word, ("q", text) quoted
    word, ("v", name) a `"$name"` word, ("d", text) a data word, ("op", op), ("r", redirect).
    Raises _SimpleFail."""
    return _simple_lex_skeleton(command)[0]


def _simple_skeleton(command: str) -> str:
    """The command text with every d token replaced by one fixed word (for the shlex check)."""
    return _simple_lex_skeleton(command)[1]


def _simple_lex_skeleton(command: str) -> tuple[list[tuple[str, str]], str]:
    if not _command_chars_ok(command):
        raise _SimpleFail("a character outside the printable whitelist")
    spans: list[tuple[int, int]] = []
    toks: list[tuple[str, str]] = []
    n = len(command)
    i = 0
    while i < n:
        ch = command[i]
        if ch == " ":
            i += 1
            continue
        at_word_start = i == 0 or command[i - 1] == " "
        redirect = None
        if at_word_start:
            for red in _SIMPLE_REDIRECTS:
                if command.startswith(red, i):
                    redirect = red
                    break
        if redirect is not None:
            end = i + len(redirect)
            if end < n and command[end] not in " ;|&":
                raise _SimpleFail("redirect glued to a word")
            toks.append(("r", redirect))
            i = end
            continue
        if command.startswith("&&", i) or command.startswith("||", i):
            toks.append(("op", command[i:i + 2]))
            i += 2
            continue
        if ch in "|;":
            toks.append(("op", ch))
            i += 1
            continue
        if ch in "&<>":
            raise _SimpleFail("lone & or an unlisted redirect")
        if ch in "\"'":
            if not at_word_start:
                raise _SimpleFail("quote inside a word")
            if ch == '"' and command.startswith('"$(', i):
                if not command.startswith(_HEREDOC_OPEN, i):
                    raise _SimpleFail("command substitution")
                body, end = _scan_heredoc(command, i)
                if end < n and command[end] not in _AFTER_WORD_CHARS:
                    raise _SimpleFail("heredoc data not a whole word")
                toks.append(("d", body))
                spans.append((i, end))
                i = end
                continue
            close = command.find(ch, i + 1)
            if close == -1:
                raise _SimpleFail("unterminated quote")
            body = command[i + 1:close]
            if close + 1 < n and command[close + 1] not in _AFTER_WORD_CHARS:
                raise _SimpleFail("quote not around a whole word")
            if ch == "'" and body and not _q_body_ok(body):
                toks.append(("d", body))
                spans.append((i, close + 1))
            elif ch == '"' and body.startswith("$") and _SIMPLE_VAR_RE.match(body[1:]):
                toks.append(("v", body[1:]))
            else:
                if not body:
                    raise _SimpleFail("empty quoted word")
                for c in body:
                    if not (" " <= c <= "~") or c in _SIMPLE_QUOTED_BANNED:
                        raise _SimpleFail("banned character inside quotes")
                toks.append(("q", body))
            i = close + 1
            continue
        j = i
        while j < n and command[j] not in " ;|&<>":
            c = command[j]
            if c in "\"'":
                raise _SimpleFail("quote inside a word")
            if c not in _SIMPLE_WORD_CHARS:
                raise _SimpleFail("character outside the grammar")
            j += 1
        word = command[i:j]
        _check_plain_word(word)
        toks.append(("w", word))
        i = j
    parts: list[str] = []
    last = 0
    for a, b in spans:
        parts.append(command[last:a])
        parts.append(_DATA_PLACEHOLDER)
        last = b
    parts.append(command[last:])
    return toks, "".join(parts)


def _shlex_expected(toks: list[tuple[str, str]]) -> list[str]:
    out: list[str] = []
    for kind, text in toks:
        if kind == "r":
            out.extend(_SIMPLE_REDIRECTS[text])
        elif kind == "v":
            out.append("$" + text)
        elif kind == "d":
            out.append(_DATA_PLACEHOLDER)
        else:
            out.append(text)
    return out


def _parse_pipeline(toks, var):
    """-> list of simple commands. `var` = (name, (kind, text)) substitutes `"$name"`."""
    cmds: list[list[tuple[str, str]]] = []
    cur: list[tuple[str, str]] = []
    for kind, text in list(toks) + [("op", "|")]:
        if kind == "op":
            if text != "|" or not cur:
                raise _SimpleFail("empty pipeline stage or a list operator inside a pipeline")
            cmds.append(cur)
            cur = []
            continue
        if kind == "v":
            if var is None or text != var[0] or not cur:
                raise _SimpleFail("a variable outside its loop, or as the program word")
            cur.append(var[1])
            continue
        if kind == "r" and not cur:
            raise _SimpleFail("redirect before the program word")
        cur.append((kind, text))
    return cmds


def _parse_loop(toks, i):
    """`for V in <words>; do <pipeline>; done` -> (next index, [pipeline per loop word])."""
    n = len(toks)
    if i + 3 >= n or toks[i + 1][0] != "w" or toks[i + 2] != ("w", "in"):
        raise _SimpleFail("not a for V in ... loop")
    name = toks[i + 1][1]
    if not _SIMPLE_VAR_RE.match(name):
        raise _SimpleFail("loop variable name")
    j = i + 3
    words = []
    while j < n and toks[j][0] in ("w", "q"):
        words.append(toks[j])
        j += 1
    if not words or j + 1 >= n or toks[j] != ("op", ";") or toks[j + 1] != ("w", "do"):
        raise _SimpleFail("loop header")
    k = j + 2
    body_start = k
    while k < n and toks[k] != ("op", ";"):
        if toks[k][0] == "op" and toks[k][1] != "|":
            raise _SimpleFail("loop body is not one pipeline")
        k += 1
    if k + 1 >= n or toks[k + 1] != ("w", "done"):
        raise _SimpleFail("loop not closed by ; done")
    body = toks[body_start:k]
    if not body:
        raise _SimpleFail("empty loop body")
    runs = [_parse_pipeline(body, (name, w)) for w in words]
    return k + 2, runs


def _simple_parse(command: str):
    """Parse a command into segments; each segment is a list of simple commands (one pipeline,
    or a for-loop body substituted once per loop word). A simple command is a list of
    ("w"|"q"|"r", text). None = not in the grammar (fail closed)."""
    try:
        if not command:
            return None
        toks = _simple_lex(command)
        if not toks:
            return None
        skeleton = _simple_skeleton(command)
        if "\r" in skeleton or "\n" in skeleton:
            return None  # a newline is legal only inside a d token
        lx = _shlex.shlex(skeleton, posix=True, punctuation_chars=True)
        lx.whitespace_split = True
        if list(lx) != _shlex_expected(toks):
            return None  # our lexer and the shell-like reference disagree: fail closed
        segments = []
        i = 0
        n = len(toks)
        while True:
            if i >= n:
                return None
            if toks[i] == ("w", "for"):
                i, runs = _parse_loop(toks, i)
            else:
                j = i
                while j < n and not (toks[j][0] == "op" and toks[j][1] in _SIMPLE_LIST_OPS):
                    j += 1
                runs = [_parse_pipeline(toks[i:j], None)]
                i = j
            segments.append([cmd for run in runs for cmd in run])
            if i >= n:
                break
            if toks[i][0] != "op" or toks[i][1] not in _SIMPLE_LIST_OPS:
                return None
            i += 1
            if i >= n:
                return None  # a trailing list operator
        return segments
    except _SimpleFail:
        return None


def _short_cluster_has(word: str, letters: str) -> bool:
    return (word.startswith("-") and not word.startswith("--") and len(word) > 1
            and any(c in word[1:] for c in letters))


def _long_name(word: str) -> str | None:
    if not word.startswith("--") or word == "--":
        return None
    return word[2:].split("=", 1)[0]


def _long_banned(word: str, banned, both_ways: bool = False) -> bool:
    """A long option that IS, or is an accepted abbreviation of, a banned option."""
    name = _long_name(word)
    if not name:
        return False
    return any(b.startswith(name) or (both_ways and name.startswith(b)) for b in banned)


def _allow_grep(args):
    return not any(_short_cluster_has(a, _GREP_BANNED_SHORT) or _long_banned(a, _GREP_BANNED_LONG)
                   for a, _g in args)


def _allow_rg(args):
    return not any(_short_cluster_has(a, _RG_BANNED_SHORT)
                   or _long_banned(a, _RG_BANNED_LONG, both_ways=True) for a, _g in args)


def _allow_sort(args):
    return not any(_short_cluster_has(a, _SORT_BANNED_SHORT) or _long_banned(a, _SORT_BANNED_LONG)
                   for a, _g in args)


def _allow_uniq(args):
    positional = 0
    after_dashdash = False
    for a, glob in args:
        if after_dashdash or a == "-" or not a.startswith("-"):
            if glob:
                return False  # one glob word can expand to an INPUT and an OUTPUT file
            positional += 1
        elif a == "--":
            after_dashdash = True
    return positional <= _UNIQ_MAX_POSITIONALS


class _Data(str):
    """The text of a d token: marks a word that may stand only as a listed flag's value."""


def _flag_command_names(rest, flags, positional_max, positional_re):
    """Walk the words after `gh pr create` / `git commit`: only flags of the table (exact
    spelling; `--long=value` allowed), values w/q (d only where the table says), at most
    `positional_max` positionals matching `positional_re`. -> set of canonical flag names, or None."""
    names: set[str] = set()
    positional = 0
    k = 0
    while k < len(rest):
        a, glob = rest[k]
        if glob or isinstance(a, _Data):
            return None
        value = None
        if a in flags:
            spec = flags[a]
            if spec[1]:
                if k + 1 >= len(rest) or rest[k + 1][1]:
                    return None
                value = rest[k + 1][0]
                k += 1
        elif a.startswith("--") and "=" in a and a.split("=", 1)[0] in flags:
            name, value = a.split("=", 1)
            spec = flags[name]
            if not spec[1]:
                return None
        elif a.startswith("-"):
            return None
        else:
            positional += 1
            if positional > positional_max or not positional_re.match(a):
                return None
            k += 1
            continue
        if spec[1]:
            if isinstance(value, _Data):
                if not spec[2]:
                    return None
            elif value.startswith("-") or (spec[0] == "repo" and not _GH_REPO_VALUE_RE.match(value)):
                return None
        names.add(spec[0])
        k += 1
    return names


def _allow_sed(args):
    """Print-only sed: flags from _SED_FLAG_LETTERS, one script, then files."""
    if any(isinstance(a, _Data) for a, _g in args):
        return False
    i = 0
    while i < len(args) and args[i][0].startswith("-"):
        a = args[i][0]
        if a.startswith("--") or len(a) < 2 or any(c not in _SED_FLAG_LETTERS for c in a[1:]):
            return False
        i += 1
    if i >= len(args):
        return False
    script, script_glob = args[i]
    if script_glob or not _SED_SCRIPT_RE.match(script):
        return False
    return not any(a.startswith("-") for a, _g in args[i + 1:])


def _allow_git(args):
    if not args or isinstance(args[0][0], _Data):
        return False
    if args[0][0] == "commit":
        names = _flag_command_names(args[1:], _GIT_COMMIT_FLAGS, 0, _GH_WRITER_POSITIONAL_RE)
        return names is not None and "message" in names
    if args[0][0] not in _GIT_SUBCOMMANDS:
        return False  # nothing (no -c, -C, --exec-path, ...) before the subcommand
    if any(isinstance(a, _Data) for a, _g in args):
        return False
    sub = args[0][0]
    rest = args[1:]
    if any(_long_banned(a, _GIT_BANNED_LONG) or _short_cluster_has(a, _GIT_BANNED_SHORT)
           for a, _g in rest):
        return False
    if sub == "ls-remote":
        # Only listed no-value flags: -u / --upload-pack / --exec and -o / --server-option
        # (which takes a separate value and would shift the remote) are all refused here.
        remote_seen = False
        for a, _g in rest:
            if a.startswith("-"):
                if a not in _GIT_LS_REMOTE_FLAGS and not _GIT_LS_REMOTE_SORT_RE.match(a):
                    return False
            elif not remote_seen:
                if not _GIT_REMOTE_RE.match(a):
                    return False
                remote_seen = True
        return True
    if sub == "cat-file":
        return all(a in _GIT_CAT_FILE_FLAGS for a, _g in rest if a.startswith("-"))
    return True


def _allow_gh(args):
    if (len(args) >= 2 and not isinstance(args[0][0], _Data) and not isinstance(args[1][0], _Data)
            and args[1][0] in _GH_WRITER_ACTIONS.get(args[0][0], ())):
        names = _flag_command_names(args[2:], _GH_WRITER_FLAGS,
                                    _GH_WRITER_POSITIONALS.get(args[1][0], 0),
                                    _GH_WRITER_POSITIONAL_RE)
        return bool(names)
    if any(isinstance(a, _Data) for a, _g in args):
        return False
    if len(args) < 2 or args[0][0] not in _GH_GROUPS or args[1][0] not in _GH_ACTIONS:
        return False
    rest = [a for a, _g in args[2:]]
    k = 0
    while k < len(rest):
        a = rest[k]
        value = None
        if a in ("-R", "--repo"):
            if k + 1 >= len(rest):
                return False
            value = rest[k + 1]
            k += 1
        elif a.startswith("--repo="):
            value = a[len("--repo="):]
        elif a.startswith("-R"):
            value = a[2:]
        else:
            name = _long_name(a)
            if name and "repo".startswith(name):
                return False  # an abbreviated --repo spelling
        if value is not None and not _GH_REPO_VALUE_RE.match(value):
            return False
        k += 1
    return True


def _allow_any(args):
    return True


_PROGRAM_RULES = {
    "grep": _allow_grep,
    "rg": _allow_rg,
    "sort": _allow_sort,
    "uniq": _allow_uniq,
    "git": _allow_git,
    "gh": _allow_gh,
    "sed": _allow_sed,
}
for _p in sorted(_SIMPLE_ANY_ARGS):
    _PROGRAM_RULES[_p] = _allow_any


def _words_of(cmd):
    """Normalised (text, is_glob) of each word of a simple command, redirects dropped."""
    out = []
    for k, t in cmd:
        if k == "d":
            out.append((_Data(t), False))
        elif k in ("w", "q"):
            out.append((t, k == "w" and "*" in t))
    return out


def _program_allows(cmd) -> bool:
    if not cmd or cmd[0][0] not in ("w", "q"):
        return False
    words = _words_of(cmd)
    prog, prog_glob = words[0]
    if prog_glob:
        return False
    if prog not in _DATA_PROGRAMS and any(isinstance(w, _Data) for w, _g in words):
        return False  # a data token is accepted only by the writer programs
    rule = _PROGRAM_RULES.get(prog)
    if rule is None:
        return False
    return bool(rule(words[1:]))


# Ported from branch w-041-guard-reads (commit 6b0daf7): resolve a path word with certainty, every
# home `~` might expand to, and "outside every kit root" (cross-drive commonpath ValueError ->
# outside, never a crash or a fail-open).
_BAD_TOKEN_CHARS = frozenset("$%*?[]{}()<>|&;`!#^=\"'")
_MAX_WALK_DIRS = 2000


def _resolve_token(text: str, cwd: str | None, allow_relative: bool, allow_tilde: bool) -> str | None:
    """Canonical location of a clean path word, or None when it cannot be resolved with certainty
    (variables, globs, flag-embedded values, odd drive forms, unknown Git Bash mounts)."""
    if not text or any(c.isspace() for c in text):
        return None
    if any(c in _BAD_TOKEN_CHARS for c in text) or text[0] in "-@":
        return None
    t = text.replace("\\", "/")
    if t.startswith("~"):
        if not allow_tilde or not (t == "~" or t.startswith("~/")):
            return None
        t = os.path.expanduser(t).replace("\\", "/")
        if t.startswith("~"):
            return None
    if os.name == "nt":
        m = re.match(r"^/([A-Za-z])(?:/(.*))?$", t)
        if m:
            t = m.group(1) + ":/" + (m.group(2) or "")
        elif t.startswith("/"):
            return None  # //unc, /tmp, /home ... : a Git Bash mount we cannot map for certain
        if ":" in t and not re.match(r"^[A-Za-z]:/", t):
            return None  # d:foo, stream names, provider paths
    if not (t.startswith("/") or re.match(r"^[A-Za-z]:/", t)):
        if not allow_relative or not cwd:
            return None
        t = os.path.join(cwd, t)
    return _canon(t)


def _is_under(path: str, root: str) -> bool:
    try:
        return os.path.commonpath([path, root]) == root
    except ValueError:  # different drives: provably not under it
        return False


def _kit_root_below(directory: str) -> bool:
    """True if a kit project root may sit anywhere under `directory`. Bounded: running out of
    budget fails closed (reported as a kit root below)."""
    seen = 0
    for dirpath, _dirs, _files in os.walk(directory):
        seen += 1
        if seen > _MAX_WALK_DIRS:
            return True
        if os.path.isfile(os.path.join(dirpath, LOCK_REL)):
            return True
    return False


def _outside_every_kit_root(resolved: str, project_root: str) -> bool:
    """True only when `resolved` is provably not inside, and not an ancestor of, any kit root:
    the project root, the root found by walking up from the path to ITS OWN lock file (so a
    sibling checkout stays protected against its own root), or a root below it."""
    root = _canon(project_root)
    if _is_under(resolved, root) or _is_under(root, resolved):
        return False
    cur = resolved
    while True:
        if os.path.isfile(os.path.join(cur, LOCK_REL)):
            return False
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    if os.path.isdir(resolved) and _kit_root_below(resolved):
        return False
    return True


def _is_abs_form(text: str) -> bool:
    """Absolute (`/x`), home-shortcut (`~` or `~/x`) or drive form (`C:/x`). Nothing relative."""
    t = text.replace("\\", "/")
    return t == "~" or t.startswith("~/") or t.startswith("/") or bool(re.match(r"^[A-Za-z]:/", t))


def _home_candidates() -> list[str]:
    """Every home directory the shell might expand `~` to: HOME, USERPROFILE, HOMEDRIVE+HOMEPATH
    from the hook's own environment (unset or empty values are skipped)."""
    out: list[str] = []
    for key in ("HOME", "USERPROFILE"):
        v = os.environ.get(key)
        if v:
            out.append(v)
    hd, hp = os.environ.get("HOMEDRIVE"), os.environ.get("HOMEPATH")
    if hd and hp:
        out.append(hd + hp)
    return out


def _abs_resolutions(text: str) -> list[str]:
    """Every canonical location an absolute / `~` / drive-form plain word may name; [] when it
    cannot be resolved with certainty. `~` resolves against EVERY home candidate."""
    if not _is_abs_form(text):
        return []
    t = text.replace("\\", "/")
    if t.startswith("~"):
        homes = _home_candidates()
        if not homes:
            return []
        out: list[str] = []
        for h in homes:
            r = _resolve_token(h.replace("\\", "/") + t[1:], None, False, False)
            if r is None:
                return []
            out.append(r)
        return out
    r = _resolve_token(text, None, False, False)
    return [r] if r is not None else []


def _launcher_allows(cmd, project_root: str, lock) -> bool:
    """`powershell|pwsh [-NoProfile|-ExecutionPolicy <word>] -File <abs/~/drive path outside
    every kit root> [args]`; no argument names a protected path; never -Command."""
    if any(k in ("r", "d") for k, _t in cmd) or cmd[0][0] != "w" or cmd[0][1] not in _LAUNCHER_PROGRAMS:
        return False
    i = 1
    while i < len(cmd) and cmd[i][0] == "w" and cmd[i][1].lower() != "-file":
        f = cmd[i][1].lower()
        if f in _LAUNCHER_FLAG_NOVALUE:
            i += 1
        elif f in _LAUNCHER_FLAG_VALUE:
            if (i + 1 >= len(cmd) or cmd[i + 1][0] != "w"
                    or not _LAUNCHER_VALUE_RE.match(cmd[i + 1][1])):
                return False
            i += 2
        else:
            return False  # -Command, -EncodedCommand and anything unlisted
    if i + 1 >= len(cmd) or cmd[i][0] != "w" or cmd[i][1].lower() != "-file":
        return False
    script_kind, script = cmd[i + 1]
    if script_kind != "w" or "*" in script:
        return False  # a quoted `~` is not expanded by the shell; a glob is not one path
    resolved = _abs_resolutions(script)
    if not resolved or not all(_outside_every_kit_root(r, project_root) for r in resolved):
        return False
    names = [_norm_command_text(rel) for rel, _k in _protected_rel_names(project_root, lock)]
    for kind, text in cmd[i + 2:]:
        if kind == "w" and "*" in text:
            return False
        if text.lower().startswith(_LAUNCHER_ARG_BANNED_PREFIXES):
            return False  # no -Command / -EncodedCommand spelling anywhere, even as a script arg
        norm = _norm_command_text(text)
        if any(_contains_path_token(norm, tok) for tok in names):
            return False
        if kind == "w" and _is_abs_form(text):
            r = _abs_resolutions(text)
            if not r or not all(_outside_every_kit_root(x, project_root) for x in r):
                return False
    return True


def _cd_dir_ok(text: str) -> bool:
    return bool(text) and not text.startswith("-") and "*" not in text


def _has_cd_prefix(command: str, segments) -> bool:
    """True when the command starts `cd <one plain word> <op in _CD_PREFIX_OPS>` and more follows."""
    toks = _simple_lex(command)
    return (len(toks) >= 4 and toks[0] == ("w", _CD_PROGRAM) and toks[1][0] == "w"
            and _cd_dir_ok(toks[1][1]) and toks[2][0] == "op" and toks[2][1] in _CD_PREFIX_OPS
            and len(segments) >= 2 and segments[0] == [[toks[0], toks[1]]])


def _lock_root_dir(text: str, cwd: str | None) -> str | None:
    """Canonical directory named by `.` or one plain absolute word, when it holds a lock file at its
    root; else None. No `~`, no glob, no relative word other than `.` (fail closed)."""
    if not text or "*" in text or "~" in text:
        return None
    if text == ".":
        if not cwd:
            return None
        resolved = _canon(cwd)
    else:
        if not _is_abs_form(text):
            return None
        found = _abs_resolutions(text)
        if len(found) != 1:
            return None
        resolved = found[0]
    if not os.path.isdir(resolved) or not os.path.isfile(os.path.join(resolved, LOCK_REL)):
        return None
    return resolved


def _in_any_kit_folder(resolved: str, project_root: str) -> bool:
    """True when `resolved` sits inside (or is) a protected folder of the current project or of the
    project that contains it (the first lock found walking up from its parent)."""
    roots = [_canon(project_root)]
    cur = os.path.dirname(resolved)
    while True:
        if os.path.isfile(os.path.join(cur, LOCK_REL)):
            roots.append(_canon(cur))
            break
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    for root in roots:
        for folder in _GENERATOR_DIR_BANNED_FOLDERS:
            if _is_under(resolved, _canon(os.path.join(root, folder))):
                return True
    return False


def _generator_dir_ok(text: str, cwd: str | None, project_root: str) -> bool:
    resolved = _lock_root_dir(text, cwd)
    return resolved is not None and not _in_any_kit_folder(resolved, project_root)


def _generator_run_allows(cmd, cwd: str | None, project_root: str) -> bool:
    """W-051: `python tools/<generator> <dir> [exact trailing words]`, every token a plain word, run
    from a directory holding a lock file (so `tools/<generator>` is that project's kit tool)."""
    if not cmd or any(k != "w" for k, _t in cmd):
        return False
    words = [t for _k, t in cmd]
    if len(words) < 3 or words[0] not in _GENERATOR_PROGRAMS or not words[1].startswith("tools/"):
        return False
    trailing = _GENERATOR_RUNS.get(words[1][len("tools/"):])
    if trailing is None or tuple(words[3:]) != tuple(trailing):
        return False
    if _lock_root_dir(".", cwd) is None:
        return False  # tools/<generator> must be a lock-holding project's own kit tool
    return _generator_dir_ok(words[2], cwd, project_root)


def _cd_target(command: str, cwd: str | None):
    """(canonical cd target, the command text after `&&`) for `cd <one plain word> && <rest>`, or
    None. The target must hold a lock file at its root; CDPATH set in the hook's environment, a `~`,
    a glob or a word starting with `-` fail closed."""
    toks = _simple_lex(command)
    if (len(toks) < 4 or toks[0] != ("w", _CD_PROGRAM) or toks[1][0] != "w"
            or toks[2] != ("op", "&&") or not _cd_dir_ok(toks[1][1])):
        return None
    if os.environ.get("CDPATH"):
        return None
    word = toks[1][1]
    if "~" in word:
        return None
    if _is_abs_form(word):
        found = _abs_resolutions(word)
        target = found[0] if len(found) == 1 else None
    elif word in (".", "..") or word.startswith(("./", "../")):
        target = _resolve_token(word, cwd, True, False)  # bash never applies CDPATH to these
    else:
        return None  # `cd name` may follow CDPATH set in a shell rc the hook cannot see
    if target is None or not os.path.isdir(target) or not os.path.isfile(os.path.join(target, LOCK_REL)):
        return None
    head = command.find("&&")  # the cd word is a plain word, so the first && is the operator
    if head < 0:
        return None
    return target, command[head + 2:].strip()


def _cd_kit_tool_allows(command: str, project_root: str, lock, cwd: str | None) -> bool:
    """W-051: `cd <lock-holding dir> && X`, X ONE kit tool run (`python tools/<name>.py ...`) that
    main's guard allows on its own as a read-only kit tool run, judged against the current project's
    lock AND the cd target's lock, or X the generator shape with `.` meaning the cd target."""
    found = _cd_target(command, cwd)
    if found is None:
        return False
    target, rest = found
    segs = _simple_parse(rest)
    if not segs or len(segs) != 1 or len(segs[0]) != 1:
        return False  # nothing may follow X: no list, no pipeline, no loop
    cmd = segs[0][0]
    if len(cmd) < 2 or any(k not in ("w", "q") for k, _t in cmd):
        return False  # no redirect, no data token, no variable
    if cmd[0][0] != "w" or cmd[0][1] not in _CD_TOOL_PROGRAMS:
        return False
    if cmd[1][0] != "w" or not _CD_TOOL_WORD_RE.match(cmd[1][1]):
        return False
    if _in_any_kit_folder(target, project_root):
        return False
    if _generator_run_allows(cmd, target, project_root):
        return True
    if cmd[1][1][len("tools/"):] in _KIT_TOOLS_ALWAYS_WRITE:
        return False
    if not _is_readonly_segment(rest, "Bash"):
        return False  # main's own read-only kit tool rule (writer flags, conditional writers)
    target_lock = load_lock(target)
    if target_lock is None:
        return False
    return (check_shell_tool(rest, project_root, lock, "Bash") is None
            and check_shell_tool(rest, target, target_lock, "Bash") is None)


def _protected_word_hit(word: str, names) -> bool:
    norm = _norm_command_text(word)
    return any(_contains_path_token(norm, tok) for tok in names)


def _bare_flags_only_mention(command: str, project_root: str, lock) -> bool:
    """W-051: True when every protected-name mention in the (strict-grammar) command is a bare flag
    word. False when no word explains main's deny at all (fail closed: something else did)."""
    toks = _simple_lex(command)
    names = [_norm_command_text(rel) for rel, _k in _protected_rel_names(project_root, lock)]
    if any(any(c.isspace() for c in tok) for tok in names):
        return False  # a protected name could span words: cannot judge word by word
    mentions = [(k, t) for k, t in toks if _protected_word_hit(t, names)]
    if not mentions:
        return False
    return all(k == "w" and _BARE_FLAG_RE.match(t) for k, t in mentions)


def _simple_allows(command: str, project_root: str, lock, cwd: str | None = None) -> bool:
    """True only when the whole command is in the strict grammar and every program passes.
    `cwd` is the directory the shell runs in (the payload's cwd); None means the project root."""
    if cwd is None:
        cwd = project_root
    segments = _simple_parse(command)
    if not segments:
        return False
    if len(segments) == 1 and len(segments[0]) == 1 and not command.startswith("for "):
        # the whole-command shapes: never inside a loop, a list or a pipeline
        only = segments[0][0]
        if _generator_run_allows(only, cwd, project_root):
            return True
        if only[0][0] == "w" and only[0][1] in _LAUNCHER_PROGRAMS:
            return _launcher_allows(only, project_root, lock)
    if _bare_flags_only_mention(command, project_root, lock):
        return True  # main denied only because a bare flag word spells a protected name
    if _has_cd_prefix(command, segments):
        if len(segments) == 2 and _cd_kit_tool_allows(command, project_root, lock, cwd):
            return True
        segments = segments[1:]  # the leading cd is checked above; every later segment is not
    return all(_program_allows(cmd) for seg in segments for cmd in seg)


def check_shell_command(
    tool_name: str, command: str, project_root: str, lock: dict | None, cwd: str | None = None
) -> tuple[str, str] | None:
    """Main's verdict first; a denied command is allowed only from the Bash tool, and only when
    _simple_allows proves it (any internal error keeps the deny). W-046 merge: the tool name is
    passed on, so main's verdict applies the PowerShell-only checks to PowerShell commands."""
    hit = check_shell_tool(command, project_root, lock, tool_name)
    if hit is None:
        return None
    if tool_name != "Bash":
        return hit
    try:
        if _simple_allows(command, project_root, lock, cwd):
            return None
    except Exception:
        return hit
    return hit


OUTSIDE_NOTE = (
    "Every path this names is outside the project: use the Read and Write tools for files "
    "outside the project, not a shell command."
)


def _outside_only(command: str, project_root: str, lock) -> bool:
    """W-051 deny text: True when every word naming a protected name is an absolute (or `~`) path
    that resolves outside the project root. Any doubt -> False (the plain message)."""
    try:
        words = _shlex.split(command, posix=True)
    except Exception:
        return False
    names = [_norm_command_text(rel) for rel, _k in _protected_rel_names(project_root, lock)]
    mentions = [w for w in words if _protected_word_hit(w, names)]
    if not mentions:
        return False
    root = _canon(project_root)
    for w in mentions:
        found = _abs_resolutions(w)
        if not found or any(_is_under(r, root) for r in found):
            return False
    return True


def main() -> None:
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8", errors="replace"))
    except Exception:
        sys.exit(0)

    tool_name = payload.get("tool_name")
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}
    cwd = payload.get("cwd") or os.getcwd()

    if tool_name not in FILE_TOOLS and tool_name not in SHELL_TOOLS:
        sys.exit(0)

    try:
        project_root = find_project_root(cwd)
        if project_root is None:
            for key in FILE_PATH_KEYS:
                raw = tool_input.get(key)
                if isinstance(raw, str) and raw and os.path.isabs(raw):
                    project_root = find_project_root(os.path.dirname(raw))
                    if project_root:
                        break
        if project_root is None:
            _warn_once("no lock file found; allowing (fail open)")
            sys.exit(0)

        lock = load_lock(project_root)

        if tool_name in FILE_TOOLS:
            if os.environ.get(ALLOW_ENV) == "1":
                sys.exit(0)
            hit = check_file_tool(tool_input, project_root, cwd, lock)
            if hit:
                path_shown, kind = hit
                deny(path_shown, kind)
        elif tool_name in SHELL_TOOLS:
            command = tool_input.get("command", "") or ""
            hit = check_shell_command(tool_name, command, project_root, lock, cwd)
            if hit:
                path_shown, kind = hit
                try:
                    note = OUTSIDE_NOTE if _outside_only(command, project_root, lock) else ""
                except Exception:
                    note = ""
                deny(path_shown, kind, note)
    except SystemExit:
        raise
    except Exception:
        # Fail open ONLY for failures before a protected path is known (no lock, no project, a
        # file-tool resolve error). Once check_shell_tool has matched a protected path, its own
        # error handling returns a DENY (W-046 r2), so it never reaches here.
        sys.exit(0)

    sys.exit(0)


if __name__ == "__main__":
    main()
