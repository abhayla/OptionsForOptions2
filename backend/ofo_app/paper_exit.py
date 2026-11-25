"""The paper exit door (modular doors Phase 4, PLAN-phases-3-8 5.4.2; B1): "given a strategy, exit its open legs".

Spec basis: REQ-109 AC-4 (an exit closes what is open, through the same confirm list); AC-5 / ADR-322 (3) (an exit is
judged per leg, a leg with no live price is refused); AC-7 (settle at intrinsic value); AC-8 (a stop records the tick
that crossed and fires once); ADR-117 / D-02 (buys first, by ``paper_store.place``); ADR-212 (no fill at a closing
price); ADR-002; ADR-281 (paper only: this module reaches no broker door, ``test_paper_order_door`` walks it).

Two functions, used by every server path that builds paper exit orders:

- ``live_exit_prices``: the ONE live exit read (the tracking exit route, the manual orders route and the exit-risk
  read all call it). It keeps today's read (``routes.tracking._snapshot``: one snapshot, then the planned-entry wait for
  a leg nobody holds) so no refusal changes. ``connected_rule`` is "ctx" (the orders route: a market context exists) or
  "provider" (the tracking route: the provider says connected); ``on_read_error`` is "refuse" (a failed read is "no
  price", the orders route) or "raise" (the tracking route lets it be a 500). The market half of ``may_act`` stays
  in the callers, where it always was, so no refusal changes order. Never call it under a strategy lock: it can wait.
- ``exit_strategy``: lock, load, choose, price, claim, write, in this order and for every caller:
  1. the strategy's row lock FIRST (the monitor used to claim its trigger before the lock: deadlock A3);
  2. the book under the lock -> the net per contract;
  3. ``closes="locked"``: ``open_legs_to_close(net, only)`` on the locked net (``only`` may be a function of that net);
     nothing to close -> ``Flat``. A caller passing its own ``closes`` (the tracking route's pre-read book) is used as
     given and not filtered; the store's reducing check then refuses a leg that shrank or went flat;
  4. every close needs a price in ``prices`` (a mapping read BEFORE the lock); a missing one -> ``NotYet``, nothing
     stored;
  5. ``before_write`` (the monitor's trigger claim); False -> ``Refused(already_fired)``;
  6. the orders, built in the order of the closes, then ``write(orders)``; the store puts BUY exits first.
  The door never commits: each caller keeps its own transaction.
"""
from __future__ import annotations

import datetime
import logging
from collections.abc import Awaitable, Callable, Hashable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

from ofo.tracking import paper
from ofo.tracking.closing import Close, open_legs_to_close
from ofo.tracking.orderbook import net_positions

from ofo_app import may_act, paper_store
from ofo_app import strategy_store as store
from ofo_app.errors import Failure
from ofo_app.paper_book import NewOrder, StoredOrder

log = logging.getLogger(__name__)

NOT_CONNECTED = "tracking_not_connected"
CONTRACT_NOT_LIVE = "tracking_exit_contract_not_live"
ALREADY_FIRED = "already_fired"

Refused = may_act.Refused


async def live_exit_prices(ctx: Any, feed: Any, underlying: str,  # noqa: PLR0913 - the plan's signature
                           feed_keys: Sequence[str | None], *,
                           connected_rule: Literal["ctx", "provider"],
                           on_read_error: Literal["refuse", "raise"]) -> dict[str, paper.Price] | Refused:
    """The live price answer of each feed key, or the ``Refused`` the routes always gave (``may_act.require``).
    ``feed_keys`` are read as given (a None key is a contract that is no longer live). Answer states: no market
    (``tracking_not_connected``); a contract not live (``tracking_exit_contract_not_live``, never "try again"); a failed
    read (refused or raised per ``on_read_error``); any price not live (``tracking_exit_prices_not_live``)."""
    from ofo_app.routes import tracking  # noqa: PLC0415 - the exit route's own market read, looked up at call time
    connected = ctx is not None and (connected_rule == "ctx" or ctx.provider.status().connected)
    if not connected:
        return Refused(NOT_CONNECTED, Failure.CONFLICT)
    keys = [k for k in feed_keys if k is not None]
    if len(keys) != len(feed_keys):  # never priced from another contract's quote (token reused, delisted, retired)
        return Refused(CONTRACT_NOT_LIVE, Failure.CONFLICT)
    if on_read_error == "raise":
        snapshot = await tracking.exit_snapshot(ctx, feed, underlying, keys)
        prices = {k: paper.leg_price(snapshot, k) for k in keys}
    else:
        try:
            snapshot = await tracking.exit_snapshot(ctx, feed, underlying, keys)
            prices = {k: paper.leg_price(snapshot, k) for k in keys}
        except Exception:  # any failed read is "no price": refused by name, nothing written
            log.exception("paper exit price read failed")
            return may_act.Refused(may_act.EXIT_PRICES_NOT_LIVE, Failure.CONFLICT)
    decision = may_act.prices_ok("exit", [may_act.state_of(p) for p in prices.values()])
    return decision if isinstance(decision, Refused) else prices


