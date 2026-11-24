"""D-12 (ADR-320 (1)) in the adjustment drawer's Compare: on expiry day the Theta row is replaced by "Decay left today",
the sum over the legs after each approach of the engine's per-unit decay left (``leg_decay_left_today``, carried as
``Context.leg_decay_left``) x lots x lot size x sign (BUY +1, SELL -1); other days the row is theta as before.
Real fixture: ADJ-02 (the scenario the Compare core test uses)."""
from __future__ import annotations

import dataclasses
from decimal import Decimal as D

from ofo.adjustment.compare import compare
from test_approach_compare import build_columns, row


def _units(cols):
    """A distinct per-unit decay for every symbol any approach holds (-0.01 x its place), so a dropped or doubled leg
    shows in the sum."""
    syms = sorted({x.tradingsymbol for c in cols for x in c.built.after})
    return {s: D("-0.01") * (i + 1) for i, s in enumerate(syms)}


def test_expiry_day_theta_row_is_decay_left_today_summed_per_approach():
    sc, cols, ctx = build_columns("ADJ-02")
    units = _units(cols)
    got = row(compare(cols, dataclasses.replace(ctx, leg_decay_left=units)), "theta")
    assert str(got.label) == "Decay left today (Rs)"
    for c in cols:
        if not c.built.after:
            continue
        hand = sum((units[x.tradingsymbol] * x.lots * ctx.position.lot * (1 if x.side == "BUY" else -1)
                    for x in c.built.after), D(0)).quantize(D("0.01"))
        cell = got.values[c.built.id]
        assert cell.value == hand, (c.built.id, cell.value, hand)
        assert str(cell.text) == f"Decay left today: {_rupees(hand)}"


def test_another_day_theta_row_is_unchanged():
    _sc, cols, ctx = build_columns("ADJ-02")
    got = row(compare(cols, ctx), "theta")
    assert str(got.label) == "Theta"
    assert all(not str(v.text).startswith("Decay left today") for v in got.values.values())


def test_a_leg_with_no_decay_figure_is_a_dash_never_a_partial_sum():
    _sc, cols, ctx = build_columns("ADJ-02")
    units = _units(cols)
    units.pop(next(iter(units)))
    got = row(compare(cols, dataclasses.replace(ctx, leg_decay_left=units)), "theta")
    assert any(v.value is None for v in got.values.values())


def _rupees(value: D) -> str:
    from ofo.errors.explanations import render_explanation
    return str(render_explanation("decay_left_today_text", amount=value)).removeprefix("Decay left today: ")
