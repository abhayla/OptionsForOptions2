# Lane D owner questions (26-27 Nov 2026)

Asked through the coordinator only. Each has the spec basis, the real case, options and a recommendation.

## D-Q1 (#732): tell the user when a price-level exit is waiting for prices?

Spec basis: none: the spec says nothing about a conditional exit that cannot fire because a contract has no live
price (searched: conditional exit, not live, armed, waiting). ADR-003 (wording is decision support).
Real case: no real case recorded; code path `backend/ofo_app/paper_monitor.py:227-229` returns silently and the
trigger stays armed.
Options:
1. (Recommended) One information alert per trigger per day: "Your exit at <level> could not run: <contract> has no
   live price. It stays armed." No order is placed. Cost: a new catalogue text and alert kind.
2. A line on the trade's page only (no alert).
3. Leave it silent.

## D-Q2 (#733): "Keep this level" when the index has already crossed that level

Spec basis: ADR-317 (treated as low risk); none on a crossed level (searched: keep this level, keep_paper_trigger).
Real case: no real case recorded.
Options:
1. (Recommended) Refuse with a named sentence: "NIFTY is already past <level>; pick a new level." Nothing changes.
2. Keep it and let it fire on the next tick (today; the same as arming a crossed level the first time).

## D-Q3 (#753): what "saved before ADR-247" means once a plan is edited

Spec basis: ADR-250 (plans saved before ADR-247 keep their own stops), ADR-247. Today the test reads `accepted_at`,
which migration 0041 restamps on every edit, so the first edit adds the 2x-credit line.
Real case: no real case found in the data this lane can read (no production DB here).
Options:
1. (Recommended) "First saved before ADR-247", read from the plan's `created_at` (never changes): an edited old plan
   keeps its own stops and gains no 2x-credit line. No migration.
2. Keep today's behaviour: an edit counts as a new acceptance under the new rules (then only the docstring changes).
3. A new stored marker column (a migration; not this lane).
