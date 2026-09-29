"""REQ-035: the single strategy table. Core proof: the golden Iron Condor table matches AC-2's locked column
order and every leg/total cell exactly (scenario-calculations.md §6).

Round-3 fix (independent verifier finding: round-2's Greek tests asserted numbers produced by RUNNING the code
under test, so a round-then-scale bug passed unnoticed). Every Greek assertion below is checked against an
independent Black-Scholes implementation written in THIS file (``math.erf``, no import from ``ofo.engine``), never
against a hard-coded number that came from the table module itself.
"""
import math
from decimal import ROUND_HALF_EVEN, Decimal as D

import pytest

from ofo.engine.inputs import LegInput
from ofo.engine.legs import Action, Instrument
from ofo.engine.black_scholes import Greeks
from ofo.table.columns import ColumnId
from ofo.table.model import CellKind, StrategyHealth, TOTAL_ROW_ID, build_table

from conftest import GOLDEN_SPOT, NIFTY_EXPIRY, RATE, VALUATION, nifty_input, nifty_leg

FIXED_ORDER = [
    ColumnId.LEG, ColumnId.ACTION, ColumnId.INSTRUMENT, ColumnId.EXPIRY, ColumnId.STRIKE, ColumnId.QUANTITY,
    ColumnId.ENTRY_PRICE, ColumnId.LTP, ColumnId.ENTRY_VALUE, ColumnId.CURRENT_VALUE, ColumnId.UNREALIZED_PNL,
    ColumnId.PNL_PERCENT, ColumnId.IV, ColumnId.DELTA, ColumnId.GAMMA, ColumnId.THETA, ColumnId.VEGA,
]
TRAILING_ORDER = [ColumnId.LOWER_BE, ColumnId.UPPER_BE, ColumnId.STATUS]
GREEK_COLUMNS = [ColumnId.DELTA, ColumnId.GAMMA, ColumnId.THETA, ColumnId.VEGA]
GREEK_NAMES = ("delta", "gamma", "theta", "vega")

LEG_ENTRY_VALUES = [D("3187.50"), D("6450"), D("6862.50"), D("3300")]
LEG_LIVE_PNL = [D("-322.50"), D("1012.50"), D("1012.50"), D("-337.50")]
LEG_PNL_PERCENT = [D("-10.12"), D("15.70"), D("14.75"), D("-10.23")]
LEG_CURRENT_VALUES = [D("2865"), D("5437.50"), D("5850"), D("2962.50")]

# The §6 golden legs' own data, needed by the independent Black-Scholes check below (kept separate from
# conftest.GOLDEN_LEGS so this file never imports a computed Greek from anywhere).
GOLDEN_STRIKES = [22800.0, 23000.0, 23400.0, 23600.0]
GOLDEN_IVS = [0.117446, 0.108838, 0.093349, 0.102360]
GOLDEN_IS_CALL = [False, False, True, True]  # PE, PE, CE, CE
GOLDEN_SIGNS = [D(1), D(-1), D(-1), D(1)]  # BUY, SELL, SELL, BUY
GOLDEN_QTY = D(75)
DAYS_IN_YEAR = 365
YEARS = 10 / 365  # VALUATION -> NIFTY_EXPIRY is exactly 10 calendar days at the same 15:30 IST close


def _independent_bs_greeks(is_call: bool, s: float, k: float, t: float, r: float, v: float) -> dict:
    """A from-scratch Black-Scholes Greeks implementation (Hull), independent of ofo.engine.black_scholes."""
    d1 = (math.log(s / k) + (r + 0.5 * v * v) * t) / (v * math.sqrt(t))
    d2 = d1 - v * math.sqrt(t)
    pdf = math.exp(-0.5 * d1 * d1) / math.sqrt(2.0 * math.pi)
    cdf = lambda x: 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))  # noqa: E731
    delta = cdf(d1) if is_call else cdf(d1) - 1.0
    gamma = pdf / (s * v * math.sqrt(t))
    vega = s * pdf * math.sqrt(t) / 100.0
    decay = -s * pdf * v / (2.0 * math.sqrt(t))
    carry = r * k * math.exp(-r * t)
    theta_year = decay - carry * cdf(d2) if is_call else decay + carry * cdf(-d2)
    return {"delta": delta, "gamma": gamma, "theta": theta_year / DAYS_IN_YEAR, "vega": vega}


