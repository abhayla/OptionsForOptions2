"""W-111 Positions read (REQ-044 AC-3 part 1; ADR-109 (2), (5); ADR-110; REQ-009 AC-3; ADR-027): quantities only.

Basis: ADR-109 (2): a strategy owns the fills of orders this app placed; lots beyond that are OUTSIDE lots, shown
apart and blocking nothing. One GET reads Zerodha's positions through the existing read path, at most once per
45 s per user (REQ-118 AC-7: ``kite_period_reads.screen_positions``, the same answer the connect-time periodic read
stores; ``read_at`` is that read's own time) (``kite_reads`` + ``kite_replies.positions_from_reply``) and Zerodha's
order book (``fetch_orders`` + ``kite_replies.orders_from_reply``), and asks W-108's ``attribute_and_compare`` for
the split (W-108 loads every stored plan itself). The route takes NO held units or outside lots from the client (finding
``caller-supplied-verdict-trusted``): it has no body and no query. The answer carries units and the owning strategy's id
only: no price, P&L, margin or Greeks key exists on it (part 2), and no order is ever sent (ADR-002, ADR-027).
No recorded standalone store exists yet (REQ-060 AC-7), so the standalone map passed is empty: a position in no strategy
is shown as outside. Without a Zerodha session, or on a failed or unreadable read of EITHER reply, the answer is a
catalogue refusal (409), never an empty list that would read as "all flat" and never an empty order book (which would
read every open plan as pending for the wrong reason).

ADR-110: a contract an open (or contradicted) plan touches is PENDING: the row carries Zerodha's units as read (the page
marks them "not yet confirmed"), ``pending_plans`` (strategy id, plan number), an empty ``own`` and null
``own_units`` / ``outside_units`` ("makes no own/outside split for it"; 0 would read as a split). Every blocked flag is
W-108's ``blocked`` set: a strategy blocked anywhere (a mismatch or a pending plan) is shown blocked on every row.

ADR-138 (2): "Positions screen: strategy groups, strategy P&L, the mismatch badge and "N outside lots - view on
Kite"; no copy of Kite's full position list." So the answer is grouped by strategy and lists only contracts linked to a
strategy; units no strategy owns are one count (``outside_lots``) the page links to Kite with, never their own rows.
Strategy P&L is W-111 part 2.
"""
from __future__ import annotations

import dataclasses
import datetime
from collections.abc import Callable
from typing import Annotated, Any, Literal, Optional

from fastapi import APIRouter, Depends
from ofo.engine import real_pnl
from ofo.errors import render
from ofo.errors.explanations import render_explanation
from ofo.instruments.models import is_lot_aligned
from ofo.timeutil import IST

from ofo_app import kite_period_reads
from ofo_app import reconcile_attribution as ra
from ofo_app import strategy_store as store
from ofo_app.api_models import ApiModel, CatalogueText, Identifier, Money
from ofo_app.catalogue_store import load_catalogue
from ofo_app.db import get_db
from ofo_app.errors import ClosedRoute, Failure
from ofo_app.kite_reads import KiteReadError, unconfirmed_template
from ofo_app.kite_replies import ContractIndex, KiteReplyError, log_ignored, orders_from_reply, positions_from_reply
from ofo_app.routes import paper
from ofo_app.routes.broker import current_user_ref
from ofo_app.routes.execute import KiteSession, get_execute_clock, get_kite_session
from ofo_app.routes.strategies import StrategyRefused

router = APIRouter(route_class=ClosedRoute)


