"""REQ-081 AC-4 / ADR-167 (1), (3), (4) (W-154): every At Expiry curve and scenario value is the engine's P&L BEFORE
charges and before exercise STT; the charges ride beside the values (``ScenarioValues.charges``) and only the max-profit
and max-loss sentences include them.

Core: scenario_values(At Expiry) totals == the engine grid totals at every level, with and without a rate table, on the
2026-10-08 recorded frames (a NIFTY 13-Oct condor) and on the golden condor (a bought option in the money at 22000 and
24000). Before the fix the totals were grid - round trip - exercise STT (views.py:97).
Hand figures (golden condor, tests/scenario/test_expiry_values_with_charges.py): 6,825 at 23,047; -8,175 at 22,000 and
24,000 (grid, before charges); the max loss on the replay is 8,245.25 before charges.

Spec basis: ADR-167 "Every payoff curve and every scenario value on the"; ADR-167 "stays out of the curves and appears";
scenario-calculations.md "the max-loss and max-profit sentences still include charges per ADR-082 (2)".
Sensibull: screen 022 (values before charges and taxes, charges shown separately).
"""
import datetime
from decimal import Decimal as D

import pytest
from marketdata._kite_fixture import all_instrument_ids, new_provider, replay
from ofo.engine import scenario_grid
from ofo.engine.legs import Action
from ofo.marketdata.kite_provider import IST
from ofo.outcome import OutcomeState, PlannedLeg, StrategyDefinition, build_outcome, read_snapshot
from ofo.scenario.levels import build_level_set
from ofo.scenario.views import View, scenario_values
from test_expiry_values_with_charges import RATES

VALUATION = datetime.datetime(2026, 10, 8, 9, 20, 9, tzinfo=IST)
REPLAY_CONDOR = (
    ("NSE_FO:44624", Action.SELL), ("NSE_FO:44632", Action.BUY), ("NSE_FO:44604", Action.SELL),
    ("NSE_FO:44595", Action.BUY),
)
REPLAY_MAX_LOSS = D("8245.25")


@pytest.fixture(scope="module")
def replayed():
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    replay(provider, clock)
    return provider


def outcome_of(provider, rates, view=View.AT_EXPIRY):
    d = StrategyDefinition("NIFTY", tuple(PlannedLeg(i, a, 1, provider.book.get(i, VALUATION).ltp, VALUATION)
                                          for i, a in REPLAY_CONDOR))
    snap = read_snapshot(provider, "NIFTY", [p.instrument_id for p in d.legs], VALUATION, D("0.065"))
    out = build_outcome(d, snap, VALUATION, rates=rates, view=view)
    assert out.state is OutcomeState.COMPUTED, out.reason
    return out


def test_core_probe_replay_totals_equal_the_grid_not_grid_minus_charges(replayed):
    plain, priced = outcome_of(replayed, None), outcome_of(replayed, RATES)
    charges = priced.summary.charges
    assert charges is not None and charges > 0
    print(f"\nPROBE replay: charges={charges} levels={len(priced.scenario.levels)}")
    for level, grid_total, shown in zip(plain.scenario.levels, plain.scenario.totals, priced.scenario.totals,
                                        strict=True):
        print(f"  level {level}: grid {grid_total}  shown {shown}  diff {grid_total - shown}")
    assert priced.scenario.levels == plain.scenario.levels
    assert priced.scenario.totals == plain.scenario.totals  # the grid, at every level
    assert priced.scenario.charges == charges  # carried beside the values (ADR-167 (2))
    assert [p[1] for p in priced.payoff_points] == [p[1] for p in plain.payoff_points]
    # ADR-167 (3): the sentence figure still includes the charges and does not come from the curve
    assert priced.summary.max_loss == REPLAY_MAX_LOSS + charges


@pytest.mark.parametrize("rates", [None, RATES], ids=["no_rates", "rates"])
def test_guard_every_view_and_rate_pair_over_the_golden_condor_equals_the_engine_grid(golden, settings, rates):
    ls = build_level_set(golden, settings.for_index("NIFTY"))
    grid = scenario_grid(golden.strategy, ls.levels)
    for view in View:
        v = scenario_values(ls, golden, view, rates=rates)
        if view is View.AT_EXPIRY:
            assert v.totals == grid.totals and v.leg_rows == grid.leg_rows, view  # no charges, no exercise STT
            assert (v.charges is None) == (rates is None)
        else:
            assert v.charges is None  # Estimated Now never reads the rates
    by_level = dict(zip(ls.levels, scenario_values(ls, golden, View.AT_EXPIRY, rates=rates).totals, strict=True))
    assert by_level[D("23047")] == D("6825")  # hand figure, before charges
    assert by_level[D("22000")] == D("-8175") and by_level[D("24000")] == D("-8175")  # bought option ITM: no exercise STT