@dataclass(frozen=True)
class Written:
    """One order the door wrote (the key is the close's contract key)."""

    key: Hashable
    side: str
    quantity: int
    price: Decimal
    placed_at: datetime.datetime


@dataclass(frozen=True)
class Exited:
    book: tuple[StoredOrder, ...]  # the whole book after the write, as the store returned it
    written: tuple[Written, ...]  # in the order of the closes (the store may have stored them buys first)


@dataclass(frozen=True)
class NotYet:
    missing: tuple[Hashable, ...]  # the closes that had no price: nothing was stored


@dataclass(frozen=True)
class Flat:
    strategy_flat: bool  # True: no leg is open at all; False: only the named legs were flat


Outcome = Exited | Refused | NotYet | Flat
#: ``only`` as given, or a function of the locked net (the monitor fires in contract-id order)
Only = Sequence[Hashable] | Callable[[Mapping[Hashable, int]], Sequence[Hashable]] | None


def _per(value: Any, key: Hashable) -> Any:
    return value[key] if isinstance(value, Mapping) else value


async def exit_strategy(conn: Any, *, user_ref: str, strategy_id: int, kind: str,  # noqa: PLR0913
                        prices: Mapping[Hashable, Decimal], placed_at: datetime.datetime | Mapping[Hashable, Any],
                        write: Callable[[list[NewOrder]], Awaitable[Sequence[StoredOrder]]],
                        only: Only = None, closes: Literal["locked"] | Sequence[Close] = "locked",
                        reason: str | Mapping[Hashable, Any] | None = None, trigger_id: int | None = None,
                        before_write: Callable[[], Awaitable[bool]] | None = None) -> Outcome:
    """Exits the strategy's open legs; see the module docstring for the order of the steps. ``placed_at`` and
    ``reason`` are one value for every order or a mapping from the close's key."""
    await store.lock_strategy(conn, user_ref, strategy_id)  # 1: lock first, for every caller
    stored = await paper_store.load(conn, strategy_id)  # 2: the book under the lock
    net: dict[Hashable, int] = ({int(p.instrument_id): p.net_quantity
                                 for p in net_positions([o.order.as_paper() for o in stored], {}).positions
                                 if p.net_quantity} if stored else {})
    chosen = only(net) if callable(only) else only  # 3: "locked": chosen on the locked net
    todo = open_legs_to_close(net, chosen) if isinstance(closes, str) else list(closes)
    if not todo:
        return Flat(strategy_flat=not net)
    missing = tuple(c.key for c in todo if prices.get(c.key) is None)  # 4
    if missing:
        return NotYet(missing)
    if before_write is not None and not await before_write():  # 5
        return Refused(ALREADY_FIRED, None)
    orders = [NewOrder(int(c.key), c.side, c.quantity, prices[c.key], kind, _per(placed_at, c.key),
                       _per(reason, c.key), trigger_id) for c in todo]  # 6: in the order of the closes
    book = await write(orders)
    return Exited(tuple(book), tuple(Written(c.key, c.side, c.quantity, prices[c.key], _per(placed_at, c.key))
                                     for c in todo))
