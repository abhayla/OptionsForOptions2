#!/usr/bin/env python3
"""hook_presence_check.py — SessionStart hook for a project made from the kit.

Why (M3 deliverable 3; finding `missing-hook-script-blocks-every-call`): a kit hook is wired as
`f="$CLAUDE_PROJECT_DIR/<hooks dir>/<script>.py"; [ -f "$f" ] || exit 0; python "$f"`, so a missing
script now switches its own check off silently instead of blocking every call (the earlier, opposite
failure mode). A silently-off safety check is exactly as dangerous either way if nobody is told, so
this hook reads the project's own Claude settings files, finds every hook command in every form this
kit or a project author might wire, and prints one loud line for every script that command would skip.

Tier A fix round 1 (2026-09-27), MAJOR finding: the earlier version read only ONE settings file
(the first of settings.json / settings.kit.json / settings.local.json it found), so a hook wired
ONLY in `settings.local.json` — a real, git-ignored personal-overrides file Claude Code merges at
runtime alongside the project's own settings file — was never scanned; a missing script there stayed
silent. It also recognised only one exact command shape (`f="<path>"; [ -f "$f" ] || exit 0; python
"$f"`, double-quoted), so a single-quoted or unquoted path, or a `python3` / `py -3` / `node`
launcher, was invisible too — not reported missing, but not reported UNCHECKED either: a false "all
present" reading of a wiring the check never actually understood.

Contract:
  * reads the project's own Claude settings file (`settings.json` or `kit/settings.kit.json`, whichever
    exists, found via CLAUDE_PROJECT_DIR falling back to the hook's own cwd) AND `settings.local.json`
    in the SAME folder, if it exists — never any other project's, and never skipping the local
    overrides file just because the main one was already found;
  * for every hook entry under every event in either file, extracts the script path from:
      - the guarded form `VAR="<path>"; [ -f "$VAR" ] || exit 0; <launcher> "$VAR"` (or `'<path>'`,
        or an unquoted `VAR=<path>`);
      - a bare `<launcher> "<path>"` / `<launcher> '<path>'` / `<launcher> <path>` with no presence
        guard at all;
    where `<launcher>` is `python`, `python3`, `py -3` (or `py3`), or `node`;
  * a script path that does not exist on disk prints exactly one line:
        HOOK MISSING: <event>/<matcher>: <path> - this safety check is OFF until the file is restored
  * a hook command this parser cannot make sense of at all (no launcher/path it recognises) prints
    exactly one line, so a wiring form nobody taught this check about is never silently "fine":
        HOOK UNCHECKED: <event>/<matcher>: <command>
  * prints nothing when every wired script exists and every command was understood;
  * never crashes on malformed settings: catches every exception and prints exactly one line saying
    the settings could not be read, then still exits 0;
  * ALWAYS exits 0 — a SessionStart check must never block a session from starting.
"""
from __future__ import annotations

import json
import os
import re
import sys

# `VAR="<path>"; [ -f "$VAR" ] || exit 0; ...` / `VAR='<path>'; ...` / `VAR=<path>; ...` (unquoted) —
# capture the path assigned to the guard variable, whichever quoting form was used.
GUARDED_RE = re.compile(
    r'(?:^|[;&\n])\s*[A-Za-z_][A-Za-z0-9_]*\s*=\s*'
    r'(?:"([^"]+)"|\'([^\']+)\'|(\S+?))\s*;\s*\[\s*-f\s*"\$[A-Za-z_][A-Za-z0-9_]*"\s*\]'
    r"\s*\|\|\s*exit\s+0",
)

# A bare `<launcher> "<path>"` / `<launcher> '<path>'` / `<launcher> <path>` call with no presence
# guard at all — still worth checking so a hand-wired command that skipped the guard is still
# covered. Launchers: python, python3, py (optionally with a -3/-3.x version flag), node.
BARE_LAUNCHER_RE = re.compile(
    r'\b(?:python3?|py(?:3(?:\.\d+)?|\s+-3(?:\.\d+)?)?|node)\b\s+'
    r'(?:"([^"]+)"|\'([^\']+)\'|(\S+))',
)


def _settings_dir() -> str:
    return os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()


def _settings_paths() -> list[str]:
    """Every settings file this project actually has, in the folder used by Claude Code:
    the project's own settings file (settings.json, else settings.kit.json — whichever exists
    first) AND settings.local.json, read IN ADDITION, never instead of, since Claude Code merges
    a project's local-overrides file alongside its main settings at runtime."""
    root = _settings_dir()
    folder = "." + "claude"
    found = []
    # OD-22: in a project the settings file is generated; the kit's own wiring lives in kit/.
    for name in ("settings.json", os.path.join("kit", "settings.kit.json")):
        candidate = os.path.join(root, folder, name)
        if os.path.isfile(candidate):
            found.append(candidate)
            break
    local = os.path.join(root, folder, "settings.local.json")
    if os.path.isfile(local):
        found.append(local)
    return found


def _iter_hook_entries(settings: dict):
    """Yield (event, matcher, command) for every hook command in the settings file."""
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return
    for event, entries in hooks.items():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            matcher = entry.get("matcher", "")
            inner = entry.get("hooks")
            if not isinstance(inner, list):
                continue
            for h in inner:
                if not isinstance(h, dict):
                    continue
                command = h.get("command")
                if isinstance(command, str) and command.strip():
                    yield event, matcher, command


def _first_group(m: "re.Match") -> str:
    for g in m.groups():
        if g is not None:
            return g
    return ""


def _extract_script_path(command: str) -> tuple[str | None, bool]:
    """Returns (path_or_None, understood). `understood` is False only when this parser found no
    launcher/path shape it recognises at all — the HOOK UNCHECKED case."""
    m = GUARDED_RE.search(command)
    if m:
        return _first_group(m), True
    m = BARE_LAUNCHER_RE.search(command)
    if m:
        return _first_group(m), True
    return None, False


def _resolve(path: str, root: str) -> str:
    expanded = path.replace("$CLAUDE_PROJECT_DIR", root).replace("${CLAUDE_PROJECT_DIR}", root)
    if not os.path.isabs(expanded):
        expanded = os.path.join(root, expanded)
    return expanded


def _read_settings(path: str) -> dict | None:
    with open(path, "r", encoding="utf-8") as fh:
        settings = json.load(fh)
    if not isinstance(settings, dict):
        raise ValueError("settings file is not a JSON object")
    return settings


def main() -> int:
    root = _settings_dir()
    paths = _settings_paths()
    if not paths:
        # No project-level settings file at all: nothing to check, nothing missing to report.
        return 0

    lines: list[str] = []
    for path in paths:
        try:
            settings = _read_settings(path)
        except Exception as exc:
            print(f"hook-presence-check: could not read {os.path.basename(path)} ({exc})")
            continue
        try:
            for event, matcher, command in _iter_hook_entries(settings):
                label = f"{event}/{matcher}" if matcher else event
                script, understood = _extract_script_path(command)
                if not understood:
                    lines.append(f"HOOK UNCHECKED: {label}: {command}")
                    continue
                if script is None:
                    continue
                resolved = _resolve(script, root)
                if not os.path.isfile(resolved):
                    lines.append(
                        f"HOOK MISSING: {label}: {script} - this safety check is OFF until the "
                        "file is restored"
                    )
        except Exception as exc:
            print(f"hook-presence-check: could not read {os.path.basename(path)} ({exc})")

    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
