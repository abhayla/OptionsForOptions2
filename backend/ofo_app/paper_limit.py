"""GC-ICGUIDE g10 (audit C9; ADR-255; REQ-109 AC-1): the plan's most adjustments, checked when paper orders are SAVED.

Both user save paths (``routes.paper.place_paper_orders`` and ``routes.tracking.exit_tracking``) call
``place_checked``, which refuses every fill outside market hours (ADR-212), stores through ``paper_store.place`` and
then checks the order size (``check_order_size``) and the adjustment limit, so neither path can skip a check.
 The offered approaches were already filtered by the limit
(``ofo.adjustment.offered``); this refuses a batch a user builds by hand beyond it. Counting is the history page's
(``adjustment_readers.history_count``: every batch after the entry is one adjustment, a partial exit included, the
entry batch never). A batch that closes the whole strategy is always allowed, before any history or plan is read;
over the maximum a batch made only of reducing orders (ADR-318 (5)) is allowed too, and still counts.

Answer states of the plan read: its own plan -> its ``guards.max_adjustments``; no plan -> the active playbook of the
position's type (the plan sheet's pre-fill); a readable plan or playbook that sets no maximum, or no plan and no
playbook for the shape (nothing sets a maximum) -> no limit; a read error or a maximum that is not a whole number
>= 0 -> refused by name (``paper_adjustment_limit_unread``), never allowed.
"""
from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from ofo.engine.legs import Instrument
from ofo.errors import render
from ofo.tracking.orderbook import net_positions

from ofo_app import paper_store, playbook_store, tracked_contracts
from ofo_app.errors import Failure
from ofo_app.order_lots import LegLots, check_lots
from ofo_app.strategy_refused import StrategyRefused

log = logging.getLogger(__name__)
_OPTION_TYPES = (Instrument.CE.value, Instrument.PE.value)


async def _plan_body(db: Any, user_ref: str, strategy_id: int) -> Any:
    """ADR-330 (11), Q7: only the strategy's own plan sets a maximum; no plan -> None -> no limit applies."""
    plan = await playbook_store.plan_for(db, user_ref, strategy_id)
    return None if plan is None else plan.body


async def _read_before(reader: Any, strategy_id: int, rates: Any) -> Any:
    """The position as it stands BEFORE this request's orders are stored, as a reader the check calls later. The
    request's session sees its own inserts (#682), so a read after them would type the position after the batch and
    pick another playbook's limit. A failed read is kept and raised when the check asks, so it still refuses by name."""
    failure: Exception | None = None
    tracked = None
    try:
        tracked = await reader(strategy_id, rates)
    except Exception as exc:  # noqa: BLE001 - raised again where the check reads it
        failure = exc

    async def read(_strategy_id: int, _rates: Any) -> Any:
        if failure is not None:
            raise failure
        return tracked
    return read


def _unread() -> StrategyRefused:
    return StrategyRefused("paper_adjustment_limit_unread")


async def check_adjustment_limit(db: Any, user_ref: str, strategy_id: int,  # noqa: PLR0913
                                 existing: Sequence[Any], new: Sequence[Any], reader: Any, rates: Any,
                                 listed: Any) -> None:
    """Raises ``StrategyRefused`` when ``new`` (the batch just stored, ``.order`` rows' orders) would be adjustment
    number > the plan's maximum and opens or adds to a leg (ADR-318 (5): a batch of reducing orders passes), over the
    ``existing`` stored rows. No stored order before (the entry) or a batch that adds no adjustment -> returns without
    reading the plan."""
    from ofo_app.adjustment_readers import history_count  # noqa: PLC0415 - it imports the route layer
    if not existing:
        return
    after_orders = [*existing, *(SimpleNamespace(order=o) for o in new)]
    if all(p.net_quantity == 0 for p in net_positions([o.order.as_paper() for o in after_orders], {}).positions):
        return  # a full exit of the whole strategy is always allowed, even when the history cannot be read
    found = {c.contract_id: c for c in await tracked_contracts.resolve(
        db, sorted({o.order.contract_id for o in existing} | {o.contract_id for o in new}))}

    def is_option(cid: int) -> bool:
        stored = found[cid].stored
        return stored is not None and stored.listed.contract.instrument_type in _OPTION_TYPES
    before, after = history_count(existing, is_option), history_count(after_orders, is_option)
    if after is None:
        raise _unread()
    if before is not None and after <= before:
        return
    try:
        body = await _plan_body(db, user_ref, strategy_id)
        guards = {} if body is None else body.get("guards", {})  # no plan: nothing sets a maximum (ADR-330 (11))
    except Exception as exc:  # noqa: BLE001 - any failure of the read is "unreadable", never a silent allow
        log.warning("paper adjustment limit: strategy %s plan unreadable (%s)", strategy_id, type(exc).__name__)
        raise _unread() from None
    limit = _limit_of(guards)
    if limit is not None and after > limit and not all(o.kind in paper_store.REDUCING_KINDS for o in new):
        # ADR-318 (5): at the maximum a basket of reducing orders is accepted (paper_store.place already refused any
        # that exceeds the open quantity); one that opens or adds to a leg is refused with the approaches list's reason
        raise StrategyRefused("paper_adjustment_limit", message=render("paper_adjustment_limit", limit=limit))


