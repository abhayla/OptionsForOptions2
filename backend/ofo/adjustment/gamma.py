"""T-14 gamma figures (goal contract ic-e2e-paper, design decision 8; ADR-008 one engine, exact decimal money).

The whole-position P&L change if spot were ``playbook_eval.GAMMA_MOVE_PCT`` % up and down NOW: the open legs valued by
``ofo.engine.model.estimate(model, level)`` (the what-if path's one valuation; ``at`` left to the model's own valuation
time, so the base and both moves use the SAME clock and the SAME per-leg IVs), minus the same estimate at the spot.
Booked P&L is the same in all three and cancels, so it is not read. The levels are rounded half-even to 0.01 points
exactly as the carry check's gap levels (``carry.gap_levels``); each change is rounded half-even to the paisa.

Answer states: no model (spot or forward refused) or an option leg without an IV -> no figures, ``gamma_unknown``;
the engine refusing the valuation -> ``gamma_unknown``. Never a zero. Pure: no clock read, no DB.
"""
from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal

from ofo.adjustment import carry
from ofo.adjustment import playbook_eval as pe
from ofo.engine.model import ModelInputs, estimate
from ofo.money import PAISE


def gamma_figures(model: ModelInputs | None) -> pe.GammaFigures:
    """T-14's figures for ``model`` (see the module docstring for every answer state)."""
    if model is None or any(leg.leg.is_option and leg.iv is None for leg in model.legs):
        return pe.GammaFigures(None, None, pe.GAMMA_UNKNOWN)
    spot = model.spot_level
    up_level, down_level = carry.gap_levels(spot, pe.GAMMA_MOVE_PCT)
    try:
        base = estimate(model, spot)
        up = estimate(model, up_level)
        down = estimate(model, down_level)
    except (ValueError, ArithmeticError):
        return pe.GammaFigures(None, None, pe.GAMMA_UNKNOWN)
    at = base.assumptions.valuation_time
    if not (up.assumptions.valuation_time == down.assumptions.valuation_time == at):  # one clock, never two
        return pe.GammaFigures(None, None, pe.GAMMA_UNKNOWN)

    def change(e) -> Decimal:
        return (e.total - base.total).quantize(PAISE, rounding=ROUND_HALF_EVEN)

    return pe.GammaFigures(change(up), change(down), None, at, (up_level, down_level))


__all__ = ["gamma_figures"]
