"""PostgreSQL store of the paper order book (GC-TP step 1a; REQ-109 AC-4; ADR-207). Schema: migration 0028.

- place: under the strategy's row lock (one writer per strategy), inserts the orders as given, except a batch against
  an open position, which goes in buys first (D-02). Another user's strategy answers NOT_FOUND exactly like a missing
  one. An order of kind exit / settle / stop must REDUCE the open
  quantity of its contract and never exceed it (EXIT_EXCEEDS_OPEN, nothing stored); the check runs on the book as
  stored plus the earlier orders of the same call, through the one engine (ofo.tracking.orderbook). Insert-only; the
  caller commits. ADR-243: ``entry`` is a keyword every app caller passes explicitly (a repo scan in
  tests_app/test_entry_facts.py fails a call without it; tests may omit it): the strategy's entry
  facts as the caller read them (``entry_facts_of``: the spot at this fill and each side's short distance; None when
  no spot could be read, or for an exit / settle / stop, which can never be a first fill); written ONCE, only when the
  book was empty before this call, through ``entry_facts_store.record_first``; never on a later fill.
  GC-ICGUIDE g23 (audit C13): when a reducing order leaves every contract flat, the same transaction stores the
  strategy's status 'closed' (draft -> closed only; migration 0049). Every last exit (route, settlement) passes here.
- reconcile_triggers (ADR-317 (4)): inside ``place``, armed leg stops on a flat contract and every armed trigger of a
  strategy with no open leg are cancelled, whoever placed the order (route, stop fire, settlement).
- tracked_ids: which of the given strategies have at least one paper order (REQ-134 AC-4).
- load: the orders of one strategy the caller already loaded for its user, in placement order (the id).
- load_all: every order of ONE user's visible strategies with name and underlying, in ONE query whatever the count
  (finding F-3: a per-strategy loop cost 12 s). The user filter is the strategies table's owner column.
The prices come only from the server's live read or the migration; this store takes no price from a request.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ofo.adjustment.approaches import EntryFacts
from ofo.tracking.orderbook import PaperOrder, net_positions
from sqlalchemy import text

from ofo_app import entry_facts_store
from ofo_app import strategy_store as store
from ofo_app.errors import Failure
from ofo_app.paper_book import COLUMNS as _COLUMNS
from ofo_app.paper_book import NewOrder, StoredOrder, UserBook
from ofo_app.paper_book import order_from_row as _row
from ofo_app.strategy_refused import StrategyRefused

EXIT_EXCEEDS_OPEN = "exit_exceeds_open"
REDUCING_KINDS = frozenset({"exit", "settle", "stop"})

_INSERT = text(
    "INSERT INTO public.paper_orders (strategy_id, contract_id, side, quantity, price, kind, placed_at, reason, "
    "trigger_id) VALUES (:strategy_id, :contract_id, :side, :quantity, :price, :kind, :placed_at, :reason, "
    ":trigger_id)")
_CLOSE = text("UPDATE public.strategies SET status = 'closed' WHERE id = :id AND status = 'draft'")
_STATUS = text("SELECT status FROM public.strategies WHERE id = :id")
# ADR-317 (4): armed triggers of a strategy that no longer act: every one when no leg is open, else the leg stops on a
# contract with no open quantity (an index exit stays armed while any leg is open)
_STALE = ("FROM public.paper_triggers WHERE strategy_id = :sid AND fired_at IS NULL AND cancelled_at IS NULL "
          "AND (CAST(:none AS BOOLEAN) OR (kind = 'leg_stop' AND NOT contract_id = ANY(CAST(:open AS BIGINT[]))))")
_STALE_IDS = text("SELECT id " + _STALE + " ORDER BY id")
_STALE_CANCEL = text("UPDATE public.paper_triggers SET cancelled_at = clock_timestamp() WHERE id IN (SELECT id "  # noqa: S608
                     + _STALE + ") RETURNING id")
_SELECT = text(f"SELECT {_COLUMNS} FROM public.paper_orders "  # noqa: S608 constant columns
               "WHERE strategy_id = :id ORDER BY id")
_SELECT_TRACKED = text("SELECT DISTINCT strategy_id FROM public.paper_orders "
                       "WHERE strategy_id = ANY(CAST(:ids AS BIGINT[]))")
_SELECT_USER = text(
    "SELECT o.id, o.strategy_id, o.contract_id, o.side, o.quantity, o.price, o.kind, o.placed_at, o.created_at, "
    "o.reason, o.trigger_id, s.name, s.underlying, s.status, s.scenario_id FROM public.paper_orders AS o "
    "JOIN public.strategies AS s ON s.id = o.strategy_id "
    "WHERE s.user_ref = :user_ref AND s.deleted_at IS NULL ORDER BY o.strategy_id, o.id")



_SETTLED_SQL = ("SELECT o.id, o.strategy_id, o.contract_id, o.side, o.quantity, o.price, o.kind, o.placed_at, "
                "o.created_at, o.reason, o.trigger_id, s.name FROM public.paper_orders AS o "
                "JOIN public.strategies AS s ON s.id = o.strategy_id "
                "WHERE s.user_ref = :user_ref AND s.deleted_at IS NULL AND o.kind = 'settle' AND {scope} "
                "ORDER BY o.placed_at DESC, o.strategy_id, o.id LIMIT :limit")


async def settlements(conn: Any, user_ref: str, limit: int = 200) -> list[tuple[str | None, StoredOrder]]:
    """D-71: the user's expiry-settlement orders, newest first, each with its strategy's saved name (scope: this
    process's live or scenario strategies only, like every other alert reader)."""
    from ofo_app.scenario_mode import scope_clause  # noqa: PLC0415 - the one isolation helper
    clause, params = scope_clause("s")
    rows = (await conn.execute(text(_SETTLED_SQL.format(scope=clause)),
                               {"user_ref": user_ref, "limit": limit, **params})).all()
    return [(r.name, _row(r)) for r in rows]


def _check_reducing(book: list[PaperOrder], order: PaperOrder) -> None:
    net = 0
    if book:
        found = [p for p in net_positions(book, {}).positions if p.instrument_id == order.instrument_id]
        net = found[0].net_quantity if found else 0
    reduces = (net > 0 and order.side == "SELL") or (net < 0 and order.side == "BUY")
    # GC-TPD R-22: an open / add against the held side would reduce or flip it: refused the same way as a bad exit
    refused = (not reduces or order.quantity > abs(net)) if order.kind in REDUCING_KINDS else reduces
    if refused:
        raise store.StrategyStoreError(EXIT_EXCEEDS_OPEN, f"contract {order.instrument_id}: a {order.kind} of "
                                                          f"{order.side} {order.quantity} against an open {net}")


def buys_first(orders: Sequence[NewOrder]) -> list[NewOrder]:
    """D-02 (REQ-159 AC-6, REQ-058 Q238): BUY exits, BUY adds, SELL exits, SELL adds, stable inside each group. Every
    BUY precedes every SELL, so a short is never naked between two fills; an exit stays before an add of its side so
    the reducing check sees the book it reduces. ``place`` applies it only to a batch against an open position (an entry
    on an empty book has nothing to protect and keeps the trader's leg order).

    Plainly: a paper ENTRY is recorded as sent, in the trader's leg order, so it may show a sale before its hedge. Only
    a batch against an open position (an adjustment, an exit, a stop-out) is reordered, buys first."""
    return sorted(orders, key=lambda o: (o.side != "BUY", o.kind not in REDUCING_KINDS))  # sorted is stable


async def reconcile_triggers(conn: Any, strategy_id: int, book: Sequence[PaperOrder], *,
                             dry_run: bool = False) -> list[int]:
    """ADR-317 (4): cancels the strategy's armed triggers that cannot act on ``book`` (the whole order list, as it will
    be stored): all of them when no leg is open, else the leg stops on a flat contract. Returns the ids; ``dry_run``
    only names them. The one place every paper order passes (``place``) calls it; the caller commits."""
    open_ids = [int(p.instrument_id) for p in net_positions(list(book), {}).positions if p.net_quantity]
    params = {"sid": strategy_id, "none": not open_ids, "open": open_ids}
    return [int(r.id) for r in (await conn.execute(_STALE_IDS if dry_run else _STALE_CANCEL, params)).all()]


async def place(conn: Any, user_ref: str, strategy_id: int, orders: Sequence[NewOrder], *,
                entry: EntryFacts | None = None) -> tuple[StoredOrder, ...]:
    """Stores ``orders`` as given on an empty book, buys first otherwise (D-02; module docstring) and returns the
    whole book as stored; at the strategy's FIRST fill (the book empty before this call) also its entry facts
    ``entry`` when known (ADR-243), same transaction."""
    if not orders:
        raise ValueError("place needs at least one order")
    paper = [o.as_paper() for o in orders]  # refuses a bad side, kind, quantity or price before any write
    async with conn.begin_nested():
        await store.lock_strategy(conn, user_ref, strategy_id)  # NOT_FOUND for a missing or another user's strategy
        if any(o.kind not in REDUCING_KINDS for o in paper) and (
                await conn.execute(_STATUS, {"id": strategy_id})).scalar_one() == "closed":
            raise StrategyRefused("paper_strategy_closed", Failure.CONFLICT)  # a closed strategy never reopens
        book = [o.order.as_paper() for o in await load(conn, strategy_id)]
        first_fill = not book
        if not first_fill:  # D-02: against an open position no short is ever without its protection between two fills
            orders = buys_first(orders)
            paper = [o.as_paper() for o in orders]
        for new in paper:
            _check_reducing(book, new)
            book.append(new)
        for o in orders:
            await conn.execute(_INSERT, {"strategy_id": strategy_id, "contract_id": o.contract_id, "side": o.side,
                                         "quantity": o.quantity, "price": o.price, "kind": o.kind,
                                         "placed_at": o.placed_at, "reason": o.reason, "trigger_id": o.trigger_id})
        if any(o.kind in REDUCING_KINDS for o in paper) and not any(
                p.net_quantity for p in net_positions(book, {}).positions):
            await conn.execute(_CLOSE, {"id": strategy_id})  # GC-ICGUIDE g23: last open leg went
        await reconcile_triggers(conn, strategy_id, book)  # ADR-317 (4): every leg change passes here
        if first_fill and entry is not None:  # written once; a later fill never reaches here (ADR-243)
            await entry_facts_store.record_first(conn, strategy_id, entry)
    return await load(conn, strategy_id)


async def tracked_ids(conn: Any, strategy_ids: Sequence[int]) -> set[int]:
    """REQ-134 AC-4: which of the given strategies (already filtered to the signed-in user's own) have a paper order.
    A read failure raises: the caller decides what 'unknown' shows."""
    if not strategy_ids:
        return set()
    return {int(r.strategy_id) for r in await conn.execute(_SELECT_TRACKED, {"ids": list(strategy_ids)})}


async def load(conn: Any, strategy_id: int) -> tuple[StoredOrder, ...]:
    return tuple(_row(r) for r in (await conn.execute(_SELECT, {"id": strategy_id})).all())


async def load_all(conn: Any, user_ref: str) -> list[UserBook]:
    """Every paper book of ``user_ref``'s visible strategies, oldest strategy first, in one query. A read failure
    raises: the caller refuses the whole list, never a partial one."""
    heads: dict[int, tuple[str | None, str, str, str | None]] = {}
    orders: dict[int, list[StoredOrder]] = {}
    for r in (await conn.execute(_SELECT_USER, {"user_ref": user_ref})).all():
        sid = int(r.strategy_id)
        heads.setdefault(sid, (r.name, r.underlying, r.status, getattr(r, "scenario_id", None)))
        orders.setdefault(sid, []).append(_row(r))
    return [UserBook(sid, name, underlying, tuple(orders[sid]), status, scenario_id)
            for sid, (name, underlying, status, scenario_id) in heads.items()]
