"""Recovery of a partly executed or blocked strategy: which actions are offered and what each would build (#380-3).

Spec basis: ADR-136 (1)-(7) (amends REQ-058 AC-2), ADR-137 (1)-(5) (amends REQ-060), ADR-135 (four order states),
ADR-117 (2)(b) (a sell at most what its protective buy filled), ADR-100/ADR-079 (the app never edits, cancels or
re-prices an order; never a second order for a leg still open), REQ-055 AC-4 (margin short), Q223 (cancel open entry
orders on Kite first), Q238 / #389 (exits: buy back the shorts first, then sell the longs).

This module decides only from ZERODHA's own reads (``ZerodhaRead``: the day's whole order book and the net positions),
never from a caller's verdict (finding caller-supplied-verdict-trusted). It places nothing and talks to nobody: an
action that builds orders returns the legs of exactly ONE basket; the route prices them fresh, runs the shared gate
(``recovery_gate`` -> ``check_pre_execution``: market hours, kill switch, reconciliation block, data health) and builds
the Kite basket through the one basket path.

Guards are allow-lists (finding guard-as-forbidden-list): an order is settled only when its status is one of Kite's
three terminal statuses; ANY other text (OPEN, TRIGGER PENDING, an unknown status) counts as still open and refuses.

Answer states of Zerodha's reads and what each does (standing item (d)):
- stated: rows read and parsed -> decided from them.
- absent: a planned contract has no row -> nothing was sent or filled for it (ADR-135 "Not sent to Zerodha").
- not found: no row carries the plan's tags at all -> nothing filled -> not a partial state (``NOT_PARTIAL``).
- failed: a read could not be made (``None``) -> every action refused ``READ_FAILED``.
- empty: an empty book / no net rows -> stated "nothing" (all flat); not a partial state.
- ambiguous: two rows with one of our tags, or a read stamped in the future/too old -> refused (``AMBIGUOUS`` /
  ``READ_STALE``).
"""
from __future__ import annotations

import datetime
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Final

from ofo.engine import Action, Leg, Strategy, strategy_metrics
from ofo.engine.metrics import MultiExpiryError, StrategyMetrics
from ofo.errors.explanations import CHOICE_LABEL_TEXT, ExplanationText, render_explanation
from ofo.execution.basket import parse_tag
from ofo.execution.planned import ExecutionPlan, PlannedLeg
from ofo.execution.safety import SafetyResult, check_pre_execution
from ofo.execution.sequence import protects
from ofo.instruments.models import is_lot_aligned
from ofo.timeutil import IST, MAX_READ_AGE, MAX_READ_FUTURE_SKEW, SESSION_CLOSE, SESSION_OPEN

#: Kite's terminal order statuses: the ONE home (``ofo_app.execute_plan`` imports it). Anything else is open.
TERMINAL_ORDER_STATUSES: Final = frozenset({"COMPLETE", "CANCELLED", "REJECTED"})


class RecoveryAction(Enum):
    """ADR-136 (1) and ADR-137 (1): the labels are the decisions' own words (CHOICE_LABEL_TEXT)."""

    CHECK_WITH_ZERODHA = CHOICE_LABEL_TEXT["CHECK_WITH_ZERODHA"]
    PLACE_MISSING_LEGS = CHOICE_LABEL_TEXT["PLACE_MISSING_LEGS"]
    CLOSE_FILLED_LEGS = CHOICE_LABEL_TEXT["CLOSE_FILLED_LEGS"]
    MANAGE_ON_KITE = CHOICE_LABEL_TEXT["MANAGE_ON_KITE"]
    CHANGE_PRICE_ON_KITE = CHOICE_LABEL_TEXT["CHANGE_PRICE_ON_KITE"]
    USE_ZERODHA_NUMBERS = CHOICE_LABEL_TEXT["USE_ZERODHA_NUMBERS"]
    CLOSE_VIA_BASKET = CHOICE_LABEL_TEXT["CLOSE_VIA_BASKET"]


