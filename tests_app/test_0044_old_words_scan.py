"""Issue 658 (Stage B5 of the ic-e2e-paper run): the fixed "+/-2% gap" words of situation S-06 are gone from the app
outside the migrations and the seed JSON (a repository text scan, moved out of the 0044 DB test file so the
repo_scan mark covers only this scan)."""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.repo_scan


def test_old_words_are_gone_outside_migrations_and_the_seed():
    root = Path(__file__).resolve().parents[1]
    hits = []
    for base in ("backend", "frontend/src"):
        for path in (root / base).rglob("*"):
            parts = path.parts
            if (not path.is_file() or "node_modules" in parts or "alembic" in parts
                    or path.name == "system_playbooks.json" or path.suffix in {".pyc", ".png", ".ico"}):
                continue
            if "+/-2% gap" in path.read_text(encoding="utf-8", errors="ignore"):
                hits.append(str(path))
    assert hits == []