def _limit_of(guards: Any) -> int | None:
    """The plan's most adjustments; None = the plan sets none; anything unreadable raises the named refusal."""
    if not isinstance(guards, dict):
        raise _unread()
    limit = guards.get("max_adjustments")
    if limit is None:
        return None
    if type(limit) is not int or limit < 0:
        raise _unread()
    return limit


def _signed(order: Any) -> int:
    return order.quantity if order.side == "BUY" else -order.quantity


async def check_order_size(db: Any, existing: Sequence[Any], new: Sequence[Any],
                           settings: Mapping[str, Decimal]) -> None:
    """ADR-330 (50), (51), (52), ADR-081, ADR-092 (Lane K): the size check every paper order passes, at the one door
    (``place_checked``); ``existing`` are the stored rows before this batch (``.order`` rows), ``new`` the batch's
    ``NewOrder`` rows. PAPER AND REAL ARE THE SAME (ADR-330 (58)): a real-order path calls this same function.
    Per order, every kind (an exit too, (51)): units must be below the contract's stored exchange freeze limit; an
    exit over it says how many lots one exit may carry. No stored limit -> no freeze refusal (ADR-081, coordinator
    ruling 27 Nov; the lots limit below still applies). A limit below one lot ->
    ``paper_leg_limit_below_one_lot``. Per leg: the lots the leg will hold after EACH order of the batch (held +
    added, signed net of its contract, in stored order) may
    not exceed ``limits.max_lots`` (default 100, (52)); an order that does not grow the leg's net (a cut back of a
    leg already over a lowered limit) passes. An unreadable setting or store raises: nothing placed."""
    from ofo.settings import calc  # noqa: PLC0415
    from ofo.strategy.definition import display_contract  # noqa: PLC0415

    from ofo_app import freeze_read  # noqa: PLC0415 - read side only; no order module in its closure
    from ofo_app.routes.paper import identity_of  # noqa: PLC0415 - it imports the route layer
    if not new:
        return
    found = {c.contract_id: c for c in await tracked_contracts.resolve(db, sorted({o.contract_id for o in new}))}

    def name_of(contract_id: int) -> str:
        return display_contract(identity_of(found[contract_id]))
    _check_freeze(await freeze_read.limits_in_force(db), found, new, name_of)
    _check_leg_totals(calc.max_lots(settings), found, existing, new, name_of)


