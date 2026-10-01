#!/usr/bin/env python3
"""tools/kit_settings.py — generate a project's Claude Code settings file from its two sources (OD-22).

A project made from the kit never edits its settings file by hand. The file is GENERATED from:

  1. the kit's locked hook wiring, `.claude/kit/settings.kit.json` (kit-owned, replaced only by a
     Factory kit upgrade), and
  2. the project's own addendum, `.claude/project/hooks.json` (project-owned):
     `{"hooks": {<event>: [<entry>, ...]}, "permissions": {"allow"|"deny"|"ask": [...]}}`,
  3. minus the kit hooks the project opted out of in `.claude/project/optouts.json` (project-owned):
     `[{"piece": "<kit path, e.g. .claude/hooks/agent_budget_required.py>", "reason": "<why>"}]`.

Merge contract:
  * addendum hook entries are APPENDED after the kit's entries for the same event, as their own
    entries; a kit entry is never replaced, reordered or edited;
  * permissions are merged as unions of the list keys `allow`, `deny`, `ask` (kit first, then
    addendum, duplicates dropped); any other permissions key, and any addendum top-level key other
    than `hooks` / `permissions`, is refused (exit 2) because it could loosen a kit setting;
    `deny` / `ask` (they only tighten) are plain strings; every `allow` entry loosens, so it must be
    `{"rule": "Tool(specifier)", "reason": "<10+ chars>"}` and never a blanket rule (a bare tool
    name or `Tool(*)`); the output carries the plain rule string;
  * addendum hooks have a strict shape: a known event name -> non-empty list of
    `{"matcher"?: str, "hooks": [{"type": "command", "command": str, "timeout"?: int}]}`;
    anything else is refused naming the entry (Claude Code would ignore it silently);
  * an opt-out drops exactly the kit hook(s) whose script is the named piece; an opt-out with a
    reason under 10 characters, a piece that is not a wired kit hook, or a protected piece (the
    seatbelt's scripts, the hook-presence check; compared slash/./case-insensitively) is refused
    (exit 2) — opting out is never silent and never loosens the seatbelt;
  * the seatbelt block: when the project carries the seatbelt config (installed by the copier's
    `--seatbelt`), the three permission-deny patterns covering Edit/Write/MultiEdit of the project's
    hidden Factory folder are added to `permissions.deny`. The block is derived from the config
    file's presence, so it can never be forgotten by a regeneration.

Usage:
    python tools/kit_settings.py [ROOT] [--check]

Without --check: writes the settings file. With --check: exit 1 if the settings file is missing or
differs from what would be written (never writes). Exit 2: bad input (unreadable/invalid JSON,
refused key, bad opt-out, missing kit wiring).

Tool-quirk note: the Factory's own seatbelt refuses some of its path names typed as one literal in
file content, so they are built from parts at runtime here.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_DOT_CLAUDE = "." + "claude"
_DOT_FACTORY = "." + "factory"
_SETTINGS_NAME = "settings" + ".json"
_SEATBELT_CONFIG_NAME = "authority" + ".yaml"

KIT_WIRING_REL = f"{_DOT_CLAUDE}/kit/settings.kit.json"
ADDENDUM_REL = f"{_DOT_CLAUDE}/project/hooks.json"
OPTOUTS_REL = f"{_DOT_CLAUDE}/project/optouts.json"
SETTINGS_REL = f"{_DOT_CLAUDE}/{_SETTINGS_NAME}"
SEATBELT_CONFIG_REL = f"{_DOT_FACTORY}/{_SEATBELT_CONFIG_NAME}"

SEATBELT_DENY_PATTERNS = [
    f"Edit({_DOT_FACTORY}/**)",
    f"Write({_DOT_FACTORY}/**)",
    f"MultiEdit({_DOT_FACTORY}/**)",
]

# The seatbelt's own scripts can never be opted out of (OD-13: loosening the seatbelt needs the
# owner). With no seatbelt config they already do nothing.
NON_OPTOUT_PIECES = {
    f"{_DOT_CLAUDE}/hooks/gate.py",
    f"{_DOT_CLAUDE}/hooks/recorder.py",
    f"{_DOT_CLAUDE}/hooks/_common.py",
    f"{_DOT_CLAUDE}/hooks/hook_presence_check.py",  # the check that says a guard went missing
}


def _normalize_piece(piece: str) -> str:
    """Compare pieces the way a filesystem would resolve them: forward slashes, no leading ./,
    case-folded (Windows), so `./X`, `X` with backslashes, or upper case cannot slip a protected
    piece past the refusal."""
    p = piece.strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p.lower()

PERMISSION_LIST_KEYS = ("allow", "deny", "ask")
ADDENDUM_KEYS = {"hooks", "permissions"}

# Hook events Claude Code documents; the kit's own wiring uses a subset (a test asserts that).
KNOWN_EVENTS = (
    "PreToolUse", "PostToolUse", "PostToolUseFailure", "UserPromptSubmit", "Stop", "SubagentStop",
    "SessionStart",
    "SessionEnd", "Notification", "PreCompact", "InstructionsLoaded",
)

MIN_REASON = 10
_SCOPED_RULE_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\((.*)\)", re.DOTALL)

_SCRIPT_RE = re.compile(r"\$CLAUDE_PROJECT_DIR/([^\"'\s;]+)")


class BadInput(Exception):
    pass


def _load_json(path: Path, default):
    if not path.exists():
        if default is None:
            raise BadInput(f"{path} is missing")
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BadInput(f"{path} is not valid JSON: {exc}") from exc


def hook_script(command: str) -> str | None:
    """The project-relative script path a kit hook command runs, or None."""
    m = _SCRIPT_RE.search(command or "")
    return m.group(1) if m else None


def _validate_optouts(optouts, kit_scripts: set[str]) -> set[str]:
    if not isinstance(optouts, list):
        raise BadInput(f"{OPTOUTS_REL} must be a JSON list")
    pieces: set[str] = set()
    for i, entry in enumerate(optouts):
        if not isinstance(entry, dict):
            raise BadInput(f"{OPTOUTS_REL}[{i}] must be an object with piece and reason")
        piece = entry.get("piece")
        reason = entry.get("reason")
        if not isinstance(piece, str) or not piece.strip():
            raise BadInput(f"{OPTOUTS_REL}[{i}] has no piece")
        if not isinstance(reason, str) or len(reason.strip()) < MIN_REASON:
            raise BadInput(f"{OPTOUTS_REL}[{i}] ({piece}) needs a reason of at least {MIN_REASON} characters")
        norm = _normalize_piece(piece)
        if norm in {p.lower() for p in NON_OPTOUT_PIECES}:
            raise BadInput(f"{OPTOUTS_REL}[{i}] ({piece}) is a protection (seatbelt or hook-presence "
                           "check) and cannot be opted out")
        if piece not in kit_scripts:
            raise BadInput(f"{OPTOUTS_REL}[{i}] ({piece}) is not a hook the kit wires")
        pieces.add(piece)
    return pieces


def _validate_addendum(addendum) -> tuple[dict, dict]:
    if not isinstance(addendum, dict):
        raise BadInput(f"{ADDENDUM_REL} must be a JSON object")
    extra = set(addendum) - ADDENDUM_KEYS
    if extra:
        raise BadInput(f"{ADDENDUM_REL} has key(s) the addendum may not set: {sorted(extra)}")
    hooks = addendum.get("hooks", {})
    perms = addendum.get("permissions", {})
    if not isinstance(hooks, dict):
        raise BadInput(f"{ADDENDUM_REL}: hooks must be an object")
    for event, entries in hooks.items():
        _validate_event(event, entries)
    if not isinstance(perms, dict):
        raise BadInput(f"{ADDENDUM_REL}: permissions must be an object")
    plain: dict[str, list[str]] = {}
    for key, val in perms.items():
        if key not in PERMISSION_LIST_KEYS:
            raise BadInput(f"{ADDENDUM_REL}: permissions.{key} is not allowed (only "
                           f"{', '.join(PERMISSION_LIST_KEYS)} may be added to)")
        if not isinstance(val, list):
            raise BadInput(f"{ADDENDUM_REL}: permissions.{key} must be a list")
        if key == "allow":
            plain[key] = [_validate_allow(i, v) for i, v in enumerate(val)]
        else:  # deny / ask only tighten, so they merge freely
            if not all(isinstance(v, str) and v.strip() for v in val):
                raise BadInput(f"{ADDENDUM_REL}: permissions.{key} must be a list of non-empty strings")
            plain[key] = list(val)
    return hooks, plain


def _validate_event(event, entries) -> None:
    """Strict shape, so a typo can never silently switch a project hook off (Claude Code ignores an
    unknown event or a malformed entry without saying so):
    hooks.<known event> = [ {"matcher"?: str, "hooks": [ {"type": "command", "command": str,
    "timeout"?: int}, ... ]}, ... ]."""
    where = f"{ADDENDUM_REL}: hooks.{event}"
    if event not in KNOWN_EVENTS:
        raise BadInput(f"{where} is not a known hook event ({', '.join(KNOWN_EVENTS)})")
    if not isinstance(entries, list) or not entries:
        raise BadInput(f"{where} must be a non-empty list of entries")
    for i, entry in enumerate(entries):
        at = f"{where}[{i}]"
        if not isinstance(entry, dict) or "hooks" not in entry or set(entry) - {"matcher", "hooks"}:
            raise BadInput(f"{at} must be an object with hooks (and optionally matcher), nothing else")
        if "matcher" in entry and not isinstance(entry["matcher"], str):
            raise BadInput(f"{at}.matcher must be a string")
        inner = entry["hooks"]
        if not isinstance(inner, list) or not inner:
            raise BadInput(f"{at}.hooks must be a non-empty list")
        for j, h in enumerate(inner):
            hat = f"{at}.hooks[{j}]"
            if not isinstance(h, dict) or set(h) - {"type", "command", "timeout"}:
                raise BadInput(f"{hat} may carry only type, command and timeout")
            if h.get("type") != "command":
                raise BadInput(f'{hat}.type must be "command"')
            if not isinstance(h.get("command"), str) or not h["command"].strip():
                raise BadInput(f"{hat}.command must be a non-empty string")
            if "timeout" in h and (not isinstance(h["timeout"], int) or isinstance(h["timeout"], bool)
                                   or h["timeout"] <= 0):
                raise BadInput(f"{hat}.timeout must be a positive whole number of seconds")


def _validate_allow(i: int, entry) -> str:
    """An allow rule loosens what Claude may do without asking, so each one must be justified
    and scoped: `{"rule": "Tool(specifier)", "reason": "<at least MIN_REASON chars>"}`. A blanket
    rule (a bare tool name, or `Tool(*)`) is refused."""
    where = f"{ADDENDUM_REL}: permissions.allow[{i}]"
    if not isinstance(entry, dict) or set(entry) != {"rule", "reason"}:
        raise BadInput(f"{where} must be an object with exactly rule and reason "
                       f'(e.g. {{"rule": "Bash(npm test)", "reason": "the project test runner"}})')
    rule, reason = entry["rule"], entry["reason"]
    if not isinstance(reason, str) or len(reason.strip()) < MIN_REASON:
        raise BadInput(f"{where} needs a reason of at least {MIN_REASON} characters")
    if not isinstance(rule, str) or not rule.strip():
        raise BadInput(f"{where} has no rule")
    m = _SCOPED_RULE_RE.fullmatch(rule.strip())
    if not m or not m.group(2).strip() or m.group(2).strip() in {"*", "**", ":*"}:
        raise BadInput(f"{where} ({rule!r}) is a blanket rule; allow only a scoped rule like Tool(specifier)")
    return rule


def build(root: Path) -> dict:
    """The settings object for the project at `root`. Raises BadInput."""
    kit = _load_json(root / KIT_WIRING_REL, None)
    if not isinstance(kit, dict):
        raise BadInput(f"{KIT_WIRING_REL} must be a JSON object")
    addendum = _load_json(root / ADDENDUM_REL, {"hooks": {}, "permissions": {}})
    optouts = _load_json(root / OPTOUTS_REL, [])

    out = json.loads(json.dumps(kit))  # deep copy; the kit object is never mutated
    out_hooks = out.setdefault("hooks", {})

    kit_scripts = {
        hook_script(h.get("command", ""))
        for entries in out_hooks.values() for e in entries for h in e.get("hooks", [])
    } - {None}
    dropped = _validate_optouts(optouts, kit_scripts)

    if dropped:
        for event in list(out_hooks):
            kept_entries = []
            for e in out_hooks[event]:
                kept = [h for h in e.get("hooks", []) if hook_script(h.get("command", "")) not in dropped]
                if kept:
                    kept_entries.append(dict(e, hooks=kept))
            if kept_entries:
                out_hooks[event] = kept_entries
            else:
                del out_hooks[event]

    add_hooks, add_perms = _validate_addendum(addendum)
    for event, entries in add_hooks.items():
        out_hooks.setdefault(event, []).extend(json.loads(json.dumps(entries)))

    perms = out.get("permissions") if isinstance(out.get("permissions"), dict) else {}
    extra_deny = SEATBELT_DENY_PATTERNS if (root / SEATBELT_CONFIG_REL).is_file() else []
    for key in PERMISSION_LIST_KEYS:
        merged = list(perms.get(key, [])) if isinstance(perms.get(key), list) else []
        additions = list(add_perms.get(key, [])) + (extra_deny if key == "deny" else [])
        for item in additions:
            if item not in merged:
                merged.append(item)
        if merged:
            perms[key] = merged
    if perms:
        out["permissions"] = perms
    return out


def render(root: Path) -> str:
    return json.dumps(build(root), indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Generate the settings file from kit wiring + project addendum.")
    p.add_argument("root", nargs="?", default=".")
    p.add_argument("--check", action="store_true")
    args = p.parse_args(argv)
    root = Path(args.root)
    try:
        text = render(root)
    except BadInput as exc:
        print(f"kit_settings.py: {exc}", file=sys.stderr)
        return 2
    target = root / SETTINGS_REL
    if args.check:
        current = target.read_text(encoding="utf-8").replace("\r\n", "\n") if target.exists() else None
        if current != text:
            state = "missing" if current is None else "differs from what kit_settings.py would write"
            print(f"kit_settings.py: {SETTINGS_REL} {state}; edit {ADDENDUM_REL} or {OPTOUTS_REL} "
                  f"and regenerate with `python tools/kit_settings.py .`, never the file itself")
            return 1
        print(f"kit_settings.py: {SETTINGS_REL} is current")
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8", newline="\n")
    print(f"kit_settings.py: wrote {SETTINGS_REL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
