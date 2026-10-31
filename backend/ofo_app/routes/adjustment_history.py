"""GET /api/strategies/{id}/adjustment-history (GC-ADJ2 step 6; REQ-163 AC-1..AC-3, F-74, ADR-214, ADR-008).

The rows and whole-trade totals come only from ``ofo.engine.adjust_history`` over the stored paper orders; this module
reads, prices and words, and adds no arithmetic of its own.

Inputs, each from the reader the paper book already uses (never a second reader of the same source):
- orders: ``paper_book.load_owned`` (owner check in the query). None -> the adjustment-check route's not-found answer.
- current prices: the paper book's market read (``routes.paper._snapshot`` / ``_prices``, ADR-212 display prices);
  stale or missing for any open contract -> open P&L, P&L and premium left None with ``prices_reason`` (booked and
  credit still shown, never 0).
- charges: ``ofo.charges.paper_charges`` per order (the paper book's Charges figure, REQ-109 AC-10); rates unreadable
  or an order the rate table cannot price -> charges None with the paper book's reason.
- the plan's maximum: the strategy's own plan (``playbook_store.plan_for``), else the type's active playbook
  (``adjustment_check.resolve``), guard ``max_adjustments``; none found or not a whole number -> None with
  ``max_reason`` ("1 of -").
- why: no suggestion link is stored on a paper order today (REQ-112 AC-1 records are GC-ADJ2 step 5), so every row is
  "Your own change"; a linked rule id would be sent as ``rule_id``.
- fill: every paper order is "Paper - not sent to Zerodha" (REQ-163 AC-1).

Suggest-only: nothing here places an order. The user comes from the session (``current_user_ref``).
"""
from __future__ import annotations

import datetime
import logging
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from ofo.charges import ChargeRates
from ofo.charges.paper_charges import PaperFill, paper_charges
from ofo.charges.round_trip import ChargesNotComputable, to_paise_up
from ofo.engine import adjust_history as ah
from ofo.engine.legs import Instrument
from ofo.errors.explanations import render_explanation
from ofo.outcome.price_text import price_text
from ofo.strategy.definition import describe_contract
from ofo.tracking import paper as paper_prices

from ofo_app import paper_book, playbook_store, tracked_contracts
from ofo_app.api_models import ApiModel, CatalogueText, Identifier, Money
from ofo_app.db import get_db
from ofo_app.errors import ClosedRoute, Failure
from ofo_app.live_push import LiveFeed
from ofo_app.paper_reasons import reason_text
from ofo_app.routes import paper
from ofo_app.routes.adjustment import TrackedReader, get_tracked_reader
from ofo_app.routes.broker import current_user_ref
from ofo_app.routes.outcome import MarketContext, get_market_context, load_charge_rates
from ofo_app.routes.planned_entry import get_live_feed
from ofo_app.strategy_refused import StrategyRefused

log = logging.getLogger(__name__)
router = APIRouter(route_class=ClosedRoute)
_NOT_AVAILABLE = "user_input_request_not_available"  # the adjustment-check route's not-found answer
NO_PLAN_MAX = "no_plan_max"


class HistoryOrderOut(ApiModel):
    side: Literal["BUY", "SELL"]
    contract_text: CatalogueText
    quantity: int
    price: Money
    price_text: CatalogueText
    kind: Literal["open", "add", "exit", "settle", "stop"]


class HistoryRowOut(ApiModel):
    step: Literal["entry", "adjustment", "settle", "stop"]
    number: int | None
    at: datetime.datetime
    orders: list[HistoryOrderOut]
    cash: Money
    cash_text: CatalogueText
    booked: Money | None  # None = pending
    booked_text: CatalogueText | None
    booked_pending: CatalogueText | None
    charges: Money | None
    rule_id: Identifier | None
    why_text: CatalogueText | None  # set when rule_id is None
    fill: Literal["paper", "confirmed", "unconfirmed", "failed"]
    fill_text: CatalogueText | None  # paper rows: in place of a fill state


class HistoryTotalsOut(ApiModel):
    pnl: Money | None
    pnl_text: CatalogueText | None
    booked: Money
    booked_text: CatalogueText
    open_pnl: Money | None
    open_pnl_text: CatalogueText | None
    credit: Money
    credit_text: CatalogueText
    premium_left: Money | None
    premium_left_text: CatalogueText | None
    prices_reason: paper_prices.PauseReason | None
    prices_reason_text: CatalogueText | None
    adjustments_used: int
    adjustments_max: int | None
    max_reason: Literal["no_plan_max"] | None
    max_reason_text: CatalogueText | None
    charges: Money | None
    charges_text: CatalogueText | None
    charges_reason: paper.ChargesReason | None
    charges_reason_text: CatalogueText | None


class AdjustmentHistoryOut(ApiModel):
    strategy_id: int
    rows: list[HistoryRowOut]
    totals: HistoryTotalsOut


def _per_order_charges(orders: Any, found: dict, underlying: str,
                       rates: ChargeRates | None) -> tuple[list[Decimal] | None, str | None]:
    if rates is None:
        return None, paper.RATES_UNAVAILABLE
    fills = [PaperFill(o.order.kind, o.order.side, o.order.quantity, o.order.price,
                       paper._identity(found[o.order.contract_id])[1] is not Instrument.FUT) for o in orders]
    try:
        return list(paper_charges(fills, underlying, rates).per_order), None
    except ChargesNotComputable:
        return None, paper.NOT_PRICED


