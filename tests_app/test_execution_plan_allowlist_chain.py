"""W-094 / ADR-048: migration 0016 extends the app-role allow-list exactly like 0013 does, so a later wider grant or a
dropped guard trigger on ``execution_plans`` / ``execution_plan_orders`` fails the migration chain. No database needed.

Class: every table a migration creates after 0006 must appear in the allow-list post-phase (before this migration's
fix: 0016's two tables were missing; after: both are named, with their exact column grants and pinned guard bodies).
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

VERSIONS = Path(__file__).resolve().parents[1] / "backend" / "ofo_app" / "alembic" / "versions"
THIS = "0016_execution_plans"


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
    assert "0013_exchange_freeze_limits" in markers and len(markers) >= 9, markers
    assert {n: m for n, m in markers.items() if m not in text} == {}
    assert text.count(mine.ALLOWLIST_BLOCK_MARKER) == 1
    assert text.count("CREATE OR REPLACE FUNCTION") == 1 and "CREATE FUNCTION" not in text


def test_own_marker_number_is_unique_in_the_chain() -> None:
    mine = _mine()
    number = re.match(r"-- (\d+)\.", mine.ALLOWLIST_BLOCK_MARKER)
    assert number is not None
    assert number.group(1) not in {re.match(r"-- (\d+)\.", m).group(1) for m in _earlier_markers().values()}


def test_block_names_both_tables_with_their_exact_grants_and_pins() -> None:
    mine = _mine()
    block = mine._block()
    for table in (mine.PLANS, mine.ORDERS):
        assert f"to_regclass('{table}')" in block
    for guard in (mine.PLAN_GUARD, mine.ORDER_GUARD):
        assert f"to_regprocedure('{guard}()')" in block
    assert mine.PLAN_PIN in block and mine.ORDER_PIN in block and mine.PLAN_PIN != mine.ORDER_PIN
    # the column lists the grants use are the ones the post-phase check asserts (one source)
    assert "ARRAY['strategy_id', 'plan_number', 'action']::TEXT[]" in block
    assert "ARRAY['status', 'close_reason']::TEXT[]" in block
    assert "ARRAY['filled_quantity']::TEXT[]" in block
    assert "filled_quantity" not in mine.ORDER_INSERT_COLUMNS
    # DELETE / TRUNCATE are checked as not granted on both tables
    assert block.count("has_table_privilege(r.oid, 'public.execution_plans', 'DELETE')") == 1
    assert block.count("has_table_privilege(r.oid, 'public.execution_plan_orders', 'TRUNCATE')") == 1


def test_a_changed_guard_body_changes_the_pin() -> None:
    """The pin is the md5 of the guard text installed by upgrade(): an edit to the guard cannot keep the old pin."""
    mine = _mine()
    assert mine._M4._md5_body(mine._plan_guard_sql().replace("only inserted open", "inserted anyhow")) != mine.PLAN_PIN
    assert mine._M4._md5_body(mine._order_guard_sql().replace("insert-only", "anything")) != mine.ORDER_PIN


def test_a_later_migration_can_build_on_this_text_and_a_second_block_is_refused() -> None:
    mine = _mine()
    assert mine.extended_allowlist_sql() == mine.extended_allowlist_sql()
    original = mine.previous_allowlist_sql
    try:
        mine.previous_allowlist_sql = lambda: original() + mine.ALLOWLIST_BLOCK_MARKER
        try:
            mine.extended_allowlist_sql()
        except RuntimeError:
            pass
        else:
            raise AssertionError("a block 15 already in the predecessor must fail closed")
    finally:
        mine.previous_allowlist_sql = original


def test_predecessor_comes_from_down_revision_alone() -> None:
    mine = _mine()
    assert Path(mine._PREVIOUS.__file__).name == f"{mine.down_revision}.py"
    assert mine._PREVIOUS.revision == mine.down_revision
    source = (VERSIONS / f"{THIS}.py").read_text(encoding="utf-8")
    assert re.findall(r"""_load\(\s*["']\d{4}_""", source) == []


def test_upgrade_installs_the_extended_text_and_downgrade_restores_the_previous_one() -> None:
    source = (VERSIONS / f"{THIS}.py").read_text(encoding="utf-8")
    assert "op.execute(extended_allowlist_sql())" in source
    assert "op.execute(previous_allowlist_sql())" in source
