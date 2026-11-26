"""Phase 7 R2 (modular-doors plan 5.7): the strategy-ownership SQL has ONE home, ``strategy_store.py``.

Spec basis: none: the spec says nothing about helper layout (searched: ownership SQL, owns). Kit C3 (structural
guarantee first): a store asks ``strategy_store.owns``; it never carries its own copy of the read. The scan matches the
SQL text whitespace-insensitively and case-insensitively, so a re-wrapped or re-cased copy is caught too. Out of scope
by shape: ``_OWNED_MANY`` (``id = ANY(:ids)``, a different read) and ``playbook_store`` (no ``deleted_at``).
"""
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.repo_scan  # reads backend source text

BACKEND = Path(__file__).resolve().parents[1] / "backend"
HOME = "strategy_store.py"
SQL = "FROM public.strategies WHERE id = :s AND user_ref = :u AND deleted_at IS NULL"


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def problems(sources: dict[str, str]) -> list[str]:
    """``sources``: file name -> text. One problem per file outside the home that holds the ownership SQL."""
    want = _squash(SQL)
    return [f"ownership SQL outside strategy_store.owns: {name}" for name, text in sorted(sources.items())
            if Path(name).name != HOME and want in _squash(text)]


def _all_sources() -> dict[str, str]:
    return {str(p.relative_to(BACKEND)): p.read_text(encoding="utf-8") for p in sorted(BACKEND.rglob("*.py"))}


def test_the_ownership_sql_lives_only_in_strategy_store():
    assert problems(_all_sources()) == []


def test_the_scan_sees_the_sql_in_its_home_and_flags_a_copy():
    # Mutation proof: the same text in the home is no problem; in another store, re-wrapped and re-cased, it is one.
    wrapped = 'text("SELECT 1 from public.strategies\n   WHERE id = :s AND user_ref = :u\n AND deleted_at is null")'
    assert problems({"ofo_app/strategy_store.py": wrapped}) == []
    assert problems({"ofo_app/strategy_pause_store.py": wrapped}) == [
        "ownership SQL outside strategy_store.owns: ofo_app/strategy_pause_store.py"]
    other = 'text("SELECT id FROM public.strategies WHERE id = ANY(:ids) AND user_ref = :u AND deleted_at IS NULL")'
    assert problems({"ofo_app/execution_plan_store.py": other}) == []
