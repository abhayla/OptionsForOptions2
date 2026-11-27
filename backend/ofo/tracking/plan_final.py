"""ADR-330 (57): the one read-only line a fully closed or settled trade shows on the builder page: what the plan was
and how the trade ended ("Plan: stop Rs 300, target Rs 800. Closed by your exit at 11:23.").

Built here, in words from the catalogue, from figures the caller took from the stored plan (the rupee levels) and
from the order that closed the trade; the page prints it as sent. Nothing is computed from a live price, and a level
that cannot be worked out prints no number. The endings are the three orders the book records (``exit``, ``stop``,
``settle``): the plan's own stop, target and time exit raise alerts only (ADR-003), so a close that followed one is
recorded as the user's exit, never as a plan close.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from ofo.errors.explanations import ExplanationText, render_explanation
from ofo.timeutil import IST

__all__ = ["NOT_SHOWN", "Ending", "PlanLevels", "plan_final_line"]

Ending = Literal["exit", "stop", "settle"]
#: a level the plan holds but that cannot be worked out in rupees (distinct from None = the plan sets none)
NOT_SHOWN = "not_shown"
_HOW = {"exit": "plan_final_how_exit", "stop": "plan_final_how_stop", "settle": "plan_final_how_settle"}


@dataclass(frozen=True)
class PlanLevels:
    """The plan's whole-trade levels in rupees: a Decimal, None (the plan sets none) or ``NOT_SHOWN``."""
    stop_rupees: Decimal | str | None
    target_rupees: Decimal | str | None


def _level(kind: str, value: Decimal | str | None) -> ExplanationText:
    if value is None:
        return render_explanation(f"plan_final_{kind}_none")
    if value == NOT_SHOWN:
        return render_explanation(f"plan_final_{kind}_unknown")
    if not isinstance(value, Decimal):
        raise ValueError(f"a plan level is a Decimal, None or NOT_SHOWN, got {value!r}")
    return render_explanation(f"plan_final_{kind}", amount=value)


def plan_final_line(plan: PlanLevels | None, ending: Ending | None, closed_at: datetime.datetime | None,
                    today: datetime.date | None) -> ExplanationText:
    """``plan`` None = the trade had no plan; ``ending`` None = no closing order is recorded; ``closed_at`` (timezone
    aware) is that order's time, and ``today`` the India date it is judged against (an earlier day is named)."""
    if ending is not None and ending not in _HOW:
        raise ValueError(f"an ending is exit, stop or settle, got {ending!r}")
    if closed_at is not None and closed_at.tzinfo is None:
        raise ValueError("the closing time carries its zone")
    first = (render_explanation("plan_final_no_plan") if plan is None else render_explanation(
        "plan_final_levels", stop=_level("stop", plan.stop_rupees), target=_level("target", plan.target_rupees)))
    if ending is None:
        second = render_explanation("plan_final_end_unknown")
    else:
        how = render_explanation(_HOW[ending])
        if closed_at is None:
            second = render_explanation("plan_final_end_no_time", how=how)
        else:
            at = closed_at.astimezone(IST)
            if today is not None and at.date() != today:
                second = render_explanation("plan_final_end_on", how=how, day=at.date(), time=at.time().replace(
                    second=0, microsecond=0, tzinfo=None))
            else:
                second = render_explanation("plan_final_end_at", how=how, time=at.time().replace(
                    second=0, microsecond=0, tzinfo=None))
    return render_explanation("plan_final_line", plan=first, end=second)
