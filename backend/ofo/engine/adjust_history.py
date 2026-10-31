"""REQ-163 (ADR-214, ADR-008, F-74): a strategy's adjustment history and its whole-trade totals, from its orders.

Spec basis: REQ-163 AC-1 (the entry, then each adjustment with its time, orders, cash in or out, booked P&L, why and
fill state; a paper strategy shows "Paper - not sent to Zerodha" in place of a fill state), AC-2 (whole-trade totals,
each computed by the one engine and equal to the sum of its rows), AC-3 (an adjustment whose fills Zerodha has not
confirmed, or whose answer failed, is listed with that state and its booked P&L "pending", never in the totals);
REQ-109 AC-4 (the order book; the engine's average-price rule); REQ-112 AC-3 (fill states only from Zerodha's fills).

Batch rule (measured, GC-ADJ2 step 6): one placement request stores every one of its orders with ONE ``placed_at``
(``routes.paper.place_paper_orders`` sets ``placed_at = now()`` once per call; ``scripts/seed_scenario.py`` writes
three times for ADJ-13: the history legs' opens at clock - 2 h, their exits at clock - 1 h, the four current legs at
clock). So a step is a run of consecutive orders (in placement order) sharing one ``placed_at``. The first such step
is the entry; each later one an adjustment. Inside a step, ``settle`` and ``stop`` orders form their own row,
labelled by kind (server-written, not the user's change).

Per row:
- cash: SELL price x qty in, BUY price x qty out (``adjust_money.trade_credit``).
- booked: the P&L of the legs the row closes, each at the engine's average entry of that contract just before the
  closing order (``ofo.tracking.orderbook.net_positions``) through ``adjust_money.closed_booked`` (no new formula).
- charges: the sum of the caller's per-order charges (``ofo.charges.paper_charges``), exact; None when not given.
- why: the rule id of the suggestion the row acted on; None = "Your own change" (no suggestion link is stored today).
- fill: ``paper`` / ``confirmed`` / ``unconfirmed`` / ``failed``. Any order unconfirmed or failed makes the row that
  state (failed first); its booked is None ("pending") and the row is left out of every total, and its orders out of
  the position the totals are read from (an unfilled order holds nothing).

Totals (the filled rows only): booked (sum of rows; asserted equal to the engine book's booked), credit collected
(sum of rows' cash; asserted equal to the engine book's cash), open P&L (the engine's unbooked of the open contracts
at the live prices; None when any is missing), P&L (booked + open; asserted equal to the engine's total), premium
still left (``adjust_money.premium_left`` over the open contracts at the live prices; None when any is missing),
adjustments used (filled adjustment rows) of the plan's maximum (None when the caller has none), charges (sum of rows;
None when any row's is None). A total that does not equal the sum of its rows raises ``HistoryMismatch``: a figure
that does not add up is never shown.

Answer states: no orders -> ``ValueError`` (the caller answers not found); a float or a price finer than a paisa ->
``ValueError`` (the engine's checks); a live price absent for an open contract -> the price-dependent totals None.
Standard library only; no clock is read here.
"""
from __future__ import annotations

import datetime
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Final, Literal

from ofo.engine.adjust_money import closed_booked, premium_left, trade_credit
from ofo.engine.orderbook import OrderKind, PaperOrder, Side, net_positions

FillState = Literal["paper", "confirmed", "unconfirmed", "failed"]
FILL_STATES: Final[tuple[FillState, ...]] = ("paper", "confirmed", "unconfirmed", "failed")
PENDING_FILLS: Final = frozenset({"unconfirmed", "failed"})
Step = Literal["entry", "adjustment", "settle", "stop"]
OWN_KINDS: Final = frozenset({"settle", "stop"})  # each is its own row, labelled by kind

#: The words shown (paper fill, "Your own change", "pending") are catalogue texts (``adjust_history_*``), worded by
#: the route; nothing here is shown text.


class HistoryMismatch(ValueError):
    """A total does not equal the sum of its rows (REQ-163 AC-2): nothing is shown rather than a wrong figure."""