def _independent_position_greeks() -> list[dict]:
    """The independent per-leg POSITION Greeks (per-unit x quantity x sign), one dict per golden leg."""
    s, r = float(GOLDEN_SPOT), float(RATE)
    out = []
    for i in range(4):
        per_unit = _independent_bs_greeks(GOLDEN_IS_CALL[i], s, GOLDEN_STRIKES[i], YEARS, r, GOLDEN_IVS[i])
        sign = 1.0 if GOLDEN_SIGNS[i] == D(1) else -1.0
        out.append({name: value * sign * 75.0 for name, value in per_unit.items()})
    return out


def test_core_golden_iron_condor_column_order_matches_ac2(golden, golden_scenario):
    """Core/AC-2: the table's column order is exactly Leg..Vega, the scenario levels, Lower BE, Upper BE, Status."""
    level_set, values = golden_scenario
    table = build_table(golden, level_set=level_set, scenario=values)
    ids = table.column_ids
    assert ids[: len(FIXED_ORDER)] == tuple(FIXED_ORDER)
    n_levels = len(level_set.levels)
    assert ids[len(FIXED_ORDER): len(FIXED_ORDER) + n_levels] == level_set.levels
    assert ids[len(FIXED_ORDER) + n_levels:] == tuple(TRAILING_ORDER)


def test_ac1_exactly_one_table_five_rows(golden, golden_scenario):
    """AC-1: one table, one row per leg (4) plus one TOTAL row, never two tables."""
    level_set, values = golden_scenario
    table = build_table(golden, level_set=level_set, scenario=values)
    assert len(table.rows) == 5
    assert [r.row_id for r in table.rows] == ["1", "2", "3", "4", TOTAL_ROW_ID]


def test_ac2_leg_row_values_exact(golden, golden_scenario):
    """AC-2: every leg row's core money/points cells are exact engine values, no re-derivation."""
    level_set, values = golden_scenario
    table = build_table(golden, level_set=level_set, scenario=values)
    expected_actions = [Action.BUY, Action.SELL, Action.SELL, Action.BUY]
    expected_instruments = [Instrument.PE, Instrument.PE, Instrument.CE, Instrument.CE]
    expected_strikes = [D("22800"), D("23000"), D("23400"), D("23600")]
    for i, row in enumerate(table.rows[:4]):
        assert row.cell(ColumnId.LEG).value == str(i + 1)
        assert row.cell(ColumnId.ACTION).value == expected_actions[i].value
        assert row.cell(ColumnId.INSTRUMENT).value == expected_instruments[i].value
        assert row.cell(ColumnId.EXPIRY).value == NIFTY_EXPIRY.isoformat()
        assert row.cell(ColumnId.STRIKE).value == expected_strikes[i]
        assert row.cell(ColumnId.QUANTITY).value == 75
        assert row.cell(ColumnId.ENTRY_VALUE).value == LEG_ENTRY_VALUES[i]
        assert row.cell(ColumnId.CURRENT_VALUE).value == LEG_CURRENT_VALUES[i]
        assert row.cell(ColumnId.UNREALIZED_PNL).value == LEG_LIVE_PNL[i]
        assert row.cell(ColumnId.PNL_PERCENT).value == LEG_PNL_PERCENT[i]


def test_ac2_total_row_values_exact(golden, golden_scenario):
    """AC-2: the strategy TOTAL row sums the legs exactly (§6: net +1,365.00 live P&L)."""
    level_set, values = golden_scenario
    table = build_table(golden, level_set=level_set, scenario=values)
    total = table.rows[-1]
    assert total.cell(ColumnId.ENTRY_VALUE).value == D("19800.00")
    assert total.cell(ColumnId.UNREALIZED_PNL).value == D("1365.00")
    assert total.cell(ColumnId.LOWER_BE).value == D("22909")
    assert total.cell(ColumnId.UPPER_BE).value == D("23491")


