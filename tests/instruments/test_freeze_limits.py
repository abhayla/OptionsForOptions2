"""The stored freeze limit lives with the instruments (ADR-092); the order review and the leg-edit route share it."""
from __future__ import annotations

import ast
import datetime
from pathlib import Path

import pytest
from ofo.execution import freeze as order_freeze
from ofo.instruments import freeze_limits

D = datetime.date(2026, 10, 15)
ROUTE = Path(__file__).resolve().parents[2] / "backend" / "ofo_app" / "routes" / "leg_edit.py"


def test_one_source_of_truth_the_order_path_uses_the_same_objects():
    assert order_freeze.StoredFreeze is freeze_limits.StoredFreeze
    assert order_freeze.largest_allowed_units is freeze_limits.largest_allowed_units


@pytest.mark.parametrize(("limit", "lot", "largest"), [(3511, 65, 3510), (3510, 65, 3445), (1441, 30, 1440)])
def test_largest_allowed_units_is_below_the_limit_in_whole_lots(limit, lot, largest):
    """Limit known: the largest whole-lot order is strictly below the limit (F-36)."""
    got = freeze_limits.largest_allowed_units(freeze_limits.StoredFreeze(limit, lot, D))
    assert got == largest
    assert got < limit
    assert got % lot == 0


@pytest.mark.parametrize(("limit", "lot"), [(0, 65), (-1, 65), (3511, 0), (True, 65), (3511, True), (35.5, 65)])
def test_an_unusable_limit_or_lot_is_refused(limit, lot):
    """A limit that is not a positive integer is refused, never stored as a made-up value."""
    with pytest.raises(ValueError, match="positive integer"):
        freeze_limits.StoredFreeze(limit, lot, D)


def test_the_leg_edit_route_imports_no_order_module():
    """REQ-076 AC-5: the leg-edit route is not an order route; the freeze lookup comes from the instruments."""
    imported = set()
    for node in ast.walk(ast.parse(ROUTE.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
    assert "ofo.instruments.freeze_limits" in imported
    assert not [m for m in imported if m.split(".")[:2] in (["ofo", "execution"], ["ofo", "orders"])]
