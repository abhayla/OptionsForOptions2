# Builder brief: mechanism for finding request-clock-for-database-stamped-fact - the audit store stamps its own time from the database clock (Tier A: audit store, hash input)

Core: `audit_store.append` no longer accepts a `timestamp` from its caller: inside the lock it reads the database
clock (`SELECT clock_timestamp()`, the clock `last_seen_at` and grants already use) and that value goes into the
event, the hash and the row. Every caller is updated (catalogue_store, entitlement_store, the return route, and the
Execute route's `order_prepared` from W-103). A caller passing `timestamp=` is a TypeError, so the class cannot come
back at a call site.
Proof: on ofo_test, an append inside a transaction whose session clock is set far from the request clock (a pinned
request clock 2026-10-16 15:07 IST) stores a timestamp within 5 s of `clock_timestamp()` read in the same
transaction; the chain verifies after appends from all four callers (`tests_app/test_audit_store.py` + the callers'
own test files).

Tier: A. Model: opus.
Budget: 55 min wall-clock, 60 tool calls. HARD limit: at call 56 commit, push, report.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under 250 words, `git status --short` empty,
each new guard with its killing test (mutation-run).
Copy from: none - `entitlement_store` already relies on the database stamp (read how it checks "stamp +/- 60 s").
Findings checked: request-clock-for-database-stamped-fact, store-rule-enforced-per-call-site, wall-clock-assertion-flakes-under-load, branch-migration-tests-move-shared-db
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py ; then python -m pytest -q -p no:cacheprovider -m repo_scan tests

## Spec basis
- Finding `request-clock-for-database-stamped-fact` (3 occurrences in GC-2c; the mechanism the GC-2e contract item 8
  names: "the audit and entitlement stores stamp their own times from the database clock (callers cannot pass one)").
- REQ-063 AC-5 (the audit store) is unchanged in what it stores; only who supplies the time changes.

## Build
1. `backend/ofo_app/audit_store.py` `append`: drop the `timestamp` parameter; after `_take_lock`, read
   `clock_timestamp()` (timezone-aware) and use it. Keep the READ COMMITTED check.
2. Update every caller (grep `audit_store.append`): catalogue_store, entitlement_store, and W-103's
   `backend/ofo_app/order_audit.py` (merged #367; it reads `clock_timestamp()` itself and passes it in - that read
   moves into the store). Remove now-unused clock plumbing only where it existed solely for this call.
3. `entitlement_store.append`: confirm in the report whether any time it stores comes from the caller; if one does,
   apply the same rule; if none, say so with the line numbers.
4. Tests: the far-request-clock case above; a call with `timestamp=` raises TypeError; the chain verifies across all
   callers; no wall-clock equality asserts (finding wall-clock-assertion-flakes-under-load: compare to the database
   value read in the same transaction).

## DB
You are THE shared-DB holder for this item (W-103 has released it). DB commands only through
`python D:/Abhay/Ventures/OptionsForOptions2/scripts/orchestrator/db_run.py <your worktree> python -m ...`; no
migration in this item; finish with `alembic current` printing main's head.

## Rules
- Branch `build/db-clock-stores` from origin/main (after W-103 merged). No work card (a mechanism, like GC-2c's
  atool_restore); the finding's `detection` and `fix` fields are updated by the orchestrator in the docs batch.
- Never copy .env; no PR. No kit or `spec/` edit, no `views/`, no `evidence/`. Common rules: `docs/process/builder-brief.md`.