def test_total_row_pnl_percent_leaves_leg_rows_unchanged(golden, golden_scenario):
    """AC-2: a leg's P&L % still uses unrealized / |entry value| x 100 (only the TOTAL row is risk-based, Q233)."""
    level_set, values = golden_scenario
    table = build_table(golden, level_set=level_set, scenario=values)
    assert table.rows[0].cell(ColumnId.PNL_PERCENT).value == LEG_PNL_PERCENT[0]


def test_ac2_scenario_level_columns_match_engine_exactly(golden, golden_scenario):
    """AC-2: the scenario level cells are exactly ofo.scenario's totals/leg_rows, never recomputed."""
    level_set, values = golden_scenario
    table = build_table(golden, level_set=level_set, scenario=values)
    for i, level in enumerate(level_set.levels):
        assert table.rows[-1].cell(level).value == values.totals[i]
        for leg_idx in range(4):
            assert table.rows[leg_idx].cell(level).value == values.leg_rows[leg_idx][i]


def test_ac6_iv_and_greeks_from_platform_black_scholes(golden, golden_scenario):
    """AC-6: IV cells are exact; Greek cells are POSITION-level (per-unit x quantity x sign), the platform's
    per-unit Black-Scholes value kept as the secondary ``per_unit`` field. Every value is checked against an
    INDEPENDENT Black-Scholes computation (``_independent_bs_greeks``, this file's own ``math.erf``), never a
    hard-coded number produced by running ``ofo.engine`` (round-3 fix: that is exactly how round-2's
    round-then-scale bug passed unnoticed).

    Mutation test: round-then-scale (rounding each per-unit Greek to 4 dp before x quantity) fails this test — the
    tolerance (0.00005) is sized to cover only the position cell's OWN final 4 dp rounding (max half-step 0.00005),
    not an extra compounded per-unit rounding error (which was up to 0.0035 on the golden Gamma legs).
    """
    level_set, values = golden_scenario
    table = build_table(golden, level_set=level_set, scenario=values)
    ivs = [D("0.117446"), D("0.108838"), D("0.093349"), D("0.102360")]
    independent = _independent_position_greeks()
    tolerance = 0.00005
    for i, row in enumerate(table.rows[:4]):
        assert row.cell(ColumnId.IV).value == ivs[i]
        for name, cid in zip(GREEK_NAMES, GREEK_COLUMNS):
            cell = row.cell(cid)
            assert abs(float(cell.value) - independent[i][name]) <= tolerance, (i, name, cell.value)

    total = table.rows[-1]
    independent_total = {name: sum(leg[name] for leg in independent) for name in GREEK_NAMES}
    for name, cid in zip(GREEK_NAMES, GREEK_COLUMNS):
        assert abs(float(total.cell(cid).value) - independent_total[name]) <= tolerance, name


def test_fix_round_leg_display_sums_within_rounding_tolerance_of_total(golden, golden_scenario):
    """Round-3 fix item 1: legs are rounded individually, TOTAL is rounded once after summing the UNROUNDED
    values — so the four DISPLAYED leg cells sum to within 0.0001 x 4 of the displayed TOTAL, not exactly."""
    level_set, values = golden_scenario
    table = build_table(golden, level_set=level_set, scenario=values)
    tolerance = D("0.0001") * 4
    for cid in GREEK_COLUMNS:
        leg_sum = sum((table.rows[i].cell(cid).value for i in range(4)), D(0))
        assert abs(leg_sum - table.rows[-1].cell(cid).value) <= tolerance, cid


def test_fix_round_unrounded_leg_greeks_sum_exactly_to_total(golden, golden_scenario):
    """Round-3 fix item 1, exact check: summing the legs' UNROUNDED ``per_unit`` Greeks (x quantity x sign) and
    rounding ONCE gives EXACTLY the TOTAL cell — proving TOTAL is sum-then-round, never round-then-sum."""
    level_set, values = golden_scenario
    table = build_table(golden, level_set=level_set, scenario=values)
    for cid in GREEK_COLUMNS:
        raw_sum = sum(
            (table.rows[i].cell(cid).per_unit * GOLDEN_SIGNS[i] * GOLDEN_QTY for i in range(4)), D(0)
        )
        assert raw_sum.quantize(D("0.0001"), rounding=ROUND_HALF_EVEN) == table.rows[-1].cell(cid).value, cid


