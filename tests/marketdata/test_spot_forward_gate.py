"""W-060 round 3 class test (REQ-072 AC-2, AC-3; ADR-061, ADR-063).

Class: a stale or missing index value used silently in a calculation, and IV/Greeks not using the parity forward with
its label and timestamp. Every product entry point x spot {missing, unhealthy, unavailable, stale, delayed, available}
x forward {parity, spot fallback, unavailable, mismatched spot level / time / health / valuation / rate}.

Red on c8e09c6: build_table computed a DELTA from an UNAVAILABLE spot with no label, and estimate_now ran with
spot=None. Expected Greeks come from Hull ch. 17 (an index paying a continuous yield q), computed here with math, on the
real 2026-10-08 09:20:09 NIFTY 13-Oct forward (work/W-060.md proof), never from running the new code.
"""
import dataclasses
import datetime
import math
from decimal import Decimal

import pytest

from ofo.engine.inputs import LegInput, SpotReading, StrategyInput
from ofo.engine.legs import Action, Instrument
from ofo.engine.model import ModelInputs, SpotRefused, estimate, expiry_model, greeks, implied_vol, model_inputs
from ofo.marketdata.forward import ForwardUnavailable, parity_forward, spot_fallback_forward
from ofo.marketdata.kite_provider import IST
from ofo.rules.inputs import DataHealth
from ofo.scenario.config import ScenarioSettings
from ofo.scenario.levels import build_level_set
from ofo.scenario.outcome import payoff_graph, scenario_table
from ofo.scenario.views import View, scenario_values
from ofo.table.columns import ColumnId
from ofo.table.model import build_table

from _kite_fixture import all_instrument_ids, new_provider, replay

VALUATION = datetime.datetime(2026, 10, 8, 9, 20, 9, tzinfo=IST)
RATE = Decimal("0.065")
EXPIRY = datetime.date(2026, 10, 13)
CONFIG = ScenarioSettings().for_index("NIFTY")
STRIKE, VOL, QTY = Decimal("22550"), Decimal("0.12"), 65


@pytest.fixture(scope="module")
def live_forward():
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    replay(provider, clock)
    return parity_forward(provider.option_chain_snapshot("NIFTY", EXPIRY), provider.underlying_quote("NIFTY"), EXPIRY,
                          VALUATION, RATE)


def _leg():
    return LegInput(underlying="NIFTY", contract="NSE_FO:44614", action=Action.BUY, instrument=Instrument.CE,
                    strike=STRIKE, expiry=EXPIRY, quantity=QTY, premium=Decimal("100.00"), iv=VOL)


def _inputs(reading):
    return StrategyInput(underlying="NIFTY", spot=reading, valuation_time=VALUATION, rate=RATE, legs=(_leg(),))


def _reading(f, health=DataHealth.AVAILABLE):
    return SpotReading(level=f.spot, at=f.spot_timestamp, health=health)


def _forward_on(f, health, source):
    """The forward read on a reading of ``health`` from the same snapshot (parity), or its spot fallback."""
    if source == "parity":
        return dataclasses.replace(f, spot_health=health)
    return spot_fallback_forward(EXPIRY, f.spot, f.spot_timestamp, VALUATION, RATE, spot_health=health)


def _hull_call_delta(s, k, t, r, q, v):
    d1 = (math.log(s / k) + (r - q + v * v / 2) * t) / (v * math.sqrt(t))
    return math.exp(-q * t) * 0.5 * (1 + math.erf(d1 / math.sqrt(2)))


def _all_outputs(model):
    """Every product entry point on one gated model: (name, value, spot_level, spot_at, label)."""
    ls = build_level_set(model, CONFIG)
    est_view = scenario_values(ls, model, View.ESTIMATED_NOW)
    table = build_table(model, level_set=ls, scenario=est_view)
    graph = payoff_graph(model, CONFIG, View.ESTIMATED_NOW)
    st = scenario_table(model, CONFIG, View.ESTIMATED_NOW)
    est = estimate(model, model.spot_level)
    em = model.expiry_model(EXPIRY)
    iv = implied_vol(em, Instrument.CE, Decimal("100.00"), STRIKE)
    g = greeks(em, Instrument.CE, STRIKE, VOL)
    return [
        ("scenario_values", est_view.totals, est_view.spot_level, est_view.spot_at, est_view.output_label),
        ("scenario_table", st.values.totals, st.values.spot_level, st.values.spot_at, st.values.output_label),
        ("payoff_graph", graph.points, graph.spot_level, graph.spot_at, graph.output_label),
        ("build_table", table.rows[-1].cell(ColumnId.DELTA).value, table.spot_level, table.spot_at, table.output_label),
        ("estimate", est.total, est.spot_level, est.spot_at, est.label),
        ("implied_vol", iv.iv, iv.spot_level, iv.spot_at, iv.label),
        ("greeks", g.greeks.delta, g.spot_level, g.spot_at, g.label),
    ]


# ---- spot x forward: computed, each output carries the spot, its time and the exact label ------------------------
@pytest.mark.parametrize("health, data", [(DataHealth.AVAILABLE, None), (DataHealth.STALE, "stale since 09:20 IST"),
                                          (DataHealth.DELAYED, "delayed, as of 09:20 IST")])
