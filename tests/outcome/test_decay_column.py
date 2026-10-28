"""GC-UI step 4 server round 4 (D-B34, REQ-145 AC-2): the Greeks table's Decay column, per leg and on the TOTAL row.

REQ-145 AC-2: "Decay is in rupees for the ticked legs, computed on the server from the engine reply, exact decimal
(ADR-008)". Definition (F-63): a leg's Decay = (model value at the next market open - model value now) x quantity x
sign (+1 BUY / -1 SELL), the same spot, IV, rate and q, calendar days / 365 like every model figure; TOTAL = the sum of
the legs, absent when any leg is absent (never a partial sum).

Real rows: strategy 54 (BUY 22600 CE / SELL 22800 CE, 1 lot, 13-Oct) and the calendar on the recorded 2026-10-08 NIFTY
replay (valuation Thu 09:20:09 IST, next open Fri 2026-10-09 09:15 IST). The expected values below are recomputed in
this test from the reply's own IV and the engine's model inputs with ``math.erf`` (no Sensibull number, no figure
typed from memory). Answer states: leg with IV, leg without IV, FUT leg (a true 0), expiry-day leg (its remaining
time value is lost), no next open, TOTAL with one leg absent.
"""
from __future__ import annotations

import dataclasses
import datetime
import math
from decimal import Decimal

import pytest
from ofo.engine.black_scholes import GREEK_STEP
from ofo.engine.inputs import LegInput, StrategyInput
from ofo.engine.legs import Action, Instrument
from ofo.engine.model import model_inputs
from ofo.errors.explanations import render_explanation
from ofo.market_calendar import next_open
from ofo.outcome import build_outcome
from ofo.outcome.serialize import outcome_to_dict
from ofo.scenario.spot import spot_reading
from ofo.table import build_table
from ofo.table.columns import LEADING_COLUMNS, ColumnId
from outcome._both_curves_cases import CALENDAR, S54, as_json, definition, market, snapshot
from outcome.test_same_engine import VALUATION

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
NEXT_OPEN = datetime.datetime(2026, 10, 9, 9, 15, tzinfo=IST)  # Fri after Thu 2026-10-08 (no holiday in between)


@pytest.fixture(scope="module")
def provider():
    return market()


def _ncdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _bsm(s: float, k: float, t: float, r: float, q: float, v: float, kind: Instrument) -> float:  # noqa: PLR0913
    if t <= 0:
        return max(s - k, 0.0) if kind is Instrument.CE else max(k - s, 0.0)
    d1 = (math.log(s / k) + (r - q + 0.5 * v * v) * t) / (v * math.sqrt(t))
    d2 = d1 - v * math.sqrt(t)
    if kind is Instrument.CE:
        return s * math.exp(-q * t) * _ncdf(d1) - k * math.exp(-r * t) * _ncdf(d2)
    return k * math.exp(-r * t) * _ncdf(-d2) - s * math.exp(-q * t) * _ncdf(-d1)


def _expected_unit_decay(model, leg, until: datetime.datetime) -> float:
    """Unsigned per-unit decay, recomputed here: calendar seconds / (365 x 86400) to the 15:30 IST expiry close."""
    em = model.expiry_model(leg.expiry)
    close = datetime.datetime.combine(leg.expiry, datetime.time(15, 30), IST)
    t_now = (close - model.inputs.valuation_time).total_seconds() / (365 * 86400)
    t_then = max((close - until).total_seconds(), 0.0) / (365 * 86400)
    args = (float(em.level), float(leg.strike))
    r, q, v = float(em.forward.rate), float(em.dividend_yield), float(leg.iv)
    return _bsm(*args, t_then, r, q, v, leg.instrument) - _bsm(*args, t_now, r, q, v, leg.instrument)


def _rows(out) -> dict:
    return {r["row_id"]: r["cells"] for r in as_json(outcome_to_dict(out))["table"]["rows"]}


def _model(provider, legs, replace=None):
    """The reply's own engine inputs: its legs (with the IV the reply solved), spot and forwards, through the gate."""
    d = definition(provider, legs)
    snap = snapshot(provider, d)
    out = build_outcome(d, snap, VALUATION)
    inputs = [LegInput("NIFTY", x.symbol or x.instrument_id, x.action, x.instrument, x.strike, x.expiry, x.quantity,
                       x.planned_entry, x.ltp, x.iv) for x in out.legs]
    if replace is not None:
        inputs = replace(inputs)
    return model_inputs(StrategyInput("NIFTY", spot_reading(snap.spot), VALUATION, snap.rate, tuple(inputs)),
                        snap.forwards)


def test_the_replay_valuation_has_the_next_open_this_test_assumes():
    assert next_open(VALUATION) == NEXT_OPEN


def test_decay_column_sits_between_theta_and_vega_in_the_greek_columns():
    assert ColumnId.DECAY.value == "decay"
    greeks = [c for c in LEADING_COLUMNS if c in (ColumnId.DELTA, ColumnId.GAMMA, ColumnId.THETA, ColumnId.DECAY,
                                                  ColumnId.VEGA)]
    assert greeks == [ColumnId.DELTA, ColumnId.GAMMA, ColumnId.THETA, ColumnId.DECAY, ColumnId.VEGA]
    assert render_explanation("table_column_label", column=ColumnId.DECAY) == "Decay"


