"""Replay one Alembic migration's SQL inside a test transaction, wherever it sits in the chain.

The database under test is at HEAD. A test that replays migration N's downgrade directly assumes N is head and breaks
as soon as N+1 exists (0010 broke 0009's round-trip test in CI, 2026-10-10). `round_trip_sql(N)` therefore returns
the downgrade of every later migration (newest first) followed by N's downgrade, and N's upgrade followed by every
later upgrade (oldest first), so the database ends at head again.
"""
from __future__ import annotations

import functools
import importlib.util
from pathlib import Path
from types import SimpleNamespace

VERSIONS = Path(__file__).resolve().parents[1] / "backend" / "ofo_app" / "alembic" / "versions"


# Only the FINAL recorded SQL text is cached, keyed by the file name and the file's own text (and the phase), so an edit
# to the file is a cache miss. No module object or its globals is shared between recordings: a shared module keeps its
# first globals, so a later recording that sets `module.op = ...` on a cached earlier migration missed (0002 recorded,
# then 0003 -> NameError, 2026-11-13).
@functools.cache
def _recorded_text(name: str, text: str, phase: str) -> tuple[str, ...]:
    found = importlib.util.spec_from_file_location(f"ofo_replay_{name[:-3]}_{phase}", VERSIONS / name)
    migration = importlib.util.module_from_spec(found)
    found.loader.exec_module(migration)  # type: ignore[union-attr]
    out: list[str] = []
    migration.op = SimpleNamespace(execute=lambda sql, *a, **k: out.append(str(sql)))
    if hasattr(migration, "_BASE"):
        migration._BASE._app_role = lambda: "ofo_app"
    getattr(migration, phase)()
    return tuple(out)


def recorded(name: str, phase: str) -> list[str]:
    """The SQL migration `name` (a file name like '0009_minute_history.py') executes in `phase` ('upgrade' or
    'downgrade'), with the app role fixed to ofo_app."""
    return list(_recorded_text(name, (VERSIONS / name).read_text(encoding="utf-8"), phase))


def later_than(name: str) -> list[str]:
    """Migration files above `name`, oldest first."""
    return sorted(p.name for p in VERSIONS.glob("[0-9][0-9][0-9][0-9]_*.py") if p.name > name)


def own_step_sql(name: str) -> tuple[list[str], list[str]]:
    """(own_down, own_up): only the migration's own SQL; round_trip_sql also records every later migration."""
    return recorded(name, "downgrade"), recorded(name, "upgrade")


def round_trip_sql(name: str) -> tuple[list[str], list[str], list[str], list[str]]:
    """(own_down, own_up, down_to_before_name, up_back_to_head): the first two are the migration's own SQL (for
    assertions about its pre/post checks); the last two are what a round-trip test executes."""
    own_down, own_up = recorded(name, "downgrade"), recorded(name, "upgrade")
    later = later_than(name)
    down = [sql for n in reversed(later) for sql in recorded(n, "downgrade")] + own_down
    up = own_up + [sql for n in later for sql in recorded(n, "upgrade")]
    return own_down, own_up, down, up
