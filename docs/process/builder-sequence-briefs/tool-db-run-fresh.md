# Tool: run DB tests in a throwaway database (issue #497 structural fix; Tier A, size M)

Common brief: docs/process/builder-brief.md (Budget hard stop; scratch-copy mutations; full changed test files).

Core: one command creates an empty database, migrates it to head, runs the given test command as the limited app
role against it, and drops it - so a test that needs an empty catalogue runs locally exactly as in CI.
Proof: the orchestrator runs it after an independent check on the five row-5 tests that need an empty catalogue
(`tests_app/test_catalogue_refresh.py`); step 1 for you is a test that the drop refuses any name not made by the tool.

Spec basis: none: the spec says nothing about test databases (searched: test database, throwaway, ofo_test). Issue
#497's fix: "every DB test that writes catalogue rows runs inside a rolled-back transaction or a per-run throwaway
schema". ADR-048 (tests run as the limited ofo_app role, migrations as the owner role). The catalogue delete guards of
migrations 0003/0004 are never disabled (REQ-053 AC-2: contracts are never permanently deleted).
Copy from: none - project tooling.

## Where you work
Worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `build/seq-chunk-1`. Commit with
`git add <paths>` (never `-A`); do NOT push. Do NOT create or drop a real database yourself: tests use fakes. Read
`scripts/orchestrator/db_run.py` (env reading, owner URL built in memory, never printed) and how CI prepares its
database in `.github/workflows/app-tests.yml` (Read tool only: grants for the `ofo_app` role, migration step). Scratch:
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\cdc8b776-da99-4858-844d-ba9899512551\scratchpad\tool-fresh`.

## What to build (orchestrator decisions, technical)
- `scripts/orchestrator/db_run_fresh.py <checkout> <command...>`: reuses db_run.py's env reading (import it, no copy).
  As the owner role on the same server: `CREATE DATABASE ofo_test_tmp_<UTC yyyymmddhhmmss>_<4 random hex>`; apply the
  same grants CI applies for `ofo_app`; `alembic upgrade head` as owner against it; run the command with
  TEST_DATABASE_URL / TEST_ADMIN_DATABASE_URL / ALEMBIC_DATABASE_URL pointed at it; always drop it in a `finally`.
- Drop allow-list: only a name matching exactly `^ofo_test_tmp_\d{14}_[0-9a-f]{4}$` may be dropped; any other name ->
  refuse (exit 2). A `--sweep` mode drops leftover names matching the same pattern older than 24 h (e.g. after a
  crash) and lists them first.
- Exit code = the command's exit code; a failure creating or migrating the database exits 3 with the step named.
- Never prints a password or URL.

Attack list: (each names its test file: `tests/orchestrator/test_db_run_fresh.py`)
1. Drop refuses `ofo_test`, `ofo_dev`, `ipodhan`, `postgres`, `ofo_test_tmp_x`, `ofo_test_tmp_20261022000000_zzzz`, a
   name with quotes or spaces -> exit 2, no DROP issued.
2. The database is dropped when the command fails, when migration fails, and on KeyboardInterrupt.
3. The command sees TEST_DATABASE_URL naming the temp database and the `ofo_app` role, never the owner role.
4. Sweep drops only pattern names older than 24 h; a younger one and a non-pattern one are kept.
5. Output never contains the password (assert on captured stdout/stderr with a fake secret).
6. The created name is unique per run (two calls in the same second differ).

Standing items: (a) n/a: no time-budgeted job; (b) n/a: no CI step changes; (c) the drop check is an allow-list
pattern, exact match, fail closed; (d) the server's answers: CREATE refused (no privilege), migration error, DROP
refused (open connections: terminate the temp database's own connections first, never another database's) - each
reported with its step.
Threat model: in scope - dropping any database the tool did not create, the owner role reaching the test command,
a leaked secret; out of scope - an attacker with the owner password.
Findings checked: branch-migration-tests-move-shared-db, guard-as-forbidden-list
Reviewer checklist: exact-match drop allow-list before any DROP; finally-drop on every path; app role for the command;
no secret printed; every guard has a test that dies without it (scratch-copy mutation list); reuse db_run's helpers;
ruff baseline must not rise; targeted tests only.

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Plus `tests/orchestrator/test_db_run_fresh.py` and `python scripts/ruff_ratchet.py`.
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table