class Refusal(Enum):
    """Why an action builds nothing. The six ADR-142 lines come from ``refusal_line``; other codes have no line."""

    READ_FAILED = "read_failed"
    READ_STALE = "read_stale"
    AMBIGUOUS = "ambiguous"
    NOT_PARTIAL = "not_partial"
    ORDER_OPEN = "order_open"  # ADR-136 (2): never a second order for a leg still open (any tag)
    ENTRY_ORDER_OPEN = "entry_order_open"  # Q223: cancel it on Kite first
    MARGIN_SHORT = "margin_short"  # ADR-136 (3)
    MARGIN_UNKNOWN = "margin_unknown"  # fail closed
    NOT_WHOLE_LOTS = "not_whole_lots"
    NOTHING_TO_PLACE = "nothing_to_place"
    NOTHING_TO_CLOSE = "nothing_to_close"
    BLOCKED = "reconciliation_blocked"  # ADR-120 (2)
    NOT_BLOCKED = "not_blocked"
    CLOSING = "closing_started"  # a later plan of ours already sells/buys back a filled leg: never "place missing"
    GATE = "gate"  # the shared gate refused (market hours, kill switch, data, ...)


@dataclass(frozen=True)
class ZerodhaOrder:
    """One row of Zerodha's order book (any tag, or none)."""

    contract: str
    side: Action
    status: str
    quantity: int
    filled_quantity: int
    tag: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.side, Action) or not isinstance(self.status, str):
            raise ValueError(f"order row needs an Action side and a status text, got {self.side!r} {self.status!r}")
        for name, value in (("quantity", self.quantity), ("filled_quantity", self.filled_quantity)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer, got {value!r}")
        if self.filled_quantity > self.quantity:
            raise ValueError(f"filled {self.filled_quantity} exceeds ordered {self.quantity}")

    @property
    def is_open(self) -> bool:
        return self.status not in TERMINAL_ORDER_STATUSES


@dataclass(frozen=True)
class ZerodhaRead:
    """Zerodha's two reads. ``None`` = the read failed. A contract absent from ``net`` is flat."""

    orders: tuple[ZerodhaOrder, ...] | None
    net: Mapping[str, int] | None
    read_at: datetime.datetime


@dataclass(frozen=True)
class RecoveryLeg:
    """One order of a recovery basket: the planned leg's contract, the side to send and the units."""

    leg_ref: str
    contract: str
    side: Action
    units: int


@dataclass(frozen=True)
class Outcome:
    """What an action does: the legs of ONE basket (empty when refused) or the refusal, plus the worst case after it."""

    action: RecoveryAction
    legs: tuple[RecoveryLeg, ...] = ()
    refusal: Refusal | None = None
    contracts: tuple[str, ...] = ()  # the contracts a refusal names (open orders, short margin ...)
    step: int = 1  # Close: 1 = buy back the shorts, 2 = sell the longs (Q238)
    worst_case_after: Decimal | None = None  # engine max loss of the position after the choice (ADR-136 (4))
    units_after: Mapping[str, int] = field(default_factory=dict)  # Use Zerodha's numbers: the new units per contract

    @property
    def builds(self) -> bool:
        return self.refusal is None and bool(self.legs)


@dataclass(frozen=True)
class Scope:
    """Which plan of which strategy, the lot size per contract, the route clock, and whether the strategy is blocked
    (read by the caller from the one reconciler, never from the user)."""

    strategy_number: int
    plan_version: int
    lot_sizes: Mapping[str, int]
    now: datetime.datetime
    blocked: bool


@dataclass(frozen=True)
class MarginAnswer:
    """Zerodha's figures for the missing-legs basket; ``None`` = not read (fail closed)."""

    available: Decimal | None
    required: Decimal | None


def _fresh(read: ZerodhaRead, now: datetime.datetime) -> Refusal | None:
    if read.read_at.utcoffset() is None or now.utcoffset() is None:
        raise ValueError("read_at and now must be timezone-aware")
    if read.read_at - now > MAX_READ_FUTURE_SKEW or now - read.read_at > MAX_READ_AGE:
        return Refusal.READ_STALE
    return None


def _ours(order: ZerodhaOrder, strategy_number: int) -> bool:
    try:
        return parse_tag(order.tag).strategy_id == strategy_number
    except ValueError:
        return False


@dataclass(frozen=True)
class _Fills:
    filled: dict[str, int]  # planned contract -> units our ENTRY orders filled (the plan's side)
    open_entries: tuple[str, ...]  # contracts with one of our entry orders still open
    open_any: frozenset[str]  # every contract with ANY open order, whatever its tag (ADR-136 (2))
    closing: frozenset[str] = frozenset()  # contracts a LATER plan of ours trades on the closing side


def _fills(plan: ExecutionPlan, orders: tuple[ZerodhaOrder, ...], strategy_number: int,
           plan_version: int) -> _Fills | Refusal:
    """Our orders of ``plan_version`` AND of every later plan (a Place missing legs basket is a new plan number, so
    its fills count towards the same planned legs: a second press never re-places what the first one filled). A later
    plan's order on the opposite side is a close (``closing``); on the base plan it is ambiguous."""
    filled = {p.contract: 0 for p in plan.legs}
    tags: set[str] = set()
    open_entries: list[str] = []
    closing: set[str] = set()
    for order in orders:
        if not _ours(order, strategy_number) or parse_tag(order.tag).plan_version < plan_version:
            continue
        planned = plan.by_contract(order.contract)
        if order.tag in tags or planned is None:
            return Refusal.AMBIGUOUS  # a tag twice, or our tag on a contract the plan does not have
        tags.add(order.tag)
        if order.side is not planned.leg.action:
            if parse_tag(order.tag).plan_version == plan_version:
                return Refusal.AMBIGUOUS  # the base plan's own tag on the other side
            closing.add(order.contract)
            continue
        filled[order.contract] += order.filled_quantity
        if order.is_open:
            open_entries.append(order.contract)
    open_any = frozenset(o.contract for o in orders if o.is_open)
    return _Fills(filled, tuple(open_entries), open_any, frozenset(closing))


def _lot(plan_leg: PlannedLeg, lot_sizes: Mapping[str, int]) -> int:
    lot = lot_sizes.get(plan_leg.contract)
    if isinstance(lot, bool) or not isinstance(lot, int) or lot <= 0:
        raise ValueError(f"no lot size for {plan_leg.contract!r}")
    return lot


def _worst(legs: Sequence[Leg]) -> Decimal | None:
    """The engine's max loss of ``legs`` (ADR-136 (4)); None when flat or not exactly computable."""
    if not legs:
        return None
    try:
        metrics: StrategyMetrics = strategy_metrics(Strategy(tuple(legs)))
    except MultiExpiryError:
        return None
    return metrics.max_loss if isinstance(metrics.max_loss, Decimal) else None


def _held_legs(plan: ExecutionPlan, units: Mapping[str, int]) -> list[Leg]:
    return [Leg(p.leg.action, p.leg.instrument, p.leg.strike, p.leg.expiry, units[p.contract], p.leg.entry_price)
            for p in plan.legs if units.get(p.contract, 0) > 0]


def _start(read: ZerodhaRead, now: datetime.datetime, blocked: bool) -> Refusal | None:
    if read.orders is None:
        return Refusal.READ_FAILED
    stale = _fresh(read, now)
    if stale is not None:
        return stale
    return Refusal.BLOCKED if blocked else None


def _sell_cap(p: PlannedLeg, plan: ExecutionPlan, filled: Mapping[str, int], lot: int) -> int:
    """ADR-117 (2)(b): a sell at most what its protective buys filled, less what other filled sells already use of
    the same protection; whole lots only."""
    cover = sum(filled[q.contract] for q in plan.legs if protects(q.leg, p.leg))
    used = sum(filled[s.contract] for s in plan.legs if s is not p and s.leg.action is Action.SELL
               and any(protects(q.leg, s.leg) and protects(q.leg, p.leg) for q in plan.legs))
    return max(0, cover - used) // lot * lot


def _missing(plan: ExecutionPlan, fills: _Fills, lot_sizes: Mapping[str, int]) -> tuple[RecoveryLeg, ...] | Outcome:
    action = RecoveryAction.PLACE_MISSING_LEGS
    filled = fills.filled
    missing = {p.contract: p.leg.quantity - filled[p.contract] for p in plan.legs
               if filled[p.contract] < p.leg.quantity}
    open_missing = tuple(c for c in missing if c in fills.open_any)
    if open_missing:
        return Outcome(action, refusal=Refusal.ORDER_OPEN, contracts=open_missing)
    legs: list[RecoveryLeg] = []
    for p in plan.legs:
        lot = _lot(p, lot_sizes)
        if not (is_lot_aligned(filled[p.contract], lot) and is_lot_aligned(p.leg.quantity, lot)):
            return Outcome(action, refusal=Refusal.NOT_WHOLE_LOTS, contracts=(p.contract,))
        units = missing.get(p.contract, 0)
        if units and p.leg.action is Action.SELL:
            units = min(units, _sell_cap(p, plan, filled, lot))
        if units:
            legs.append(RecoveryLeg(p.leg_ref, p.contract, p.leg.action, units))
    return tuple(legs)


def missing_legs(plan: ExecutionPlan, read: ZerodhaRead, scope: Scope) -> Outcome:
    """ADR-136 (1) "Place missing legs", before margin: quantity = planned minus filled in whole lots; each sell at
    most what its protective buys filled (ADR-117 (2)(b)); refused while ANY order is open on a missing contract."""
    action = RecoveryAction.PLACE_MISSING_LEGS
    fills = _start(read, scope.now, scope.blocked) or _fills(plan, read.orders, scope.strategy_number,
                                                             scope.plan_version)
    if isinstance(fills, Refusal):
        return Outcome(action, refusal=fills)
    filled = fills.filled
    if not any(filled.values()) or all(filled[p.contract] >= p.leg.quantity for p in plan.legs):
        return Outcome(action, refusal=Refusal.NOT_PARTIAL)
    if fills.closing:
        return Outcome(action, refusal=Refusal.CLOSING, contracts=tuple(sorted(fills.closing)))
    legs = _missing(plan, fills, scope.lot_sizes)
    if isinstance(legs, Outcome) or not legs:
        return legs or Outcome(action, refusal=Refusal.NOTHING_TO_PLACE)
    after = dict(filled)
    for leg in legs:
        after[leg.contract] += leg.units
    return Outcome(action, legs=legs, worst_case_after=_worst(_held_legs(plan, after)))


def place_missing_legs(plan: ExecutionPlan, read: ZerodhaRead, margin: MarginAnswer, scope: Scope) -> Outcome:
    """``missing_legs`` plus Zerodha's margin for exactly that basket (REQ-055 AC-4 / ADR-136 (3)): unread -> refused;
    short -> refused, and only Close filled legs / keep remain offered (``offers``)."""
    out = missing_legs(plan, read, scope)
    if not out.builds:
        return out
    if not isinstance(margin.available, Decimal) or not isinstance(margin.required, Decimal):
        return Outcome(out.action, refusal=Refusal.MARGIN_UNKNOWN)
    if max(margin.required, Decimal(0)) > margin.available:
        return Outcome(out.action, refusal=Refusal.MARGIN_SHORT)
    return out


def shorts_first(signed: Mapping[str, int]) -> tuple[int, dict[str, int]]:
    """Q238 / #389, the ONE home of the exit order: step 1 = every contract held short (negative units), so the
    buy-backs go first; only when nothing is short, step 2 = every long. Zero units are dropped. A mix of shorts and
    longs therefore always takes two baskets, the longs never before the shorts are bought back."""
    for value in signed.values():
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"signed units must be integers, got {value!r}")
    shorts = {c: u for c, u in signed.items() if u < 0}
    return (1, shorts) if shorts else (2, {c: u for c, u in signed.items() if u > 0})


