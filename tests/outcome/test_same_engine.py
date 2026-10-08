"""REQ-034 AC-8 (W-063 core): on the real 2026-10-08 09:20 frames, the outcome of a NIFTY 13-Oct iron condor gives
every scenario cell equal to REQ-033 AC-1's formula computed HERE in Decimal (never by calling the engine), the
current level 22,533.25 is a column flagged current, and the payoff points are the same scenario values the table
shows, from ONE engine computation (counted).
"""
import datetime
from decimal import Decimal

import pytest

import ofo.scenario.views as views_module
from ofo.engine.legs import Action
from ofo.marketdata.kite_provider import IST
from ofo.outcome import OutcomeState, PlannedLeg, StrategyDefinition, build_outcome, read_snapshot
from ofo.table import TOTAL_ROW_ID, UXLevel

from marketdata._kite_fixture import all_instrument_ids, new_provider, replay

VALUATION = datetime.datetime(2026, 10, 8, 9, 20, 9, tzinfo=IST)
RATE = Decimal("0.065")
LOT = 65
# SELL 22800CE / BUY 23000CE / SELL 22400PE / BUY 22200PE, NIFTY 13-Oct (instrument ids from the recorded catalogue)
CONDOR = (
    ("NSE_FO:44624", Action.SELL, "CE", Decimal("22800")),
    ("NSE_FO:44632", Action.BUY, "CE", Decimal("23000")),
    ("NSE_FO:44604", Action.SELL, "PE", Decimal("22400")),
    ("NSE_FO:44595", Action.BUY, "PE", Decimal("22200")),
)
CURRENT = Decimal("22533.25")


@pytest.fixture(scope="module")
def replayed():
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    replay(provider, clock)
    return provider


def entries(provider):
    """Planned entry per leg = that leg's LTP in the replay (ADR-068: the LTP captured when the leg is added)."""
    out = {}
    for iid, *_ in CONDOR:
        q = provider.book.get(iid, VALUATION)
        out[iid] = q.ltp
    return out


def definition(provider):
    e = entries(provider)
    return StrategyDefinition("NIFTY", tuple(PlannedLeg(iid, action, 1, e[iid], VALUATION)
                                             for iid, action, _, _ in CONDOR))


def outcome_of(provider, **kw):
    d = definition(provider)
    snap = read_snapshot(provider, "NIFTY", [p.instrument_id for p in d.legs], VALUATION, RATE)
    return build_outcome(d, snap, UXLevel.STANDARD, VALUATION, **kw)


def formula_pnl(level, provider):
    """REQ-033 AC-1, written out: CE value max(L-K,0), PE max(K-L,0); BUY (V-E)xQ, SELL (E-V)xQ; summed over legs."""
    e = entries(provider)
    total = Decimal(0)
    for iid, action, kind, strike in CONDOR:
        value = max(level - strike, Decimal(0)) if kind == "CE" else max(strike - level, Decimal(0))
        total += ((value - e[iid]) if action is Action.BUY else (e[iid] - value)) * LOT
    return total


def test_every_scenario_cell_equals_the_independent_formula(replayed):
    out = outcome_of(replayed)
    assert out.state is OutcomeState.COMPUTED, out.reason
    total_row = next(r for r in out.table.rows if r.row_id == TOTAL_ROW_ID)
    levels = out.level_set.levels
    assert len(levels) >= 10
    for level in levels:
        assert total_row.cell(level).value == formula_pnl(level, replayed), level


def test_current_level_is_a_flagged_column(replayed):
    out = outcome_of(replayed)
    assert out.spot_level == CURRENT
    current = [c for c in out.level_set.columns if c.is_current]
    assert [c.level for c in current] == [CURRENT]
    spec = next(c for c in out.table.columns if c.id == CURRENT)
    assert spec.is_scenario_level and "CURRENT" in spec.markers


def test_payoff_points_equal_the_table_values_at_the_same_levels(replayed):
    out = outcome_of(replayed)
    total_row = next(r for r in out.table.rows if r.row_id == TOTAL_ROW_ID)
    assert [lvl for lvl, _ in out.payoff_points] == list(out.level_set.levels)
    for level, pnl in out.payoff_points:
        assert pnl == total_row.cell(level).value == formula_pnl(level, replayed)


def test_one_engine_computation_feeds_table_and_payoff(replayed, monkeypatch):
    """AC-8 mutation guard: a second engine path for the payoff makes this count 2."""
    calls = []
    real = views_module.scenario_grid

    def counting(*a, **k):
        calls.append(1)
        return real(*a, **k)

    monkeypatch.setattr(views_module, "scenario_grid", counting)
    outcome_of(replayed)
    assert len(calls) == 1


def test_expiry_scenarios_use_planned_entry_not_current_ltp(replayed):
    """REQ-033 AC-3: a planned entry that differs from the live LTP moves every scenario cell by (E'-E) x Q."""
    base = outcome_of(replayed)
    d = definition(replayed)
    bumped = StrategyDefinition("NIFTY", (PlannedLeg(d.legs[0].instrument_id, Action.SELL, 1,
                                                     d.legs[0].planned_entry + Decimal("10"), VALUATION),) + d.legs[1:])
    snap = read_snapshot(replayed, "NIFTY", [p.instrument_id for p in bumped.legs], VALUATION, RATE)
    out = build_outcome(bumped, snap, UXLevel.STANDARD, VALUATION)
    a, b = dict(base.payoff_points), dict(out.payoff_points)
    common = [lvl for lvl in a if lvl in b]  # breakeven columns move with the entry; the grid levels are shared
    assert len(common) >= 10
    for lvl in common:
        assert b[lvl] - a[lvl] == Decimal("10") * LOT, lvl


def test_breakevens_and_max_profit_loss_match_the_formula(replayed):
    e = entries(replayed)
    credit = (e["NSE_FO:44624"] - e["NSE_FO:44632"] + e["NSE_FO:44604"] - e["NSE_FO:44595"])
    out = outcome_of(replayed)
    s = out.summary
    assert s.max_profit == credit * LOT
    assert s.max_loss == (Decimal(200) - credit) * LOT
    assert s.lower_be == Decimal("22400") - credit
    assert s.upper_be == Decimal("22800") + credit
    assert s.breakevens == (s.lower_be, s.upper_be)
    assert s.what_can_i_lose.startswith("At most ₹")
    assert s.where_do_i_start_losing.startswith("If NIFTY ends below ")
    assert out.margin.state == "NOT_AVAILABLE_YET"
