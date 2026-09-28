#!/usr/bin/env python3
"""pathsafe.py — shared path-confinement helper for kit tools.

Split out of ``kit_drift.py`` (M3 5b) so a kit tool that only needs path confinement (e.g.
``check_spec_refs.py``) does not have to import the whole drift checker — a project template that
ships ``check_spec_refs.py`` without ``kit_drift.py`` would otherwise crash with ImportError.
"""
from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath


def contained(base: Path, rel: str) -> Path | None:
    """Resolve `rel` against `base` and return the resolved Path only if it stays inside `base`.

    Returns None (never raises) when `rel` is not a string, is absolute (POSIX or Windows style,
    so a Windows-only absolute path like `C:/Windows/win.ini` is rejected even on a checkout where
    pathlib would treat it as relative), or resolves outside `base` (e.g. via `../..` traversal).
    A caller must never open a path this function refused."""
    if not isinstance(rel, str) or not rel:
        return None
    if PurePosixPath(rel).is_absolute() or PureWindowsPath(rel).is_absolute():
        return None
    base_resolved = base.resolve()
    candidate = (base_resolved / rel).resolve()
    try:
        candidate.relative_to(base_resolved)
    except ValueError:
        return None
    return candidate
