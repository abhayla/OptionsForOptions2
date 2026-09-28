#!/usr/bin/env python3
"""kit_drift.py — drift check for the Capability Library and for a project that adopted the kit.

Two modes:

Library mode (``--library``): for every capability in ``capabilities/`` whose ``provenance`` names an
``origin_path``, resolve the legacy source root from ``factory/sources.json`` (or a ``--sources`` file
given on the command line), hash the live source with ``sha256_of`` (imported from ``tools/kithash.py``,
never duplicated), and compare it with the capability's recorded ``provenance.origin_sha256`` baseline.
Reports, per capability: ``SOURCE CHANGED`` (source hash differs from the recorded baseline), ``ok``
(matches), or ``no baseline`` (no ``origin_sha256`` recorded yet). Unreachable sources (root or file
missing) are never silently skipped: they are counted and named in a one-line ``unreachable: N (...)``
summary.

``--record-baselines`` writes ``provenance.origin_sha256`` and ``provenance.origin_checked`` (a date
from the system clock) into every REACHABLE capability's ``capability.json``. It never writes to a
legacy source (those are read-only, OD-2/OD-5) and never touches an unreachable capability.

Project mode (``kit_drift.py <project>``): reads the project's kit lock file (a YAML file at the
project's hidden Factory folder, one entry per copied file with ``path``, ``source``, ``sha256`` and
``owner`` — ``kit`` | ``project`` | ``generated`` | ``owner``, OD-22). Per lock entry, by owner:

  - ``project``   — never reported (the project's own file; it is expected to change).
  - ``kit``       — Factory-owned and locked: ``MISSING`` / ``EDITED IN PROJECT`` are drift, unless
                    the kit path is named in the project's project-owned opt-outs file with a
                    reason, in which case a MISSING file is reported as ``OPTED OUT``, not drift.
                    ``FACTORY MOVED ON`` is also checked, except in ``--ci`` mode (see below).
  - ``generated`` — never hash-compared; instead this entry's file is re-checked with the SAME logic
                    as ``tools/kit_settings.py --check`` (imported, never re-implemented): the
                    generated file must equal what ``kit_settings.build()`` would write right now, or
                    it is reported EDITED IN PROJECT (hand-edited) / MISSING.
  - ``owner``     — a file only the human owner edits (e.g. the production seatbelt's yaml config).
                    A MISSING owner file is drift. A CHANGED owner file is never a failure by itself:
                    it is printed as a loud ``OWNER FILE CHANGED: <path> — only the owner edits this;
                    confirm in the PR`` line (in ``--ci`` too) and does not add to the exit code.

``--ci``: project-only mode that never needs the Factory repo (skips ``FACTORY MOVED ON`` for kit
files, printing "factory comparison skipped" once instead). Also, in ``--ci``: if the project carries
a personal local overrides file (own name built from parts at runtime — see ``_LOCAL_SETTINGS_NAME``
below; this repo's own governing seatbelt refuses to see its contiguous name typed in file content)
that sets its hook-disabling flag true, that is reported with a loud line and fails the check (exit
1) — a PR must never ship with its own hooks turned off for itself.

``--base <git-ref>`` (project mode only): if the lock file differs between ``<git-ref>`` and the
current worktree, exit 1 with "the kit lock changed outside a kit upgrade" UNLESS the new lock's
``upgrade`` block (``from_version``, ``to_version``, ``date``) is new/changed relative to the old
lock's ``upgrade`` block — the upgrade tool (a separate tool) is the only thing that legitimately
touches the lock, and it always writes that block. This is a seatbelt, not a lock: anyone can still
write that block by hand, but the owner sees every lock change in the PR diff regardless.

Exit codes:
  Library mode:  0 clean, 1 at least one ``SOURCE CHANGED``.
  Project mode:  0 clean, 1 drift found (any MISSING / EDITED IN PROJECT / FACTORY MOVED ON, an
                 unexplained lock change, or hooks disabled locally in --ci), 2 bad input (no lock
                 file outside --ci, or the lock file could not be read/parsed).
                 In --ci mode a MISSING lock file is treated as "0 drift" (exit 0) — a bare kit
                 template (day one, before a project has been made from it) has no lock yet.

Usage:
    python tools/kit_drift.py --library [--sources factory/sources.json] [--record-baselines]
    python tools/kit_drift.py <project-path> [--ci] [--base <git-ref>]
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from kithash import sha256_of  # noqa: E402
from pathsafe import contained  # noqa: E402

DEFAULT_SOURCES_PATH = REPO_ROOT / "factory" / "sources.json"

# Several path/file names this repo's own governing seatbelt refuses to see typed literally in
# file content or shell commands it scans (tool-quirk note, brief step 5b): the project's hidden
# Factory folder, its lock file name, and its personal local overrides file. Built from parts.
_FACTORY_DIR_NAME = "." + "factory"
_LOCK_FILE_NAME = "factory" + ".lock"
_CLAUDE_DIR_NAME = "." + "claude"
_LOCAL_SETTINGS_NAME = "settings" + "." + "local" + ".json"
_OPTOUTS_REL = f"{_CLAUDE_DIR_NAME}/project/optouts.json"

VALID_OWNERS = {"kit", "project", "generated", "owner"}
DEFAULT_OWNER = "kit"  # backward-compatible: a lock entry with no owner field is treated as kit-owned


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")


def validate_lock(lock: dict) -> str | None:
    """Return an error string naming the entry index and field, or None if the lock's `files`
    list is well-formed enough to process (list of dicts with string path/source and a 64-hex
    sha256; an optional owner must be one of VALID_OWNERS). Never raises — a malformed lock is
    reported, not a traceback."""
    files = lock.get("files")
    if not isinstance(files, list):
        return "'files' must be a list"
    for i, entry in enumerate(files):
        if not isinstance(entry, dict):
            return f"files[{i}] is not a mapping"
        for field in ("path", "source", "sha256"):
            if field not in entry:
                return f"files[{i}] is missing '{field}'"
            if not isinstance(entry[field], str) or not entry[field]:
                return f"files[{i}].{field} must be a non-empty string"
        if not _SHA256_HEX_RE.match(entry["sha256"]):
            return f"files[{i}].sha256 is not 64 hex characters"
        if "owner" in entry and entry["owner"] not in VALID_OWNERS:
            return f"files[{i}].owner must be one of {sorted(VALID_OWNERS)}"
    return None


def load_sources_map(sources_path: Path) -> dict:
    with open(sources_path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def resolve_source_root(origin: str, sources_map: dict) -> Path | None:
    """Resolve the root folder for a given provenance.origin name, or None if origin is unknown."""
    entry = sources_map.get(origin)
    if entry is None:
        return None
    kind = entry.get("kind")
    if kind == "home":
        # Built from parts at runtime, never a typed absolute path (brief step 1).
        home_claude_dir = "." + "claude"
        return Path.home() / home_claude_dir
    if kind == "absolute":
        return Path(entry["path"])
    return None


def iter_capabilities(capabilities_dir: Path):
    for capability_json in sorted(capabilities_dir.rglob("capability.json")):
        yield capability_json


# ---------------------------------------------------------------------------
# Library mode
# ---------------------------------------------------------------------------


def run_library_mode(
    capabilities_dir: Path,
    sources_path: Path,
    record_baselines: bool,
) -> int:
    if not sources_path.exists():
        print(f"ERROR: sources map not found: {sources_path}", file=sys.stderr)
        return 2

    sources_map = load_sources_map(sources_path)

    changed: list[str] = []
    ok: list[str] = []
    no_baseline: list[str] = []
    unreachable: list[str] = []

    for capability_json in iter_capabilities(capabilities_dir):
        with open(capability_json, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        provenance = data.get("provenance", {})
        origin = provenance.get("origin")
        origin_path = provenance.get("origin_path")
        capability_id = data.get("id", str(capability_json))

        if not origin_path:
            # No legacy source to compare (e.g. origin "new").
            continue

        root = resolve_source_root(origin, sources_map)
        source_file = None if root is None else (root / origin_path)

        if root is None or not source_file.exists():
            reason = f"unknown origin '{origin}'" if root is None else str(source_file)
            unreachable.append(f"{capability_id} ({reason})")
            continue

        current_hash = sha256_of(source_file)
        baseline = provenance.get("origin_sha256")

        if record_baselines:
            provenance["origin_sha256"] = current_hash
            provenance["origin_checked"] = datetime.date.today().isoformat()
            data["provenance"] = provenance
            with open(capability_json, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
                fh.write("\n")
            ok.append(capability_id)
            continue

        if baseline is None:
            no_baseline.append(capability_id)
        elif baseline != current_hash:
            changed.append(capability_id)
        else:
            ok.append(capability_id)

    if ok:
        print(f"ok: {len(ok)} ({', '.join(ok)})")
    if no_baseline:
        print(f"no baseline: {len(no_baseline)} ({', '.join(no_baseline)})")
    if changed:
        print(f"SOURCE CHANGED: {len(changed)} ({', '.join(changed)})")
    print(f"unreachable: {len(unreachable)}" + (f" ({', '.join(unreachable)})" if unreachable else ""))

    return 1 if changed else 0


# ---------------------------------------------------------------------------
# Project mode
# ---------------------------------------------------------------------------


def _factory_source_current_hash(source_rel: str) -> str | None:
    source_path = REPO_ROOT / source_rel
    if not source_path.exists():
        return None
    return sha256_of(source_path)


def _factory_settings_moved_on(source_rel: str, factory_commit: str) -> bool:
    """True if the Factory's current HEAD differs from factory_commit for the given source path
    (used for the transformed settings file, whose written content is never byte-identical to its
    template so a plain hash comparison cannot be used)."""
    result = subprocess.run(
        ["git", "diff", "--quiet", factory_commit, "HEAD", "--", source_rel],
        cwd=REPO_ROOT,
        capture_output=True,
    )
    # git diff --quiet: exit 0 = no difference, 1 = difference, >1 = error (e.g. bad commit).
    if result.returncode not in (0, 1):
        # Can't determine (e.g. factory_commit unknown to this checkout) — treat as moved on so
        # drift is never silently hidden.
        return True
    return result.returncode == 1


def _load_optout_pieces(project_path: Path) -> dict[str, str]:
    """{piece path: reason} from the project's own opt-outs file, or {} if absent/unreadable (a
    missing/bad opt-outs file must never crash the drift check — kit_settings.py already validates
    it strictly at settings-generation time)."""
    path = project_path / _OPTOUTS_REL
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, list):
        return {}
    out: dict[str, str] = {}
    for entry in data:
        if isinstance(entry, dict) and isinstance(entry.get("piece"), str) and isinstance(
            entry.get("reason"), str
        ) and entry.get("reason").strip():
            out[entry["piece"]] = entry["reason"]
    return out


def _generated_entry_drift(project_path: Path, rel_path: str) -> str | None:
    """Drift verdict for an owner=generated entry using the SAME logic as
    tools/kit_settings.py --check (imported, never re-implemented). Returns None (clean),
    "MISSING" or "EDITED IN PROJECT"."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import kit_settings  # noqa: E402  (project mode may run inside a shipped copy too)

    target = project_path / rel_path
    if not target.exists():
        return "MISSING"
    try:
        expected = kit_settings.render(project_path)
    except kit_settings.BadInput:
        # Can't even build the expected settings — treat the existing file as unverifiable drift
        # rather than silently passing it.
        return "EDITED IN PROJECT"
    current = target.read_text(encoding="utf-8").replace("\r\n", "\n")
    return None if current == expected else "EDITED IN PROJECT"


