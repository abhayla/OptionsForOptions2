"""The carry check's figures (GC-IC1 step 1b; REQ-159 AC-4, S-06 "overnight margin, gap loss").

The whole-trade P&L (booked plus the open legs) if spot gaps ``other.carry_gap_percent`` (a setting) up and down at the
NEXT session's open (``market_calendar.next_open``), and the broker-stated overnight margin.

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

CARRY_GAP_UNKNOWN: Final = f"{pe.P}carry_gap_unknown"
MISSING_MARGIN: Final = f"{pe.P}missing_margin"
_HUNDRED: Final = Decimal(100)


def gap_levels(spot: Decimal, gap_pct: Decimal) -> tuple[Decimal, Decimal]:
    """(up, down): spot x (1 +/- gap_pct / 100), rounded half-even to 0.01 points (the what-if path's rule).
    ``gap_pct`` is the setting ``other.carry_gap_percent`` in force (REQ-167 AC-4), passed in."""
    up = spot * (_HUNDRED + gap_pct) / _HUNDRED
    down = spot * (_HUNDRED - gap_pct) / _HUNDRED
    return up.quantize(PAISE, rounding=ROUND_HALF_EVEN), down.quantize(PAISE, rounding=ROUND_HALF_EVEN)


def _whole_trade(model: ModelInputs, booked: Decimal, level: Decimal, at: datetime.datetime) -> Decimal:
    return adjust_money.with_booked(booked, estimate(model, level, at).total).quantize(PAISE, rounding=ROUND_HALF_EVEN)


def carry_figures(model: ModelInputs | None, booked: Decimal | None, margin: Decimal | None,  # noqa: PLR0913
                  now: datetime.datetime, holidays: mc.Holidays | None = None, *,
                  gap_pct: Decimal | None, gap_source: str | None = None,
                  gap_setting_reason: str | None = None) -> pe.CarryFigures:
    """The carry record's content at ``now`` (see the module docstring for every answer state). ``gap_source``: where
    the gap in force came from (ADR-245, ``ofo.settings.layers``); ``gap_setting_reason``: why it could not be read."""
    margin_reason = None if margin is not None else MISSING_MARGIN
    named = {"gap_source": None if gap_pct is None else gap_source, "gap_setting_reason": gap_setting_reason}
    if gap_pct is None:  # the gap setting not read: no figures and a named reason, never a typed stand-in
        return pe.CarryFigures(None, None, CARRY_GAP_UNKNOWN, margin, margin_reason, None, None, **named)
    opens = mc.next_open(now, holidays)
    if opens is None:
        return pe.CarryFigures(None, None, pe.HOLIDAY_LIST_UNKNOWN, margin, margin_reason, None, gap_pct, **named)
    if model is None or booked is None or any(leg.leg.is_option and leg.iv is None for leg in model.legs):
        return pe.CarryFigures(None, None, CARRY_GAP_UNKNOWN, margin, margin_reason, opens, gap_pct, **named)
    up, down = gap_levels(model.spot.level, gap_pct)  # the gated reading's level (== ModelInputs.spot_level)
    return pe.CarryFigures(_whole_trade(model, booked, up, opens), _whole_trade(model, booked, down, opens), None,
                           margin, margin_reason, opens, gap_pct, **named)


__all__ = ["CARRY_GAP_UNKNOWN", "MISSING_MARGIN", "carry_figures", "gap_levels"]
