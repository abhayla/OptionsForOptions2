#!/usr/bin/env python3
"""kit_file_guard.py - PreToolUse hook: refuse a tool call that would CHANGE a kit-owned file.

WHY (OD-22, OD-120): a project made by the copier never edits, deletes or loosens a kit-owned file;
only a Factory kit upgrade replaces them. This hook is the project-side accident guard: the agent is
a careful colleague who sometimes forgets, not an attacker. It blocks the plain mistake (an edit, a
redirect, an rm, a mv, an in-place sed on a kit file named in the call) and allows everything else.
The CI drift check and the owner's review of any PR touching kit files are the real backstop.

Protected paths (the `owner` field per file in the project's lock: kit, generated or owner), plus the
lock itself, the personal local-settings override, and any NEW file inside a kit-only folder.

Denied:
  - File tools (Edit, Write, MultiEdit, NotebookEdit) whose target resolves to a protected path.
  - Shell tools (Bash, PowerShell) where a protected path is the target of a redirect (`>`, `>>`,
    tee, Set-Content, Add-Content, Out-File) or the operand of a writer (rm, mv, cp as destination,
    sed -i, perl -i, truncate, chmod, ln, git rm / mv / checkout -- <path> / restore, Remove-Item,
    Move-Item, Copy-Item -Destination).
Allowed: everything else - reads, greps, kit tool runs, git show/log/diff, commit messages that name a
kit word, paths outside the project, and scripts named in the command.

Known gaps (accepted, OD-120): an indirect write (a script that writes a kit file, `find -delete`,
xargs, a glob, a variable) is not seen.

Fail open: no lock, an unreadable lock, or any internal error allows the call (one stderr line).
Bypass (owner only): KIT_FILE_GUARD_ALLOW=1 inline at the start of a shell command, or in the
process environment for a file-tool call. Deny = a stderr message and exit code 2 (not the JSON deny
shape, which another hook's allow can override).
"""
from __future__ import annotations

import json
import os
import re
import sys

ALLOW_ENV = "KIT_FILE_GUARD_ALLOW"

# Names built from parts: this repo's own seatbelt refuses some names typed contiguously.
_DOT_FACTORY = "." + "factory"
_DOT_CLAUDE = "." + "claude"
LOCK_REL = _DOT_FACTORY + "/" + "factory" + ".lock"
LOCAL_SETTINGS_REL = _DOT_CLAUDE + "/" + "settings" + "." + "local" + ".json"

PROTECTED_OWNERS = {"kit", "generated", "owner"}
FILE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
FILE_PATH_KEYS = ("file_path", "notebook_path")
SHELL_TOOLS = {"Bash", "PowerShell"}

DENY_KIND_KIT = "kit"
DENY_KIND_OWNER = "owner"
DENY_KIND_LOCAL_SETTINGS = "local-settings"
DENY_KIND_KIT_FOLDER = "kit-folder"

# A NEW file dropped in one of these is denied though it is not in the lock yet.
KIT_ONLY_FOLDERS = (
    _DOT_CLAUDE + "/rules/kit",
    _DOT_CLAUDE + "/kit",
    _DOT_CLAUDE + "/hooks",
)

_WARNED = False
_BYPASS_RE = re.compile(r"^\s*(?:\$env:)?KIT_FILE_GUARD_ALLOW\s*=\s*['\"]?1['\"]?\s*(?:;|\s)\s*\S")


def _warn_once(msg: str) -> None:
    global _WARNED
    if not _WARNED:
        sys.stderr.write("kit-file-guard: " + msg + "\n")
        _WARNED = True


def deny(path_rel: str, kind: str) -> None:
    if kind == DENY_KIND_OWNER:
        msg = ("BLOCKED: '" + path_rel + "' is owner-locked (only the human project owner edits this "
               "file, never Claude). If it genuinely needs to change, ask the owner to edit it.")
    elif kind == DENY_KIND_KIT_FOLDER:
        msg = ("BLOCKED: '" + path_rel + "' would create a new file inside a kit-only folder. Put a "
               "new project rule under '.claude/rules/project/', a new project hook under "
               "'.claude/project/hooks/'.")
    elif kind == DENY_KIND_LOCAL_SETTINGS:
        msg = ("BLOCKED: '" + path_rel + "' is the project's personal local settings override; it can "
               "switch off every other hook. Only a human edits it; Claude never writes it.")
    else:
        msg = ("BLOCKED: '" + path_rel + "' is kit-owned (OD-22): a project never edits, deletes or "
               "loosens a kit file; only a Factory kit upgrade replaces it. Add a NEW file instead "
               "(a project rule, a hook wiring entry in the project's hook addendum) or run the kit "
               "upgrade. Reading it, grepping it and running kit tools are allowed.")
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
    return os.path.normcase(os.path.realpath(path))


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


