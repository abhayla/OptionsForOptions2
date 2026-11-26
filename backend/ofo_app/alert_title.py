"""ADR-330 (19)(b): the ONE function that words the strategy part of every alert title.

Spec basis (quoted): "Alert titles and lists carry the trade's number and expiry beside the name, as in 'Short Iron
Condor (#172, 1 Dec)'." Same rule as the frontend ``strategyListLabel`` (frontend/src/lib/saveDraft.js): exactly ONE
distinct expiry prints it ('(#172, 1 Dec)'); several or none print only the number ('(#172)'); a strategy with no name
shows 'Strategy <id>' (the number is already in it).

Which expiries: the contracts the strategy's paper book holds open now; a book with nothing open (a stop just fired,
the trade settled) reads the contracts it last held, so a closed trade's History keeps the title it had when it fired.
A contract the store cannot resolve counts as no expiry (fail closed: only the number). The year is not printed (the
spec's text is 'd Mon'). Text only; no date arithmetic.
"""
from __future__ import annotations

import datetime
from collections.abc import Iterable, Sequence
from typing import Any

from ofo.errors.explanations import ExplanationText, render_explanation
from ofo.strategy import stored_form as sf
from ofo.tracking.orderbook import net_positions

from ofo_app import paper_store, tracked_contracts

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def strategy_label(name: str | None, strategy_id: int, expiries: Iterable[datetime.date | None]) -> ExplanationText:
    """The label: name, number and (one distinct expiry only) the expiry; ``expiries`` may repeat, None = unreadable."""
    if not name:
        return render_explanation("alert_title_unnamed", id=strategy_id)
    shown = sf.shown_name(name)
    seen = list(expiries)
    days = {e for e in seen if isinstance(e, datetime.date)}
    if len(days) != 1 or any(e is None for e in seen):
        return render_explanation("alert_title_label_no_expiry", name=shown, id=strategy_id)
    day = next(iter(days))
    return render_explanation("alert_title_label", name=shown, id=strategy_id, day=day.day,
                              month=_MONTHS[day.month - 1])


async def strategy_expiries(conn: Any, strategy_id: int) -> list[datetime.date | None]:
    """The expiry of each contract the strategy's book holds open (else of each it ever booked); None = unresolved."""
    booked = await paper_store.load(conn, strategy_id)
    if not booked:
        return []
    held = {int(p.instrument_id) for p in net_positions([o.order.as_paper() for o in booked], {}).positions
            if p.net_quantity}
    ids = sorted(held or {o.order.contract_id for o in booked})
    found = await tracked_contracts.resolve(conn, ids)
    return [None if c.stored is None else c.stored.listed.contract.expiry for c in found]


async def labels(conn: Any, rows: Sequence[tuple[int, str | None]]) -> dict[int, ExplanationText]:
    """strategy id -> label, for (id, stored name) pairs; one read per distinct strategy."""
    return {sid: strategy_label(name, sid, await strategy_expiries(conn, sid)) for sid, name in dict(rows).items()}