async def _plan_max(db: Any, user_ref: str, strategy_id: int, reader: tuple[TrackedReader, ChargeRates | None],
                    ctx: MarketContext | None) -> int | None:
    from ofo_app import adjustment_check as check  # noqa: PLC0415 - it imports routes.adjustment
    from ofo_app.adjustment_readers import TrackedUnreadable  # noqa: PLC0415
    plan = await playbook_store.plan_for(db, user_ref, strategy_id)
    body: Any = None if plan is None else plan.body
    if body is None:
        try:
            tracked = await reader[0](strategy_id, reader[1])
        except TrackedUnreadable:
            tracked = None  # nothing open: no type, so no type playbook
        if tracked is not None:
            listed = None if ctx is None else ctx.provider.instrument_master()
            stype = check.strategy_type(tracked.position, None, listed)
            body = (await check.resolve(db, user_ref, strategy_id, stype)).body
    mx = None if body is None else body.get("guards", {}).get("max_adjustments")
    return mx if type(mx) is int and mx >= 0 else None


def _money_text(value: Decimal | None) -> Any:
    return paper._signed(value)


def _row(r: ah.HistoryRow, found: dict) -> dict:
    return {"step": r.step, "number": r.number, "at": r.at,
            "orders": [{"side": o.side,
                        "contract_text": describe_contract(paper._identity(found[int(o.instrument_id)])),
                        "quantity": o.quantity, "price": o.price, "price_text": price_text(o.price), "kind": o.kind}
                       for o in r.orders],
            "cash": r.cash, "cash_text": _money_text(r.cash),
            "booked": paper._exact(r.booked), "booked_text": _money_text(r.booked),
            "booked_pending": render_explanation("adjust_history_pending") if r.booked is None else None,
            "charges": paper._exact(r.charges), "rule_id": r.rule_id,
            "why_text": render_explanation("adjust_history_own_change") if r.rule_id is None else None,
            "fill": r.fill, "fill_text": render_explanation("adjust_history_paper_fill") if r.fill == "paper" else None}


@router.get("/api/strategies/{strategy_id}/adjustment-history", response_model=AdjustmentHistoryOut)
async def adjustment_history(  # noqa: PLR0913 - FastAPI dependencies, one per input
        strategy_id: int,
        db: Annotated[Any, Depends(get_db)], user_ref: Annotated[str, Depends(current_user_ref)],
        ctx: Annotated[MarketContext | None, Depends(get_market_context)],
        feed: Annotated[LiveFeed | None, Depends(get_live_feed)],
        tracked_reader: Annotated[TrackedReader, Depends(get_tracked_reader)],
        rates: Annotated[ChargeRates | None, Depends(load_charge_rates)]) -> AdjustmentHistoryOut:
    rates = rates if isinstance(rates, ChargeRates) else None
    orders = await paper_book.load_owned(db, user_ref, strategy_id)
    if not orders:
        raise StrategyRefused(_NOT_AVAILABLE, Failure.NOT_FOUND)
    found = {c.contract_id: c for c in await tracked_contracts.resolve(db, sorted({o.order.contract_id
                                                                                     for o in orders}))}
    underlying = paper._identity(found[orders[0].order.contract_id])[0]
    open_ids = paper._open_ids(orders)
    snapshot = None
    keys = [k for k in (found[c].feed_key for c in open_ids) if k is not None]
    if paper._connected(ctx) and keys:
        snapshot = await paper._snapshot(ctx, feed, underlying, keys)  # type: ignore[arg-type]
    prices = paper._prices(open_ids, found, snapshot)
    live = {str(cid): p.price for cid, p in prices.items() if paper_prices.is_live(p) and p.price is not None}
    per_order, charges_reason = _per_order_charges(orders, found, underlying, rates)
    plan_max = await _plan_max(db, user_ref, strategy_id, (tracked_reader, rates), ctx)
    history = ah.adjustment_history(
        [ah.HistoryOrder(str(o.order.contract_id), o.order.side,  # type: ignore[arg-type]
                         o.order.quantity, o.order.price, o.order.kind, o.order.placed_at)  # type: ignore[arg-type]
         for o in orders], live, adjustments_max=plan_max,
        per_order_charges=per_order)
    t = history.totals
    paused = t.open_pnl is None
    prices_reason = None
    if paused:
        prices_reason = next((found[c].state for c in prices if found[c].state != tracked_contracts.LIVE),
                             paper_prices.PRICES_NOT_LIVE)
    shown_charges = None if t.charges is None else to_paise_up(t.charges)
    totals = {"pnl": paper._exact(t.pnl), "pnl_text": _money_text(t.pnl),
              "booked": paper._exact(t.booked), "booked_text": _money_text(t.booked),
              "open_pnl": paper._exact(t.open_pnl), "open_pnl_text": _money_text(t.open_pnl),
              "credit": t.credit, "credit_text": _money_text(t.credit),
              "premium_left": t.premium_left, "premium_left_text": _money_text(t.premium_left),
              "prices_reason": prices_reason, "prices_reason_text": reason_text(prices_reason),
              "adjustments_used": t.adjustments_used, "adjustments_max": t.adjustments_max,
              "max_reason": NO_PLAN_MAX if t.adjustments_max is None else None,
              "max_reason_text": (render_explanation("adjust_history_no_plan_max") if t.adjustments_max is None
                                  else None),
              "charges": paper._exact(t.charges),
              "charges_text": None if shown_charges is None else render_explanation(paper.PAPER_CHARGES,
                                                                                   amount=shown_charges),
              "charges_reason": None if t.charges is not None else charges_reason,
              "charges_reason_text": None if t.charges is not None else reason_text(charges_reason)}
    return AdjustmentHistoryOut.model_validate({"strategy_id": strategy_id,
                                                "rows": [_row(r, found) for r in history.rows], "totals": totals})