class StrategyContractOut(ApiModel):
    tradingsymbol: Identifier
    zerodha_units: int  # Zerodha's net units on this contract, as read (a pending row marks them "not yet confirmed")
    units: int | None  # this strategy's own units (signed: BUY +, SELL -); null while pending (no own/outside split)
    pending: bool  # an open plan of this strategy is not final at Zerodha yet (ADR-110)
    pending_plans: list[int]  # this strategy's plan numbers that keep the contract pending (empty when not pending)
    # Lane S (ADR-330 (24)): Zerodha's own P&L for the contract, re-derived by the engine from Zerodha's own
    # fields and shown only when both agree; no split of a shared contract, ever
    pnl: Money | None  # exact Decimal (2 dp, a string on the wire), null unless pnl_state is "stated"
    pnl_text: CatalogueText | None  # the server's signed-paisa text of that figure
    pnl_state: Literal["stated", "not_available", "mismatch", "shared", "pending", "stale"]
    pnl_reason: CatalogueText | None  # the catalogue sentence for a state without a figure


class StrategyPositionsOut(ApiModel):
    strategy_id: int  # the page links to /strategy/{strategy_id}/execute: every action routes back to the strategy
    blocked: bool  # in W-108's blocked set (a mismatch or a pending plan): the page's mismatch badge
    contracts: list[StrategyContractOut]  # tradingsymbol order; empty for a blocked strategy with no own row


class RealPnlOut(ApiModel):
    """ADR-330 (10): the "Real P&L" total of the one Positions list: the exact sum of the rows' figures, never added to
    Paper P&L. ``state``: stated | empty | partial | stale (no figure in any state but stated)."""

    value: Money | None
    pnl_text: CatalogueText | None
    state: Literal["stated", "empty", "partial", "stale", "not_connected"]  # FD2 D-2: not_connected = no session
    reason: CatalogueText | None
    source: Literal["Zerodha"]
    read_at: datetime.datetime
    caption: CatalogueText  # "Zerodha, as at HH:MM:SS IST"
    excludes_note: CatalogueText | None  # what the total leaves out, when it leaves something out (ADR-330 (24))


class PositionsOut(ApiModel):
    read_at: datetime.datetime
    real_pnl: RealPnlOut
    pnl_text: CatalogueText | None  # the one reader's figure: equal to real_pnl.pnl_text
    strategies: list[StrategyPositionsOut]  # strategy-id order; only contracts linked to a strategy (ADR-138 (2))
    has_outside: bool  # Zerodha holds units on a NIFTY/SENSEX contract that no strategy owns (ADR-109 (2))
    outside_lots: int | None  # those units in lots, summed; null when a lot size cannot be read exactly (never guessed)
    blocked: bool
    blocked_strategy_ids: list[int]  # W-108's blocked set, ascending
    #: FD2 item 3 D-2: false when no Zerodha session is stored: the Real part is ``real_pnl.state == "not_connected"``
    #: with its reason; nothing was read at Zerodha. True in every other answer.
    broker_connected: bool = True


def _refuse(template: str) -> StrategyRefused:
    return StrategyRefused(template, Failure.CONFLICT, message=render(template))


@dataclasses.dataclass(frozen=True)
class _ReadSnapshot:
    net: Any
    orders: tuple[Any, ...]
    index: ContractIndex
    read_at: datetime.datetime  # when Zerodha was read (the periodic job's read or this request's), never "now"
    money: Any = None  # Lane S: per contract, the P&L fields of Zerodha's non-flat rows (PositionsRead.money)
    flat_platform: int = 0  # Lane S: closed-today rows of ours (flat); the total leaves them out
    flat_keys: frozenset[Any] = frozenset()  # Lane S: the contracts those flat rows are on (reported apart)


def _read(session: KiteSession, catalogue: Any) -> _ReadSnapshot:
    """Both Zerodha reads, or a refusal: a failed or unreadable orders reply is refused exactly like a positions
    reply, never replaced by an empty book. An empty list read successfully is a real answer (no orders today)."""
    index = ContractIndex.from_catalogue(catalogue)
    try:
        answer = kite_period_reads.screen_positions(session.reads)  # REQ-118 AC-7: at most one read per 45 s per user
        positions_reply, orders_reply = answer.value
        read = positions_from_reply(positions_reply, index)
        orders = orders_from_reply(orders_reply)
    except (KiteReadError, KiteReplyError, ValueError) as exc:
        raise _refuse(unconfirmed_template(exc)) from None
    log_ignored(read, "positions read")  # rows never ours, named in one line (as the Execute and return routes do)
    return _ReadSnapshot(read.net, orders, index, answer.read_at, read.money, read.flat_platform, read.flat_keys)


