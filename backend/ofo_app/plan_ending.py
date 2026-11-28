"""ADR-330 (57): the closed trade's one read-only plan line, from the stored plan and the order that closed the trade.

One reader for the builder page: the plan's rupee levels come from the plan sheet's own helpers
(``ofo.checks.rupee_figures`` / ``pnl_amount``, ``settings_in_force.sheet_stop``: a stored rupee level, else the percent
of the stop base fixed at entry), not from ``routes.adjustment_plan`` (a paper-exit module must not reach the alert
gate, REQ-170 AC-5); the ending is the LAST reducing order of the book (exit, stop or settle). Writes nothing.
"""
from __future__ import annotations

import datetime
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from ofo.adjustment import stop_lines as sl
from ofo.checks import pnl_amount as rupee
from ofo.checks import rupee_figures as figs
from ofo.errors.explanations import ExplanationText
from ofo.tracking.plan_final import NOT_SHOWN, Ending, PlanLevels, plan_final_line

from ofo_app import adjustment_check as check
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


def _guards(body: Any) -> dict:
    found = body.get("guards") if isinstance(body, dict) else None
    return found if isinstance(found, dict) else {}


def _stop_level(plan: Any, loss: Decimal | None) -> Decimal | str | None:
    """The plan's stop in rupees: the stored rupee level, else its percent-of-max-loss stop worked out from the stop
    base fixed at entry (the plan sheet's own helpers); set but not worked out -> NOT_SHOWN; none set -> None."""
    try:
        stored = rupee.level_of(_guards(plan.body).get(sl.RUPEE_LOSS_KEY)
                                if isinstance(_guards(plan.body).get(sl.RUPEE_LOSS_KEY), str) else None)
    except ValueError:
        return NOT_SHOWN
    if stored is not None:
        return figs.from_rupees(stored, loss, None).rupees or NOT_SHOWN
    percent = sif.sheet_stop(plan.body, None)
    if percent is None:
        return None
    return figs.from_percent(percent, loss, None).rupees or NOT_SHOWN


def _target_level(plan: Any) -> Decimal | str | None:
    """The plan's target in rupees: the stored rupee level; a percent target needs the entry max profit, which a
    closed book does not hold, so it is NOT_SHOWN (never a guess); no target on -> None."""
    try:
        stored = rupee.level_of(_guards(plan.body).get(sl.RUPEE_PROFIT_KEY)
                                if isinstance(_guards(plan.body).get(sl.RUPEE_PROFIT_KEY), str) else None)
    except ValueError:
        return NOT_SHOWN
    if stored is not None:
        return figs.from_rupees(stored, None, None).rupees or NOT_SHOWN
    trigger = (check.with_plan_target(plan.body).get("triggers") or {}).get("T-07")
    return NOT_SHOWN if isinstance(trigger, dict) and trigger.get("on") else None


async def plan_final_text(db: Any, user_ref: str, strategy_id: int, orders: Sequence[Any],
                          today: datetime.date | None) -> ExplanationText:
    """The line for a fully closed book (the caller decides it is closed)."""
    plan = await playbook_store.plan_for(db, user_ref, strategy_id)
    ending, at = closing_order(orders)
    if plan is None:
        return plan_final_line(None, ending, at, today)
    base = sif.stop_base_from_json(plan.stop_base)
    loss = base.max_loss if base is not None and isinstance(base.max_loss, Decimal) else None
    return plan_final_line(PlanLevels(_stop_level(plan, loss), _target_level(plan)), ending, at, today)
