"""The one table of every generated file the kit maintains (REQ-063 AC-4, W-077).

Two readers, one table: `ci_local.py --regen` rewrites each file with its regenerate command, and the merge gate
(`merge_when_green.py`) treats a table file that changed after review as bookkeeping only when its check command
passes on the git archive of the head. A file that is not in this table is never bookkeeping.

Each row: path of the generated file, the tool in tools/ that makes it, the arguments of its regenerate form and
of its check form (both run as `python tools/<tool> . <args>` from the project root), and `when`, a condition the
regenerate step applies: None (always), "findings" (only when knowledge/findings/*.json exist), "trace-view" (only
when views/trace.md exists). Stdlib only; copied byte-identically into every project's tools/.
"""
from __future__ import annotations

from typing import NamedTuple


class Generated(NamedTuple):
    path: str
    tool: str
    regen_args: tuple
    check_args: tuple
    when: str | None


GENERATED: tuple = (
    Generated("views/spec-digest.md", "build_spec_digest.py", (), ("--check",), None),
    Generated("spec/requirements/INDEX.md", "build_spec_index.py", (), ("--check",), None),
    Generated("views/build-order.md", "build_order.py", (), ("--check",), None),
    Generated("knowledge/findings/INDEX.md", "build_findings_index.py", (), ("--check",), "findings"),
    Generated("views/trace.md", "trace_check.py", ("--write-view",), ("--check-view",), "trace-view"),
)


def regen_steps() -> tuple:
    """(tool, regenerate args list, generated file, when) per row, in table order (ci_local's REGEN_STEPS form)."""
    return tuple((g.tool, list(g.regen_args), g.path, g.when) for g in GENERATED)


def paths() -> frozenset:
    return frozenset(g.path for g in GENERATED)


def row_for(path: str) -> Generated | None:
    """The row whose generated file is exactly `path`, else None (a file not in the table)."""
    for g in GENERATED:
        if g.path == path:
            return g
    return None