async def _attribute(db: Any, user_ref: str, snap: _ReadSnapshot, sources: ra.Sources,
                     now: datetime.datetime) -> ra.Attribution:
    """The ONE call into W-108: the route hands over only the account (connection + user), Zerodha's net and Zerodha's
    order book; W-108 loads the strategies and plans itself (never held units, plans or outside lots from here or the
    client)."""
    return await ra.attribute_and_compare(ra.Account(db, user_ref), STANDALONE, snap.net, snap.orders, sources,
                                          at=now)


def _symbol(key: Any, index: ContractIndex) -> str:
    symbol = index.symbol_of(key)
    if symbol is None:
        raise _refuse("strategy_stored_unreadable")  # a strategy's contract the catalogue cannot name: never guessed
    return symbol


def _outside_lots(result: ra.Attribution, index: ContractIndex) -> int | None:
    """Every outside unit (any sign) in lots, summed: None when a contract's lot size is not exactly one value or its
    units are not a whole number of lots (the page then says "outside positions" without a number)."""
    lots = 0
    for key, units in result.outside.items():
        if not units:
            continue
        lot = index.lot_of(key)
        if lot is None or not is_lot_aligned(units, lot):
            return None
        lots += abs(units) // lot
    return lots


STALE_AFTER_SECONDS = 90  # Lane S: a figure from a read older than this is not shown (against the route's clock)
SOURCE = "Zerodha"
_NO_FIGURE = {"pnl": None, "pnl_text": None}


STANDALONE: dict[Any, int] = {}  # no recorded standalone store yet (REQ-060 AC-7); the ONE map attribution and the
# sole-holder check both read, so a future standalone cannot pass the check unseen


def _foreign_fill(symbol: str, sid: str, snap: _ReadSnapshot) -> bool:
    """(e): any order on this contract today with a filled quantity (any status) whose tag does not decode (new or
    legacy grammar) to THIS strategy: another strategy's, an outside or an unreadable fill, all inside Zerodha's
    buy_value / sell_value for the contract, so the row is not the strategy's alone."""
    for order in snap.orders:
        if order.tradingsymbol != symbol or not order.filled_quantity:
            continue
        if ra.tag_strategy_id(order.tag) == int(sid):
            continue  # an untagged or foreign-grammar tag decodes to None: not this app's
        return True
    return False


def _sole_reason(key: Any, sid: str, result: ra.Attribution, snap: _ReadSnapshot,
                 standalone: Any = None) -> str | None:
    """None when this strategy is the sole holder of Zerodha's whole figure for the contract, else the reason
    template of the row: "real_pnl_shared" or "real_pnl_part_closed". Sole holder = (a) exactly one strategy holds the
    contract, (b) no outside units on it, (c) no recorded standalone on it, (d) own units == Zerodha's net, (e)
    every order filled on it today carries this strategy's own tag, (f) no flat (closed today) row of another product
    on it."""
    standalone = STANDALONE if standalone is None else standalone
    units = result.held.get(sid, {}).get(key, 0)
    holders = [h for h, held in result.held.items() if held.get(key, 0) != 0]
    if holders != [sid] or result.outside.get(key, 0) or standalone.get(key, 0):
        return "real_pnl_shared"
    symbol = _symbol(key, snap.index)
    if units != snap.net.get(key, 0) or _foreign_fill(symbol, sid, snap):
        return "real_pnl_shared"
    if key in snap.flat_keys:
        return "real_pnl_part_closed"
    return None