def _check_freeze(stored: Any, found: Mapping[int, Any], new: Sequence[Any], name_of: Any) -> None:
    """Per order, every kind: the freeze quantity (see ``check_order_size``)."""
    from ofo.instruments.freeze_limits import StoredFreeze, largest_allowed_units  # noqa: PLC0415
    from ofo.instruments.models import InstrumentId  # noqa: PLC0415
    for o in new:
        c = found[o.contract_id].stored.listed.contract  # a contract with no stored row was refused before the door
        limit = stored.get(InstrumentId(c.exchange_segment, c.exchange_token))
        if limit is None:
            continue  # ADR-081: no stored freeze quantity (SENSEX has no BSE_FO source) is not a freeze refusal
        freeze = StoredFreeze(limit.freeze_limit, c.lot_size, limit.file_date)
        if o.quantity < freeze.limit:
            continue
        top_lots = largest_allowed_units(freeze) // freeze.lot
        if top_lots < 1:  # the limit is below one lot: no whole-lot order is allowed
            raise StrategyRefused("paper_leg_limit_below_one_lot", message=render(
                "paper_leg_limit_below_one_lot", contract=name_of(o.contract_id), limit=freeze.limit, lot=freeze.lot))
        code = "paper_exit_over_order_limit" if o.kind in paper_store.REDUCING_KINDS else "paper_leg_over_order_limit"
        raise StrategyRefused(code, message=render(
            code, contract=name_of(o.contract_id), lots=-(-o.quantity // freeze.lot), max_lots=top_lots))


def _check_leg_totals(top: int, found: Mapping[int, Any], existing: Sequence[Any], new: Sequence[Any],
                      name_of: Any) -> None:
    """Per leg: the total it holds after EACH order, in stored order (ADR-330 (50)); both doors"""
    check_lots(top, [
        LegLots(name_of(cid), leg.stored.listed.contract.lot_size,
                sum(_signed(r.order) for r in existing if r.order.contract_id == cid),
                [_signed(o) for o in new if o.contract_id == cid])
        for cid, leg in found.items()])


#: the kinds only the server writes (the monitor's stop-out, the expiry settlement): never refused here, they never come
#: from a user door (the store's own guard lets ``settle`` through for a held position, ADR-292)
SERVER_KINDS = frozenset({"stop", "settle"})


async def refuse_real_position(db: Any, strategy_id: int, orders: Sequence[Any]) -> None:
    """I-158 + FD5 N1 (ADR-330 (64), (58)): a USER order of any kind (open, add, exit) on a real or unknown position is
    refused by name before anything is stored: a real position takes no paper order, and an order must never turn its
    kind from real to paper. Server-written kinds (stop, settle) come from the monitor and settlement, never through
    here and never refused. A kind read that fails raises (never read as paper)."""
    if all(o.kind in SERVER_KINDS for o in orders):
        return
    from ofo_app import position_kind, strategy_store  # noqa: PLC0415
    if await strategy_store.paper_order_refused(db, strategy_id, [o.kind for o in orders]):
        raise StrategyRefused(position_kind.refusal_code(o.kind for o in orders), Failure.CONFLICT)


refuse_real_exit = refuse_real_position  # the I-158 name (tracking exit, tests)


async def place_checked(db: Any, user_ref: str, strategy_id: int, orders: Sequence[Any], *,  # noqa: PLR0913
                        entry: Any, ctx: Any, at: Any, reader: Any, rates: Any,
                        settings: Mapping[str, Decimal], swept: list[int] | None = None) -> tuple[Any, ...]:
    """The ONE write both user save paths use (ADR-212, ADR-255): every fill outside market hours at ``at`` is refused
    (``gate_market_closed``; no market context fails closed by the calendar), then ``paper_store.place``, then the
    adjustment limit on the stored book. The caller commits, or rolls back on any raise. Returns the whole book."""
    from ofo_app import adjustment_check as check  # noqa: PLC0415 - it imports the route layer
    from ofo_app import may_act  # noqa: PLC0415 - it imports the route layer
    may_act.refuse_unless_allowed(ctx, "place", at)  # ADR-212
    await refuse_real_position(db, strategy_id, orders)
    reader = await _read_before(reader, strategy_id, rates)
    book = await paper_store.place(db, user_ref, strategy_id, orders, entry=entry, swept=swept)
    # ADR-330 (50)-(52): the size of every order and the total of every leg, on the stored book
    await check_order_size(db, book[:-len(orders)], [o.order for o in book[-len(orders):]], settings)
    await check_adjustment_limit(db, user_ref, strategy_id, book[:-len(orders)], [o.order for o in book[-len(orders):]],
                                 reader, rates, check.listed_of(ctx))
    return book


async def record_checked(db: Any, user_ref: str, strategy_id: int, orders: Sequence[Any], *,  # noqa: PLR0913
                         ctx: Any, at: Any, settings: Mapping[str, Decimal], request_key: str | None = None,
                         reason: str | None = None) -> tuple[Any, ...]:
    """Lane R1 (ADR-330 (73), ADR-281): the ONE write for a user's open / add / exit of a REAL position. It runs the
    checks a paper order runs (every fill outside market hours refused, ADR-212 / (60); the size of every order and leg
    total, ADR-330 (50)-(52), over an empty book: the broker's quantity is not in this app) and then stores one record
    per action in ``real_action_records``. It never reaches ``paper_store`` and never a broker: the position, its
    quantity and its P&L stay the broker's figure. A kind that is not real, or cannot be read, is refused (fail closed).
    The caller commits, or rolls back on any raise. Returns the records of this request."""
    from ofo_app import may_act, position_kind, real_action_store, strategy_store  # noqa: PLC0415 - route layer
    may_act.refuse_unless_allowed(ctx, "place", at)  # ADR-212 / (60): the same rule, before anything is stored
    if not position_kind.takes_records((await strategy_store.kinds_of(db, [strategy_id])).get(strategy_id)):
        raise StrategyRefused("user_input_request_not_available", Failure.UPSTREAM_BUSY)
    if any(o.kind not in real_action_store.USER_ACTIONS for o in orders):
        raise StrategyRefused("user_input_request_not_available", Failure.CONFLICT)
    await check_order_size(db, [], orders, settings)
    stored = []
    for action in dict.fromkeys(o.kind for o in orders):  # one record per action, in the order the basket named them
        legs = [real_action_store.Leg(o.contract_id, o.side, o.quantity, o.price) for o in orders if o.kind == action]
        await real_action_store.record(db, user_ref=user_ref, strategy_id=strategy_id, action=action, legs=legs,
                                       stored_at=at, reason=reason, request_key=request_key)
        stored.append(action)
    return tuple(await real_action_store.load(db, strategy_id))
