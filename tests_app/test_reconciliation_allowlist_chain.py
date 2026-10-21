"""#380 step 2.1 / ADR-048: migration 0019 extends the app-role allow-list for the reconciliation store, and its closed
lists are the store's. No database needed.

Spec basis: REQ-060 AC-6 "While a mismatch is unresolved, new execution and adjustment execution are blocked (Q199).";
ADR-109 (4) (the three first resolution actions); ADR-048 (the limited application role).
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest
from ofo.reconciliation.triggers import Trigger
from ofo.strategy.definition import MAX_UNITS
from ofo_app import execution_plan_store as plans
from ofo_app import reconciliation_store as rs

pytestmark = pytest.mark.repo_scan

VERSIONS = Path(__file__).resolve().parents[1] / "backend" / "ofo_app" / "alembic" / "versions"
THIS = "0019_reconciliation_store"
EARLIER_BLOCKS = 10  # 0002 .. 0016 publish an allow-list block
TABLES = 3
EMPTY_UPDATE_ARRAYS = 4  # UPDATE on mismatches and on resolutions: no column (each array is used twice)
REPORT_CAP = 65_536


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


def test_ac6_allowlist_holds_every_earlier_block_and_its_own_exactly_once() -> None:
    """AC-6: the store's tables are in the allow-list post-phase, with every earlier block kept."""
    mine = _mine()
    text = mine.extended_allowlist_sql()
    markers = _earlier_markers()
    assert "0016_execution_plans" in markers and len(markers) >= EARLIER_BLOCKS, markers
    assert {n: m for n, m in markers.items() if m not in text} == {}
    assert text.count(mine.ALLOWLIST_BLOCK_MARKER) == 1
    assert text.count("CREATE OR REPLACE FUNCTION") == 1 and "CREATE FUNCTION" not in text
    number = re.match(r"-- (\d+)\.", mine.ALLOWLIST_BLOCK_MARKER)
    assert number is not None
    assert number.group(1) not in {re.match(r"-- (\d+)\.", m).group(1) for m in markers.values()}


def test_ac6_block_names_the_three_tables_with_exact_grants_and_pins() -> None:
    """AC-6: exact column grants (no UPDATE on mismatches or resolutions), DELETE checked, three distinct pins."""
    mine = _mine()
    block = mine._block()
    for table in (mine.MISMATCHES, mine.RESOLUTIONS, mine.STANDALONE):
        assert f"to_regclass('{table}')" in block
        assert block.count(f"has_table_privilege(r.oid, '{table}', 'DELETE')") == 1
        assert block.count(f"has_table_privilege(r.oid, '{table}', 'TRUNCATE')") == 1
    for guard in (mine.MISMATCH_GUARD, mine.RESOLUTION_GUARD, mine.STANDALONE_GUARD):
        assert f"to_regprocedure('{guard}()')" in block
    pins = {mine.MISMATCH_PIN, mine.RESOLUTION_PIN, mine.STANDALONE_PIN}
    assert len(pins) == TABLES and all(p in block for p in pins)
    assert block.count("ARRAY[]::TEXT[]") == EMPTY_UPDATE_ARRAYS
    assert "ARRAY['units']::TEXT[]" in block
    assert f"has_sequence_privilege(r.oid, '{mine.MISMATCH_SEQUENCE}', 'UPDATE')" in block
    assert "detected_at" not in mine.MISMATCH_INSERT_COLUMNS and "resolved_at" not in mine.RESOLUTION_INSERT_COLUMNS
    assert "actor" in mine.RESOLUTION_INSERT_COLUMNS and "updated_at" not in mine.STANDALONE_INSERT_COLUMNS


def test_ac6_a_changed_guard_body_changes_the_pin_and_a_second_block_fails_closed() -> None:
    """AC-6: an edited guard cannot keep its pin; a predecessor already holding block 16 is refused."""
    mine = _mine()
    assert mine._M4._md5_body(mine._mismatch_guard_sql().replace("insert-only", "anything")) != mine.MISMATCH_PIN
    assert mine._M4._md5_body(mine._standalone_guard_sql().replace("never deleted", "x")) != mine.STANDALONE_PIN
    original = mine.previous_allowlist_sql
    mine.previous_allowlist_sql = lambda: original() + mine.ALLOWLIST_BLOCK_MARKER
    try:
        with pytest.raises(RuntimeError):
            mine.extended_allowlist_sql()
    finally:
        mine.previous_allowlist_sql = original


def test_ac6_closed_lists_match_the_store_and_the_domain() -> None:
    """AC-6 / ADR-109 (4): the migration's literals are the store's: three accepted actions + two reserved; the
    sources are the domain's triggers plus the next-day resolution; the close reasons gain exactly one."""
    mine = _mine()
    assert mine.ACTIONS == rs.ACTIONS + rs.RESERVED_ACTIONS
    assert rs.ACTIONS == ("reconciled_by_basket", "marked_requiring_attention", "kite_flat_marked_exited")
    assert mine.SOURCES == rs.SOURCES
    assert rs.SOURCES[:-1] == tuple(t.name.lower() for t in Trigger) and rs.SOURCES[-1] == "next_day_resolution"
    assert mine.REASONS_AFTER == plans.CLOSE_REASONS
    assert set(mine.REASONS_AFTER) - set(mine.REASONS_BEFORE) == {"unresolved_from_positions"}
    assert mine.MAX_UNITS == MAX_UNITS and mine.MAX_REPORT_BYTES == rs.MAX_REPORT_BYTES == REPORT_CAP
    assert f"^{rs._CONTRACT_KEY.pattern}$" == mine.CONTRACT_KEY_REGEX


def test_ac6_predecessor_from_down_revision_and_downgrade_restores_it() -> None:
    """AC-6: the predecessors are read from down_revision alone; downgrade re-installs 0017's text (0018 leaves the
    allow-list untouched) and the reason CHECK."""
    mine = _mine()
    assert mine._PREVIOUS.revision == mine.down_revision == "0018_basket_tag_8"
    assert mine._ALLOWLIST_BASE.revision == mine._PREVIOUS.down_revision == "0017_audit_order_prepared"
    source = (VERSIONS / f"{THIS}.py").read_text(encoding="utf-8")
    assert re.findall(r"""_load\(\s*["']\d{4}_""", source) == []
    assert "op.execute(extended_allowlist_sql())" in source and "op.execute(previous_allowlist_sql())" in source
    assert "for statement in reason_check_sql(REASONS_BEFORE):" in source
