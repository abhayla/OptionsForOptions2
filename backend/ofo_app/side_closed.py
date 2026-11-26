"""The side_closed alert of an iron condor that lost one side (ADR-330 (2), P7).

Spec basis: ADR-330 (2) (b): "When a side closes, the user is told so and asked whether he wants to add new positions on
the closed side ... If no, he is told that the strategy will then change from its entry shape to the shape that remains
(iron condor to bull put spread when the call side closed; bear call spread when the put side closed) and asked to
confirm. If he confirms, the strategy is shown as the new shape from then on ... Until he answers, the trade keeps its
entry shape name with the notice showing ... nothing is added without the user."

The alert is raised through ``actionable_alerts.raise_actionable`` (kind ``side_closed``), never by its own code, once
per (strategy, closed side): an open row or the user's answer stops a second one (a system-closed row does not). It is
not closed by a position change (P1). Storing the confirmed shape needs no column: the answered row IS the record (answer
``confirm_new_shape``), read back by ``confirmed_shape``. ``add_legs`` stores the answer only and places no order.
Answer states of ``confirmed_shape``: stated (a confirmed row) -> the label; absent / not answered / answered
``add_legs`` -> None (the trade keeps its entry shape name); a closed side with no known remaining shape -> never
raised.
"""
from __future__ import annotations

from datetime import datetime
from functools import cache
from typing import Any, Final

from ofo import alerts as kinds
from ofo.adjustment import side_scope
from ofo.strategy.loader import load_templates

RULE_PREFIX: Final = "side.closed."
_REMAINING: Final = side_scope.REMAINING_SHAPE
_CONDOR_LEGS: Final = 4


def rule_id(side: str) -> str:
    return RULE_PREFIX + side


@cache
def _names() -> dict[str, str]:
    return {t.id: t.name for t in load_templates()}


def _is_condor(legs: Any) -> bool:
    """Entered as a short iron condor: per side one SELL and one BUY, the wings outside the shorts (put BUY < put SELL <
    call SELL < call BUY). A reverse (long) condor or an iron butterfly is not named by ADR-330 (2): no alert."""
    legs = tuple(legs or ())
    if len(legs) != _CONDOR_LEGS:
        return False
    by = {(x.type, x.side): x.strike for x in legs}
    if set(by) != {(t, s) for t in ("CE", "PE") for s in ("BUY", "SELL")}:
        return False
    return by["PE", "BUY"] < by["PE", "SELL"] < by["CE", "SELL"] < by["CE", "BUY"]


def remaining_label(entry_legs: Any, closed: frozenset[str]) -> str | None:
    """The shape name that remains ("Bull Put Spread" / "Bear Call Spread"); None when it cannot be said (not an
    iron condor at entry, or not exactly one side closed): then no alert is raised."""
    if len(closed) != 1 or not _is_condor(entry_legs):
        return None
    return _names().get(_REMAINING[next(iter(closed))])


async def raise_if_closed(conn: Any, user_ref: str, strategy_id: int, tracked: Any, *,  # noqa: PLR0913
                          at: datetime, source: str | None = None) -> int | None:
    """Raise the one side_closed alert when a side of the entry condor is closed now. Returns the alert id, or None
    (nothing closed, unreadable, unknown shape, or already raised once for this side)."""
    from ofo_app import actionable_alerts as aa  # noqa: PLC0415

    entry = getattr(tracked, "entry_position", None)
    now = getattr(tracked, "position", None)
    if entry is None or now is None:
        return None
    closed = side_scope.closed_sides(entry.legs, now.legs)
    label = remaining_label(entry.legs, closed)
    if label is None:
        return None
    rule = rule_id(next(iter(closed)))
    rows = [*await aa.unanswered(conn, user_ref), *await aa.history(conn, user_ref)]
    # only an open row or the user's own answer stops a new raise; a row the system closed (plan removed, not monitored)
    # does not: the side is still closed and the user was never asked
    if any(r.strategy_id == strategy_id and r.rule_id == rule and r.answer != kinds.CLOSED_BY_SYSTEM for r in rows):
        return None
    alert = await aa.raise_actionable(conn, user_ref, strategy_id, rule, kinds.SIDE_CLOSED, at=at, value=None,
                                      threshold=None, source=source, label=label)
    return alert.id


async def confirmed_shape(conn: Any, user_ref: str, strategy_id: int) -> str | None:
    """The shape name the user confirmed for this strategy, else None (the entry shape name stands)."""
    from ofo_app import actionable_alerts as aa  # noqa: PLC0415

    for row in await aa.history(conn, user_ref):  # newest first
        if (row.strategy_id == strategy_id and row.kind == kinds.SIDE_CLOSED
                and row.answer == kinds.CONFIRM_NEW_SHAPE and row.rule_id.startswith(RULE_PREFIX)):
            return _names().get(_REMAINING[row.rule_id.removeprefix(RULE_PREFIX)])
    return None
