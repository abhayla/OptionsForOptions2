"""The carry check's figures (GC-IC1 step 1b; REQ-159 AC-4, S-06 "overnight margin, gap loss").

The whole-trade P&L (booked plus the open legs) if spot gaps ``CARRY_GAP_PCT`` up and down at the NEXT session's
open (``market_calendar.next_open``), and the broker-stated overnight margin.

One valuation, never a second formula (ADR-008, finding engine-input-chosen-per-caller): each open leg is valued by
``ofo.engine.model.estimate(model, level, at)``, the function the what-if path ``scenario.views.scenario_values``
calls for its Estimated view at a what-if time; the level is rounded half-even to 0.01 points as that path does.
``scenario_values`` itself is not called: it needs a ``LevelSet`` built on the admin scenario grid, which has no
column at spot x 1.02. Booked P&L is added by ``adjust_money.with_booked``; each figure is rounded half-even to the
paisa (``ofo.money.PAISE``).

Answer states: next open not known (the holiday list has no year it needs) -> no figures, ``holiday_list_unknown``;
no model (spot not available) or an option leg without an IV -> no figures, ``carry_gap_unknown`` (never a zero);
margin not stated (None) -> ``missing_margin``, never a computed stand-in. Pure: the caller passes ``now``.
"""
from __future__ import annotations

import datetime
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Final

from ofo import market_calendar as mc
from ofo.adjustment import playbook_eval as pe
from ofo.engine import adjust_money
from ofo.engine.model import ModelInputs, estimate
from ofo.money import PAISE

CARRY_GAP_PCT: Final = Decimal(2)
CARRY_GAP_UNKNOWN: Final = f"{pe.P}carry_gap_unknown"
MISSING_MARGIN: Final = f"{pe.P}missing_margin"
_HUNDRED: Final = Decimal(100)


def gap_levels(spot: Decimal) -> tuple[Decimal, Decimal]:
    """(up, down): spot x (1 +/- CARRY_GAP_PCT / 100), rounded half-even to 0.01 points (the what-if path's rule)."""
    up = spot * (_HUNDRED + CARRY_GAP_PCT) / _HUNDRED
    down = spot * (_HUNDRED - CARRY_GAP_PCT) / _HUNDRED
    return up.quantize(PAISE, rounding=ROUND_HALF_EVEN), down.quantize(PAISE, rounding=ROUND_HALF_EVEN)


def _whole_trade(model: ModelInputs, booked: Decimal, level: Decimal, at: datetime.datetime) -> Decimal:
    return adjust_money.with_booked(booked, estimate(model, level, at).total).quantize(PAISE, rounding=ROUND_HALF_EVEN)


def carry_figures(model: ModelInputs | None, booked: Decimal | None, margin: Decimal | None,
                  now: datetime.datetime, holidays: mc.Holidays | None = None) -> pe.CarryFigures:
    """The carry record's content at ``now`` (see the module docstring for every answer state)."""
    margin_reason = None if margin is not None else MISSING_MARGIN
    opens = mc.next_open(now, holidays)
    if opens is None:
        return pe.CarryFigures(None, None, pe.HOLIDAY_LIST_UNKNOWN, margin, margin_reason)
    if model is None or booked is None or any(leg.leg.is_option and leg.iv is None for leg in model.legs):
        return pe.CarryFigures(None, None, CARRY_GAP_UNKNOWN, margin, margin_reason, opens)
    up, down = gap_levels(model.spot.level)  # the gated reading's level (== ModelInputs.spot_level)
    return pe.CarryFigures(_whole_trade(model, booked, up, opens), _whole_trade(model, booked, down, opens), None,
                           margin, margin_reason, opens)


__all__ = ["CARRY_GAP_PCT", "CARRY_GAP_UNKNOWN", "MISSING_MARGIN", "carry_figures", "gap_levels"]
