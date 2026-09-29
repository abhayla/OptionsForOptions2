"""REQ-035 AC-7: the column order stays locked; what is shown depends on the UX level."""
from dataclasses import replace as _replace
from decimal import Decimal

from ofo.table.columns import ColumnId, UXLevel
from ofo.table.model import build_table, scenario_header, visible_columns

GUIDED_EXPECTED = [
    ColumnId.LEG, ColumnId.ACTION, ColumnId.INSTRUMENT, ColumnId.EXPIRY, ColumnId.STRIKE, ColumnId.QUANTITY,
    ColumnId.ENTRY_PRICE, ColumnId.LTP, ColumnId.ENTRY_VALUE, ColumnId.CURRENT_VALUE, ColumnId.UNREALIZED_PNL,
    ColumnId.STATUS,
]
STANDARD_ADDS = [ColumnId.PNL_PERCENT, ColumnId.LOWER_BE, ColumnId.UPPER_BE]
ADVANCED_ADDS = [ColumnId.IV, ColumnId.DELTA, ColumnId.GAMMA, ColumnId.THETA, ColumnId.VEGA]


def _fixed_ids(table, level):
    return [c.id for c in visible_columns(table, level) if not c.is_scenario_level]


def test_ac7_guided_hides_pnl_percent_iv_greeks_and_breakevens(golden, golden_scenario):
    """AC-7: Guided hides IV/Greek columns by default (Q31, T1 #78-#79), and P&L %/breakevens (added at Standard)."""
    level_set, values = golden_scenario
    table = build_table(golden, level_set=level_set, scenario=values)
    assert _fixed_ids(table, UXLevel.GUIDED) == GUIDED_EXPECTED
    for hidden in (ColumnId.PNL_PERCENT, ColumnId.IV, ColumnId.DELTA, ColumnId.GAMMA, ColumnId.THETA,
                   ColumnId.VEGA, ColumnId.LOWER_BE, ColumnId.UPPER_BE):
        assert hidden not in _fixed_ids(table, UXLevel.GUIDED)


def test_ac7_standard_adds_percent_return_and_breakevens(golden, golden_scenario):
    """AC-7: Standard adds % return and breakevens, but still hides Greeks/IV."""
    level_set, values = golden_scenario
    table = build_table(golden, level_set=level_set, scenario=values)
    standard = _fixed_ids(table, UXLevel.STANDARD)
    expected = [
        ColumnId.LEG, ColumnId.ACTION, ColumnId.INSTRUMENT, ColumnId.EXPIRY, ColumnId.STRIKE, ColumnId.QUANTITY,
        ColumnId.ENTRY_PRICE, ColumnId.LTP, ColumnId.ENTRY_VALUE, ColumnId.CURRENT_VALUE, ColumnId.UNREALIZED_PNL,
        ColumnId.PNL_PERCENT, ColumnId.LOWER_BE, ColumnId.UPPER_BE, ColumnId.STATUS,
    ]
    assert standard == expected
    for hidden in (ColumnId.IV, ColumnId.DELTA, ColumnId.GAMMA, ColumnId.THETA, ColumnId.VEGA):
        assert hidden not in standard
    for shown in (ColumnId.PNL_PERCENT, ColumnId.LOWER_BE, ColumnId.UPPER_BE):
        assert shown in standard


def test_ac7_advanced_adds_greeks_and_iv(golden, golden_scenario):
    """AC-7: Advanced adds Greeks and IV assumptions on top of Standard."""
    level_set, values = golden_scenario
    table = build_table(golden, level_set=level_set, scenario=values)
    advanced = _fixed_ids(table, UXLevel.ADVANCED)
    standard = _fixed_ids(table, UXLevel.STANDARD)
    for shown in (ColumnId.IV, ColumnId.DELTA, ColumnId.GAMMA, ColumnId.THETA, ColumnId.VEGA):
        assert shown in advanced
    assert set(advanced) - set(standard) == set(ADVANCED_ADDS)


def test_ac7_column_order_is_identical_across_levels_hidden_columns_keep_their_position(golden, golden_scenario):
    """AC-7: the order never changes between levels — a level's visible list is the FULL order with gaps removed,
    never a reordering. Proven by checking every level's visible list is a subsequence of the full column order."""
    level_set, values = golden_scenario
    table = build_table(golden, level_set=level_set, scenario=values)
    full_order = table.column_ids
    for level in UXLevel:
        visible_ids = [c.id for c in visible_columns(table, level)]
        # every visible id appears in full_order in the same relative order (a subsequence).
        positions = [full_order.index(cid) for cid in visible_ids]
        assert positions == sorted(positions), f"{level} column order was not preserved"


