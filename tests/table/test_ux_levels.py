"""REQ-035 AC-7: the column order stays locked; what is shown depends on the UX level."""
from ofo.table.columns import ColumnId, UXLevel
from ofo.table.model import build_table, visible_columns

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
