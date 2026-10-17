# Fix brief: W-094 round 3 - no Zerodha identifier outside broker_instruments; the filled-quantity test's role (Tier A: migration)

Core: CI run 38992320936 (`api` job) on PR #357: 2 failed, 2160 passed -
(1) `tests_app/test_broker_instruments.py::test_ac3_no_table_but_broker_instruments_has_a_zerodha_id_column`: "Left
contains one more item: ('execution_plan_orders', 'tradingsymbol')"; (2)
`tests_app/test_execution_plan_store.py::test_the_database_guards_the_filled_quantity`: `assert '42501' == 'OF016'`
("permission denied for table execution_plan_orders").
Proof: both green in this PR's CI; locally the non-DB checks below.

RCA (1): the plan-orders table stores the Zerodha trading symbol, a broker identifier; the identity rule keeps every
broker identifier in `broker_instruments` only (the row already carries the internal `instrument_id`; matching uses
the tag). RCA (2): the test expects the guard's code from an UPDATE the application role is not GRANTED at all, so
PostgreSQL refuses before the guard runs - the test asserts the wrong layer.
Class (1): every column in a table other than `broker_instruments` named `instrument_token`, `tradingsymbol`,
`broker_token` or `broker_symbol` - before 1 (`execution_plan_orders.tradingsymbol`), after 0. Class (2): guard tests
that act as the application role on a column it has no grant for - before 1, after 0 (run as the owner role to reach
the guard; keep one assertion that the application role gets 42501).
Proof: CI `api` job green on the PR.

Tier: A. Model: sonnet.
Budget: 30 min wall-clock, 36 tool calls. HARD limit: at call 33 commit, push, report.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under 200 words.
Copy from: none - fixes in this item's own migration, store and tests.
Findings checked: instrument-identity-keyed-on-one-broker, identifier-unique-only-by-convention,
repo-wide-scan-outside-targeted-tests, privilege-guard-as-denylist
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py

## Spec basis
- ADR-050 item 2 (a per-broker table holds broker token / broker symbol; "A contract with no row for a broker cannot be
  traded at that broker (no symbol guessing)").

## Fix
1. Migration 0016: drop the `tradingsymbol` column from `execution_plan_orders` (and every grant, CHECK, guard and
   allow-list text that names it; re-pin the guard md5 if the guard body changes).
2. Store: `PlanOrder.tradingsymbol` STAYS in the dataclass (two parallel items code against it). `record_plan` checks
   each order's `tradingsymbol` equals the catalogue's ZERODHA broker symbol for its `instrument_id` (refused
   `bad_plan` otherwise, no symbol guessing); `plans_for` / `open_plan` fill it back from the catalogue's ZERODHA row by
   `instrument_id` (one query join or one lookup; a missing row -> `bad_plan`, never a blank). Read how
   `catalogue_store` maps an `InstrumentId` string to its broker rows before writing the join.
3. Test (2): reach the guard as the owner role (the fixture the migration tests use), asserting OF016; keep one
   assertion that the application role gets 42501 for that UPDATE.

## Rules
- Branch: `git fetch origin && git checkout -B land/W-094 origin/land/W-094`; push to `land/W-094`.
- NO database run locally (another builder is using the shared test DB); CI proves the DB tests.
- Before push, each as its own command: `python -m pytest -q -p no:cacheprovider tests/errors/ tests/test_*.py tests/engine/test_pricing_scan.py`,
  `python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_execution_plan_allowlist_chain.py tests_app/test_migration_sql_parses.py`,
  `python scripts/ruff_ratchet.py`, `python scripts/alembic_migration_guard.py`.
- No kit or `spec/` edit, no `views/`, no regenerated files, no `evidence/`. No PR (it is #357).
