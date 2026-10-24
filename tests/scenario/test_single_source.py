"""REQ-034 AC-8: the payoff graph and the scenario table come from the same engine and the same level set, on the
product's path: ONE build_outcome call (the outcome route and the live push call it) builds one level set and one
scenario computation; the payoff points are the table's TOTAL row at the same levels (real 2026-10-08 NIFTY frames)."""
from decimal import Decimal as D

import ofo.outcome.service as service_module
import pytest
from marketdata._kite_fixture import all_instrument_ids, new_provider, replay
from ofo.scenario.views import View
from ofo.table import TOTAL_ROW_ID
from outcome.test_same_engine import CURRENT, outcome_of

CALLS = len(View)  # one level set and one computation per build_outcome call, one call per view


@pytest.fixture(scope="module")
def replayed():
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    replay(provider, clock)
    return provider


def _spy(monkeypatch, module, name):
    calls = []
    real = getattr(module, name)

    def wrapper(*args, **kwargs):
        calls.append((args, kwargs))
        return real(*args, **kwargs)

    monkeypatch.setattr(module, name, wrapper)
    return calls


def test_ac8_graph_and_table_from_one_build_outcome_call(replayed, monkeypatch):
    """AC-8: per view, one call builds the level set once and computes once; points == the table's totals."""
    level_calls = _spy(monkeypatch, service_module, "build_level_set")
    value_calls = _spy(monkeypatch, service_module, "scenario_values")
    for view in View:
        out = outcome_of(replayed, view=view)
        values = out.scenario
        assert out.payoff_points == tuple(zip(values.levels, values.totals, strict=True))
        assert tuple(level for level, _ in out.payoff_points) == out.level_set.levels
        total_row = next(r for r in out.table.rows if r.row_id == TOTAL_ROW_ID)
        for level, total in out.payoff_points:
            assert total_row.cell(level).value == total, (view, level)
        assert out.level_set.current == CURRENT
        assert out.summary.breakevens == out.level_set.breakevens
        assert values.view is view
        assert (values.spot_level, values.spot_at) == (out.spot_level, out.spot_at)
    assert len(level_calls) == CALLS and len(value_calls) == CALLS


def test_ac8_graph_unavailable_with_same_reason_as_table(replayed, monkeypatch):
    """AC-8 negative: when Estimated Now is unavailable the graph is empty and the table carries the reason."""
    monkeypatch.setattr(service_module, "_leg_iv", lambda *a, **k: None)
    out = outcome_of(replayed, view=View.ESTIMATED_NOW)
    assert out.payoff_points == ()
    assert out.scenario.unavailable_reason is not None
    assert out.level_set.current == D("22533.25")