def _close(action: RecoveryAction, plan: ExecutionPlan, read: ZerodhaRead, held_cap: Mapping[str, int],
           open_any: frozenset[str]) -> Outcome:
    """Q238 / #389: step 1 buys back every short Zerodha still shows; only once Zerodha shows no short left does
    step 2 sell the longs. Refused while any order is open on a contract it would trade."""
    if read.net is None:
        return Outcome(action, refusal=Refusal.READ_FAILED)
    held = {p.contract: min(abs(read.net.get(p.contract, 0)), held_cap.get(p.contract, 0)) for p in plan.legs}
    step, chosen = shorts_first({p.contract: held[p.contract] * (1 if read.net.get(p.contract, 0) > 0 else -1)
                                 for p in plan.legs})
    group = [p for p in plan.legs if p.contract in chosen]
    side = Action.BUY if step == 1 else Action.SELL
    if not group:
        return Outcome(action, refusal=Refusal.NOTHING_TO_CLOSE)
    busy = tuple(p.contract for p in group if p.contract in open_any)
    if busy:
        return Outcome(action, refusal=Refusal.ORDER_OPEN, contracts=busy)
    legs = tuple(RecoveryLeg(p.leg_ref, p.contract, side, held[p.contract]) for p in group)
    after = {p.contract: held[p.contract] for p in plan.legs}
    for leg in legs:
        after[leg.contract] = 0
    signed = [p for p in plan.legs if after[p.contract]]
    worst = _worst([Leg(Action.BUY if read.net[p.contract] > 0 else Action.SELL, p.leg.instrument, p.leg.strike,
                        p.leg.expiry, after[p.contract], p.leg.entry_price) for p in signed])
    return Outcome(action, legs=legs, step=step, worst_case_after=worst)


