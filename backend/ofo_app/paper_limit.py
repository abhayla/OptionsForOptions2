"""GC-ICGUIDE g10 (audit C9; ADR-255; REQ-109 AC-1): the plan's most adjustments, checked when paper orders are SAVED.

The one save path is ``routes.paper.place_paper_orders``. The offered approaches were already filtered by the limit
(``ofo.adjustment.offered``); this refuses a batch a user builds by hand beyond it. Counting is the history page's
(``adjustment_readers.history_count``: every batch after the entry is one adjustment, a partial exit included, the
entry batch never). A batch that closes the whole strategy is always allowed.

Answer states of the plan read: its own plan -> its ``guards.max_adjustments``; no plan -> the active playbook of the
position's type (the plan sheet's pre-fill); a readable plan or playbook that sets no maximum -> no limit; no plan and
no type, a read error, or a maximum that is not a whole number >= 0 -> refused by name
(``paper_adjustment_limit_unread``), never allowed.
"""
from __future__ import annotations

import logging
from collections.abc import Sequence
from types import SimpleNamespace
from typing import Any

from ofo.engine.legs import Instrument
from ofo.errors import render
from ofo.tracking.orderbook import net_positions

from ofo_app import playbook_store, tracked_contracts
from ofo_app.strategy_refused import StrategyRefused

log = logging.getLogger(__name__)
_OPTION_TYPES = (Instrument.CE.value, Instrument.PE.value)


async def _plan_body(db: Any, user_ref: str, strategy_id: int, reader: Any,  # noqa: PLR0913
                     rates: Any, listed: Any) -> Any:
    from ofo_app import adjustment_check as check  # noqa: PLC0415 - it imports the route layer
    plan = await playbook_store.plan_for(db, user_ref, strategy_id)
    if plan is not None:
        return plan.body
    tracked = await reader(strategy_id, rates)  # raises when the open legs cannot be read: refused by name
    stype = check.strategy_type(tracked.position, None, listed)
    return (await check.resolve(db, user_ref, strategy_id, stype)).body


def _unread() -> StrategyRefused:
    return StrategyRefused("paper_adjustment_limit_unread")


async def check_adjustment_limit(db: Any, user_ref: str, strategy_id: int,  # noqa: PLR0913
                                 existing: Sequence[Any], new: Sequence[Any], reader: Any, rates: Any,
                                 listed: Any) -> None:
    """Raises ``StrategyRefused`` when ``new`` (the batch just stored, ``.order`` rows' orders) would be adjustment
    number > the plan's maximum over the ``existing`` stored rows. No stored order before (the entry) or a batch that
    adds no adjustment -> returns without reading the plan."""
    from ofo_app.adjustment_readers import history_count  # noqa: PLC0415 - it imports the route layer
    if not existing:
        return
    found = {c.contract_id: c for c in await tracked_contracts.resolve(
        db, sorted({o.order.contract_id for o in existing} | {o.contract_id for o in new}))}

    def is_option(cid: int) -> bool:
        stored = found[cid].stored
        return stored is not None and stored.listed.contract.instrument_type in _OPTION_TYPES
    after_orders = [*existing, *(SimpleNamespace(order=o) for o in new)]
    before, after = history_count(existing, is_option), history_count(after_orders, is_option)
    if after is None:
        raise _unread()
    if before is not None and after <= before:
        return
    if all(p.net_quantity == 0 for p in net_positions([o.order.as_paper() for o in after_orders], {}).positions):
        return  # a full exit of the whole strategy is always allowed
    try:
        body = await _plan_body(db, user_ref, strategy_id, reader, rates, listed)
        guards = None if body is None else body.get("guards", {})
    except Exception as exc:  # noqa: BLE001 - any failure of the read is "unreadable", never a silent allow
        log.warning("paper adjustment limit: strategy %s plan unreadable (%s)", strategy_id, type(exc).__name__)
        raise _unread() from None
    limit = _limit_of(guards)
    if limit is not None and after > limit:
        raise StrategyRefused("paper_adjustment_limit",
                              message=render("paper_adjustment_limit", limit=limit, number=after))


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