def sole_holder(key: Any, sid: str, result: ra.Attribution, snap: _ReadSnapshot, standalone: Any = None) -> bool:
    """The one predicate every stated Real P&L row passes through (ADR-330 (24)): see ``_sole_reason``."""
    own = result.held.get(sid, {}).get(key, 0)
    return own != 0 and _sole_reason(key, sid, result, snap, standalone) is None


def _row_pnl(key: Any, sid: str, skip: str | None, result: ra.Attribution, snap: _ReadSnapshot) -> dict[str, Any]:
    """One real contract row's P&L (ADR-330 (24)): stale, pending and shared rows and every engine state other
    than "stated" carry no figure and the catalogue's reason; the figure is Zerodha's own, checked by the engine.
    ``skip`` is "stale" or "pending" (checked in that order) or None."""
    symbol = _symbol(key, snap.index)

    def none(state: str, template: str, **slots: Any) -> dict[str, Any]:
        return {**_NO_FIGURE, "pnl_state": state, "pnl_reason": render_explanation(template, **slots)}

    if skip == "stale":
        return none("stale", "real_pnl_stale", seconds=STALE_AFTER_SECONDS)
    if skip == "pending":
        return none("pending", "real_pnl_pending")
    if not sole_holder(key, sid, result, snap):  # another strategy, outside lots or trades, or a closed sibling
        reason = _sole_reason(key, sid, result, snap) or "real_pnl_shared"  # row: never a split
        return none("shared", reason, **({"contract": symbol} if reason == "real_pnl_part_closed" else {}))
    figure = real_pnl.broker_contract_pnl(list((snap.money or {}).get(key, ())))
    if figure.state == real_pnl.STATED and figure.value is not None:
        return {"pnl": figure.value, "pnl_text": paper.signed(figure.value), "pnl_state": "stated",
                "pnl_reason": None, "_value": figure}
    template = "real_pnl_mismatch" if figure.state == real_pnl.MISMATCH else "real_pnl_not_available"
    return none(figure.state, template, contract=symbol)


def _groups(result: ra.Attribution, index: ContractIndex, snap: _ReadSnapshot,
            stale: bool) -> tuple[list[dict[str, Any]], list[tuple[Any, real_pnl.BrokerPnl]]]:
    """ADR-138 (2): one group per strategy, holding only the contracts linked to it: its own units (W-108's ``held``)
    or its plans that keep a contract pending (ADR-110: no own/outside split there). A blocked strategy with no such
    contract still gets its group, so its badge is shown. Outside-only contracts are never a row. Also returns the
    engine's figure of every row (the total's input)."""
    rows: dict[str, dict[Any, dict[str, Any]]] = {}
    for sid, units in result.held.items():
        for key, own in units.items():
            rows.setdefault(str(sid), {})[key] = {"units": own, "pending": False, "pending_plans": []}
    for key, entries in result.pending.items():
        for entry in entries:
            row = rows.setdefault(str(entry.strategy_id), {}).setdefault(
                key, {"units": None, "pending": True, "pending_plans": []})
            row.update(units=None, pending=True)
            if entry.plan_number not in row["pending_plans"]:
                row["pending_plans"].append(entry.plan_number)
    for sid in result.blocked:
        rows.setdefault(str(sid), {})
    groups = []
    figures: list[tuple[Any, real_pnl.BrokerPnl]] = []
    for sid in sorted(rows, key=int):
        contracts = []
        for key, row in rows[sid].items():
            symbol = _symbol(key, index)
            skip = "stale" if stale else ("pending" if row["pending"] else None)
            pnl = _row_pnl(key, sid, skip, result, snap)
            figures.append((key, pnl.pop("_value", None)
                           or real_pnl.BrokerPnl(pnl["pnl_state"], None, None, None)))
            contracts.append({"tradingsymbol": symbol, "zerodha_units": result.raw_net.get(key, 0),
                              **row, **pnl, "pending_plans": sorted(row["pending_plans"])})
        groups.append({"strategy_id": int(sid), "blocked": sid in result.blocked,
                       "contracts": sorted(contracts, key=lambda c: c["tradingsymbol"])})
    return groups, figures