def test_fix_round_futures_leg_delta_is_position_level_and_included_in_total():
    """Fix round Proof: a table with one SELL NIFTY FUT x 75 shows leg Delta -75 and TOTAL Delta -75 (futures
    legs were silently excluded from the TOTAL Greek aggregate — the second half of the Class defect)."""
    fut_leg = LegInput(
        underlying="NIFTY", contract="NIFTY26OCTFUT", action=Action.SELL, instrument=Instrument.FUT,
        strike=None, expiry=NIFTY_EXPIRY, quantity=75, premium=D("23050.00"), ltp=D("23060.00"),
    )
    inputs = nifty_input([fut_leg])
    table = build_table(inputs)
    row = table.rows[0]
    assert row.cell(ColumnId.DELTA).value == D("-75")
    assert row.cell(ColumnId.GAMMA).value == D("0")
    assert row.cell(ColumnId.THETA).value == D("0")
    assert row.cell(ColumnId.VEGA).value == D("0")
    total = table.rows[-1]
    assert total.cell(ColumnId.DELTA).value == D("-75")
    # per-unit for a futures leg (secondary field): +1 magnitude, direction applied like any other leg.
    assert row.cell(ColumnId.DELTA).per_unit == D("1")


def test_ac6_vendor_greek_is_a_reference_field_never_the_value(golden_scenario):
    """AC-6: a vendor Greek is kept only as a reference (``Cell.vendor``); it never replaces the platform value."""
    level_set, values = golden_scenario
    vendor_greeks = Greeks(D("-0.9999"), D("0.9999"), D("0.9999"), D("0.9999"))
    legs = [
        nifty_leg(Action.BUY, Instrument.PE, "22800", "42.50", "38.20", "0.117446", greeks=vendor_greeks),
        nifty_leg(Action.SELL, Instrument.PE, "23000", "86.00", "72.50", "0.108838"),
        nifty_leg(Action.SELL, Instrument.CE, "23400", "91.50", "78.00", "0.093349"),
        nifty_leg(Action.BUY, Instrument.CE, "23600", "44.00", "39.50", "0.102360"),
    ]
    inputs = nifty_input(legs)
    table = build_table(inputs, level_set=level_set, scenario=values)
    delta_cell = table.rows[0].cell(ColumnId.DELTA)
    independent_delta = _independent_position_greeks()[0]["delta"]
    assert abs(float(delta_cell.value) - independent_delta) <= 0.00005  # the platform value, not vendor's -0.9999
    assert delta_cell.value != vendor_greeks.delta
    assert delta_cell.vendor == vendor_greeks.delta


def test_missing_iv_gives_none_greeks_with_reason_but_exact_pnl(golden_scenario):
    """Red case: a leg with no IV gets None IV/Greek cells and a reason; its P&L cells stay exact."""
    level_set, values = golden_scenario
    legs = [
        nifty_leg(Action.BUY, Instrument.PE, "22800", "42.50", "38.20", iv=None),
        nifty_leg(Action.SELL, Instrument.PE, "23000", "86.00", "72.50", "0.108838"),
        nifty_leg(Action.SELL, Instrument.CE, "23400", "91.50", "78.00", "0.093349"),
        nifty_leg(Action.BUY, Instrument.CE, "23600", "44.00", "39.50", "0.102360"),
    ]
    inputs = nifty_input(legs)
    table = build_table(inputs, level_set=level_set, scenario=values)
    row = table.rows[0]
    assert row.cell(ColumnId.IV).value is None
    assert row.cell(ColumnId.IV).reason
    for cid in GREEK_COLUMNS:
        cell = row.cell(cid)
        assert cell.value is None
        assert cell.reason
    assert row.cell(ColumnId.UNREALIZED_PNL).value == D("-322.50")
    assert row.cell(ColumnId.ENTRY_VALUE).value == D("3187.50")
    # a leg missing IV means the TOTAL row's Greeks are None too, never a partial sum.
    total = table.rows[-1]
    for cid in GREEK_COLUMNS:
        cell = total.cell(cid)
        assert cell.value is None
        assert cell.reason


