"""Lane R1 (28 Nov 2026; ADR-330 (73), ADR-016 to ADR-019): the structural guard "no reader counts a record". A REAL
position's records live in ``real_action_records``; the broker's quantity and P&L are never changed by one. Only the
record store, the routes and worker that store and read records back, and the migration may name the table or the
module: no paper book, P&L, position, adjustment or tracking reader does. A source scan: no database, no broker."""
from __future__ import annotations

import pathlib

import pytest

pytestmark = pytest.mark.repo_scan

ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_no_book_or_pnl_reader_counts_a_record():
    """The guard: only the record store, the order and stop routes (which store and read back records) and the worker
    (stage 3) name the table or the module; no paper book, P&L, position, adjustment or tracking reader does."""
    allowed = {"backend/ofo_app/real_action_store.py", "backend/ofo_app/routes/paper.py",
               "backend/ofo_app/paper_limit.py", "backend/ofo_app/paper_monitor.py",
               "backend/ofo_app/routes/alerts.py", "backend/ofo_app/routes/strategies.py",
               "backend/ofo_app/routes/tracking.py", "backend/ofo_app/routes/plan_watch.py",
               "backend/ofo_app/alembic/versions/0063_position_tags.py", "backend/ofo_app/position_kind.py"}
    hits = {str(p.relative_to(ROOT)).replace("\\", "/") for p in (ROOT / "backend").rglob("*.py")
            if any(w in p.read_text(encoding="utf-8") for w in ("real_action_records", "real_action_store"))}
    assert hits <= allowed, sorted(hits - allowed)