@dataclass(frozen=True)
class HistoryOrder:
    instrument_id: str
    side: Side
    quantity: int
    price: Decimal
    kind: OrderKind
    placed_at: datetime.datetime
    fill: FillState = "paper"
    rule_id: str | None = None  # the suggestion's rule id, when the order is linked to one

    def __post_init__(self) -> None:
        if self.fill not in FILL_STATES:
            raise ValueError(f"a fill state is one of {FILL_STATES}, got {self.fill!r}")
        self.as_paper()  # refuses a bad side, kind, quantity or price (a float included)

    def as_paper(self) -> PaperOrder:
        return PaperOrder(self.instrument_id, self.side, self.quantity, self.price, self.kind, self.placed_at)


@dataclass(frozen=True)
class HistoryRow:
    step: Step
    number: int | None  # the adjustment's number (1, 2, ...); None for the entry, settle and stop rows
    at: datetime.datetime
    orders: tuple[HistoryOrder, ...]
    cash: Decimal  # + in, - out
    booked: Decimal | None  # None = pending (unconfirmed or failed fills)
    charges: Decimal | None
    fill: FillState
    rule_id: str | None  # None = "Your own change"

    @property
    def pending(self) -> bool:
        return self.fill in PENDING_FILLS


@dataclass(frozen=True)
class HistoryTotals:
    pnl: Decimal | None
    booked: Decimal
    open_pnl: Decimal | None
    credit: Decimal
    premium_left: Decimal | None
    adjustments_used: int
    adjustments_max: int | None
    charges: Decimal | None


@dataclass(frozen=True)
class History:
    rows: tuple[HistoryRow, ...]
    totals: HistoryTotals


def _steps(orders: Sequence[HistoryOrder]) -> list[list[int]]:
    """Order indexes per row: runs of one ``placed_at`` (the batch rule), each split into its non-settle/stop part,
    then its settle part, then its stop part (empty parts dropped)."""
    batches: list[list[int]] = []
    for i, o in enumerate(orders):
        if batches and orders[batches[-1][0]].placed_at == o.placed_at:
            batches[-1].append(i)
        else:
            batches.append([i])
    return [part for batch in batches
            for part in ([i for i in batch if orders[i].kind not in OWN_KINDS],
                         *([i for i in batch if orders[i].kind == k] for k in ("settle", "stop"))) if part]


def _row_fill(orders: Sequence[HistoryOrder]) -> FillState:
    states = {o.fill for o in orders}
    if "failed" in states:
        return "failed"
    if "unconfirmed" in states:
        return "unconfirmed"
    if len(states) != 1:
        raise ValueError(f"a step mixes paper and real fills: {sorted(states)}")
    return next(iter(states))


def _row_rule(orders: Sequence[HistoryOrder]) -> str | None:
    rules = {o.rule_id for o in orders if o.rule_id is not None}
    if len(rules) > 1:
        raise ValueError(f"one step is linked to several suggestions: {sorted(rules)}")
    return next(iter(rules), None)


def _closing(book: Sequence[PaperOrder], order: PaperOrder) -> tuple[str, Decimal, Decimal, int] | None:
    """The leg ``order`` closes, as closed_booked's (side, entry, exit, quantity), or None when it closes nothing."""
    if not book:
        return None
    found = [p for p in net_positions(book, {}).positions if p.instrument_id == order.instrument_id]
    if not found or found[0].net_quantity == 0 or found[0].average is None:
        return None
    net = found[0].net_quantity
    if (net > 0) == (order.side == "BUY"):
        return None  # same side: it adds
    return ("BUY" if net > 0 else "SELL", found[0].average, order.price, min(order.quantity, abs(net)))