def _real_total(figures: list[tuple[Any, real_pnl.BrokerPnl]], has_outside: bool, snap: _ReadSnapshot,
                stale: bool) -> dict[str, Any]:
    """ADR-330 (10) / LQS-2 (a): the exact sum of the rows' figures, only when EVERY row is stated; stale, empty and
    partial carry no figure and say why. The note says what the total leaves out (outside lots, contracts closed
    today)."""
    clock_text = snap.read_at.astimezone(IST).strftime("%H:%M:%S")
    total = real_pnl.broker_total([f for _, f in figures])
    missing, contracts = real_pnl.contracts_without_figure(figures)
    if stale:
        state, reason = "stale", render_explanation("real_pnl_stale", seconds=STALE_AFTER_SECONDS)
    elif not figures:
        state, reason = "empty", render_explanation("real_pnl_total_empty")
    elif total is None:
        state, reason = "partial", render_explanation("real_pnl_total_partial", missing=missing, total=contracts)
    else:
        state, reason = "stated", None
    leaves_out = has_outside or snap.flat_platform > 0
    return {"value": total if state == "stated" else None,
            "pnl_text": paper.signed(total) if state == "stated" else None, "state": state,
            "reason": reason, "source": SOURCE, "read_at": snap.read_at,
            "caption": render_explanation("real_pnl_caption", time=clock_text),
            "excludes_note": render_explanation("real_pnl_excludes") if leaves_out else None}


def _answer(result: ra.Attribution, snap: _ReadSnapshot, now: datetime.datetime) -> PositionsOut:
    stale = (now - snap.read_at).total_seconds() > STALE_AFTER_SECONDS
    groups, figures = _groups(result, snap.index, snap, stale)
    blocked_ids = sorted(int(sid) for sid in result.blocked)
    has_outside = any(result.outside.values())
    real = _real_total(figures, has_outside, snap, stale)
    return PositionsOut.model_validate({
        "read_at": snap.read_at, "real_pnl": real, "pnl_text": real["pnl_text"], "strategies": groups,
        "has_outside": has_outside, "outside_lots": _outside_lots(result, snap.index),
        "blocked": bool(blocked_ids), "blocked_strategy_ids": blocked_ids})


def _not_connected(now: datetime.datetime) -> PositionsOut:
    """No stored Zerodha session: the answer states it (the gate's own sentence) and carries no figure or group."""
    said = render("gate_broker_not_connected")
    real = {"value": None, "pnl_text": None, "state": "not_connected", "reason": said, "source": SOURCE,
            "read_at": now, "caption": said, "excludes_note": None}
    return PositionsOut.model_validate({
        "read_at": now, "real_pnl": real, "pnl_text": None, "strategies": [], "has_outside": False,
        "outside_lots": None, "blocked": False, "blocked_strategy_ids": [], "broker_connected": False})


@router.get("/positions", response_model=PositionsOut)
async def read_positions(
    session: Annotated[Optional[KiteSession], Depends(get_kite_session)],  # noqa: UP045
    clock: Annotated[Callable[[], datetime.datetime], Depends(get_execute_clock)],
    db: Annotated[Any, Depends(get_db)], user_ref: Annotated[str, Depends(current_user_ref)],
) -> PositionsOut:
    if session is None:  # FD2 D-2: a calm state the page shows, not a red 409 on every load (ADR-330 (63))
        return _not_connected(clock())
    catalogue = await load_catalogue(db)
    snap = _read(session, catalogue)
    now = clock()
    try:
        result = await _attribute(db, user_ref, snap, ra.Sources(catalogue, clock), now)
    except (ra.AttributionError, store.StrategyStoreError, ValueError):
        raise _refuse("strategy_stored_unreadable") from None
    return _answer(result, snap, now)


__all__ = ["PositionsOut", "RealPnlOut", "StrategyContractOut", "StrategyPositionsOut", "read_positions"]
