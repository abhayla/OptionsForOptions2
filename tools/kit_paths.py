#!/usr/bin/env python3
"""Where the kit workflow lives in a project (REQ-066 AC-3, W-092).

A new project has the kit workflow at .github/workflows/ci.yml. An adopted project keeps its own ci.yml, so the kit
workflow sits beside it (kit-ci.yml) and the kit lock records that path. Every kit tool that needs the kit workflow
(ci_local, the merge gate, kit_upgrade, kit_selftest) asks this one helper; none guesses the name.

    kit_workflow_path(project) -> (path, reason)

path is a POSIX path relative to the project. reason says why: "lock" (the lock names it), "no-lock" (no lock file),
"no-entry" (the lock has no kit-owned workflow entry), "unreadable" (the lock cannot be read), "unsafe" (the lock's
path is not a workflow file under .github/workflows/), "no-git" (not inside a git work tree). Every reason other than "lock" returns the default, exactly what the tools did before.
It never returns "no workflow": a gate that cannot tell falls back to the default and so judges the default file.
Also here (REQ-066 AC-5, W-093): the one zero-records helper every kit check calls.

    zero_records_line(project) -> str | None   the one line naming what is missing, or None
    note_zero_records(project)                 prints it (stdout) when it applies

A kit project (it has spec/requirements/) with no requirement, work item or decision record is not "passing": the
check says what is missing and the next step. A folder that is not a kit project, or has any record, gets nothing.

Reads from the repository top (git rev-parse --show-toplevel), so any subfolder gives the same answer.
One lock reader (read_lock) serves kit_upgrade and this helper. PyYAML is imported lazily; without it the
lock is "unreadable" and the default is used.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

DEFAULT_WORKFLOW = ".github/workflows/ci.yml"
_LOCK_REL = "." + "factory" + "/" + "factory" + ".lock"   # the same name tools/new_project.py builds from parts
_TEMPLATE_TAIL = "/" + DEFAULT_WORKFLOW                    # a source ends with templates/project-os/.github/workflows/ci.yml
_WF_DIR = ".github/workflows/"


def lock_file(project) -> Path:
    return Path(project) / _LOCK_REL


def read_lock(lock_path):
    """THE lock reader (kit_upgrade uses it too): the lock as a dict. Raises on any failure."""
    import yaml

    with open(lock_path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def repo_top(folder):
    """The git work tree top of `folder`, or None when git cannot say."""
    try:
        cp = subprocess.run(["git", "-C", str(folder), "rev-parse", "--show-toplevel"],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    out = cp.stdout.strip()
    return Path(out) if cp.returncode == 0 and out else None


def lock_kit_workflow_entries(doc):
    """The kit-owned lock entries whose source is the template's ci.yml, as [(path, source)]."""
    out = []
    files = doc.get("files") if isinstance(doc, dict) else None
    for entry in files if isinstance(files, list) else []:
        if not isinstance(entry, dict):
            continue
        src = entry.get("source")
        if entry.get("owner") == "kit" and isinstance(src, str) and (src.endswith(_TEMPLATE_TAIL) or src == DEFAULT_WORKFLOW):
            out.append((entry.get("path"), src))
    return out


def _safe(rel):
    """The normalised path when it is a workflow file under .github/workflows/, else None."""
    if not isinstance(rel, str):
        return None
    rel = rel.replace("\\", "/")                       # normalise first, then judge
    parts = rel.split("/")
    if (not rel.startswith(_WF_DIR) or "/" in rel[len(_WF_DIR):] or ".." in parts or "" in parts or ":" in parts[0]
            or not rel.lower().endswith((".yml", ".yaml"))):
        return None
    return rel


def kit_workflow_path(project) -> tuple[str, str]:
    """(path relative to the repository top, reason). `project` may be any folder inside the work tree."""
    top = repo_top(project)
    if top is None:
        return DEFAULT_WORKFLOW, "no-git"
    lock = lock_file(top)
    if not lock.is_file():
        return DEFAULT_WORKFLOW, "no-lock"
    try:
        doc = read_lock(lock)
    except Exception:  # noqa: BLE001 - any failure to read is "unreadable", never "no workflow"
        return DEFAULT_WORKFLOW, "unreadable"
    if not isinstance(doc, dict) or not isinstance(doc.get("files"), list):
        return DEFAULT_WORKFLOW, "unreadable"            # a lock that exists but is empty or malformed
    entries = lock_kit_workflow_entries(doc)
    if not entries:
        return DEFAULT_WORKFLOW, "no-entry"
    rel = _safe(entries[0][0])
    if rel is None:
        return DEFAULT_WORKFLOW, "unsafe"
    return rel, "lock"


def kit_workflow_file(project) -> tuple[Path, str]:
    """(absolute path of the kit workflow, reason): under the repository top, or under `project` with no git."""
    rel, reason = kit_workflow_path(project)
    return (repo_top(project) or Path(project)) / rel, reason


ZERO_RECORDS_LINE = ("0 requirements, 0 work items, 0 decisions: start the spec with the intake skill "
                     "(it can start from existing code)")


def zero_records_line(project) -> "str | None":
    root = Path(project)
    if not (root / "spec" / "requirements").is_dir():
        return None
    for folder, pattern in (("spec/requirements", "REQ-*.md"), ("work", "W-*.md"), ("spec/decisions", "ADR-*.md")):
        d = root / folder
        if d.is_dir() and any(d.glob(pattern)):
            return None
    return ZERO_RECORDS_LINE


def note_zero_records(project) -> None:
    line = zero_records_line(project)
    if line:
        print(line)


def _stdio_replace() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(errors="replace")
            except (ValueError, OSError):
                pass


if __name__ == "__main__":
    _stdio_replace()
    note_zero_records(sys.argv[1] if len(sys.argv) > 1 else ".")
