"""Environment for every child of the merge path (merge.py, land.py): local git grafts switched off.

Kit 1.12.0's merge gate builds a truncated pull request's file list with local git and turns off replace refs, but not
grafts. One line in the shared .git/info/grafts (any worktree can write it) cuts a commit's parents, the three-dot diff
comes back empty and the gate treats the changed files as coming from the base: RE-REVIEW NEEDED became a pass (Tier A
review of PR #546, 2026-10-25). Pointing GIT_GRAFT_FILE at a path that cannot exist makes git ignore the grafts file.
Stop-gap until the kit gate does this itself (harvest issue filed in the kit repo).
"""
from __future__ import annotations

import os
import tempfile
import uuid


def no_graft_env(base: dict[str, str] | None = None) -> dict[str, str]:
    # a fresh random directory name, never created, so no process can have planted a grafts file at this path
    absent = os.path.join(tempfile.gettempdir(), f"ofo-no-grafts-{uuid.uuid4().hex}", "grafts")
    return {**(os.environ if base is None else base), "GIT_GRAFT_FILE": absent}