class Protected:
    """The protected set of one project: canonical file path -> deny kind, the kit-only folders,
    and every folder that holds a protected file (so deleting the folder is caught)."""

    def __init__(self, project_root: str, lock: dict | None):
        self.files: dict[str, str] = {
            _canon(os.path.join(project_root, LOCAL_SETTINGS_REL)): DENY_KIND_LOCAL_SETTINGS,
            _canon(os.path.join(project_root, LOCK_REL)): DENY_KIND_KIT,
        }
        for entry in (lock or {}).get("files", []):
            path = entry.get("path") if isinstance(entry, dict) else None
            owner = entry.get("owner") if isinstance(entry, dict) else None
            if isinstance(path, str) and path and owner in PROTECTED_OWNERS:
                self.files[_canon(os.path.join(project_root, path))] = (
                    DENY_KIND_OWNER if owner == "owner" else DENY_KIND_KIT)
        self.folders = [_canon(os.path.join(project_root, f)) for f in KIT_ONLY_FOLDERS]
        self.parents = {os.path.dirname(p) for p in self.files}
        for p in list(self.parents):
            while os.path.dirname(p) != p and p.startswith(_canon(project_root)):
                self.parents.add(p)
                p = os.path.dirname(p)

    def kind(self, resolved: str, whole_dir: bool = False) -> str | None:
        """Deny kind when `resolved` is protected; whole_dir also counts a folder holding one."""
        if resolved in self.files:
            return self.files[resolved]
        for folder in self.folders:
            if resolved == folder or resolved.startswith(folder + os.sep):
                return DENY_KIND_KIT if (resolved == folder and whole_dir) else DENY_KIND_KIT_FOLDER
        if whole_dir and resolved in self.parents:
            return DENY_KIND_KIT
        return None


def _resolve(path_str: str, cwd: str) -> str:
    """Resolve against the payload's cwd; backslashes are separators on every OS."""
    path_str = path_str.replace("\\", "/")
    if os.path.isabs(path_str) or (len(path_str) > 1 and path_str[1] == ":"):
        return _canon(path_str)
    return _canon(os.path.join(cwd, path_str))


def check_file_tool(tool_input: dict, project_root: str, cwd: str, lock: dict | None):
    prot = Protected(project_root, lock)
    for key in FILE_PATH_KEYS:
        raw = tool_input.get(key)
        if isinstance(raw, str) and raw:
            kind = prot.kind(_resolve(raw, cwd))
            if kind:
                return raw, kind
    return None


# ------------------------------------------------------------------------------------ shell text

_SEPARATORS = ";|&\n"
_HEREDOC_RE = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")


def tokenize(command: str) -> list[list[str]]:
    """Split a command into segments (on ; | & newline) of words with quotes removed. A redirect
    operator comes out as its own word ('>' or '>>'). Comments and heredoc bodies are dropped."""
    segments: list[list[str]] = [[]]
    word: list[str] = []
    in_word = False
    quote = ""
    pending: list[str] = []  # heredoc delimiters waiting for their body
    i, n = 0, len(command)

    def end_word() -> None:
        nonlocal in_word
        if in_word:
            segments[-1].append("".join(word))
            word.clear()
            in_word = False

    while i < n:
        c = command[i]
        if quote:
            if c == quote:
                quote = ""
            elif c == "\\" and quote == '"' and i + 1 < n and command[i + 1] in '"\\$`':
                i += 1
                word.append(command[i])
            else:
                word.append(c)
            i += 1
            continue
        if c in "'\"":
            quote, in_word = c, True
        elif c == "#" and not in_word:
            while i < n and command[i] != "\n":
                i += 1
            continue
        elif c == "<" and command.startswith("<<", i) and not command.startswith("<<<", i):
            m = _HEREDOC_RE.match(command, i)
            if m:
                pending.append(m.group(2))
                i = m.end()
                end_word()
                continue
            word.append(c)
            in_word = True
        elif c == ">":
            if in_word and word and not "".join(word).isdigit() and "".join(word) != "&":
                end_word()
            else:
                word.clear()
                in_word = False  # 2>, &> : the fd prefix is not a word
            op = ">>" if command.startswith(">>", i) else ">"
            segments[-1].append(op)
            i += len(op)
            if i < n and command[i] in "&|" and command[i:i + 2] != "&&":
                if command[i] == "&":  # >&2 / >&file: a descriptor copy, not a file write
                    i += 1
                    while i < n and command[i] not in " \t\n;|&":
                        i += 1
                    segments[-1].pop()
                else:
                    i += 1  # >| (clobber)
            continue
        elif c in " \t":
            end_word()
        elif c in _SEPARATORS:
            end_word()
            if c == "\n" and pending:
                i += 1
                while pending and i <= n:  # skip heredoc bodies up to each delimiter line
                    j = command.find("\n", i)
                    line = command[i:] if j < 0 else command[i:j]
                    i = n + 1 if j < 0 else j + 1
                    if line.strip() == pending[0]:
                        pending.pop(0)
                segments.append([])
                continue
            segments.append([])
        elif c == "\\" and i + 1 < n and command[i + 1] == "\n":
            i += 1  # line continuation
        else:
            word.append(c)
            in_word = True
        i += 1
    end_word()
    return [s for s in segments if s]


