"""GC-BM F-8 (REQ-083 AC-2/AC-7, scenario-calculations section 3, Sensibull S-012): the payoff GRAPH's points include
every option leg's strike inside the range, each valued by the one engine, so the drawn line has its kinks exactly at
the strikes; the scenario TABLE keeps its columns (Q33D = C: grid + CURRENT + 0-P&L), byte for byte.

Measured live 2026-10-27 (walk 1 U-19/U-21): a 1-lot NIFTY short iron condor 22500 PE B / 22650 PE S / 22950 CE S /
23100 CE B at 110.00 / 166.00 / 101.05 / 59.10 was drawn from 22600 (Rs 3,116.75) straight to 22700 (Rs 6,366.75), so
the chart read about Rs 4,700 at 22650 where the true at-expiry P&L is Rs 6,366.75 (the flat top). Here the same strikes
and entries on the real 2026-10-08 NIFTY 13-Oct catalogue (lot 65; the at-expiry P&L depends only on strikes, entries
and quantity). Hand-computed: net credit (166.00 + 101.05 - 110.00 - 59.10) = 97.95 x 65 = Rs 6,366.75; max loss
(150 - 97.95) x 65 = Rs 3,383.25.
"""
from decimal import Decimal

import pytest

import ofo.scenario.views as views_module
from marketdata._kite_fixture import all_instrument_ids, new_provider_with_futures, replay
from ofo.engine.legs import Action
from ofo.errors.explanations import render_explanation
from ofo.outcome import OutcomeState, PlannedLeg, StrategyDefinition, build_outcome, from_entries, read_snapshot
from ofo.outcome.serialize import outcome_to_dict
from ofo.scenario.views import View
from ofo.table import TOTAL_ROW_ID
from outcome.test_same_engine import RATE, VALUATION

LOT = 65
# (instrument id, action, strike, kind, entry) - NIFTY 13-Oct, from the recorded catalogue
CONDOR = (
    ("NSE_FO:44613", Action.BUY, Decimal("22500"), "PE", Decimal("110.00")),
    ("NSE_FO:44619", Action.SELL, Decimal("22650"), "PE", Decimal("166.00")),
    ("NSE_FO:44630", Action.SELL, Decimal("22950"), "CE", Decimal("101.05")),
    ("NSE_FO:44646", Action.BUY, Decimal("23100"), "CE", Decimal("59.10")),
)
STRIKE_VALUES = {Decimal("22500"): Decimal("-3383.25"), Decimal("22650"): Decimal("6366.75"),
                 Decimal("22950"): Decimal("6366.75"), Decimal("23100"): Decimal("-3383.25")}
CALL_23000 = "NSE_FO:44632"  # 23000 CE 13-Oct: a strike that IS a grid level
PE_22650_19OCT = "NSE_FO:47142"  # 22650 PE 19-Oct: a second expiry


@pytest.fixture(scope="module")
def market():
    provider, clock, items, futures = new_provider_with_futures("NIFTY")
    provider.subscribe(all_instrument_ids(items))
    replay(provider, clock)
    c = futures[1].contract
    return provider, f"{c.exchange_segment}:{c.exchange_token}"


def _definition(legs):
    return StrategyDefinition("NIFTY", tuple(PlannedLeg(iid, action, 1, entry, VALUATION)
                                             for iid, action, entry in legs))


def _condor_legs():
    return [(iid, action, entry) for iid, action, _, _, entry in CONDOR]


def _outcome(provider, legs, **kw):
    d = _definition(legs)
    snap = read_snapshot(provider, "NIFTY", [p.instrument_id for p in d.legs], VALUATION, RATE)
    out = build_outcome(d, snap, VALUATION, **kw)
    assert out.state is OutcomeState.COMPUTED, out.reason
    return out


def _formula(level):
    """REQ-033 AC-1 written out in Decimal: CE max(L-K,0), PE max(K-L,0); BUY (V-E)xQ, SELL (E-V)xQ."""
    total = Decimal(0)
    for _, action, strike, kind, entry in CONDOR:
        value = max(level - strike, Decimal(0)) if kind == "CE" else max(strike - level, Decimal(0))
        total += ((value - entry) if action is Action.BUY else (entry - value)) * LOT
    return total


def test_core_condor_strikes_are_graph_points_with_the_engine_values(market):
    """Attack 1. Fails before F-8: 22650 and 22950 were not points (the line cut the corner from 22600 to 22700)."""
    provider, _ = market
    out = _outcome(provider, _condor_legs())
    points = dict(out.payoff_points)
    for strike, value in STRIKE_VALUES.items():
        assert strike in points, strike
        assert points[strike] == value == _formula(strike), strike
    assert points[Decimal("22650")] != (points[Decimal("22600")] + points[Decimal("22700")]) / 2  # not the chord
    levels = [lvl for lvl, _ in out.payoff_points]
    assert levels == sorted(levels)
    for level, pnl in out.payoff_points:  # every graph point is the engine's exact value
        assert pnl == _formula(level), level
    sent = outcome_to_dict(out)["payoff"]["points"]  # the reply carries them as exact strings
    assert {"level": "22650", "pnl": "6366.75"} in sent and {"level": "22950", "pnl": "6366.75"} in sent


