# Tool: reset the ofo_test catalogue (issue #497; owner approved 2026-10-22 ~14:50 IST; Tier A, size S)

Common brief: docs/process/builder-brief.md (Budget hard stop; scratch-copy mutations; full changed test files).

Core: one command empties ONLY ofo_test's catalogue tables after writing a backup, and refuses every other database.
Proof: step 1 is a test that the tool refuses a DATABASE_URL naming `ofo_dev`, `ofo`, `ipodhan`, `postgres`, an empty
name and a name containing `ofo_test` as a substring (e.g. `ofo_test_old`), before any connection; the real run on
ofo_test is done by the orchestrator AFTER an independent check.

Spec basis: none: the spec says nothing about resetting test data (searched: reset, ofo_test, catalogue reset in
spec/). Issue #497's fix text: "a re-runnable reset tool for ofo_test (owner role, refuses any database not named
ofo_test)". Owner answer 2026-10-22 (question tool): "Reset ofo_test catalogue (Recommended)" - only the catalogue and
broker-instrument tables, a backup first, never ofo_dev or any IPODhan database. ADR-048 (tests run as ofo_app,
migrations as owner).
Copy from: none - project tooling.

## Where you work
Worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `build/seq-chunk-1`. Commit with
`git add <paths>` (never `-A`); do NOT push. Do NOT run the tool against any real database yourself: tests use fakes
or a refused URL only. Scratch:
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\cdc8b776-da99-4858-844d-ba9899512551\scratchpad\tool-reset`.

## What to build (orchestrator decisions, technical)
- `scripts/orchestrator/reset_test_catalogue.py <checkout> [--yes]`: reads the owner-role URL the same way
  `scripts/orchestrator/db_run.py` does (no secret printed); the database name must equal exactly `ofo_test` (an
  allow-list of one name), else exit 2 before connecting. Without `--yes` it only prints the row counts it would
  remove (dry run).
- Tables: exactly the allow-list `public.catalogue_term_changes`, `public.broker_instruments` (and its history table if
  one exists), `public.catalogue_contracts` - read the migrations for the real names. Before deleting: for each table,
  find every foreign key that points AT it from a table outside the allow-list; if any such row exists, refuse with
  the table and count (never CASCADE into strategies or anything else).
- Backup: before any delete, write each table's rows to `D:\Abhay\scratch\ofo2-test-db-backups\<UTC stamp>\<table>.csv`
  (outside the repo); refuse to delete when the backup file count or row count does not match.
- One transaction: delete in FK order, print the counts removed, commit; any error rolls back everything.
- Triggers or guards that refuse deletes (the app role has no DELETE; history guard triggers) are respected: the tool
  runs as the owner role; if a trigger still refuses, report it and stop (do not drop or disable triggers).

Attack list: (each names its test file: `tests/orchestrator/test_reset_test_catalogue.py`)
1. Refused names: `ofo_dev`, `ofo`, `ipodhan`, `postgres`, `''`, `ofo_test_old`, `OFO_TEST`, a URL with no database
   -> exit 2, no connection opened (assert the connect function is never called).
2. Dry run (no `--yes`) -> counts printed, no delete issued.
3. A row outside the allow-list referencing a catalogue row -> refused with the table name, nothing deleted.
4. Backup mismatch (fewer rows written than counted) -> refused, nothing deleted.
5. An error during the second delete -> the first delete is rolled back.
6. The table list is an allow-list: a table name not in it is never touched (assert the exact statements issued).

Standing items: (a) n/a: no time-budgeted job; (b) n/a: no CI step changes; (c) n/a: no static detector; (d) the
database's answers: refused by trigger, FK violation, connection failure, permission denied - each reported, nothing
half-deleted.
Threat model: in scope - deleting from any database but ofo_test, deleting any table beyond the allow-list, deleting
without a backup; out of scope - an attacker with the owner password (they need no tool).
Findings checked: branch-migration-tests-move-shared-db, guard-as-forbidden-list
Reviewer checklist: the name check is exact equality before any connection; statements asserted exactly; backup
verified before delete; one transaction; no CASCADE, no trigger disabling; every guard has a test that dies without it
(scratch-copy mutation list); no new duplicated literal; reuse the existing helper (db_run's env reading); ruff baseline
must not rise; targeted tests only.

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Plus `tests/orchestrator/test_reset_test_catalogue.py` and `python scripts/ruff_ratchet.py`.
Budget: 30 min wall-clock, 40 tool calls
Report: evidence-table
