"""W-122 / ADR-048: migration 0021 extends the app-role allow-list for the two strategy tracking tables, chained from
its down_revision. No database needed (REQ-109 AC-1: the paper entry is insert-only)."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.repo_scan

VERSIONS = Path(__file__).resolve().parents[1] / "backend" / "ofo_app" / "alembic" / "versions"
THIS = "0021_strategy_tracking"
PREDECESSOR = "0020_order_book_store"
EMPTY_UPDATE_ARRAYS = 4  # no UPDATE column on either table (each array is used twice)


def _load(path: Path):
    spec = importlib.util.spec_from_file_location("ofo_chain_" + path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _mine():
    return _load(VERSIONS / f"{THIS}.py")


def _earlier_markers() -> dict[str, str]:
    out = {}
    for path in sorted(VERSIONS.glob("[0-9][0-9][0-9][0-9]_*.py")):
        if path.stem >= THIS:
            continue
        marker = getattr(_load(path), "ALLOWLIST_BLOCK_MARKER", None)
        if marker:
            out[path.stem] = marker
    return out


def test_allowlist_holds_every_earlier_block_and_its_own_exactly_once() -> None:
    mine = _mine()
    text = mine.extended_allowlist_sql()
    markers = _earlier_markers()
    assert PREDECESSOR in markers, markers
    assert {n: m for n, m in markers.items() if m not in text} == {}
    assert text.count(mine.ALLOWLIST_BLOCK_MARKER) == 1
    assert text.count("CREATE OR REPLACE FUNCTION") == 1 and "CREATE FUNCTION" not in text
    number = re.match(r"-- (\d+)\.", mine.ALLOWLIST_BLOCK_MARKER)
    assert number is not None
    assert number.group(1) not in {re.match(r"-- (\d+)\.", m).group(1) for m in markers.values()}


def test_block_names_both_tables_insert_only_with_two_pins() -> None:
    mine = _mine()
    block = mine._block()
    for table in (mine.TRACKING, mine.LEGS):
        assert f"to_regclass('{table}')" in block
        assert block.count(f"has_table_privilege(r.oid, '{table}', 'DELETE')") == 1
        assert block.count(f"has_table_privilege(r.oid, '{table}', 'TRUNCATE')") == 1
    assert {mine.TRACKING_PIN, mine.LEGS_PIN} <= {p for p in (mine.TRACKING_PIN, mine.LEGS_PIN) if p in block}
    assert mine.TRACKING_PIN != mine.LEGS_PIN
    assert block.count("ARRAY[]::TEXT[]") == EMPTY_UPDATE_ARRAYS
    assert "started_at" not in mine.TRACKING_INSERT_COLUMNS  # the database clock stamps the start


def test_a_second_block_fails_closed_and_the_predecessor_comes_from_down_revision() -> None:
    mine = _mine()
    assert mine._PREVIOUS.revision == mine.down_revision == PREDECESSOR
    original = mine.previous_allowlist_sql
    mine.previous_allowlist_sql = lambda: original() + mine.ALLOWLIST_BLOCK_MARKER
    try:
        with pytest.raises(RuntimeError):
            mine.extended_allowlist_sql()
    finally:
        mine.previous_allowlist_sql = original
    source = (VERSIONS / f"{THIS}.py").read_text(encoding="utf-8")
    assert re.findall(r"""_load\(\s*["']\d{4}_""", source) == []
    assert "op.execute(extended_allowlist_sql())" in source and "op.execute(previous_allowlist_sql())" in source