def test_strike_levels_never_become_scenario_table_columns(market):
    """Attack 5 (Q33D = C): the table columns and its scenario block are the grid + CURRENT + 0-P&L only."""
    provider, _ = market
    out = _outcome(provider, _condor_legs())
    assert Decimal("22650") not in out.level_set.levels and Decimal("22950") not in out.level_set.levels
    assert out.scenario.levels == out.level_set.levels
    total = next(r for r in out.table.rows if r.row_id == TOTAL_ROW_ID)
    scenario_cols = [c.id for c in out.table.columns if c.is_scenario_level]
    assert scenario_cols == list(out.level_set.levels)
    assert list(out.scenario.totals) == [total.cell(lvl).value for lvl in out.level_set.levels]
    body = outcome_to_dict(out)["scenario"]
    assert [x["level"] for x in body["levels"]] == [str(lvl) for lvl in out.level_set.levels]
    # the graph holds every table level with the same value, plus the strikes off the grid, nothing else
    graph = dict(out.payoff_points)
    for lvl, pnl in zip(out.level_set.levels, out.scenario.totals, strict=True):
        assert graph[lvl] == pnl
    assert set(graph) - set(out.level_set.levels) == {Decimal("22650"), Decimal("22950")}


def test_one_engine_computation_still_feeds_table_and_graph(market, monkeypatch):
    calls = []
    real = views_module.scenario_grid

    def counting(*a, **k):
        calls.append(1)
        return real(*a, **k)

    monkeypatch.setattr(views_module, "scenario_grid", counting)
    _outcome(market[0], _condor_legs())
    assert len(calls) == 1


def test_a_strike_on_the_grid_is_not_duplicated(market):
    """Attack 2: 23000 is a grid level already; it appears once."""
    provider, _ = market
    out = _outcome(provider, [(CALL_23000, Action.BUY, Decimal("81.30")), (CONDOR[2][0], Action.SELL, Decimal("101.05"))])
    levels = [lvl for lvl, _ in out.payoff_points]
    assert len(levels) == len(set(levels))
    assert levels.count(Decimal("23000")) == 1 and Decimal("22950") in levels


def test_estimated_now_points_include_the_strikes(market):
    provider, _ = market
    out = _outcome(provider, _condor_legs(), view=View.ESTIMATED_NOW)
    assert out.scenario.available, out.scenario.unavailable_reason
    points = dict(out.payoff_points)
    for strike in STRIKE_VALUES:
        assert strike in points and isinstance(points[strike], Decimal)
    assert out.scenario.levels == out.level_set.levels  # the table's estimate stays on its columns
    for lvl, pnl in zip(out.level_set.levels, out.scenario.totals, strict=True):
        assert points[lvl] == pnl


def test_futures_leg_adds_no_level_and_does_not_crash(market):
    """Attack 3: a futures leg has no strike; a lone future's graph is exactly the table's levels."""
    provider, future = market
    out = _outcome(provider, [(future, Action.BUY, Decimal("22600"))])
    assert [lvl for lvl, _ in out.payoff_points] == list(out.level_set.levels)


def test_mixed_expiry_still_has_no_at_expiry_curve(market):
    """Attack 4 (G-065, ADR-143): no points, the reason kept."""
    provider, _ = market
    legs = _condor_legs()
    legs[1] = (PE_22650_19OCT, Action.SELL, Decimal("166.00"))
    out = _outcome(provider, legs)
    assert out.payoff_points == ()
    assert not out.scenario.available
    assert out.scenario.unavailable_reason == render_explanation("mixed_expiry_worst_case")


def test_a_user_range_keeps_only_the_strikes_inside_it(market):
    from ofo.scenario.levels import RangeOverride

    provider, _ = market
    out = _outcome(provider, _condor_legs(), override=RangeOverride(Decimal("22600"), Decimal("23000")))
    levels = {lvl for lvl, _ in out.payoff_points}
    assert {Decimal("22650"), Decimal("22950")} <= levels
    assert Decimal("22500") not in levels and Decimal("23100") not in levels


def test_from_your_prices_graph_has_the_strikes_too(market):
    provider, _ = market
    d = _definition(_condor_legs())
    snap = read_snapshot(provider, "NIFTY", [p.instrument_id for p in d.legs], VALUATION, RATE)
    stored = {p.instrument_id: snap.legs[p.instrument_id].contract for p in d.legs}
    out = from_entries(d, None, stored, VALUATION)
    assert out is not None
    points = dict(out.payoff_points)
    for strike, value in STRIKE_VALUES.items():
        assert points[strike] == value
    assert Decimal("22650") not in out.level_set.levels
    # Estimated Now from your prices: unavailable, no points
    assert from_entries(d, None, stored, VALUATION, view=View.ESTIMATED_NOW).payoff_points == ()
