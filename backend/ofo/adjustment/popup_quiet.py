"""D-67 (ADR-326 (5)): when an adjustment pop-up is raised. The ONE place that decides it; the reply of
GET /adjustment-opportunities carries the answer (``popup_due``) and the browser only obeys it.

A rule that was already true when the trade was entered is not raised as a pop-up in the first 5 minutes after entry
(the figure of the REQ-170 alert cool-down). After that, if it is still open, it is raised as before. A rule that became
true after entry is raised at once. Only the pop-up waits: the record, its rule and the bell's count are unchanged.

"Already true at entry" = the rule's FIRST evaluation came right after entry and found it true:
- ``seen_clear`` False: no check has ever found the rule false (``playbook_store.rule_states``);
- ``first_check_at``, the time the rule's memory was written (an upper bound of its first check: a later rewrite only
  makes it later), is 0 to ``FIRST_CHECK_WINDOW`` after the strategy's entry (its first order,
  ``adjustment_readers.entered_at``). The worker re-reads its monitor set every 30 s (``background.REBUILD_SECONDS``,
  REQ-115 AC-3: a new strategy is checked within 60 s) and wakes every second, so the first check follows entry within
  that window. A first check later than that cannot say what the rule was at entry: it may have turned true after
  entry, so the pop-up is raised at once;
- the record opened within the quiet period (``shown_at``).

Every answer state that is not that: entry time unknown, rule memory or its write time absent, a clock that does not
agree (record before entry, no time zone) -> due at once. Fail open toward telling the trader: a pop-up that comes
early costs a glance, one that never comes costs a missed adjustment. ``now`` is the app clock the order times were
written with (the scenario's clock in scenario mode), never the real one.
"""
from __future__ import annotations

import datetime

#: ADR-326 (5), REQ-170 cool-down: the same 5 minutes
QUIET_PERIOD = datetime.timedelta(minutes=5)
#: a new strategy is checked within 60 s (REQ-115 AC-3; monitor set re-read every 30 s, ``background.REBUILD_SECONDS``)
FIRST_CHECK_WINDOW = datetime.timedelta(seconds=60)


def _aware(*times: datetime.datetime | None) -> bool:
    return all(isinstance(t, datetime.datetime) and t.tzinfo is not None for t in times)


def popup_due(*, entry_at: datetime.datetime | None, shown_at: datetime.datetime, seen_clear: bool | None,
              first_check_at: datetime.datetime | None, now: datetime.datetime) -> bool:
    """True when the pop-up for this open record is raised now."""
    if entry_at is None or seen_clear is None or seen_clear or first_check_at is None:
        return True  # unknown entry, unknown memory, or the rule was false at a check after entry: at once
    if not _aware(entry_at, shown_at, first_check_at, now):
        return True
    checked_after = first_check_at - entry_at
    if checked_after < datetime.timedelta(0) or checked_after >= FIRST_CHECK_WINDOW:
        return True  # first evaluated late: the entry state is unknown, tell the trader
    opened_after = shown_at - entry_at
    if opened_after < datetime.timedelta(0) or opened_after >= QUIET_PERIOD:
        return True  # not a rule that was true at entry (or another clock): as before
    return now >= entry_at + QUIET_PERIOD