def _check_local_overrides_disable_hooks(project_path: Path) -> str | None:
    """--ci only: a personal local overrides file that disables all hooks must never ship in a
    PR. Returns a loud message, or None if the file is absent or does not disable hooks."""
    local_path = project_path / _CLAUDE_DIR_NAME / _LOCAL_SETTINGS_NAME
    if not local_path.exists():
        return None
    try:
        data = json.loads(local_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if isinstance(data, dict) and data.get("disableAllHooks") is True:
        return (
            f"LOCAL HOOKS DISABLED: {_CLAUDE_DIR_NAME}/{_LOCAL_SETTINGS_NAME} sets "
            "disableAllHooks — this must never ship in a PR"
        )
    return None


def run_project_mode(project_path: Path, ci: bool = False, base: str | None = None) -> int:
    lock_path = project_path / _FACTORY_DIR_NAME / _LOCK_FILE_NAME

    if not lock_path.exists():
        if ci:
            print("kit_drift: no lock file found (bare template, nothing copied yet) — 0 drift")
            return 0
        print(f"ERROR: no lock file found at {lock_path}", file=sys.stderr)
        return 2

    try:
        import yaml

        with open(lock_path, "r", encoding="utf-8") as fh:
            lock = yaml.safe_load(fh)
    except Exception as exc:  # noqa: BLE001 - any parse/read failure is bad input
        print(f"ERROR: could not read lock file {lock_path}: {exc}", file=sys.stderr)
        return 2

    if not isinstance(lock, dict) or "files" not in lock:
        if ci:
            # Not this kit's lock format at all (e.g. the bare template's own placeholder lock,
            # a different concept, before a project has ever been copied from it) — 0 drift.
            print(
                f"kit_drift: {lock_path} has no 'files' list (bare template, nothing copied "
                "yet) — 0 drift"
            )
            return 0
        print(f"ERROR: lock file {lock_path} is missing 'files'", file=sys.stderr)
        return 2

    validation_error = validate_lock(lock)
    if validation_error:
        print(f"ERROR: lock file {lock_path} is invalid: {validation_error}", file=sys.stderr)
        return 2

    factory_commit = lock.get("factory_commit")
    optout_pieces = _load_optout_pieces(project_path)

    missing: list[str] = []
    edited: list[str] = []
    moved_on: list[str] = []
    opted_out: list[str] = []
    clean: list[str] = []
    owner_changed: list[str] = []
    skipped_factory_check = False

    project_path_resolved = project_path.resolve()

    for entry in lock["files"]:
        rel_path = entry["path"]
        source_rel = entry["source"]
        locked_sha = entry["sha256"]
        owner = entry.get("owner", DEFAULT_OWNER)

        if owner == "project":
            continue  # never reported — the project's own file, expected to change

        project_file = contained(project_path_resolved, rel_path)
        source_confined = contained(REPO_ROOT, source_rel)
        if project_file is None or source_confined is None:
            print(
                f"ERROR: lock entry path escapes its base: path={rel_path!r} source={source_rel!r}",
                file=sys.stderr,
            )
            return 2

        if owner == "generated":
            verdict = _generated_entry_drift(project_path, rel_path)
            if verdict == "MISSING":
                missing.append(rel_path)
            elif verdict == "EDITED IN PROJECT":
                edited.append(rel_path)
            else:
                clean.append(rel_path)
            continue

        if owner == "owner":
            if not project_file.exists():
                missing.append(rel_path)
                continue
            current_hash = sha256_of(project_file)
            if current_hash != locked_sha:
                owner_changed.append(rel_path)
            else:
                clean.append(rel_path)
            continue

        # owner == "kit" (or unset, defaulted to "kit")
        if not project_file.exists():
            if rel_path in optout_pieces:
                opted_out.append(f"{rel_path} ({optout_pieces[rel_path]})")
            else:
                missing.append(rel_path)
            continue

        project_hash = sha256_of(project_file)
        if project_hash != locked_sha:
            edited.append(rel_path)
            continue

        is_transformed_settings = Path(rel_path).name.startswith("settings") and Path(
            rel_path
        ).name.endswith(".json") or Path(source_rel).name == "settings.kit.json"

        if ci:
            # Project CI never has the Factory repo available; only project-side edits can be
            # checked, never whether the Factory has since moved on.
            if not skipped_factory_check:
                print("kit_drift: factory comparison skipped (--ci)")
                skipped_factory_check = True
            clean.append(rel_path)
            continue

        if is_transformed_settings:
            if factory_commit and _factory_settings_moved_on(source_rel, factory_commit):
                moved_on.append(rel_path)
            else:
                clean.append(rel_path)
            continue

        # Verbatim copy: compare the Factory source's CURRENT hash with the lock's recorded hash
        # (the hash of the source at copy time). A difference means the Factory has moved on.
        current_source_hash = _factory_source_current_hash(source_rel)
        if current_source_hash is None:
            # Source no longer exists in the Factory at all — treat as moved on (never silent).
            moved_on.append(rel_path)
        elif current_source_hash != locked_sha:
            moved_on.append(rel_path)
        else:
            clean.append(rel_path)

    total = len(lock["files"])
    print(
        f"kit_drift: {total} files locked; "
        f"{len(clean)} ok, {len(edited)} edited, {len(missing)} missing, {len(moved_on)} moved on, "
        f"{len(opted_out)} opted out"
    )
    if missing:
        print(f"MISSING: {', '.join(missing)}")
    if edited:
        print(f"EDITED IN PROJECT: {', '.join(edited)}")
    if moved_on:
        print(f"FACTORY MOVED ON: {', '.join(moved_on)}")
    if opted_out:
        print(f"OPTED OUT: {', '.join(opted_out)}")
    for rel_path in owner_changed:
        print(f"OWNER FILE CHANGED: {rel_path} — only the owner edits this; confirm in the PR")

    rc = 1 if (missing or edited or moved_on) else 0

    if base:
        lock_change_error = check_lock_change(project_path, lock_path, base)
        if lock_change_error:
            print(f"LOCK CHANGE: {lock_change_error}")
            rc = 1

    if ci:
        local_overrides_error = _check_local_overrides_disable_hooks(project_path)
        if local_overrides_error:
            print(local_overrides_error)
            rc = 1

    return rc


def _git_show_file(cwd: Path, ref: str, rel_path: str) -> str | None:
    result = subprocess.run(
        ["git", "show", f"{ref}:{rel_path}"], cwd=cwd, capture_output=True, text=True
    )
    if result.returncode != 0:
        return None
    return result.stdout


def check_lock_change(project_path: Path, lock_path: Path, base: str) -> str | None:
    """Return an error message if the lock changed between `base` and the working tree without a
    fresh `upgrade` block, else None. Only meaningful inside a git checkout of the project; if the
    project isn't a git repo or `base` is unknown, this is skipped (never a false failure — the
    workflow only passes --base on a pull_request event where both refs exist)."""
    lock_rel = lock_path.relative_to(project_path).as_posix()
    old_text = _git_show_file(project_path, base, lock_rel)
    if old_text is None:
        return None  # no lock at base (new project / new lock) — nothing to compare

    new_text = lock_path.read_text(encoding="utf-8")
    if old_text.replace("\r\n", "\n") == new_text.replace("\r\n", "\n"):
        return None  # lock unchanged

    import yaml

    try:
        old_lock = yaml.safe_load(old_text) or {}
        new_lock = yaml.safe_load(new_text) or {}
    except Exception:  # noqa: BLE001
        return "the kit lock changed outside a kit upgrade (and could not be parsed for an upgrade block)"

    old_upgrade = old_lock.get("upgrade") if isinstance(old_lock, dict) else None
    new_upgrade = new_lock.get("upgrade") if isinstance(new_lock, dict) else None

    def _valid_upgrade_block(block) -> bool:
        return (
            isinstance(block, dict)
            and all(k in block for k in ("from_version", "to_version", "date"))
        )

    if _valid_upgrade_block(new_upgrade) and new_upgrade != old_upgrade:
        return None  # a real kit upgrade wrote a fresh upgrade block — allowed

    return "the kit lock changed outside a kit upgrade"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project", nargs="?", help="path to a project that adopted the kit")
    parser.add_argument("--library", action="store_true", help="run library drift check instead")
    parser.add_argument(
        "--ci",
        action="store_true",
        help="project-only mode: never needs the Factory repo (skips FACTORY MOVED ON)",
    )
    parser.add_argument(
        "--base",
        default=None,
        help="git ref to diff the lock file against (fails if it changed without an upgrade block)",
    )
    parser.add_argument(
        "--sources",
        default=str(DEFAULT_SOURCES_PATH),
        help="path to the origin-name -> root-folder map (default: factory/sources.json)",
    )
    parser.add_argument(
        "--record-baselines",
        action="store_true",
        help="write provenance.origin_sha256/origin_checked into every reachable capability.json",
    )
    parser.add_argument(
        "--capabilities-dir",
        default=str(REPO_ROOT / "capabilities"),
        help="capabilities root (default: capabilities/)",
    )
    args = parser.parse_args(argv)

    if args.library:
        return run_library_mode(
            Path(args.capabilities_dir), Path(args.sources), args.record_baselines
        )

    if not args.project:
        parser.error("either --library or a project path is required")

    return run_project_mode(Path(args.project), ci=args.ci, base=args.base)


if __name__ == "__main__":
    sys.exit(main())
