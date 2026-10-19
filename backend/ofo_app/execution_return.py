"""W-096: the parts of the return from Kite that need no database (REQ-073 AC-3, ADR-105, design review 3/5/6).

Spec basis: REQ-073 AC-3 ("When the user returns from Kite, the platform reads the actual order states and positions
from Zerodha and reconciles them (REQ-057, REQ-060); a basket the user closed or only partly placed is handled as a
partial execution (REQ-058), never retried automatically."); REQ-057 AC-2 (a submitted order changes nothing until the
broker confirms execution); REQ-058 AC-2 (the four choices, in order) and AC-6 (never resubmitted); REQ-060 AC-7 (units
in no strategy block no strategy; a shortfall or the wrong side blocks this one); ADR-050 item 4(d) (external orders
recorded, never dropped).

- ``TodaysBook``: THIS strategy's rows of today's book, built by ``ofo_app.return_book.read_book`` (the one place Kite's
  reply rows are read; this module imports no Kite module, REQ-063 AC-1).
- ``classify``: one open plan against the book. The status word is kept as read and only asked "terminal?" against
  ``execute_plan.TERMINAL_ORDER_STATUSES`` (an allow-list; any other or unknown word is still working, finding
  trust-broker-status-word); quantities come from ``filled_quantity``, which must equal the sum of today's trades for
  that order, else the plan stays open and needs reconciliation (never pick one).
- ``drifted``: a CLOSED plan whose tags show, in today's book, a filled quantity other than the one stored at close (an
  order that appeared or filled after the close) needs reconciliation (design review finding 5).
- ``reconcile``: per contract the strategy traded, Zerodha's net minus the units every OTHER stored strategy holds is
  this strategy's share; ``execute_plan.strategy_blocked`` decides the block (one copy of REQ-060 AC-7). Units beyond
  the strategy are unexplained: listed, blocking nothing. A contract another strategy touches through an OPEN plan or
  a DRIFTED closed plan (``unsettled_orders``) is undecidable for this one: reconciliation required, never a pass (its
  units at Zerodha may be the other strategy's; review round 1 MAJOR 1).
- ``classify`` never closes a plan created before today's trading session (IST date on the database clock): Kite's book
  holds only today's orders, so "no tag today" says nothing about it (review round 1 MAJOR 2).

Documented limits (review round 1 MINOR 4-6): an unrelated standalone position on the same contract keeps ``exited``
from being reached; the realised P&L is from today's fills only; an external order is marked only by its correlation id.
"""
from __future__ import annotations

import datetime
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from ofo.orders.model import FillEvent, realised_pnl
from ofo.timeutil import IST

from ofo_app import execute_plan as ep
from ofo_app.execution_plan_store import PlanOrder, StoredPlan

WAITING = "waiting"
FILLED = "filled"
EXITED = "exited"
NOTHING_PLACED = "nothing_placed"
PARTIAL = "partial"
RECONCILE = "reconciliation_required"
#: REQ-058 AC-2, in its order: "Complete Strategy, Retry Failed Leg, Review Manually, Close Partial Strategy."
PARTIAL_CHOICES = ("complete_strategy", "retry_failed_leg", "review_manually", "close_partial_strategy")
#: Mismatch kinds, named by their catalogue template (ofo.reconciliation.compare's ids; the screen renders the text).
MISSING, SIDE, QUANTITY = "recon_missing_platform_position", "recon_side_mismatch", "recon_quantity_mismatch"
#: Why reconciliation is required where no quantity can be compared (named in the reply).
EARLIER_SESSION = "plan_from_earlier_session"
OTHER_UNSETTLED = "another_strategy_plan_unsettled"
DUPLICATE_TAG = "duplicate_tag"  # a basket posted twice: one tag on more broker orders than the plan holds (ADR-117 (g))


class _Side(Protocol):
    @property
    def value(self) -> str: ...