def test_futures_leg_strike_and_iv_dash_but_greeks_and_pnl_populated():
    """Red case: a futures leg has no Strike/IV ('—' + reason), but its Greeks (position-level, fix round) and
    P&L are populated, not dashed."""
    fut_leg = LegInput(
        underlying="NIFTY", contract="NIFTY26OCTFUT", action=Action.BUY, instrument=Instrument.FUT,
        strike=None, expiry=NIFTY_EXPIRY, quantity=75, premium=D("23050.00"), ltp=D("23060.00"),
    )
    other_leg = nifty_leg(Action.SELL, Instrument.CE, "23400", "91.50", "78.00", "0.093349")
    inputs = nifty_input([fut_leg, other_leg])
    table = build_table(inputs)
    row = table.rows[0]
    assert row.cell(ColumnId.STRIKE).value is None
    assert row.cell(ColumnId.STRIKE).reason
    assert row.cell(ColumnId.IV).value is None
    assert "futures" in row.cell(ColumnId.IV).reason
    assert row.cell(ColumnId.DELTA).value == D("75")  # BUY x 75, per-unit 1
    assert row.cell(ColumnId.GAMMA).value == D("0")
    # its live P&L is still exact: (23060 - 23050) * 75
    assert row.cell(ColumnId.UNREALIZED_PNL).value == D("750.00")


def test_status_leg_and_total_are_caller_supplied_not_computed(golden, golden_scenario):
    """Fix round item 3: leg Status is the caller-supplied state; TOTAL Status is the caller-supplied
    StrategyHealth using ADR-010 lines 29-30's exact labels. No status given -> '—'."""
    level_set, values = golden_scenario
    table = build_table(golden, level_set=level_set, scenario=values)
    total = table.rows[-1]
    assert table.rows[0].cell(ColumnId.STATUS).value is None
    assert table.rows[0].cell(ColumnId.STATUS).reason
    assert total.cell(ColumnId.STATUS).value is None
    assert total.cell(ColumnId.STATUS).reason

    table2 = build_table(
        golden, level_set=level_set, scenario=values,
        leg_statuses=["Open", "Open", "Open", "Open"],
        strategy_health=StrategyHealth.WATCH,
    )
    for row in table2.rows[:4]:
        assert row.cell(ColumnId.STATUS).value == "Open"
    assert table2.rows[-1].cell(ColumnId.STATUS).value == "Watch"


def test_strategy_health_labels_match_adr_010_exactly():
    """ADR-010 lines 29-30 (Q20 = B, T1 #41): the owner's exact four strategy-health labels."""
    assert {h.value for h in StrategyHealth} == {
        "Healthy", "Watch", "Adjustment opportunity", "Exit condition reached",
    }


def test_leg_statuses_length_must_match_legs(golden):
    """Fail closed: leg_statuses must have one entry per leg."""
    with pytest.raises(ValueError):
        build_table(golden, leg_statuses=["Open"])


def test_strategy_health_rejects_a_plain_string(golden):
    """Fail closed: strategy_health must be a StrategyHealth, not an arbitrary string."""
    with pytest.raises(ValueError):
        build_table(golden, strategy_health="Healthy")


def test_build_table_without_scenario_leaves_no_scenario_columns():
    """No scenario view given: no scenario level columns, and Lower/Upper BE show unavailable, not an error."""
    inputs = nifty_input(nifty_leg(*row) for row in [
        (Action.BUY, Instrument.PE, "22800", "42.50", "38.20", "0.117446"),
    ])
    table = build_table(inputs)
    ids = table.column_ids
    assert ids == tuple(FIXED_ORDER) + tuple(TRAILING_ORDER)
    total = table.rows[-1]
    assert total.cell(ColumnId.LOWER_BE).value is None
    assert total.cell(ColumnId.LOWER_BE).reason


def test_build_table_rejects_mismatched_inputs_type():
    """Fail closed: build_table refuses a non-StrategyInput."""
    with pytest.raises(ValueError):
        build_table("not a strategy input")


def test_build_table_rejects_level_set_without_scenario(golden, golden_scenario):
    """Fail closed: level_set and scenario must be given together."""
    level_set, _values = golden_scenario
    with pytest.raises(ValueError):
        build_table(golden, level_set=level_set)
