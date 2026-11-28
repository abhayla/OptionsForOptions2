"""The Exit dialog's market-closed answer (ADR-330 (60), owner 27 Nov 2026 evening; ADR-212, ADR-119,
ADR-330 (58)).

Spec basis: ADR-330 (60): while the market is closed the Exit dialog opens, shows the legs it would close and one
line ("The market is closed. Exits can be placed from 09:15 on <next trading day>.") with Confirm greyed; the
sentence and the day come from the server's ONE market-state answer (``routes.outcome.market_state``, the calendar
behind it, ADR-119), so the answer is the same with the feed process running or stopped, and for paper and real exits
alike (the question has no paper or real input). ADR-212 still refuses the exit at the server: this only moves the
reason before the press.

Answer states: open -> ``closed`` False, no sentence; closed with a next open in the calendar -> the day named; closed
and the calendar cannot name the next open (past its data) -> the sentence without a day (never a guessed day); no
context at all -> the calendar's own answer (``market_state`` fails closed). The sentence is a catalogue explanation
(typed slot), never a string built here. The next open is read from the calendar directly; Lane N's
``next_open_at`` on the market-state answer (origin/fix/last-close-1127) replaces that one call when it lands.
"""
from __future__ import annotations

import datetime

from ofo.errors.explanations import ExplanationText, render_explanation
from ofo.market_calendar import next_open
from ofo.timeutil import IST

from ofo_app.routes.outcome import MarketContext, market_state


def exit_market_answer(
        ctx: MarketContext | None, at: datetime.datetime,
) -> tuple[bool, ExplanationText | None, datetime.datetime | None]:
    """(closed, the one sentence, the next open) at ``at``."""
    if not market_state(ctx, at).closed:
        return False, None, None
    opens = next_open(at)
    if opens is None:
        return True, render_explanation("exit_market_closed_no_day"), None
    return True, render_explanation("exit_market_closed", day=opens.astimezone(IST).date()), opens


_ENTRIES_DAY, _ENTRIES_NO_DAY = "exit_market_closed_entries", "exit_market_closed_entries_no_day"


def entries_sentence(opens: datetime.datetime | None) -> ExplanationText | None:
    """FD4 item 5: the same line for ENTRIES (the Add to Paper dialog asks this route too and must not say "Exits"):
    "The market is closed. Orders can be placed from 09:15 on <day>." beside ``sentence``, the same day. Only the
    catalogue mints a line, and the two templates (``exit_market_closed_entries`` with a ``day`` slot, ``..._no_day``)
    are Lane FC3's file (explanations.py; FD4 RESULTS "For the owner lane" has the exact rows): until they land
    the field is None, never a string built here, never a guessed day. ``opens`` None = the calendar cannot name the
    next open (no day)."""
    try:
        if opens is None:
            return render_explanation(_ENTRIES_NO_DAY)
        return render_explanation(_ENTRIES_DAY, day=opens.astimezone(IST).date())
    except ValueError as exc:
        if "unknown explanation template id" not in str(exc):
            raise
        return None