def test_ac7_scenario_level_columns_always_visible(golden, golden_scenario):
    """AC-7: the market-level scenario columns are the table's core content and show at every UX level."""
    level_set, values = golden_scenario
    table = build_table(golden, level_set=level_set, scenario=values)
    for level in UXLevel:
        visible_ids = {c.id for c in visible_columns(table, level)}
        for scenario_level in level_set.levels:
            assert scenario_level in visible_ids


# Hand-derived from the §6 golden Iron Condor (NIFTY, spot 23,047, NIFTY step 100): grid 22,000..24,000 every 100,
# plus the CURRENT column 23,047 and the two 0-P&L columns. Net credit = 86 + 91.5 - 42.5 - 44 = 91 points, so the
# breakevens are 23,000 - 91 = 22,909 and 23,400 + 91 = 23,491. Sorted ascending, that is 24 columns.
EXPECTED_HEADINGS = [
    "22,000", "22,100", "22,200", "22,300", "22,400", "22,500", "22,600", "22,700", "22,800", "22,900",
    "0-P&L 22,909", "23,000", "CURRENT 23,047", "23,100", "23,200", "23,300", "23,400", "0-P&L 23,491",
    "23,500", "23,600", "23,700", "23,800", "23,900", "24,000",
]


def _scenario_labels(table, level):
    return [c.label for c in visible_columns(table, level) if c.is_scenario_level]


def test_ac7_every_ux_level_headings_are_the_index_levels_with_current_and_zero_pnl_marked(golden, golden_scenario):
    """AC-7 (Q227): each scenario column's own heading is its index level, CURRENT and 0-P&L columns marked — at
    Guided, Standard and Advanced alike. 24 columns, 24 distinct headings (round 3 gave Guided 24 identical ones)."""
    level_set, values = golden_scenario
    table = build_table(golden, level_set=level_set, scenario=values)
    for level in UXLevel:
        labels = _scenario_labels(table, level)
        assert labels == EXPECTED_HEADINGS, level
        assert len(set(labels)) == 24


def test_ac7_scenario_section_caption_is_the_pair_naming_the_underlying(golden, golden_scenario):
    """AC-7 (Q227): "NIFTY at expiry | You make/lose" is the caption of the scenario section, not a column label;
    a SENSEX strategy says SENSEX."""
    from ofo.table.model import scenario_caption

    level_set, values = golden_scenario
    table = build_table(golden, level_set=level_set, scenario=values)
    assert scenario_caption(table) == "NIFTY at expiry | You make/lose"
    for level in UXLevel:
        assert all("You make/lose" not in label for label in _scenario_labels(table, level))
    sensex = _replace(table, underlying="SENSEX")
    assert scenario_caption(sensex) == "SENSEX at expiry | You make/lose"


def test_ac7_guided_still_hides_iv_and_greek_columns_with_level_headings(golden, golden_scenario):
    """AC-7: the heading change does not un-hide anything: Guided has no IV/Greek column and keeps the locked order."""
    level_set, values = golden_scenario
    table = build_table(golden, level_set=level_set, scenario=values)
    guided_ids = [c.id for c in visible_columns(table, UXLevel.GUIDED)]
    for hidden in (ColumnId.IV, ColumnId.DELTA, ColumnId.GAMMA, ColumnId.THETA, ColumnId.VEGA):
        assert hidden not in guided_ids
    assert guided_ids == GUIDED_EXPECTED[:11] + list(level_set.levels) + [ColumnId.STATUS]


def test_scenario_header_marks_current_zero_pnl_and_both(golden):
    """AC-7: a level that is both CURRENT and a breakeven carries both marks (no mark is dropped)."""
    assert scenario_header(UXLevel.GUIDED, "NIFTY", Decimal("23047"), ("CURRENT", "0-P&L")) == "CURRENT 0-P&L 23,047"
    assert scenario_header(UXLevel.ADVANCED, "SENSEX", Decimal("75000")) == "75,000"


def test_scenario_header_rejects_bad_level_and_blank_underlying():
    """AC-7: fail closed on a non-UXLevel or blank underlying (each guard has its own killing case)."""
    import pytest

    with pytest.raises(ValueError):
        scenario_header("guided", "NIFTY", Decimal("23000"))
    with pytest.raises(ValueError):
        scenario_header(UXLevel.GUIDED, "  ", Decimal("23000"))
