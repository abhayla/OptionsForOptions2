"""GC-UI defect T-1: the Greeks TOTAL row carries per-unit figures (per_unit, per_unit_display) like every leg row.

RCA: the TOTAL cells carried only the per-position value, so the default Per unit view printed "-" for every total.
Core: TOTAL per-unit Greek = sum over legs of (quantity_i / gcd(all quantities)) x the leg row's own signed per_unit
(the leg figure already carries the side's sign, so a SELL leg is not negated again). Absent with the existing
reason when any leg lacks it (never a partial sum). IV has no total. Real rows: strategy 54 and the calendar on the
recorded 2026-10-08 replay (the round-4 Decay fixtures).
"""
from __future__ import annotations

import dataclasses
from decimal import ROUND_HALF_UP, Decimal

import pytest
from ofo.engine.legs import Instrument
from ofo.errors.explanations import render_explanation
from ofo.outcome import build_outcome
from ofo.table import build_table
from ofo.table.columns import ColumnId
from outcome._both_curves_cases import CALENDAR, S54, definition, snapshot
from outcome.test_decay_column import VALUATION, _model, _rows, market

GREEKS = (ColumnId.DELTA, ColumnId.GAMMA, ColumnId.THETA, ColumnId.DECAY, ColumnId.VEGA)
PLACES = {ColumnId.DELTA: 2, ColumnId.GAMMA: 4, ColumnId.THETA: 2, ColumnId.DECAY: 2, ColumnId.VEGA: 2}


@pytest.fixture(scope="module")
def provider():
    return market()


def _table_rows(model):
    return {r.row_id: r for r in build_table(model).rows}


def _text(value: Decimal, places: int) -> str:
    text = f"{value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP):f}"
    return text[1:] if text.startswith("-") and not text.strip("-0.") else text  # the app never prints "-0.00"


@pytest.mark.parametrize("legs", [S54, CALENDAR], ids=["s54", "calendar"])
def test_total_per_unit_is_the_signed_sum_of_the_leg_per_units_on_the_real_reply(provider, legs):
    d = definition(provider, legs)
    rows = _rows(build_outcome(d, snapshot(provider, d), VALUATION))
    for col in GREEKS:
        name = col.value
        total = rows["TOTAL"][name]
        assert total["reason"] is None and total["per_unit"] is not None, name
        expected = sum(Decimal(rows[rid][name]["per_unit"]) for rid in ("1", "2"))  # equal lots: weight 1
        assert abs(Decimal(total["per_unit"]) - expected) <= Decimal("0.0002"), name
        assert abs(Decimal(total["per_unit_display"]) - expected) <= Decimal(10) ** -PLACES[col], name
        assert total["per_unit_display"] == _text(Decimal(total["per_unit_display"]), PLACES[col]), name
        # per-position total / quantity (equal lots, gcd = quantity) equals the per-unit total
        quantity = Decimal(rows["1"]["quantity"]["value"])
        assert abs(Decimal(total["value"]) / quantity - Decimal(total["per_unit"])) <= Decimal("0.0002"), name


def test_a_sold_leg_is_not_negated_a_second_time(provider):
    """S54 is BUY 22600 CE / SELL 22800 CE: the SELL row's own per_unit delta is already negative; the total adds it."""
    rows = _table_rows(_model(provider, S54))
    leg1, leg2, total = (rows[r].cell(ColumnId.DELTA) for r in ("1", "2", "TOTAL"))
    assert leg2.per_unit < 0 < leg1.per_unit
    assert total.per_unit == leg1.per_unit + leg2.per_unit


def test_a_one_to_two_ratio_weights_the_second_leg_twice(provider):
    model = _model(provider, S54, lambda x: [x[0], dataclasses.replace(x[1], quantity=2 * x[0].quantity)])
    rows = _table_rows(model)
    for col in GREEKS:
        total = rows["TOTAL"].cell(col)
        assert total.per_unit == rows["1"].cell(col).per_unit + 2 * rows["2"].cell(col).per_unit, col
        assert total.per_unit_display == _text(total.per_unit, PLACES[col]), col
    quantity = Decimal(model.legs[0].quantity)
    delta = rows["TOTAL"].cell(ColumnId.DELTA)
    assert abs(delta.value / quantity - delta.per_unit) <= Decimal("0.01")  # per position / (lot x gcd)


def test_a_ratio_with_a_common_factor_divides_by_the_gcd(provider):
    """2:4 lots weigh exactly like 1:2 (weights are lots / gcd), so the per-unit total does not double."""
    base = _model(provider, S54, lambda x: [x[0], dataclasses.replace(x[1], quantity=2 * x[0].quantity)])
    doubled = _model(provider, S54, lambda x: [dataclasses.replace(x[0], quantity=2 * x[0].quantity),
                                               dataclasses.replace(x[1], quantity=4 * x[0].quantity)])
    a, b = (_table_rows(m)["TOTAL"].cell(ColumnId.VEGA).per_unit for m in (base, doubled))
    assert a is not None and abs(a - b) < Decimal("1e-6") * (1 + abs(a))


def test_one_leg_without_iv_makes_the_total_per_unit_absent_never_partial(provider):
    model = _model(provider, S54, lambda x: [x[0], dataclasses.replace(x[1], iv=None)])
    rows = _table_rows(model)
    for col in GREEKS:
        total = rows["TOTAL"].cell(col)
        assert total.per_unit is None and total.per_unit_display is None and total.value is None, col
        assert total.reason == render_explanation("table_reason_not_all_iv"), col


def test_a_futures_leg_adds_its_true_per_unit_to_the_total(provider):
    model = _model(provider, S54, lambda x: [dataclasses.replace(x[0], instrument=Instrument.FUT, strike=None,
                                                                 iv=None), x[1]])
    rows = _table_rows(model)
    fut, option, total = (rows[r].cell(ColumnId.DELTA) for r in ("1", "2", "TOTAL"))
    assert fut.per_unit == 1 and total.per_unit == fut.per_unit + option.per_unit
    assert rows["TOTAL"].cell(ColumnId.GAMMA).per_unit == rows["2"].cell(ColumnId.GAMMA).per_unit


def test_iv_has_no_total(provider):
    total = _table_rows(_model(provider, S54))["TOTAL"].cell(ColumnId.IV)
    assert total.per_unit is None