@pytest.mark.parametrize("source, model_label", [("parity", None), ("spot fallback", "estimated from spot")])
def test_usable_spot_computes_and_every_output_is_labelled(live_forward, health, data, source, model_label):
    f = live_forward
    model = model_inputs(_inputs(_reading(f, health)), {EXPIRY: _forward_on(f, health, source)})
    expected = "; ".join(x for x in (data, model_label) if x) or None
    for name, value, level, at, label in _all_outputs(model):
        assert value is not None and value != (), name
        assert (level, at) == (Decimal("22533.25"), f.spot_timestamp), name
        assert label == expected, (name, label, expected)


def test_table_greeks_use_spot_and_the_expiry_yield_per_hull(live_forward):
    """The table's DELTA is the engine's at S with q (ADR-063), not at a bare level with q = 0."""
    f = live_forward
    assert f.source == "parity" and f.implied_yield > Decimal("0.05")
    table = build_table(model_inputs(_inputs(_reading(f)), {EXPIRY: f}))
    hull = _hull_call_delta(float(f.spot), float(STRIKE), float(f.years), float(RATE), float(f.implied_yield),
                            float(VOL)) * QTY
    no_yield = _hull_call_delta(float(f.spot), float(STRIKE), float(f.years), float(RATE), 0.0, float(VOL)) * QTY
    delta = table.rows[0].cell(ColumnId.DELTA).value
    assert abs(float(delta) - hull) <= 1e-4, (delta, hull)
    assert abs(float(delta) - no_yield) > 0.01  # q = 0 would be visibly different (the mutant this test kills)
    assert table.rows[-1].cell(ColumnId.DELTA).value == delta


# ---- refused states -----------------------------------------------------------------------------------------------
def test_missing_spot_cannot_be_built():
    with pytest.raises(ValueError, match="SpotReading"):
        _inputs(None)
    with pytest.raises(ValueError, match="SpotReading"):
        _inputs(Decimal("22533.25"))  # a bare level is not a reading
    with pytest.raises(SpotRefused, match="bare level"):
        expiry_model(None, None)


@pytest.mark.parametrize("health", [DataHealth.UNHEALTHY, DataHealth.UNAVAILABLE])
def test_unusable_spot_is_refused_at_the_gate(live_forward, health):
    f = live_forward
    with pytest.raises(SpotRefused, match=health.value):
        model_inputs(_inputs(_reading(f, health)), {EXPIRY: _forward_on(f, health, "spot fallback")})
    with pytest.raises(SpotRefused, match=health.value):
        expiry_model(_reading(f, health), f)


def test_missing_forward_is_refused(live_forward):
    reading = _reading(live_forward)
    for forwards in ({}, {datetime.date(2026, 10, 19): live_forward}, None):
        with pytest.raises(ForwardUnavailable):
            model_inputs(_inputs(reading), forwards)


@pytest.mark.parametrize("change, what", [
    (dict(spot=Decimal("22540.00")), "spot level"),
    (dict(spot_timestamp=VALUATION + datetime.timedelta(seconds=5)), "spot time"),
    (dict(spot_health=DataHealth.STALE), "spot health"),
    (dict(valuation_time=VALUATION + datetime.timedelta(minutes=1)), "valuation time"),
    (dict(rate=Decimal("0.07")), "rate"),
])
def test_forward_read_on_another_reading_is_refused(live_forward, change, what):
    f = live_forward
    bad = dataclasses.replace(f, **change)
    with pytest.raises(ForwardUnavailable, match=what):
        model_inputs(_inputs(_reading(f)), {EXPIRY: bad})


def test_every_entry_point_refuses_an_ungated_input(live_forward):
    """The type is the gate: a StrategyInput (or a hand-built ModelInputs) is refused by every product entry."""
    raw = _inputs(_reading(live_forward))
    model = model_inputs(raw, {EXPIRY: live_forward})
    ls = build_level_set(model, CONFIG)
    calls = [lambda: build_level_set(raw, CONFIG), lambda: scenario_values(ls, raw, View.ESTIMATED_NOW),
             lambda: scenario_table(raw, CONFIG), lambda: payoff_graph(raw, CONFIG), lambda: build_table(raw),
             lambda: estimate(raw, Decimal("22533.25")),
             lambda: greeks(raw, Instrument.CE, STRIKE, VOL), lambda: implied_vol(raw, Instrument.CE,
                                                                                  Decimal("100.00"), STRIKE)]
    for call in calls:
        with pytest.raises(ValueError, match="ModelInputs|ExpiryModel"):
            call()
    with pytest.raises(TypeError, match="only by"):
        ModelInputs(raw, model.spot_level, model.spot_at, None, model.expiries, None)
    with pytest.raises(TypeError):
        dataclasses.replace(model, inputs=raw)  # an edited copy cannot be made outside the gate either
    with pytest.raises(AttributeError, match="immutable"):
        model.spot_level = Decimal("1")
    with pytest.raises(TypeError):
        model.expiries[EXPIRY] = None
