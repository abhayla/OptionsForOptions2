# Lane D owner questions (26-27 Nov 2026)

Asked through the coordinator only. Each has the spec basis, the real case, options and a recommendation.

## D-Q1 (#732): tell the user when a price-level exit is waiting for prices?

Spec basis: REQ-109 AC-8 and ADR-317 (2) (no live price at save: saved, arms at the next live tick; silent on an armed
trigger blocked by one contract); REQ-100 AC-18 (live platform stops: a missing or failed leg price blocks the fire,
alerts the user, waits for the next evaluation, no tight retry); ADR-003 (searched: conditional exit, stays armed, no
live price, not live).
Real case: no real case recorded; code path `backend/ofo_app/paper_monitor.py:227-229` returns silently and the
trigger stays armed.
Options:
1. (Recommended) One information alert per trigger per day: "Your exit at <level> could not run: <contract> has no
   live price. It stays armed." No order is placed. Cost: a new catalogue text and alert kind.
2. A line on the trade's page only (no alert).
3. Leave it silent.

## D-Q2 and D-Q3: withdrawn (the spec already answers them)

A search of the spec by subject on fix/ic-live-test-1123 found the answers, so neither goes to the owner:
- #733: ADR-317 (1) (owner-approved 23 Nov 17:12) refuses a level already crossed at save time; Keep is a save.
- #753: ADR-250 and ADR-252 (23) settle it; the fix needs a migration (sent to the coordinator).
