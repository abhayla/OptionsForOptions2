"""W-124 / ADR-048: migration 0022 extends the app-role allow-list for public.user_settings, chained from its
down_revision. No database needed (REQ-087 AC-3: SELECT, INSERT and UPDATE(value) only, never DELETE)."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.repo_scan

VERSIONS = Path(__file__).resolve().parents[1] / "backend" / "ofo_app" / "alembic" / "versions"
THIS = "0022_user_settings"
PREDECESSOR = "0021_strategy_tracking"


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


def test_block_names_the_table_with_value_as_the_only_update_column_and_one_pin() -> None:
    mine = _mine()
    block = mine._block()
    assert f"to_regclass('{mine.SETTINGS}')" in block
    assert block.count(f"has_table_privilege(r.oid, '{mine.SETTINGS}', 'DELETE')") == 1
    assert block.count(f"has_table_privilege(r.oid, '{mine.SETTINGS}', 'TRUNCATE')") == 1
    assert mine.PIN in block
    assert mine.UPDATE_COLUMNS == ("value",) and "updated_at" not in mine.INSERT_COLUMNS  # the trigger stamps it
    assert "DELETE" in mine._guard_sql() and "user_ref IS DISTINCT FROM OLD.user_ref" in mine._guard_sql()


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
