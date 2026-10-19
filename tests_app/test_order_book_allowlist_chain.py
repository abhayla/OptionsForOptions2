"""#313 / ADR-048: migration 0020 extends the app-role allow-list for the order-book store (fill prices, adopted
holdings), and its closed lists are the domain's. No database needed.

Spec basis: issue #313 ("it must be stored (fills AND adopted holdings, in the same transaction as the strategy
version)"); ADR-096 (adopted holdings count as a fill would); ADR-109 / Q224 (two holders of one contract stay
separate); ADR-048 (the limited application role).
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest
from ofo.engine.product import Product
from ofo.strategy.definition import MAX_UNITS
from ofo_app import execution_plan_store as plans

pytestmark = pytest.mark.repo_scan

VERSIONS = Path(__file__).resolve().parents[1] / "backend" / "ofo_app" / "alembic" / "versions"
THIS = "0020_order_book_store"
EARLIER_BLOCKS = 11  # 0002 .. 0018 publish an allow-list block
TABLES = 2
EMPTY_UPDATE_ARRAYS = 4  # UPDATE on both tables: no column (each array is used twice)


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
    assert "0018_reconciliation_store" in markers and len(markers) >= EARLIER_BLOCKS, markers
    assert {n: m for n, m in markers.items() if m not in text} == {}
    assert text.count(mine.ALLOWLIST_BLOCK_MARKER) == 1
    assert text.count("CREATE OR REPLACE FUNCTION") == 1 and "CREATE FUNCTION" not in text
    number = re.match(r"-- (\d+)\.", mine.ALLOWLIST_BLOCK_MARKER)
    assert number is not None
    assert number.group(1) not in {re.match(r"-- (\d+)\.", m).group(1) for m in markers.values()}


def test_block_names_both_tables_with_exact_grants_and_pins() -> None:
    """No UPDATE on either table (insert-only), DELETE/TRUNCATE checked, two distinct pins, sequence checked."""
    mine = _mine()
    block = mine._block()
    for table in (mine.FILLS, mine.HOLDINGS):
        assert f"to_regclass('{table}')" in block
        assert block.count(f"has_table_privilege(r.oid, '{table}', 'DELETE')") == 1
        assert block.count(f"has_table_privilege(r.oid, '{table}', 'TRUNCATE')") == 1
    for guard in (mine.FILL_GUARD, mine.HOLDING_GUARD):
        assert f"to_regprocedure('{guard}()')" in block
    pins = {mine.FILL_PIN, mine.HOLDING_PIN}
    assert len(pins) == TABLES and all(p in block for p in pins)
    assert block.count("ARRAY[]::TEXT[]") == EMPTY_UPDATE_ARRAYS
    assert f"has_sequence_privilege(r.oid, '{mine.HOLDING_SEQUENCE}', 'UPDATE')" in block
    assert "recorded_at" not in mine.FILL_INSERT_COLUMNS and "adopted_at" not in mine.HOLDING_INSERT_COLUMNS
    assert "id" not in mine.HOLDING_INSERT_COLUMNS


def test_guards_are_pinned_and_a_second_block_fails_closed() -> None:
    """An edited guard cannot keep its pin; the fill guard refuses a price for an unfilled order; the holdings guard
    raises its own SQLSTATE; a predecessor already holding block 17 is refused."""
    mine = _mine()
    assert mine._M4._md5_body(mine._fill_guard_sql().replace("filled_quantity > 0", "true")) != mine.FILL_PIN
    assert mine._M4._md5_body(mine._holding_guard_sql().replace("insert-only", "x")) != mine.HOLDING_PIN
    assert "filled_quantity > 0" in mine._fill_guard_sql() and "TG_OP <> 'INSERT'" in mine._fill_guard_sql()
    assert "'OF020'" in mine._holding_guard_sql() and "'OF018'" not in mine._holding_guard_sql()
    original = mine.previous_allowlist_sql
    mine.previous_allowlist_sql = lambda: original() + mine.ALLOWLIST_BLOCK_MARKER
    try:
        with pytest.raises(RuntimeError):
            mine.extended_allowlist_sql()
    finally:
        mine.previous_allowlist_sql = original


def test_closed_lists_match_the_domain_and_the_plan_store() -> None:
    mine = _mine()
    assert tuple(p.value for p in Product) == mine.PRODUCTS
    assert plans.SIDES == mine.SIDES
    assert MAX_UNITS == mine.MAX_UNITS
    assert str(plans.PRICE_LIMIT) == mine.PRICE_LIMIT


def test_one_holding_per_strategy_and_contract_not_per_contract() -> None:
    """ADR-109 / Q224: the uniqueness is (strategy_id, instrument_id), never instrument_id alone."""
    source = (VERSIONS / f"{THIS}.py").read_text(encoding="utf-8")
    mine = _mine()
    assert "CONSTRAINT {HOLDING_KEY} UNIQUE (strategy_id, instrument_id)" in source
    assert mine.HOLDING_KEY == "adopted_holdings_one_per_contract"
    assert "instrument_id    TEXT          NOT NULL CHECK" in source and "instrument_id ~" in source
    assert re.search(r"instrument_id\s+TEXT[^\n]*UNIQUE", source) is None


def test_predecessor_from_down_revision_and_downgrade_restores_it() -> None:
    mine = _mine()
    assert mine._PREVIOUS.revision == mine.down_revision == "0018_reconciliation_store"
    source = (VERSIONS / f"{THIS}.py").read_text(encoding="utf-8")
    assert re.findall(r"""_load\(\s*["']\d{4}_""", source) == []
    assert "op.execute(extended_allowlist_sql())" in source and "op.execute(previous_allowlist_sql())" in source
    assert "order book records are stored" in source
