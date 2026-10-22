"""The Option Chain's live preview of the selected legs (W-124; REQ-031 AC-1/AC-2/AC-3, REQ-030 AC-14). Framework-free.

Copy from: none - no algochanakya row. The numbers are the OUTCOME route's own (``outcome.outcome_response``: the one
engine, the one snapshot read, the same not-live rule), cut down to what the chain's selection area shows: net premium
(credit / debit), max profit, max loss, breakevens and the payoff points for a mini graph. The full scenario table,
Greeks and detailed analysis stay in the Strategy Builder (REQ-031 AC-3): none of them is carried here. There is NO
second engine call path and no margin, basket or order call (ADR-002, REQ-029 AC-6): the margin step is never passed.

Matched template (REQ-030 AC-14): the legs are matched against the reviewed templates by ``ofo.strategy.matching.match``
and the template's name is SHOWN; the selection is never converted and never executed. No match, an off-grid strike, a
missing spot or strike gap: no name (None), never a guess.
"""
from __future__ import annotations

import datetime
from collections.abc import Callable, Mapping
from decimal import Decimal
from itertools import pairwise
from typing import Literal

from ofo.engine.legs import Action, Instrument, Leg
from ofo.errors.explanations import render_explanation
from ofo.instruments.models import ListedContract
from ofo.strategy.loader import load_templates
from ofo.strategy.matching import MatchResult, match
from ofo.strategy.model import TemplateError
from pydantic import BaseModel, ConfigDict, Field

from ofo_app.api_models import ApiModel, CatalogueText, Money
from ofo_app.routes import outcome
from ofo_app.routes.outcome import LegIn, MarketContext, OutcomeResponse, PointOut

TOTAL_ROW_ID = "TOTAL"  # ofo.table.model.TOTAL_ROW_ID: the table's totals row
ENTRY_VALUE = "entry_value"  # ofo.table.columns.ColumnId.ENTRY_VALUE


class PreviewRequest(BaseModel):
    """The selected legs as the chain holds them: the same leg shape as the outcome route (never a client price)."""

    model_config = ConfigDict(extra="forbid")
    underlying: Literal["NIFTY", "SENSEX"]
    legs: list[LegIn] = Field(min_length=1, max_length=20)
    fallback: bool = Field(default=False, description="true when the screen's own live socket is down (ADR-077)")


class PreviewOut(ApiModel):
    state: Literal["COMPUTED", "NOT_CONNECTED", "REFUSED"]
    underlying: Literal["NIFTY", "SENSEX"]
    reason: CatalogueText | None
    net_premium: Money | None  # a magnitude; the side says credit (Cr) or debit (Dr)
    net_side: Literal["Cr", "Dr"] | None
    max_profit: Money | None
    max_loss: Money | None
    max_profit_unlimited: bool
    max_loss_unlimited: bool
    breakevens: list[Money]
    payoff: list[PointOut]  # the mini payoff graph's points
    matched_template: CatalogueText | None  # REQ-030 AC-14: shown only, the selection is never converted
    answered_at: datetime.datetime


def _strike_gap(ctx: MarketContext, underlying: str, expiry: datetime.date) -> Decimal | None:
    """The near-the-money strike gap of the expiry: the smallest positive step between its listed strikes (the rule of
    ``Catalogue.strike_gap``, ADR-007 Q36), read from the provider's own chain; None when it lists fewer than two."""
    strikes = sorted({q.strike for q in ctx.provider.option_chain_snapshot(underlying, expiry) if q.strike is not None})
    steps = [b - a for a, b in pairwise(strikes) if b > a]
    return min(steps) if steps else None


def _template_name(out: OutcomeResponse, ctx: MarketContext | None) -> object | None:
    if ctx is None or out.state != "COMPUTED" or out.spot_level is None or not out.legs:
        return None
    try:
        legs = [Leg(Action(leg.action), Instrument(leg.instrument), leg.strike, leg.expiry, leg.quantity,
                    leg.planned_entry) for leg in out.legs if leg.instrument and leg.quantity and leg.expiry]
        if len(legs) != len(out.legs):
            return None
        gap = _strike_gap(ctx, out.underlying, min(leg.expiry for leg in legs))
        if gap is None:
            return None
        result = match(legs, spot=out.spot_level, strike_gap=gap, templates=load_templates())
    except (ValueError, TemplateError):  # off the grid, an ambiguous catalogue, a leg the model refuses: no name
        return None
    if not isinstance(result, MatchResult):
        return None
    return render_explanation("catalogue_template_name", text=result.template.name)


def preview_answer(req: PreviewRequest, ctx: MarketContext | None,  # noqa: PLR0913 - the seams of the outcome read
                   streaming: Callable[[str], bool] | None, *, now: outcome.AnswerClock,
                   stored: Mapping[str, ListedContract] | None = None, rates=None) -> PreviewOut:
    """The one answer: ``outcome_response`` (standard level, at expiry, no margin) cut to the selection area."""
    asked = outcome.OutcomeRequest(underlying=req.underlying, legs=req.legs, ux_level="standard", view="at_expiry",
                                   fallback=req.fallback)
    out = outcome.outcome_response(asked, ctx, streaming, now=now, stored=stored, rates=rates, margin=None)
    summary = out.summary
    total = next((r for r in (out.table.rows if out.table else ()) if r.row_id == TOTAL_ROW_ID), None)
    net = None if total is None else total.cells.get(ENTRY_VALUE)
    shown = out.state == "COMPUTED"
    return PreviewOut(
        state=out.state, underlying=out.underlying, reason=out.reason,
        net_premium=net.value if shown and net is not None and isinstance(net.value, Decimal) else None,
        net_side=net.side if shown and net is not None else None,
        max_profit=summary.max_profit if shown and summary else None,
        max_loss=summary.max_loss if shown and summary else None,
        max_profit_unlimited=bool(shown and summary and summary.max_profit_unlimited),
        max_loss_unlimited=bool(shown and summary and summary.max_loss_unlimited),
        breakevens=list(summary.breakevens) if shown and summary else [],
        payoff=list(out.payoff.points) if shown and out.payoff else [],
        matched_template=_template_name(out, ctx) if shown else None,  # type: ignore[arg-type]
        answered_at=out.answered_at)