def close_filled_legs(plan: ExecutionPlan, read: ZerodhaRead, scope: Scope) -> Outcome:
    """ADR-136 (1) "Close filled legs": refused while one of our entry orders is open (Q223); then two baskets,
    shorts first (Q238). Units = what Zerodha holds, capped at what our entry filled (never outside lots)."""
    action = RecoveryAction.CLOSE_FILLED_LEGS
    fills = _start(read, scope.now, scope.blocked) or _fills(plan, read.orders, scope.strategy_number,
                                                             scope.plan_version)
    if isinstance(fills, Refusal):
        return Outcome(action, refusal=fills)
    if fills.open_entries:
        return Outcome(action, refusal=Refusal.ENTRY_ORDER_OPEN, contracts=fills.open_entries)
    return _close(action, plan, read, fills.filled, fills.open_any)


def close_via_basket(plan: ExecutionPlan, read: ZerodhaRead, *, now: datetime.datetime,
                     blocked: bool) -> Outcome:
    """ADR-137 (3): the blocked-contract exit, shorts first; it exits what ZERODHA holds on the plan's contracts.
    Offered only while the strategy is blocked (the block itself never lifts on its own, ADR-137 (5))."""
    action = RecoveryAction.CLOSE_VIA_BASKET
    if not blocked:
        return Outcome(action, refusal=Refusal.NOT_BLOCKED)
    refused = _start(read, now, False)
    if refused is not None:
        return Outcome(action, refusal=refused)
    if read.net is None:
        return Outcome(action, refusal=Refusal.READ_FAILED)
    cap = {p.contract: abs(read.net.get(p.contract, 0)) for p in plan.legs}
    return _close(action, plan, read, cap, frozenset(o.contract for o in read.orders if o.is_open))