@pytest.mark.parametrize("legs", [S54, CALENDAR], ids=["s54", "calendar"])
def test_each_leg_decay_is_the_model_revaluation_at_the_next_open_signed_and_total_is_the_sum(provider, legs):
    model = _model(provider, legs)
    d = definition(provider, legs)
    rows = _rows(build_outcome(d, snapshot(provider, d), VALUATION))
    total = Decimal(0)
    for i, leg in enumerate(model.legs, start=1):
        cell = rows[str(i)]["decay"]
        sign = 1 if leg.action is Action.BUY else -1
        unit = _expected_unit_decay(model, leg, NEXT_OPEN)
        assert cell["kind"] == "greek" and cell["reason"] is None
        assert float(cell["per_unit"]) == pytest.approx(sign * unit, abs=5e-5)  # signed, quantity 1, 4 dp (F-2)
        assert float(cell["value"]) == pytest.approx(sign * unit * leg.quantity, abs=1e-4)
        assert Decimal(cell["value"]) == Decimal(cell["value"]).quantize(GREEK_STEP)  # exact decimal, 4 dp
        assert cell["display"] == f"{Decimal(repr(sign * unit * leg.quantity)).quantize(Decimal('0.01')):f}"
        assert cell["per_unit_display"] == f"{Decimal(repr(sign * unit)).quantize(Decimal('0.01')):f}"
        total += Decimal(repr(sign * unit * leg.quantity))
    t = rows["TOTAL"]["decay"]
    assert t["reason"] is None and float(t["value"]) == pytest.approx(float(total), abs=1e-4)


def test_a_sold_leg_decays_in_the_sellers_favour(provider):
    """Signed like theta: the BUY 22600 CE loses value overnight (Decay < 0), the SELL 22800 CE gains (Decay > 0)."""
    d = definition(provider, S54)
    rows = _rows(build_outcome(d, snapshot(provider, d), VALUATION))
    assert Decimal(rows["1"]["decay"]["value"]) < 0 < Decimal(rows["2"]["decay"]["value"])
    for rid in ("1", "2"):  # same sign as theta, about one day of it (F-63: 0.74-0.84 overnight; not asserted)
        assert (Decimal(rows[rid]["decay"]["value"]) > 0) == (Decimal(rows[rid]["theta"]["value"]) > 0)


def test_a_leg_without_iv_has_no_decay_with_the_existing_reason_and_the_total_is_absent(provider):
    model = _model(provider, S54, lambda x: [x[0], dataclasses.replace(x[1], iv=None)])
    table = build_table(model)
    rows = {r.row_id: r for r in table.rows}
    leg = rows["2"].cell(ColumnId.DECAY)
    assert leg.value is None and leg.reason == render_explanation("table_reason_no_iv")
    assert rows["1"].cell(ColumnId.DECAY).value is not None  # the other leg still has its own
    total = rows["TOTAL"].cell(ColumnId.DECAY)
    assert total.value is None and total.reason == render_explanation("table_reason_not_all_iv")  # never partial
    assert total.display == render_explanation("cell_dash")


def test_no_next_open_leaves_decay_absent_with_a_reason_never_zero(provider):
    table = build_table(_model(provider, S54), decay_until=None)
    for row in table.rows:
        cell = row.cell(ColumnId.DECAY)
        assert cell.value is None and cell.reason == render_explanation("table_reason_no_next_open")


def test_a_futures_leg_has_a_true_zero_decay(provider):
    model = _model(provider, S54, lambda x: [dataclasses.replace(x[0], instrument=Instrument.FUT, strike=None,
                                                                 iv=None), x[1]])
    rows = {r.row_id: r for r in build_table(model).rows}
    cell = rows["1"].cell(ColumnId.DECAY)
    assert cell.value == Decimal(0) and cell.display == "0.00" and cell.reason is None
    assert rows["TOTAL"].cell(ColumnId.DECAY).value == rows["2"].cell(ColumnId.DECAY).value  # FUT adds nothing


def test_an_expiry_day_leg_loses_its_whole_remaining_time_value(provider):
    """RD-081: a leg whose expiry close (15:30 IST) is before the next open shows Decay = intrinsic - model value now
    (per unit, signed): its whole remaining time value, never a negative time."""
    model = _model(provider, S54)
    until = datetime.datetime(2026, 10, 14, 9, 15, tzinfo=IST)  # after the 13-Oct expiry close
    rows = {r.row_id: r for r in build_table(model, decay_until=until).rows}
    for i, leg in enumerate(model.legs, start=1):
        sign = 1 if leg.action is Action.BUY else -1
        em = model.expiry_model(leg.expiry)
        intrinsic = max(float(em.level) - float(leg.strike), 0.0)
        close = datetime.datetime.combine(leg.expiry, datetime.time(15, 30), IST)
        t_now = (close - VALUATION).total_seconds() / (365 * 86400)
        now = _bsm(float(em.level), float(leg.strike), t_now, float(em.forward.rate), float(em.dividend_yield),
                   float(leg.iv), leg.instrument)
        cell = rows[str(i)].cell(ColumnId.DECAY)
        assert float(cell.per_unit) == pytest.approx(sign * (intrinsic - now), abs=1e-6)
