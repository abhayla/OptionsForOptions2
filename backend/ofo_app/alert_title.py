"""ADR-330 (19)(b): the ONE function that words the strategy part of every alert title and alert list row.

Spec basis (quoted): "Alert titles and lists carry the trade's number and expiry beside the name, as in 'Short Iron
Condor (#172, 1 Dec)'." The expiry is the NEAREST among the strategy's open legs (Lane P's rule,
``adjustment_readers.nearest_expiry``, paper or real book); no open leg, or a book that cannot be read, prints only the
number ('(#172)'); a strategy with no name shows 'Strategy <id>'. The year is not printed. Text only.
"""
from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from ofo.errors.explanations import ExplanationText, render_explanation
from ofo.strategy import stored_form as sf

log = logging.getLogger(__name__)
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


async def labels(conn: Any, rows: Sequence[tuple[int, str | None]]) -> dict[int, ExplanationText]:
    """strategy id -> "<name> (#<id>, <nearest open-leg expiry as D Mon>)" for (id, stored name) pairs, one read per
    distinct strategy: the ONE label of every alert list and title (Active, History, the paper alert records).
    Lane J merge 26 Nov: Lane P's second push built the same label in routes/alerts.py; the two are one here, with
    Lane P's rule (the NEAREST expiry among the open legs, paper or real book: adjustment_readers.nearest_expiry) and
    its failure rule. Answer states: stated -> with the expiry; no open leg / book unreadable / not found -> "(#<id>)"
    only, never a guessed date; any failure reading ONE trade -> that row "(#<id>)", logged, the list still answers."""
    from ofo_app import adjustment_readers as readers  # noqa: PLC0415 - it imports the route modules
    out: dict[int, ExplanationText] = {}
    for sid, name in dict(rows).items():
        shown = sf.shown_name(name) if name else render_explanation("alert_title_unnamed", id=sid)
        expiry = None
        try:
            async with conn.begin_nested():  # a failed statement rolls back to here; the caller's session stays usable
                expiry = await readers.nearest_expiry(conn, sid)
        except Exception:
            log.warning("alert label: the expiry of strategy %s could not be read; its number is shown alone", sid,
                        exc_info=True)
        out[sid] = (render_explanation("alert_strategy_label_no_expiry", name=shown, number=sid) if expiry is None
                    else render_explanation("alert_strategy_label", name=shown, number=sid, day=expiry.day,
                                            month=_MONTHS[expiry.month - 1]))
    return out
