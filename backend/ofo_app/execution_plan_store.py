"""PostgreSQL store for the persisted execution-plan intent (W-094; ADR-050 item 4b).

Spec basis: ADR-050 item 4 "(b) persist the order intent before sending"; ADR-054 ("Confirmation, reconciliation and
the eight safeguards of ADR-050 item 4 run on the result (tag lookup, order updates, positions)."); REQ-073 AC-2
("Every order in the basket carries our own tag (at most 20 alphanumeric characters) that identifies the strategy and
plan version, so the result is matched by tag, never by symbol (ADR-050 item 4a)."). Schema: migration
0016_execution_plans. Technical decision (GC-2c design review 2026-10-17): the tag's plan version is a per-strategy PLAN
NUMBER minted for every Execute (entry 1, exit 2 on the real order of 2026-10-16); one plan may be open per strategy.

Copy from: none - modelled on ``strategy_store`` (row lock, id checks, error style).

- next_plan_number: locks the strategy row (the lock holds until the caller commits, so two concurrent Execute presses
  cannot both pass), refuses ``plan_open`` while a plan is open, returns max(highest stored, floor) + 1. ``floor`` is
  the highest plan number Zerodha's own order book showed today, so a number Kite already holds is never minted again.
- record_plan: inserts the plan open with its orders, in the same transaction. Every order is checked here again
  (a frozen dataclass can be forged) and the DATABASE checks it a third time: one open plan (partial unique index),
  tag = make_tag(strategy, plan, leg) (Q-grammar since 0018; legacy OFS rows still accepted), tag unique,
  positive quantity and price.
- close_plan: open -> closed once, with a reason; closed_at is the database clock. Nothing reopens a plan. A close
  that changes position also stores Zerodha's trades of each order (``PlanFill``, migration 0020, #313b) in the same
  transaction: exactly the filled quantity per tag, each (order id, trade id) once, prices exact to the paisa.
Transaction control (commit) stays with the caller. Another user's strategy answers exactly like a missing one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, Mapping, Optional, Sequence

from ofo.execution.basket import make_tag
from ofo.instruments.models import ZERODHA
from ofo.limits import INTEGER_MAX
from ofo.money import PAISE
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from ofo_app import reconciliation_store, strategy_store

PLAN_OPEN = "plan_open"
NOT_FOUND = "not_found"
BAD_PLAN = "bad_plan"
TAG_TAKEN = "tag_taken"

ACTIONS = ("ENTRY", "EXIT")
SIDES = ("BUY", "SELL")
#: ``unresolved_from_positions`` (migration 0019, #380 step 2.1): an earlier-day plan the next-day positions cannot
#: settle closes with 0 stored per order; the stored reconciliation mismatch carries the block.
UNRESOLVED = "unresolved_from_positions"
CLOSE_REASONS = ("filled", "exited", "nothing_placed", "partial", UNRESOLVED)
_NO_FILLS_REASONS = ("nothing_placed", UNRESOLVED)  # closes that store 0 for every order and take no fills
PRICE_LIMIT = Decimal(10) ** 12  # NUMERIC(14,2)
_UNIQUE_VIOLATION = "23505"
_CHECK_VIOLATION = "23514"
_ORDER_BOOK_GUARD = "OF020"  # migration 0020's fill trigger (the second layer behind _checked_trades)
_OPEN_INDEX = "execution_plans_one_open"
_PLAN_KEY = "execution_plans_pkey"
_TAG_KEY = "execution_plan_orders_tag_key"


class PlanStoreError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def _int(value: Any, what: str, minimum: int, code: str = BAD_PLAN) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= INTEGER_MAX:
        raise PlanStoreError(code, f"{what} must be an integer from {minimum} to {INTEGER_MAX}, got {value!r}")
    return value


def _text(value: Any, what: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise PlanStoreError(BAD_PLAN, f"{what} must be non-empty text, got {value!r}")
    return value


def _limit_price(value: Any) -> Decimal:
    if (not isinstance(value, Decimal) or not value.is_finite() or value <= 0 or value >= PRICE_LIMIT
            or value != value.quantize(PAISE)):
        raise PlanStoreError(BAD_PLAN, f"price must be a positive Decimal with at most 2 decimals, got {value!r}")
    return value


@dataclass(frozen=True)
class PlanOrder:
    leg_index: int
    tag: str
    instrument_id: str
    tradingsymbol: str
    transaction_type: Literal["BUY", "SELL"]
    quantity: int
    price: Decimal
    filled_quantity: Optional[int] = None

    def __post_init__(self) -> None:
        self.check()

    def check(self) -> None:
        """Raises PlanStoreError(bad_plan) unless every field is valid; record_plan calls it again."""
        _int(self.leg_index, "leg_index", 0)
        _text(self.tag, "tag")
        _text(self.instrument_id, "instrument_id")
        _text(self.tradingsymbol, "tradingsymbol")
        if self.transaction_type not in SIDES:
            raise PlanStoreError(BAD_PLAN, f"transaction_type must be BUY or SELL, got {self.transaction_type!r}")
        _int(self.quantity, "quantity", 1)
        _limit_price(self.price)
        if self.filled_quantity is not None and _int(self.filled_quantity, "filled_quantity", 0) > self.quantity:
            raise PlanStoreError(BAD_PLAN, f"filled_quantity {self.filled_quantity} is above {self.quantity}")


@dataclass(frozen=True)
class PlanFill:
    """One Zerodha trade of a plan order (#313b): the tag of the order it fills, Zerodha's order id and trade id, units
    and the trade price. ``close_plan`` stores them; ``order_book_store.fills_for`` reads them back."""

    tag: str
    broker_order_id: str
    trade_id: str
    quantity: int
    price: Decimal

    def __post_init__(self) -> None:
        self.check()

    def check(self) -> None:
        """Raises PlanStoreError(bad_plan) unless every field is valid; close_plan calls it again."""
        _text(self.tag, "tag")
        _text(self.broker_order_id, "broker_order_id")
        _text(self.trade_id, "trade_id")
        _int(self.quantity, "quantity", 1)
        _limit_price(self.price)  # more than 2 decimals is refused here, before NUMERIC(14,2) would round it


@dataclass(frozen=True)
class StoredPlan:
    strategy_id: int
    plan_number: int
    action: Literal["ENTRY", "EXIT"]
    status: Literal["open", "closed"]
    orders: tuple[PlanOrder, ...]
    created_at: datetime
    closed_at: Optional[datetime]
    close_reason: Optional[str]
    strategy_version: Optional[int] = None  # noqa: UP045 - W-144: the version it was built from; None never activates


_OWNED = text("SELECT 1 FROM public.strategies WHERE id = :s AND user_ref = :u AND deleted_at IS NULL")
_HIGHEST = text("SELECT coalesce(max(plan_number), 0) FROM public.execution_plans WHERE strategy_id = :s")
_OPEN = text("SELECT plan_number FROM public.execution_plans WHERE strategy_id = :s AND status = 'open'")
_INSERT_PLAN = text("INSERT INTO public.execution_plans (strategy_id, plan_number, action, strategy_version) "
                    "VALUES (:s, :p, :a, :v)")
_INSERT_ORDER = text(
    "INSERT INTO public.execution_plan_orders (strategy_id, plan_number, leg_index, tag, instrument_id, "
    "transaction_type, quantity, price) VALUES (:s, :p, :l, :tag, :iid, :side, :q, :price)")
_TAGS_TAKEN = text("SELECT tag FROM public.execution_plan_orders WHERE tag = ANY(:tags)")
_PLANS = text("SELECT plan_number, action, status, created_at, closed_at, close_reason, strategy_version "
              "FROM public.execution_plans WHERE strategy_id = :s ORDER BY plan_number")
_ORDERS = text("SELECT plan_number, leg_index, tag, instrument_id, transaction_type, quantity, price, "
               "filled_quantity "
               "FROM public.execution_plan_orders WHERE strategy_id = :s ORDER BY plan_number, leg_index")
# The Zerodha trading symbol is NOT stored on the plan (identity rule: broker identifiers live only in
# broker_instruments, ADR-050 item 2). It is checked against, and read back from, the catalogue by instrument_id.
_SYMBOLS = text(
    "SELECT b.broker_symbol, (NOT c.retired AND NOT c.delisted) AS live FROM public.catalogue_contracts AS c "
    "JOIN public.broker_instruments AS b ON b.contract_id = c.id "
    "WHERE c.exchange_segment = :seg AND c.exchange_token = :tok AND b.broker = :broker")
_LOCK_PLAN = text("SELECT status FROM public.execution_plans WHERE strategy_id = :s AND plan_number = :p FOR UPDATE")
_SET_FILLED = text("UPDATE public.execution_plan_orders SET filled_quantity = :f "
                   "WHERE strategy_id = :s AND plan_number = :p AND tag = :tag")
_CLOSE = text("UPDATE public.execution_plans SET status = 'closed', close_reason = :r "
              "WHERE strategy_id = :s AND plan_number = :p AND status = 'open'")
_INSERT_FILL = text("INSERT INTO public.execution_plan_fills (tag, broker_order_id, trade_id, quantity, price) "
                    "VALUES (:tag, :oid, :tid, :q, :price)")
_STORED_TRADES = text("SELECT broker_order_id, trade_id FROM public.execution_plan_fills "
                      "WHERE broker_order_id = ANY(:oids)")


async def zerodha_symbol(conn: Any, instrument_id: str) -> str:
    """The catalogue's ZERODHA trading symbol for ``instrument_id`` ("<segment>:<exchange token>"); no row, or two
    different symbols with none of them live, is ``bad_plan`` (no symbol guessing, ADR-050 item 2)."""
    segment, _, token = instrument_id.rpartition(":")
    if not segment or not token.isascii() or not token.isdigit() or int(token) > 2**63 - 1:
        raise PlanStoreError(BAD_PLAN, f"instrument_id {instrument_id!r} is not <segment>:<exchange token>")
    rows = (await conn.execute(_SYMBOLS, {"seg": segment, "tok": int(token), "broker": ZERODHA})).all()
    live = {r.broker_symbol for r in rows if r.live}
    found = live or {r.broker_symbol for r in rows}
    if len(found) != 1:
        raise PlanStoreError(BAD_PLAN, f"instrument {instrument_id!r} has {len(found)} {ZERODHA} symbols in the "
                                       f"catalogue; a plan needs exactly one")
    return next(iter(found))


async def _check_symbols(conn: Any, orders: tuple[PlanOrder, ...]) -> None:
    for o in orders:
        symbol = await zerodha_symbol(conn, o.instrument_id)
        if o.tradingsymbol != symbol:
            raise PlanStoreError(BAD_PLAN, f"leg {o.leg_index}: tradingsymbol {o.tradingsymbol!r} is not the "
                                           f"catalogue's {ZERODHA} symbol {symbol!r} for {o.instrument_id}")


async def lock_strategy(conn: Any, user_ref: str, strategy_id: Any) -> int:
    """Row-locks the user's strategy until the transaction ends; another user's or a missing one is not_found."""
    try:
        strategy_id = strategy_store.check_strategy_id(strategy_id)
        await strategy_store.lock_strategy(conn, user_ref, strategy_id)
    except strategy_store.StrategyStoreError as exc:
        raise PlanStoreError(NOT_FOUND, f"strategy {strategy_id!r}") from exc
    return strategy_id


async def owned_strategy(conn: Any, user_ref: str, strategy_id: Any) -> int:
    try:
        strategy_id = strategy_store.check_strategy_id(strategy_id)
    except strategy_store.StrategyStoreError as exc:
        raise PlanStoreError(NOT_FOUND, f"strategy {strategy_id!r}") from exc
    if (await conn.execute(_OWNED, {"s": strategy_id, "u": user_ref})).first() is None:
        raise PlanStoreError(NOT_FOUND, f"strategy {strategy_id}")
    return strategy_id


async def next_plan_number(conn: Any, user_ref: str, strategy_id: int, *, floor: int = 0) -> int:
    """The plan number for the next Execute. Run it in the transaction that then calls ``record_plan``."""
    floor = _int(floor, "floor", 0)
    strategy_id = await lock_strategy(conn, user_ref, strategy_id)
    if (await conn.execute(_OPEN, {"s": strategy_id})).first() is not None:
        raise PlanStoreError(PLAN_OPEN, f"strategy {strategy_id} already has an open plan")
    highest = int((await conn.execute(_HIGHEST, {"s": strategy_id})).scalar_one())
    number = max(highest, floor) + 1
    if number > INTEGER_MAX:
        raise PlanStoreError(BAD_PLAN, f"plan number {number} is out of range")
    return number


def _checked_orders(strategy_id: int, plan_number: int, orders: Any) -> tuple[PlanOrder, ...]:
    if not isinstance(orders, tuple) or not orders:
        raise PlanStoreError(BAD_PLAN, "a plan holds a non-empty tuple of orders")
    legs = set()
    for order in orders:
        if not isinstance(order, PlanOrder):
            raise PlanStoreError(BAD_PLAN, f"expected a PlanOrder, got {order!r}")
        order.check()  # a frozen dataclass can still be forged with object.__setattr__
        try:
            own = make_tag(strategy_id, plan_number, order.leg_index)
        except ValueError as exc:
            raise PlanStoreError(BAD_PLAN, str(exc)) from exc
        if order.filled_quantity is not None:
            raise PlanStoreError(BAD_PLAN, "a new plan holds no filled quantity; it is set by close_plan")
        if order.tag != own:
            raise PlanStoreError(BAD_PLAN, f"tag {order.tag!r} is not the tag of strategy {strategy_id}, plan "
                                           f"{plan_number}, leg {order.leg_index} ({own!r})")
        if order.leg_index in legs:
            raise PlanStoreError(BAD_PLAN, f"leg {order.leg_index} appears twice")
        legs.add(order.leg_index)
    if legs != set(range(len(orders))):
        raise PlanStoreError(BAD_PLAN, f"legs must be numbered 0..{len(orders) - 1}, got {sorted(legs)}")
    return orders


def _sqlstate(exc: DBAPIError) -> Optional[str]:
    return getattr(exc.orig, "sqlstate", None)


def _unique_violation(message: str) -> PlanStoreError:
    """Maps the constraint named in the database's message; an unknown unique constraint is never called a tag clash."""
    if _OPEN_INDEX in message:
        return PlanStoreError(PLAN_OPEN, message)
    if _TAG_KEY in message:
        return PlanStoreError(TAG_TAKEN, message)
    if _PLAN_KEY in message:
        return PlanStoreError(BAD_PLAN, f"plan number already stored for this strategy: {message}")
    return PlanStoreError(BAD_PLAN, f"unexpected unique violation: {message}")


async def record_plan(conn: Any, user_ref: str, strategy_id: int, plan_number: int,  # noqa: PLR0913 fixed API
                      action: str, orders: Sequence[PlanOrder], *,
                      strategy_version: Optional[int] = None,  # noqa: UP045
                      ) -> StoredPlan:
    """Stores the plan open, with its orders, and the version number of the definition it was built from (W-144;
    None = unknown, such a plan never activates a version). The caller commits (and has called ``next_plan_number`` in
    the same transaction: the strategy lock is taken here too, so a plan can never be recorded around it)."""
    strategy_id = await lock_strategy(conn, user_ref, strategy_id)
    number = _int(plan_number, "plan_number", 1)
    version = None if strategy_version is None else _int(strategy_version, "strategy_version", 1)
    if action not in ACTIONS:
        raise PlanStoreError(BAD_PLAN, f"action must be ENTRY or EXIT, got {action!r}")
    checked = _checked_orders(strategy_id, number, orders)
    await _check_symbols(conn, checked)
    taken = (await conn.execute(_TAGS_TAKEN, {"tags": [o.tag for o in checked]})).all()
    if taken:
        raise PlanStoreError(TAG_TAKEN, f"tag {taken[0][0]!r} is already stored")
    if (await conn.execute(_OPEN, {"s": strategy_id})).first() is not None:
        raise PlanStoreError(PLAN_OPEN, f"strategy {strategy_id} already has an open plan")
    if number <= int((await conn.execute(_HIGHEST, {"s": strategy_id})).scalar_one()):
        raise PlanStoreError(BAD_PLAN, f"plan number {number} is not above the highest stored plan number")
    try:
        async with conn.begin_nested():
            await conn.execute(_INSERT_PLAN, {"s": strategy_id, "p": number, "a": action, "v": version})
            for o in checked:
                await conn.execute(_INSERT_ORDER, {"s": strategy_id, "p": number, "l": o.leg_index, "tag": o.tag,
                                                   "iid": o.instrument_id,
                                                   "side": o.transaction_type, "q": o.quantity, "price": o.price})
    except DBAPIError as exc:
        state = _sqlstate(exc)
        if state == _UNIQUE_VIOLATION:
            raise _unique_violation(str(exc.orig)) from exc
        if state == _CHECK_VIOLATION:
            raise PlanStoreError(BAD_PLAN, str(exc.orig)) from exc
        raise
    return _one(await _read(conn, strategy_id), number)


def _one(found: tuple[StoredPlan, ...], number: int) -> StoredPlan:
    for plan in found:
        if plan.plan_number == number:
            return plan
    raise PlanStoreError(NOT_FOUND, f"plan {number}")


async def _read(conn: Any, strategy_id: int) -> tuple[StoredPlan, ...]:
    by_plan: dict[int, list[PlanOrder]] = {}
    symbols: dict[str, str] = {}
    for r in (await conn.execute(_ORDERS, {"s": strategy_id})).all():
        if r.instrument_id not in symbols:
            symbols[r.instrument_id] = await zerodha_symbol(conn, r.instrument_id)
        by_plan.setdefault(int(r.plan_number), []).append(PlanOrder(
            leg_index=int(r.leg_index), tag=r.tag, instrument_id=r.instrument_id,
            tradingsymbol=symbols[r.instrument_id],
            transaction_type=r.transaction_type, quantity=int(r.quantity), price=Decimal(r.price),
            filled_quantity=None if r.filled_quantity is None else int(r.filled_quantity)))
    return tuple(
        StoredPlan(strategy_id=strategy_id, plan_number=int(r.plan_number), action=r.action, status=r.status,
                   orders=tuple(by_plan.get(int(r.plan_number), ())), created_at=r.created_at, closed_at=r.closed_at,
                   close_reason=r.close_reason,
                   strategy_version=None if r.strategy_version is None else int(r.strategy_version))
        for r in (await conn.execute(_PLANS, {"s": strategy_id})).all())


async def plans_for(conn: Any, user_ref: str, strategy_id: int) -> tuple[StoredPlan, ...]:
    """Every plan of the strategy, ascending by plan number."""
    return await _read(conn, await owned_strategy(conn, user_ref, strategy_id))


async def open_plan(conn: Any, user_ref: str, strategy_id: int) -> Optional[StoredPlan]:
    found = [p for p in await plans_for(conn, user_ref, strategy_id) if p.status == "open"]
    return found[0] if found else None


def _checked_fills(reason: str, orders: tuple[PlanOrder, ...], filled: Mapping[str, int]) -> dict[str, int]:
    """Zerodha's filled quantity per tag at close, checked against the reason (missing tags count as 0)."""
    if not isinstance(filled, Mapping):
        raise PlanStoreError(BAD_PLAN, f"filled must map tags to quantities, got {filled!r}")
    quantities = {o.tag: o.quantity for o in orders}
    for tag, value in filled.items():
        if tag not in quantities:
            raise PlanStoreError(BAD_PLAN, f"tag {tag!r} is not in this plan")
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= quantities[tag]:
            raise PlanStoreError(BAD_PLAN, f"filled quantity {value!r} for {tag!r} must be 0..{quantities[tag]}")
    full = {tag: filled.get(tag, 0) for tag in quantities}
    some = any(full[t] > 0 for t in quantities)
    short = any(full[t] < quantities[t] for t in quantities)
    if reason in ("filled", "exited") and short:
        raise PlanStoreError(BAD_PLAN, f"reason {reason!r} needs every order filled in full")
    if reason == "nothing_placed" and some:
        raise PlanStoreError(BAD_PLAN, "reason 'nothing_placed' needs every filled quantity to be 0")
    if reason == "partial" and not (some and short):
        raise PlanStoreError(BAD_PLAN, "reason 'partial' needs one order filled at least in part and one not in full")
    return full


def _checked_trades(full: Mapping[str, int], fills: Any) -> tuple[PlanFill, ...]:
    """Zerodha's trades for the closing plan, checked against the filled quantities (an allow-list: each item a
    PlanFill re-checked, a tag of this plan, each (order id, trade id) once, one Zerodha order under one tag, and per
    tag the trades sum EXACTLY to the filled quantity). Returned sorted by (tag, order id, trade id): every writer
    takes the order-row locks and the order-id advisory locks of migration 0020's trigger in one global order (no
    deadlock)."""
    if fills is None:
        fills = ()
    if not isinstance(fills, (tuple, list)):
        raise PlanStoreError(BAD_PLAN, f"fills must be a tuple of PlanFill, got {fills!r}")
    seen: set[tuple[str, str]] = set()
    tag_of_order: dict[str, str] = {}
    units = dict.fromkeys(full, 0)
    for fill in fills:
        if not isinstance(fill, PlanFill):
            raise PlanStoreError(BAD_PLAN, f"expected a PlanFill, got {fill!r}")
        fill.check()  # a frozen dataclass can still be forged with object.__setattr__
        if fill.tag not in full:
            raise PlanStoreError(BAD_PLAN, f"trade {fill.trade_id!r}: tag {fill.tag!r} is not in this plan")
        key = (fill.broker_order_id, fill.trade_id)
        if key in seen:
            raise PlanStoreError(BAD_PLAN, f"trade {fill.trade_id!r} of order {fill.broker_order_id!r} appears twice")
        seen.add(key)
        if tag_of_order.setdefault(fill.broker_order_id, fill.tag) != fill.tag:
            raise PlanStoreError(BAD_PLAN, f"order {fill.broker_order_id!r} appears under two tags")
        units[fill.tag] += fill.quantity
    for tag, filled in full.items():
        if units[tag] != filled:
            raise PlanStoreError(BAD_PLAN, f"the trades of {tag!r} sum to {units[tag]} units; Zerodha filled {filled}")
    return tuple(sorted(fills, key=lambda f: (f.tag, f.broker_order_id, f.trade_id)))


async def _store_trades(conn: Any, trades: tuple[PlanFill, ...]) -> None:
    """Inserts the trades (after the filled quantities are set: migration 0020's trigger reads them). A trade already
    stored, or an order id already stored under any tag, is refused here with a clear error before the database's
    primary key or trigger would refuse it (they stay as the second layer, mapped to bad_plan)."""
    if not trades:
        return
    stored = (await conn.execute(_STORED_TRADES, {"oids": sorted({t.broker_order_id for t in trades})})).all()
    if stored:
        raise PlanStoreError(BAD_PLAN, f"order {stored[0].broker_order_id!r} already has stored trades "
                                       f"(trade {stored[0].trade_id!r})")
    try:
        async with conn.begin_nested():
            for t in trades:
                await conn.execute(_INSERT_FILL, {"tag": t.tag, "oid": t.broker_order_id, "tid": t.trade_id,
                                                  "q": t.quantity, "price": t.price})
    except DBAPIError as exc:
        if _sqlstate(exc) in (_UNIQUE_VIOLATION, _CHECK_VIOLATION, _ORDER_BOOK_GUARD):
            raise PlanStoreError(BAD_PLAN, str(exc.orig)) from exc
        raise


async def close_plan(conn: Any, user_ref: str, strategy_id: int, plan_number: int, *,  # noqa: PLR0913 fixed API
                     reason: str,
                     filled: Optional[Mapping[str, int]] = None,
                     fills: Sequence[PlanFill] = ()) -> StoredPlan:
    """Open -> closed, once. Closing a closed plan is ``bad_plan``; no plan number is ever reused or reopened.
    ``filled`` (tag -> Zerodha's filled quantity at close) is stored on the orders, so a restart can rebuild the
    position from the database. A close that changes position (``filled``, ``exited``, ``partial``) must carry it:
    ``filled=None`` is ``bad_plan`` for those; ``nothing_placed`` with None stores 0 for every order;
    ``unresolved_from_positions`` takes only None, stores 0 for every order, and is refused unless the strategy
    has an unresolved reconciliation mismatch (recorded earlier in this same transaction or before): the mismatch
    carries the block the open plan carried, so the close can never leave the strategy unblocked.
    ``fills`` (#313b) are Zerodha's trades of the plan's orders: per tag they must sum exactly to the filled quantity
    (so a close with fills carries its trades, and a close with nothing filled carries none); they are stored in this
    transaction, under the strategy and plan locks already held."""
    strategy_id = await lock_strategy(conn, user_ref, strategy_id)
    if not isinstance(reason, str) or reason not in CLOSE_REASONS:
        raise PlanStoreError(BAD_PLAN, f"reason must be one of {CLOSE_REASONS}, got {reason!r}")
    if isinstance(plan_number, bool) or not isinstance(plan_number, int) or not 1 <= plan_number <= INTEGER_MAX:
        raise PlanStoreError(NOT_FOUND, f"plan {plan_number!r}")
    status = (await conn.execute(_LOCK_PLAN, {"s": strategy_id, "p": plan_number})).scalar_one_or_none()
    if status is None:
        raise PlanStoreError(NOT_FOUND, f"plan {plan_number}")
    if status != "open":
        raise PlanStoreError(BAD_PLAN, f"plan {plan_number} is already closed")
    if reason == UNRESOLVED and filled is not None:
        raise PlanStoreError(BAD_PLAN, f"reason {UNRESOLVED!r} takes no filled quantities (they are unknown)")
    if reason == UNRESOLVED and not await reconciliation_store.unresolved_locked(conn, strategy_id):
        raise PlanStoreError(BAD_PLAN, f"reason {UNRESOLVED!r} needs an unresolved reconciliation mismatch of the "
                                       "strategy recorded first (it carries the block)")
    if filled is None:
        if reason not in _NO_FILLS_REASONS:
            raise PlanStoreError(BAD_PLAN, f"reason {reason!r} changes position and needs the filled quantities")
        filled = {}
    orders = _one(await _read(conn, strategy_id), plan_number).orders
    full = _checked_fills(reason, orders, filled)
    trades = _checked_trades(full, fills)
    for tag, quantity in full.items():
        await conn.execute(_SET_FILLED, {"s": strategy_id, "p": plan_number, "tag": tag, "f": quantity})
    await _store_trades(conn, trades)
    await conn.execute(_CLOSE, {"s": strategy_id, "p": plan_number, "r": reason})
    return _one(await _read(conn, strategy_id), plan_number)


__all__ = ["BAD_PLAN", "NOT_FOUND", "PLAN_OPEN", "TAG_TAKEN", "UNRESOLVED", "PlanFill", "PlanOrder", "PlanStoreError",
           "StoredPlan", "close_plan", "lock_strategy", "next_plan_number", "open_plan", "owned_strategy", "plans_for",
           "record_plan", "zerodha_symbol"]
