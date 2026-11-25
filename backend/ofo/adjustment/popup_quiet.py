"""D-67 (ADR-326 (5)): when an adjustment pop-up is raised. The ONE place that decides it; the reply of
GET /adjustment-opportunities carries the answer (``popup_due``) and the browser only obeys it.

A rule that was already true when the trade was entered is not raised as a pop-up in the first 5 minutes after entry
(the figure of the REQ-170 alert cool-down). After that, if it is still open, it is raised as before. A rule that became
true after entry is raised at once. Only the pop-up waits: the record, its rule and the bell's count are unchanged.

"Already true at entry" = the rule's first evaluation after entry found it true, and its record opened within the quiet
period: the rule's memory has never seen it false (``seen_clear`` False; ``playbook_store.rule_states``) and
``shown_at`` is 0 to 5 minutes after the strategy's entry (its first order's time, ``adjustment_readers.entered_at``).

Every answer state that is not that: entry time unknown, rule memory absent, a clock that does not agree (record before
entry, no time zone) -> due at once. Fail open toward telling the trader: a pop-up that comes early costs a glance, one
that never comes costs a missed adjustment.
"""
from __future__ import annotations

import datetime

#: ADR-326 (5), REQ-170 cool-down: the same 5 minutes
QUIET_PERIOD = datetime.timedelta(minutes=5)


def _aware(*times: datetime.datetime | None) -> bool:
    return all(isinstance(t, datetime.datetime) and t.tzinfo is not None for t in times)


def popup_due(*, entry_at: datetime.datetime | None, shown_at: datetime.datetime, seen_clear: bool | None,
              now: datetime.datetime) -> bool:
    """True when the pop-up for this open record is raised now."""
    if entry_at is None or seen_clear is None or seen_clear:
        return True  # unknown entry, unknown memory, or the rule was false at a check after entry: at once
    if not _aware(entry_at, shown_at, now):
        return True
    opened_after = shown_at - entry_at
    if opened_after < datetime.timedelta(0) or opened_after >= QUIET_PERIOD:
        return True  # not a rule that was true at entry (or another clock): as before
    return now >= entry_at + QUIET_PERIOD
