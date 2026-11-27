"""ADR-330 (57): the closed trade's one read-only plan line, from the stored plan and the order that closed the trade.

One reader for the builder page: the plan's rupee levels come from the plan sheet's own figures
(``routes.adjustment_plan``: a stored rupee level, else the percent of the stop base fixed at entry), never from a
second formula; the ending is the LAST reducing order of the book (exit, stop or settle). Writes nothing.
"""
from __future__ import annotations

import datetime
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from ofo.errors.explanations import ExplanationText
from ofo.tracking.plan_final import NOT_SHOWN, Ending, PlanLevels, plan_final_line

from ofo_app import paper_store, playbook_store
from ofo_app import settings_in_force as sif

_ENDING: dict[str, Ending] = {"exit": "exit", "stop": "stop", "settle": "settle"}


def closing_order(orders: Sequence[Any]) -> tuple[Ending | None, datetime.datetime | None]:
    """The ending and time of the last order that reduced the book (kind exit, stop or settle); (None, None) when the
    book holds none (nothing recorded says how it ended, so nothing is guessed)."""
    reducing = [o.order for o in orders if o.order.kind in paper_store.REDUCING_KINDS]
    if not reducing:
        return None, None
    last = max(reducing, key=lambda o: o.placed_at)
    return _ENDING.get(last.kind), last.placed_at


def _level(rupees: Decimal | None, percent: Decimal | None) -> Decimal | str | None:
    if isinstance(rupees, Decimal):
        return rupees
    return None if percent is None else NOT_SHOWN  # set but not worked out: say so, never "none" and never a number


async def plan_final_text(db: Any, user_ref: str, strategy_id: int, orders: Sequence[Any],
                          today: datetime.date | None) -> ExplanationText:
    """The line for a fully closed book (the caller decides it is closed)."""
    from ofo_app.routes import adjustment_plan as ap  # noqa: PLC0415 - the routes import this module's neighbours

    plan = await playbook_store.plan_for(db, user_ref, strategy_id)
    ending, at = closing_order(orders)
    if plan is None:
        return plan_final_line(None, ending, at, today)
    base = sif.stop_base_from_json(plan.stop_base)
    loss = base.max_loss if base is not None and isinstance(base.max_loss, Decimal) else None
    shown = await ap.plan_figures(db, user_ref, plan, ap.Bases(None, loss, None))
    levels = PlanLevels(_level(shown.get("stop_rupees"), shown.get("stop")),
                        _level(shown.get("target_rupees"), shown.get("target")))
    return plan_final_line(levels, ending, at, today)
