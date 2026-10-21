# Builder brief: #380 step 2.1 - stored mismatch record, sticky block, standalone store (migration, own PR) - GC-2h item 1, Tier A

Common brief: docs/process/builder-brief.md
Core: a reconciliation mismatch is stored and stays blocking until a recorded resolution lifts it; an agreeing later
comparison does not unblock by itself; a plan the next-day positions cannot settle can close with reason
`unresolved_from_positions` so one-open-plan stops blocking while the mismatch record carries the block.
Proof: the store's DB test file (via `scripts/orchestrator/db_run.py`, that file only) on the 2026-10-16 real replies'
shapes: record a mismatch for strategy 1 (contract NIFTY26O1923650CE, expected 65, Zerodha 0) -> `is_blocked(1)` True;
store an agreeing comparison -> still True; record a resolution -> False; the resolution and the record are audited.
Spec basis: REQ-060 AC-4, AC-6, AC-7; ADR-109 (1); ADR-111; Q222; Q224.

REQ-060 AC-6: "While a mismatch is unresolved, new execution and adjustment execution are blocked (Q199)."
Copy from: none - new store and migration; the legacy-reuse map has no reconciliation-store row (reconciliation is built new).
Findings checked: state-with-no-working-exit, caller-supplied-verdict-trusted, guard-without-killing-test, branch-migration-tests-move-shared-db
Tier: A (migration, reconciliation state). Branch: build/380-1-mismatch-store from origin/main. Its own PR (a migration).
Budget: 90 min wall-clock, 80 tool calls
Report: evidence-table

## Read first
docs/process/fix-380-draft-2026-10-18.md (its T5 section on the sticky block and mismatch record, the step order),
docs/process/goal-contract-GC-2h-2026-10-18.md (Core + item 1), backend/ofo_app/execution_plan_store.py (CLOSE_REASONS
`:44`, one open plan `:194`, close_plan), backend/ofo_app/alembic/versions/0016_execution_plans.py (the CHECK on close
reasons and the immutability triggers) and 0017, backend/ofo/reconciliation/ (compare report shape), ADR-109 (4) (the
three first resolution actions), REQ-060 AC-7 (standalone quantity).

## What to build
1. Migration 0018 (`op.*` calls directly, `scripts/alembic_migration_guard.py`): table(s) for (a) mismatch records
   (strategy id, contract key, expected, Zerodha net, raw report JSON, detected_at, source), (b) resolutions (which
   mismatch, action from a CLOSED list = the ADR-109 (4) actions: `reconciled_by_basket`, `marked_requiring_attention`,
   `kite_flat_marked_exited`, plus `attached_outside`/`detached_outside` reserved for later, actor, at, note), (c)
   standalone quantities per user + contract (REQ-060 AC-7); and the close reason `unresolved_from_positions` added to
   execution_plans' CHECK (a new pinned body if the migration changes a pinned function: publish PINNED_BODIES).
   Runs as the owner role; the `ofo_app` role gets only the grants it needs (ADR-048); downgrade works.
2. A store module (`backend/ofo_app/reconciliation_store.py`): record_mismatch, record_resolution (validates the action
   against the closed list and that the mismatch exists and is unresolved), is_blocked(strategy) = any mismatch without
   a resolution, standalone get/set. No caller-supplied verdict: is_blocked reads the rows itself.
3. `execution_plan_store`: accept the new close reason (with `filled=None` storing 0 per order), nothing else changes.
No route wiring here (step 2.2, GC-3F). No product behaviour changes on any route.

## Attack cases the reviewer will run
1. An agreeing comparison stored after a mismatch never unblocks (Q222).
2. A resolution for a mismatch of another user or strategy, a resolution action outside the closed list, a second
   resolution for the same mismatch -> refused.
3. Downgrade then upgrade leaves no orphan grant or trigger; the `ofo_app` role cannot delete or update a mismatch row.
4. Mutation: delete each guard and name the killing test.

## B4 standing items
(a) no time-budgeted job; (b) no new CI import; (c) not a detector - the block is a stored fact read in one place;
(d) answer states of the stored data: no mismatch / unresolved / resolved / two mismatches one resolved; standalone
present / absent / zero.

Rules: no new duplicated literal; reuse the existing helper (the store patterns of execution_plan_store.py); ruff/mypy
baselines must not rise; targeted tests only; no regenerated files in the PR. Do not open a PR. Windows: `-p no:metadata`.
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Plus: `python scripts/alembic_migration_guard.py`; the new store's DB test file via `scripts/orchestrator/db_run.py`
(that file only; the VPS PostgreSQL also serves IPODhan production); `coverage.py . --check`.