class OrderRow(Protocol):
    """What the matching reads from one parsed broker order row (built by ``return_book``, the Kite reply reader;
    this module imports no Kite module, REQ-063 AC-1)."""

    @property
    def order_id(self) -> str: ...
    @property
    def status(self) -> str: ...
    @property
    def tradingsymbol(self) -> str: ...
    @property
    def side(self) -> _Side: ...
    @property
    def filled_quantity(self) -> int: ...


@dataclass(frozen=True)
class TodaysBook:
    ours: Mapping[str, tuple[OrderRow, ...]]  # stored tag -> its rows (a basket posted twice -> two rows)
    external: tuple[Mapping[str, object], ...]  # rows tagged for this strategy with no stored plan, as read
    traded: Mapping[str, int]  # order id -> today's traded units (de-duplicated)
    fills: tuple[FillEvent, ...]  # our orders' fills, each (order id, trade id) once
    conflicting: frozenset[str]  # order ids whose trades repeat a key with other content


@dataclass(frozen=True)
class PlanAnswer:
    state: str  # WAITING | RECONCILE (plan stays open) or FILLED | NOTHING_PLACED | PARTIAL (a close reason)
    filled: Mapping[str, int]  # tag -> Zerodha's filled quantity (empty while the plan stays open)
    reason: str | None = None  # why reconciliation is required when it is not a disagreement in the book


def _agrees(order: PlanOrder, row: OrderRow, book: TodaysBook) -> bool:
    """The row is the planned order (same contract, same side) and Zerodha's fill count equals its trades."""
    return (row.tradingsymbol == order.tradingsymbol and row.side.value == order.transaction_type
            and row.order_id not in book.conflicting and book.traded.get(row.order_id, 0) == row.filled_quantity)


def _close_reason(plan: StoredPlan, filled: Mapping[str, int]) -> str:
    if all(filled[o.tag] == o.quantity for o in plan.orders):
        return FILLED
    if all(filled[o.tag] == 0 for o in plan.orders):
        return NOTHING_PLACED  # every order ended unfilled, or the user closed the basket (no tag in the book)
    return PARTIAL


def from_earlier_session(plan: StoredPlan, today: datetime.date) -> bool:
    """The plan was not created in today's trading session (IST date); an unreadable stamp counts as earlier."""
    created = plan.created_at
    return created is None or created.tzinfo is None or created.astimezone(IST).date() != today


def classify(plan: StoredPlan, book: TodaysBook, today: datetime.date) -> PlanAnswer:
    """Zerodha's answer for one OPEN plan. Nothing here is resent or retried (REQ-058 AC-6). A plan from an earlier
    session is never closed from today's book: it stays open, reconciliation required."""
    if from_earlier_session(plan, today):
        return PlanAnswer(RECONCILE, {}, EARLIER_SESSION)
    rows = {o.tag: book.ours.get(o.tag, ()) for o in plan.orders}
    if any(len(found) > 1 for found in rows.values()):
        return PlanAnswer(RECONCILE, {}, DUPLICATE_TAG)  # one tag, two broker orders: never summed, never picked
    if any(r.status not in ep.TERMINAL_ORDER_STATUSES for found in rows.values() for r in found):
        return PlanAnswer(WAITING, {})  # REQ-057 AC-2: an order still working changes nothing
    filled = {}
    for order in plan.orders:
        if not all(_agrees(order, r, book) for r in rows[order.tag]):
            return PlanAnswer(RECONCILE, {})
        filled[order.tag] = sum(r.filled_quantity for r in rows[order.tag])
        if filled[order.tag] > order.quantity:
            return PlanAnswer(RECONCILE, {})  # more filled than planned (a basket posted twice)
    return PlanAnswer(_close_reason(plan, filled), filled)


