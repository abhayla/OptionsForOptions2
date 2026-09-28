"""REQ-034 AC-8: the payoff graph and the scenario table come from the same engine and the same level set."""
from ofo.scenario import levels as levels_module
from ofo.scenario import outcome
from ofo.scenario import views as views_module
from ofo.scenario.views import View


def _spy(monkeypatch, module, name):
    calls = []
    real = getattr(module, name)

    def wrapper(*args, **kwargs):
        calls.append((args, kwargs))
        return real(*args, **kwargs)

    monkeypatch.setattr(module, name, wrapper)
    return calls


def test_ac8_table_and_graph_both_call_the_one_level_set_function(golden, settings, monkeypatch):
    """AC-8: scenario_table and payoff_graph each call build_level_set and scenario_values; same levels, same values."""
    config = settings.for_index("NIFTY")
    level_calls = _spy(monkeypatch, levels_module, "build_level_set")
    value_calls = _spy(monkeypatch, views_module, "scenario_values")
    for view in View:
        table = outcome.scenario_table(golden, config, view)
        graph = outcome.payoff_graph(golden, config, view)
        assert graph.points == tuple(zip(table.values.levels, table.values.totals))
        assert tuple(level for level, _ in graph.points) == table.level_set.levels
        assert graph.current == table.level_set.current
        assert graph.breakevens == table.level_set.breakevens
        assert graph.label == table.values.label
    assert len(level_calls) == 4 and len(value_calls) == 4


def test_ac8_graph_unavailable_with_same_reason_as_table(settings):
    """AC-8 negative: when Estimated Now is unavailable the graph is empty and carries the table's reason."""
    from decimal import Decimal as D

    from ofo.engine.legs import Action, Instrument
    from scenario_fixtures import nifty_input, nifty_leg

    inputs = nifty_input([nifty_leg(Action.SELL, Instrument.PE, "23000", "86.00")])
    config = settings.for_index("NIFTY")
    table = outcome.scenario_table(inputs, config, View.ESTIMATED_NOW)
    graph = outcome.payoff_graph(inputs, config, View.ESTIMATED_NOW)
    assert graph.points == ()
    assert graph.unavailable_reason == table.values.unavailable_reason is not None
    assert graph.current == D("23047")
