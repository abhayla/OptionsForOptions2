"""REQ-035 AC-7 / ADR-168 (4), (5): one column set for everyone; the column order stays locked."""
from dataclasses import replace as _replace
from decimal import Decimal

import pytest
from ofo import table as table_package
from ofo.table import columns
from ofo.table.columns import ColumnId
from ofo.table.model import build_table, scenario_caption, scenario_header, visible_columns

# The locked order (REQ-035 AC-2) as the Advanced list showed it at the parent commit: every fixed column.
FULL_FIXED_EXPECTED = [
    ColumnId.LEG, ColumnId.ACTION, ColumnId.INSTRUMENT, ColumnId.EXPIRY, ColumnId.STRIKE, ColumnId.QUANTITY,
    ColumnId.ENTRY_PRICE, ColumnId.LTP, ColumnId.ENTRY_VALUE, ColumnId.CURRENT_VALUE, ColumnId.UNREALIZED_PNL,
    ColumnId.PNL_PERCENT, ColumnId.IV, ColumnId.DELTA, ColumnId.GAMMA, ColumnId.THETA, ColumnId.DECAY, ColumnId.VEGA,
    ColumnId.LOWER_BE, ColumnId.UPPER_BE, ColumnId.STATUS,
]
FORMER_HIDDEN = [ColumnId.PNL_PERCENT, ColumnId.IV, ColumnId.DELTA, ColumnId.GAMMA, ColumnId.THETA, ColumnId.VEGA,
                 ColumnId.LOWER_BE, ColumnId.UPPER_BE]


def _fixed_ids(table):
    return [c.id for c in visible_columns(table) if not c.is_scenario_level]


def test_ac7_the_one_column_set_is_the_full_list_in_the_locked_order(golden, golden_scenario):
    """AC-7: every fixed column is shown, in exactly the locked order (the former Advanced list)."""
    level_set, values = golden_scenario
    table = build_table(golden, level_set=level_set, scenario=values)
    assert _fixed_ids(table) == FULL_FIXED_EXPECTED
    for shown in FORMER_HIDDEN:  # IV, Greeks, % return, breakevens: formerly hidden at Guided/Standard
        assert shown in _fixed_ids(table)


def test_ac7_the_visible_list_is_the_whole_table_in_its_own_order(golden, golden_scenario):
    """AC-7: nothing is dropped or reordered: the visible ids equal the table's own ids (leading, levels, trailing)."""
    level_set, values = golden_scenario
    table = build_table(golden, level_set=level_set, scenario=values)
    assert [c.id for c in visible_columns(table)] == list(table.column_ids)
    assert list(table.column_ids) == FULL_FIXED_EXPECTED[:18] + list(level_set.levels) + FULL_FIXED_EXPECTED[18:]


def test_ac7_dropping_one_column_from_the_set_is_caught(golden, golden_scenario):
    """AC-7 (mutation guard): a set missing any single fixed column differs from the asserted list."""
    level_set, values = golden_scenario
    table = build_table(golden, level_set=level_set, scenario=values)
    shown = _fixed_ids(table)
    for cid in FULL_FIXED_EXPECTED:
        assert [c for c in shown if c is not cid] != FULL_FIXED_EXPECTED


def test_ac7_no_level_argument_is_accepted(golden, golden_scenario):
    """AC-7: the level switch is gone: an extra argument to visible_columns or scenario_header fails."""
    level_set, values = golden_scenario
    table = build_table(golden, level_set=level_set, scenario=values)
    with pytest.raises(TypeError):
        visible_columns(table, "standard")
    with pytest.raises(TypeError):
        scenario_header("standard", "NIFTY", Decimal("23000"), ())
    for removed in ("UXLevel", "VISIBLE_FIXED_COLUMNS", "is_visible"):
        assert not hasattr(columns, removed)
        assert not hasattr(table_package, removed)


# Hand-derived from the §6 golden Iron Condor (NIFTY, spot 23,047, NIFTY step 100): grid 22,000..24,000 every 100,
# plus the CURRENT column 23,047 and the two 0-P&L columns. Net credit = 86 + 91.5 - 42.5 - 44 = 91 points, so the
# breakevens are 23,000 - 91 = 22,909 and 23,400 + 91 = 23,491. Sorted ascending, that is 24 columns.
EXPECTED_HEADINGS = [
    "22,000", "22,100", "22,200", "22,300", "22,400", "22,500", "22,600", "22,700", "22,800", "22,900",
    "0-P&L 22,909", "23,000", "CURRENT 23,047", "23,100", "23,200", "23,300", "23,400", "0-P&L 23,491",
    "23,500", "23,600", "23,700", "23,800", "23,900", "24,000",
]


def _scenario_labels(table):
    return [c.label for c in visible_columns(table) if c.is_scenario_level]


def test_ac7_headings_are_the_index_levels_with_current_and_zero_pnl_marked(golden, golden_scenario):
    """AC-7 (Q227): each scenario column's own heading is its index level, CURRENT and 0-P&L columns marked.
    24 columns, 24 distinct headings."""
    level_set, values = golden_scenario
    table = build_table(golden, level_set=level_set, scenario=values)
    labels = _scenario_labels(table)
    assert labels == EXPECTED_HEADINGS
    assert len(set(labels)) == 24


def test_ac7_scenario_section_caption_is_the_pair_naming_the_underlying(golden, golden_scenario):
    """AC-7 (Q227): "NIFTY at expiry | You make/lose" is the caption of the scenario section, not a column label;
    a SENSEX strategy says SENSEX."""
    level_set, values = golden_scenario
    table = build_table(golden, level_set=level_set, scenario=values)
    assert scenario_caption(table) == "NIFTY at expiry | You make/lose"
    assert all("You make/lose" not in label for label in _scenario_labels(table))
    sensex = _replace(table, underlying="SENSEX")
    assert scenario_caption(sensex) == "SENSEX at expiry | You make/lose"


def test_scenario_header_marks_current_zero_pnl_and_both(golden):
    """AC-7: a level that is both CURRENT and a breakeven carries both marks (no mark is dropped)."""
    assert scenario_header("NIFTY", Decimal("23047"), ("CURRENT", "0-P&L")) == "CURRENT 0-P&L 23,047"
    assert scenario_header("SENSEX", Decimal("75000")) == "75,000"


def test_scenario_header_rejects_a_blank_underlying():
    """AC-7: fail closed on a blank underlying."""
    with pytest.raises(ValueError):
        scenario_header("  ", Decimal("23000"))