def drifted(history: Sequence[StoredPlan], book: TodaysBook) -> tuple[int, ...]:
    """Closed plans whose orders, in today's book, are not terminal or filled other than stored at close."""
    out = []
    for plan in history:
        if plan.status != "closed":
            continue
        for order in plan.orders:
            found = book.ours.get(order.tag, ())
            if not found:
                continue  # not in today's book (another day): nothing to compare
            moving = any(r.status not in ep.TERMINAL_ORDER_STATUSES for r in found)
            if moving or len(found) > 1 or sum(r.filled_quantity for r in found) != (order.filled_quantity or 0):
                out.append(plan.plan_number)
                break
    return tuple(out)


def unsettled_orders(history: Sequence[StoredPlan], book: TodaysBook) -> tuple[PlanOrder, ...]:
    """Another strategy's orders whose units cannot be counted: every order of an OPEN plan (Zerodha may have filled
    it; its stored filled quantity is not known yet) and of a closed plan that has drifted in ``book`` (that
    strategy's own rows of today's book)."""
    moved = set(drifted(history, book))
    return tuple(o for p in history if p.status != "closed" or p.plan_number in moved for o in p.orders)


@dataclass(frozen=True)
class ContractCheck:
    key: tuple
    platform_units: int  # what this strategy holds by its stored fills (BUY +, SELL -)
    zerodha_units: int  # Zerodha's account-wide net
    other_units: int  # what every other stored strategy holds
    kind: str | None  # a blocking mismatch's catalogue id, else None
    undecidable: str | None = None  # OTHER_UNSETTLED: another strategy's units here are unknown -> reconcile

    @property
    def blocks(self) -> bool:
        return self.kind is not None or self.undecidable is not None

    @property
    def unexplained(self) -> int:
        """Zerodha's units beyond every stored strategy: listed, blocking nothing (REQ-060 AC-7)."""
        return self.zerodha_units - self.other_units - self.platform_units


def _kind(share: int, units: int) -> str | None:
    if not ep.strategy_blocked({"c": share}, {"c": units}):
        return None
    if share == 0:
        return MISSING
    return SIDE if (share > 0) != (units > 0) else QUANTITY


def reconcile(keys: Sequence[tuple], held: Mapping[tuple, int], others: Mapping[tuple, int],
              broker_net: Mapping[tuple, int], undecidable: frozenset = frozenset()) -> tuple[ContractCheck, ...]:
    """One row per contract the strategy traded (``keys``). A key in ``undecidable`` (another strategy's open or
    drifted plan touches it) is never decided: reconciliation required, whatever the numbers say."""
    rows = []
    for key in keys:
        units, other, net = held.get(key, 0), others.get(key, 0), broker_net.get(key, 0)
        unknown = OTHER_UNSETTLED if key in undecidable else None
        rows.append(ContractCheck(key, units, net, other, _kind(net - other, units), unknown))
    return tuple(rows)


def exit_is_clean(checks: Sequence[ContractCheck]) -> bool:
    """An EXIT reads ``exited`` only when the strategy holds 0 on every contract AND Zerodha agrees: no mismatch and
    no units left beyond the other strategies (Zerodha still holding them is not an exit)."""
    return all(c.platform_units == 0 and not c.blocks and c.unexplained == 0 for c in checks)


def pnl_or_none(fills: Sequence[FillEvent]):
    """ADR-102 through the one engine: the fills' realised P&L when they leave every contract flat, else None."""
    try:
        return realised_pnl(fills)
    except ValueError:
        return None


__all__ = ["DUPLICATE_TAG", "EARLIER_SESSION", "EXITED", "FILLED", "NOTHING_PLACED", "OTHER_UNSETTLED", "PARTIAL", "PARTIAL_CHOICES",
           "RECONCILE", "WAITING",
           "ContractCheck", "OrderRow", "PlanAnswer", "TodaysBook", "classify", "drifted", "exit_is_clean",
           "from_earlier_session", "pnl_or_none", "reconcile", "unsettled_orders"]
