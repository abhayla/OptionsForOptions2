"""PreToolUse (Bash|PowerShell) + SubagentStop hook: when a verifier subagent stops, delete every kit write-guard
snapshot its own shell calls left on disk.

Why: the kit's verifier write-guard writes a snapshot at a verifier's PreToolUse and deletes it only in its own
PostToolUse / PostToolUseFailure. A call that ANOTHER PreToolUse hook blocks (the kit path guard, a route gate) never
reaches either, so its snapshot stays, and `verifier_inflight_gate` reads it as "a verifier call is in flight" for 15
minutes after the verifier has finished (measured 2026-10-18, GC-2g: the W-112 verifier's two blocked calls).

  PreToolUse    a verifier's shell call: the snapshot path the kit guard writes for THIS call (the kit's own
                `snap_path`, imported by file path, never re-derived here) is appended to the per-agent ledger
                <verifier-write-guard>/owners/<agent_id>.txt (the ledger records its owner, run-discipline D2).
  SubagentStop  a verifier: each ledger line that names a `<16 hex>.json` file directly inside the snap folder is
                deleted if it is still there; any other line (another folder, `..`, a link) is left alone. Then the
                ledger is deleted. A ledger that is not valid UTF-8 deletes nothing and is kept.

Only this agent's ledger is read, so a parallel verifier's live snapshot is never touched: its tool_use_ids are in
its own ledger. A verifier killed without SubagentStop leaves its snapshot; the 15-minute age rule in
verifier_inflight_gate stays the fallback. The snap folder honours OFO_VERIFIER_SNAP_DIR (verifier_inflight_gate's
`snap_dir`). Never blocks: every path, including any error of its own, exits 0.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from types import ModuleType

HOOK_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(HOOK_DIR))
KIT_GUARD = HOOK_DIR.parents[1] / ".claude" / "hooks" / "verifier_write_guard.py"
SHELL_TOOLS = {"Bash", "PowerShell"}
AGENT_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")
SNAP_NAME = re.compile(r"[0-9a-f]{16}\.json")
LEDGER_DIR = "owners"


def kit_guard() -> ModuleType:
    """The kit write-guard module, loaded read-only by file path (one home for its snapshot path formula)."""
    spec = importlib.util.spec_from_file_location("_kit_verifier_write_guard", KIT_GUARD)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {KIT_GUARD}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def ledger_path(agent_id: object) -> Path | None:
    """<verifier-write-guard>/owners/<agent_id>.txt, or None when agent_id is not a plain id."""
    from verifier_inflight_gate import snap_dir  # noqa: PLC0415

    if not isinstance(agent_id, str) or not AGENT_ID.fullmatch(agent_id):
        return None
    return snap_dir().parent / LEDGER_DIR / f"{agent_id}.txt"


def _is_verifier(kit: ModuleType, data: dict) -> bool:
    return bool(kit.is_read_only(data.get("agent_type"), kit.read_only_agents()))


def record(data: dict, kit: ModuleType) -> Path | None:
    """PreToolUse: append this call's snapshot path to the agent's ledger. Returns the ledger written, or None."""
    if data.get("tool_name") not in SHELL_TOOLS or not _is_verifier(kit, data):
        return None
    ledger = ledger_path(data.get("agent_id"))
    snap = kit.snap_path(data)
    if ledger is None or not isinstance(snap, str):
        return None
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with open(ledger, "a", encoding="utf-8") as fh:
        fh.write(snap + "\n")
    return ledger


def own_snapshot(line: str) -> Path | None:
    """The snapshot file a ledger line names, only when it is a `<16 hex>.json` regular file (not a link) directly
    inside the snap folder; else None."""
    from verifier_inflight_gate import snap_dir  # noqa: PLC0415

    p = Path(line)
    if not p.is_absolute() or not SNAP_NAME.fullmatch(p.name) or ".." in p.parts:
        return None
    if os.path.normcase(os.path.realpath(p.parent)) != os.path.normcase(os.path.realpath(snap_dir())):
        return None
    if p.is_symlink() or not p.is_file():
        return None
    return p


def clean(data: dict, kit: ModuleType) -> list[Path]:
    """SubagentStop: delete this verifier's leftover snapshots and its ledger. Returns the snapshots deleted."""
    if not _is_verifier(kit, data):
        return []
    ledger = ledger_path(data.get("agent_id"))
    if ledger is None or not ledger.is_file():
        return []
    try:
        lines = ledger.read_bytes().decode("utf-8").splitlines()
    except UnicodeDecodeError:
        return []  # corrupt: delete nothing, keep the ledger for a human
    deleted = []
    for line in lines:
        snap = own_snapshot(line.strip())
        if snap is None:
            continue
        try:
            snap.unlink()
            deleted.append(snap)
        except OSError:
            continue
    ledger.unlink(missing_ok=True)
    return deleted


def main() -> int:
    try:
        data = json.loads(sys.stdin.read())
        if not isinstance(data, dict):
            return 0
        event = data.get("hook_event_name")
        if event not in ("PreToolUse", "SubagentStop"):
            return 0
        kit = kit_guard()
        if event == "PreToolUse":
            record(data, kit)
        else:
            clean(data, kit)
    except Exception:  # noqa: BLE001 - a broken hook must never block a session or a verifier
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
