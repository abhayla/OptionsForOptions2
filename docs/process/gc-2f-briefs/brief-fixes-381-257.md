# Builder brief: #381 + #257 small fixes - Tier A

Common brief: docs/process/builder-brief.md
Core: (#381) the return route can never close a plan nothing_placed while Zerodha's trades show a fill for its tag,
whatever order the orders and trades reads come back in; (#257) a freeze limit older than the age ADR-091 sets shows
the ADR-091 warning instead of being used silently.
Proof: (#381) a test on the real tests/fixtures/kite_replies/orders-122104.json + trades-122104.json where the order
read misses the order but the trades read has its fill -> not nothing_placed; (#257) a test with a freeze file dated
older than the ADR-091 age -> the warning; a fresh one -> no warning.
Spec basis: issue #381; REQ-060 AC-6; REQ-058 AC-5; ADR-105; issue #257; ADR-091.
Copy from: none - fixes in existing modules.
Findings checked: state-read-after-await, trust-broker-status-word, fill-not-exactly-once, staleness-by-last-change-age, guard-without-killing-test
Threat model: in scope - the read order of orders vs trades in the return route; the age check on the freeze limit in force; out of scope - Kite's own consistency between its endpoints.
Tier: A (order state; quantity). Branch: build/fix-381-257 from origin/main. One PR, two commits.
Budget: 75 min wall-clock, 80 tool calls
Report: evidence-table

## Constraints
- This PR is NOT merged before GC-3L ends (Monday's live run is reviewed against today's return route). Build, test,
  push only.
- Read issue #381 and #257 first (gh issue view N --repo abhayla/OptionsForOptions2); read ADR-091 for the age and
  its exact warning wording; never type the age from memory (finding date-stamp-typed-from-memory).
- #381: the fix is in backend/ofo_app/routes/execution_return.py around :164; prefer reading trades and orders so a
  late-appearing order cannot lose its trade (read trades after orders, or re-check), and test both arrival orders.

## Attack cases
1. Order appears between the two reads -> plan not closed nothing_placed (the bug in #381).
2. Trades read empty, order COMPLETE -> not closed filled without a trade (Zerodha is the authority; submitted is
   not executed).
3. Freeze file exactly at the age boundary -> per ADR-091's wording (state which side).
4. Mutation: revert each fix -> its test goes red.

B4: (d) every answer state of the orders and trades reads (present, absent, empty, failed) has a test and a stated
result.
Rules: no new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only;
no regenerated files in the PR.
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Plus the changed files' own test files (grep tests_app/ for execution_return and freeze; DB tests via
scripts/orchestrator/db_run.py, targeted files only).