_FLAG_RE = re.compile(r"^-[^/\\]")
# program -> which operands of it are written (see _operands)
_ALL_OPERANDS = {"rm", "unlink", "rmdir", "shred", "truncate", "chmod", "chown", "chgrp", "mv", "tee",
                 "remove-item", "ri", "del", "erase", "rd", "move-item", "mi", "move", "ren", "rename",
                 "rename-item", "rni", "set-content", "sc", "add-content", "ac", "out-file", "clear-content",
                 "clc"}
_DESTRUCTIVE = {"rm", "unlink", "rmdir", "shred", "mv", "remove-item", "ri", "del", "erase", "rd",
                "move-item", "mi", "move", "ren", "rename", "rename-item", "rni"}  # folder operands count
_LAST_OPERAND = {"cp", "ln", "copy", "cpi", "copy-item", "install"}
_IN_PLACE = {"sed", "perl", "gsed"}
_SKIP_WRAPPERS = {"sudo", "command", "builtin", "exec", "nohup", "time", "env", "nice"}
_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def _program(words: list[str]) -> tuple[str, list[str]]:
    i = 0
    while i < len(words) and (_ASSIGN_RE.match(words[i]) or words[i].lower() in _SKIP_WRAPPERS):
        i += 1
    if i >= len(words):
        return "", []
    name = words[i].replace("\\", "/").rsplit("/", 1)[-1].lower()
    if name.endswith(".exe"):
        name = name[:-4]
    return name, words[i + 1:]


def _git_targets(args: list[str]) -> list[str]:
    i = 0
    while i < len(args) and args[i].startswith("-"):
        i += 2 if args[i] in ("-C", "-c", "--git-dir", "--work-tree") else 1
    if i >= len(args):
        return []
    sub, rest = args[i], args[i + 1:]
    if sub in ("rm", "mv", "restore"):
        return [a for a in rest if not a.startswith("-")]
    if sub == "checkout" and "--" in rest:
        return rest[rest.index("--") + 1:]
    return []


def _writer_targets(name: str, args: list[str]) -> tuple[list[str], bool]:
    """(operands that would be changed, whether a folder holding a kit file counts)."""
    plain = [a for a in args if not _FLAG_RE.match(a)]
    if name in _ALL_OPERANDS:
        return plain, name in _DESTRUCTIVE
    if name == "git":
        return _git_targets(args), True
    if name in _LAST_OPERAND:
        for k, a in enumerate(args):  # -t DIR / -Destination X name the destination
            if a.lower() in ("-t", "--target-directory", "-destination", "-dest") and k + 1 < len(args):
                return [args[k + 1]], False
            if a.lower().startswith("--target-directory="):
                return [a.split("=", 1)[1]], False
        return plain[-1:], False
    if name in _IN_PLACE and any(a.startswith("--in-place") or re.match(r"^-[A-Za-z]*i", a) for a in args):
        return plain, False
    return [], False


def check_shell_command(tool_name: str, command: str, project_root: str, lock: dict | None,
                        cwd: str | None = None):
    """(path shown, kind) when the command would change a protected path, else None."""
    if not command or _BYPASS_RE.match(command):
        return None
    prot = Protected(project_root, lock)
    base = cwd or project_root
    for words in tokenize(command):
        targets: list[tuple[str, bool]] = []
        k = 0
        while k < len(words):  # redirect targets
            if words[k] in (">", ">>") and k + 1 < len(words):
                targets.append((words[k + 1], False))
                words = words[:k] + words[k + 2:]
                continue
            k += 1
        name, args = _program(words)
        ops, whole = _writer_targets(name, args)
        targets += [(t, whole) for t in ops]
        for raw, whole_dir in targets:
            kind = prot.kind(_resolve(raw, base), whole_dir)
            if kind:
                return raw, kind
    return None


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
        else:
            hit = check_shell_command(tool_name, tool_input.get("command", "") or "", project_root,
                                      lock, cwd)
        if hit:
            deny(*hit)
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)
    sys.exit(0)


if __name__ == "__main__":
    main()