def _numbers_refusal(contract: str, read: ZerodhaRead, holders: Mapping[str, int], now: datetime.datetime,
                     blocked: bool) -> Refusal | None:
    if not blocked:
        return Refusal.NOT_BLOCKED
    refused = _start(read, now, False)
    if refused is not None:
        return refused
    if read.net is None:
        return Refusal.READ_FAILED
    if any(o.contract == contract and o.is_open for o in read.orders):
        return Refusal.ORDER_OPEN
    return None if holders else Refusal.AMBIGUOUS


def use_zerodha_numbers(contract: str, read: ZerodhaRead, *, holders: Mapping[str, int], now: datetime.datetime,
                        blocked: bool) -> Outcome:
    """ADR-137 (2): one audited action, NO order. Needs a fresh read (taken under the per-user lock by the caller) and
    no open order on the contract. ``holders`` = each holder strategy's expected signed units on the contract; the
    result's ``units_after`` gives each holder its new units: 0 when Zerodha is flat (ADR-116), unchanged when Zerodha
    matches all holders again (ADR-123), Zerodha's net for a single holder; several holders with any other net are
    never split by guess (``AMBIGUOUS``)."""
    action = RecoveryAction.USE_ZERODHA_NUMBERS
    refused = _numbers_refusal(contract, read, holders, now, blocked)
    net = 0 if refused is not None else read.net.get(contract, 0)
    if refused is None and net == 0:
        after: dict[str, int] | None = dict.fromkeys(holders, 0)
    elif refused is None and sum(holders.values()) == net:
        after = dict(holders)
    elif refused is None and len(holders) == 1:
        after = dict.fromkeys(holders, net)
    else:
        after = None
        refused = refused or Refusal.AMBIGUOUS
    return Outcome(action, refusal=refused, contracts=(contract,), units_after=after or {})


