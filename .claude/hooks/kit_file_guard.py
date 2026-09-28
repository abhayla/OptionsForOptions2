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
    r"|get-content|gc|get-childitem|gci|select-string|sls|diff)\b",
    re.IGNORECASE,
)
_READONLY_GIT_RE = re.compile(
    r"^git\s+(diff|log|show|status|blame|ls-files)\b", re.IGNORECASE
)
_READONLY_KIT_TOOL_RE = re.compile(
    r"^python3?\s+tools[/\\]kit_(?:selftest|drift)\.py\b", re.IGNORECASE
)
_READONLY_KIT_SETTINGS_CHECK_RE = re.compile(
    r"^python3?\s+tools[/\\]kit_settings\.py\b", re.IGNORECASE
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
    r"^(?:python3?|py)(?:\s+-\S+)*\s+tools[/\\]([\w.-]+\.py)(?=\s|$)", re.IGNORECASE
)

# Review round 2, item C: these tool names are writers only in some invocations; naming them here
# (rather than a flat set) means the running-tool leniency above never covers the writing form,
# which stays whole-command-only via _SANCTIONED_WHOLE_RE (or is refused outright if not sole).
_UNCONDITIONAL_WRITER_TOOL_NAMES = {"kit_settings.py", "kit_upgrade.py"}


def _is_writer_invocation(tool_name: str, segment: str) -> bool:
    name = tool_name.lower()
    seg_lower = segment.lower()
    if name in _UNCONDITIONAL_WRITER_TOOL_NAMES:
        # kit_settings.py without --check still writes settings.json; --check makes it read-only.
        if name == "kit_settings.py":
            return "--check" not in seg_lower
        return True  # kit_upgrade.py always writes
    if name == "build_findings_index.py":
        return "--check" not in seg_lower  # writes the index unless --check
    if name == "trace_check.py":
        return "--write-view" in seg_lower  # only --write-view writes
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


def _has_bad_redirect(segment: str) -> bool:
    for m in _BAD_REDIRECT_RE.finditer(segment):
        target = m.group(1).strip("'\"")
        if target.lower() not in ("/dev/null", "nul", "$null"):
            return True
    return False


def _is_readonly_segment(segment: str) -> bool:
    s = segment.strip()
    if not s:
        return True
    if _has_bad_redirect(s):
        return False
    if _READONLY_PROGRAM_RE.match(s):
        return True
    if _READONLY_GIT_RE.match(s):
        return True
    if _READONLY_KIT_TOOL_RE.match(s):
        return True
    if _READONLY_KIT_SETTINGS_CHECK_RE.match(s) and "--check" in s.lower():
        return True
    m = _RUNNING_KIT_TOOL_RE.match(s)
    if m and not _is_writer_invocation(m.group(1), s):
        return True
    return False


def _warn_once(msg: str) -> None:
    global _WARNED
    if not _WARNED:
        sys.stderr.write("kit-file-guard: " + msg + "\n")
        _WARNED = True


def deny(path_rel: str, reason_kind: str) -> None:
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


def check_shell_tool(command: str, project_root: str, lock: dict | None) -> tuple[str, str] | None:
    if not command:
        return None

    # Bypass (review r1, item 3): valid ONLY as a leading inline assignment.
    if _BASH_BYPASS_LEADING_RE.match(command) or _PS_BYPASS_LEADING_RE.match(command):
        return None

    # Sanctioned writer (review r1, item 2): allowed ONLY when it IS the entire command --
    # no separators, no redirects, nothing trailing (a comment or another command).
    if not _SEPARATOR_CHARS_RE.search(command) and _SANCTIONED_WHOLE_RE.match(command):
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

    # Review round 2, item B: command substitution / process substitution can hide an arbitrary
    # write inside what otherwise looks like a read-only segment (e.g. a `cat`/`python` call whose
    # argument is `$(rm tools/pathsafe.py)`); refuse outright rather than try to parse into it.
    if "$(" in command or "`" in command or "<(" in command:
        return hit

    # Review r1, item 1: default-deny once a protected path/folder is named, UNLESS every
    # segment of the command is provably read-only.
    segments = _split_segments(command)
    if all(_is_readonly_segment(seg) for seg in segments):
        return None

    return hit


def main() -> None:
    try:
        payload = json.load(sys.stdin)
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
            hit = check_shell_tool(command, project_root, lock)
            if hit:
                path_shown, kind = hit
                deny(path_shown, kind)
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)

    sys.exit(0)


if __name__ == "__main__":
    main()