def _check_inputs(orders: Sequence[HistoryOrder], adjustments_max: int | None,
                  per_order_charges: Sequence[Decimal] | None) -> None:
    if not orders:
        raise ValueError("an adjustment history needs at least one order")
    if per_order_charges is not None:
        if len(per_order_charges) != len(orders):
            raise ValueError("per_order_charges must be parallel to orders")
        for c in per_order_charges:
            if type(c) is not Decimal or not c.is_finite() or c < 0:
                raise ValueError(f"a charge is a finite Decimal of at least 0, got {c!r}")
    if adjustments_max is not None and (type(adjustments_max) is not int or adjustments_max < 0):
        raise ValueError(f"adjustments_max is a whole number of at least 0, got {adjustments_max!r}")


def _booked(part: Sequence[HistoryOrder], filled: list[PaperOrder]) -> Decimal:
    """The row's booked P&L through closed_booked; appends the row's orders to ``filled`` in order."""
    closes = []
    for o in part:
        p = o.as_paper()
        leg = _closing(filled, p)
        if leg is not None:
            closes.append(leg)
        filled.append(p)
    return closed_booked(closes)


def adjustment_history(orders: Sequence[HistoryOrder], live_prices: Mapping[str, Decimal], *,
                       adjustments_max: int | None,
                       per_order_charges: Sequence[Decimal] | None = None) -> History:
    """The rows and totals of one strategy (module docstring). ``orders`` in placement order; ``live_prices`` the
    open contracts' current prices (an absent one -> the price-dependent totals None); ``per_order_charges``
    parallel to ``orders`` (None -> charges None)."""
    _check_inputs(orders, adjustments_max, per_order_charges)
    filled: list[PaperOrder] = []  # the book of filled orders so far (the averages each close is booked at)
    rows: list[HistoryRow] = []
    adjustments = 0
    for index in _steps(orders):
        part = tuple(orders[i] for i in index)
        kind = part[0].kind
        step: Step = "settle" if kind == "settle" else "stop" if kind == "stop" else (
            "entry" if not rows else "adjustment")
        number = None
        if step == "adjustment":
            adjustments += 1
            number = adjustments
        fill = _row_fill(part)
        booked = None if fill in PENDING_FILLS else _booked(part, filled)
        charges = None if per_order_charges is None else sum((per_order_charges[i] for i in index), Decimal(0))
        rows.append(HistoryRow(step, number, part[0].placed_at, part,
                               trade_credit((o.side, o.price, o.quantity) for o in part), booked, charges, fill,
                               _row_rule(part)))
    return History(tuple(rows), _totals(rows, filled, live_prices, adjustments_max))


def _totals(rows: Sequence[HistoryRow], filled: Sequence[PaperOrder], live_prices: Mapping[str, Decimal],
            adjustments_max: int | None) -> HistoryTotals:
    done = [r for r in rows if not r.pending]
    booked = sum((r.booked for r in done if r.booked is not None), Decimal(0))
    credit = sum((r.cash for r in done), Decimal(0))
    used = sum(1 for r in done if r.step == "adjustment")
    charges = None if any(r.charges is None for r in done) else sum((r.charges for r in done if r.charges is not None),
                                                                    Decimal(0))
    if not filled:  # every step pending: nothing is held, nothing booked
        return HistoryTotals(Decimal(0), Decimal(0), Decimal(0), Decimal(0), Decimal(0), 0, adjustments_max, charges)
    view = net_positions(filled, live_prices)
    if view.booked != booked:
        raise HistoryMismatch(f"booked: rows add to {booked}, the engine's book says {view.booked}")
    if view.cash != credit:
        raise HistoryMismatch(f"credit collected: rows add to {credit}, the engine's book says {view.cash}")
    open_pnl, pnl = view.unbooked, view.total
    if pnl is not None and open_pnl is not None and pnl != booked + open_pnl:
        raise HistoryMismatch(f"P&L {pnl} is not booked {booked} + open {open_pnl}")
    open_legs = [p for p in view.positions if p.net_quantity != 0]
    left: Decimal | None = None
    if all(p.instrument_id in live_prices for p in open_legs):
        left = premium_left(("BUY" if p.net_quantity > 0 else "SELL", live_prices[p.instrument_id],
                             abs(p.net_quantity)) for p in open_legs)
    return HistoryTotals(pnl, booked, open_pnl, credit, left, used, adjustments_max, charges)