def offers(plan: ExecutionPlan, read: ZerodhaRead, margin: MarginAnswer, scope: Scope) -> tuple[RecoveryAction, ...]:
    """The actions shown, in the decision's order. Blocked -> ADR-137's two (plus the Kite link, ADR-137 (4)).
    Partial -> ADR-136 (1); margin short -> only Close filled legs (and keep / manage on Kite), ADR-136 (3).
    "Change price on Kite" only while one of our entry orders is still placed."""
    if scope.blocked:
        return (RecoveryAction.USE_ZERODHA_NUMBERS, RecoveryAction.CLOSE_VIA_BASKET, RecoveryAction.MANAGE_ON_KITE)
    if read.orders is None:
        return (RecoveryAction.CHECK_WITH_ZERODHA,)
    fills = _fills(plan, read.orders, scope.strategy_number, scope.plan_version)
    if isinstance(fills, Refusal) or not any(fills.filled.values()):
        return (RecoveryAction.CHECK_WITH_ZERODHA,)
    place = place_missing_legs(plan, read, margin, scope)
    out = [RecoveryAction.CHECK_WITH_ZERODHA]
    if place.refusal is not Refusal.MARGIN_SHORT and place.refusal is not Refusal.NOT_PARTIAL:
        out.append(RecoveryAction.PLACE_MISSING_LEGS)
    out += [RecoveryAction.CLOSE_FILLED_LEGS, RecoveryAction.MANAGE_ON_KITE]
    if fills.open_entries:
        out.append(RecoveryAction.CHANGE_PRICE_ON_KITE)
    return tuple(out)


def recovery_gate(legs: Sequence[Leg], ctx: object, catalogue: object, eligibility: object, *,
                  strategy_id: str) -> SafetyResult:
    """Every recovery basket passes the ONE shared gate (market hours ADR-119, kill switch ADR-127, reconciliation
    block, data health); nothing here re-implements those checks."""
    return check_pre_execution(Strategy(tuple(legs)), ctx, catalogue, eligibility,  # type: ignore[arg-type]
                               strategy_id=strategy_id)


#: ADR-142 (1): the refusals the owner gave a line to; every other refusal has none (``refusal_line`` -> None).
_REFUSAL_LINES: Final = {Refusal.ORDER_OPEN: "recovery_order_open",
                         Refusal.ENTRY_ORDER_OPEN: "recovery_entry_order_open",
                         Refusal.READ_STALE: "recovery_read_stale"}


def refusal_line(out: Outcome, *, margin: MarginAnswer | None = None, holders: int = 0) -> ExplanationText | None:
    """ADR-142 (1): the exact line a refused action shows, from the one catalogue. Margin short needs Zerodha's two
    figures (the same answer the refusal was decided on); "several strategies" is the Use Zerodha's numbers refusal
    with more than one holder. A refusal ADR-142 gives no line to returns None (no wording is invented here)."""
    if out.refusal is Refusal.MARGIN_SHORT:
        if margin is None or margin.available is None or margin.required is None:
            raise ValueError("a margin-short line needs Zerodha's available and required figures")
        return render_explanation("recovery_margin_short", available=margin.available, required=margin.required)
    if (out.refusal is Refusal.AMBIGUOUS and out.action is RecoveryAction.USE_ZERODHA_NUMBERS and holders > 1):
        return render_explanation("recovery_shared_contract")
    template = _REFUSAL_LINES.get(out.refusal) if out.refusal is not None else None
    return None if template is None else render_explanation(template)


_SATURDAY: Final = 5  # datetime.weekday(): Monday 0 .. Friday 4 trade


def overnight_line(now: datetime.datetime, next_day: datetime.date) -> ExplanationText | None:
    """ADR-136 (5) / ADR-142: outside 09:15-15:30 IST on a weekday (or on a weekend) the screen says the position is
    carried overnight, naming the next day the caller read from the market calendar; inside the session, None."""
    if now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    local = now.astimezone(IST)
    if local.weekday() < _SATURDAY and SESSION_OPEN <= local.time() < SESSION_CLOSE:
        return None
    return render_explanation("recovery_overnight", next_day=next_day)


__all__ = [
    "TERMINAL_ORDER_STATUSES",
    "MarginAnswer",
    "Outcome",
    "RecoveryAction",
    "RecoveryLeg",
    "Refusal",
    "Scope",
    "ZerodhaOrder",
    "ZerodhaRead",
    "close_filled_legs",
    "close_via_basket",
    "missing_legs",
    "offers",
    "overnight_line",
    "place_missing_legs",
    "recovery_gate",
    "refusal_line",
    "shorts_first",
    "use_zerodha_numbers",
]
