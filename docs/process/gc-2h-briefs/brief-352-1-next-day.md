# Builder brief: #352 half 1 - an earlier-day open plan is resolved the next day, never guessed (GC-2h core) - Tier A

Common brief: docs/process/builder-brief.md
Core: an execution plan left open from an earlier trading day is never left open and never guessed: it is auto-closed
only when Zerodha's net shows its orders changed nothing; every other case is a recorded, sticky mismatch (the #380-1
store) that blocks the strategy until a recorded resolution.
Proof: tests_app/ cases on the real 2026-10-16 replies (tests/fixtures/kite_replies/, plan OFS1V1L0 BUY 65,
NIFTY26O1923650CE) with DERIVED next-day replies (orders [] and trades [] as Kite returns them the next day), base = the
net of the strategy's OTHER stored plans:
- earlier-day open ENTRY, net = base -> closed `nothing_placed`; net = base + 65 (or + 30) -> closed
  `unresolved_from_positions` + a mismatch record, strategy blocked (never `filled`);
- earlier-day open EXIT, net = held -> closed `nothing_placed` (a new EXIT can be created); net 0 -> closed
  `unresolved_from_positions` + mismatch, lifted only by the `kite_flat_marked_exited` resolution (ADR-109 (4));
- the contract expired overnight -> mismatch (never `nothing_placed`);
- a same-day open plan is untouched (ADR-110 pending; its tags are in today's book);
- a plan two days old and a strategy with another closed plan on the same contract (base from the other plans).
Spec basis: ADR-109 (2), (4); ADR-110; ADR-111; ADR-016; REQ-060 AC-1, AC-4, AC-6; Q222; #352.

ADR-109: "never automatically"
ADR-111: "the app records the resulting mismatch"
Copy from: none - extends backend/ofo_app/reconcile_attribution.py (#398) and backend/ofo_app/execution_return.py; reuses the #380-1 store.
Class: every stored plan whose status is open and whose created_at is before today's session (any strategy, ENTRY or EXIT); before the fix they stay open forever (pending under ADR-110 with no book rows), after it each is closed or a recorded mismatch.
Findings checked: state-with-no-working-exit, caller-supplied-verdict-trusted, guard-without-killing-test, guard-as-forbidden-list
Threat model: in scope - every next-day position state for an earlier-day plan (equal, more, less, opposite, flat, expired, two plans, other strategies or standalone on the contract), a plan created exactly at a day boundary, a clock that is not IST-aware; out of scope - forged stored rows (ADR-098), the close-of-day read (#352-2, GC-3F).
Why Opus: Tier A reconciliation core of GC-2h (order/position state).
Tier: A. Branch: build/352-1-next-day, based on build/380-1-mismatch-store merged with build/W-108-attribution (05ae2c5): `git fetch origin`, `git checkout -b build/352-1-next-day origin/build/380-1-mismatch-store`, `git merge --no-edit origin/build/W-108-attribution`, resolve, then build. Push to that branch; do not open a PR.
Budget: 90 min wall-clock, 80 tool calls
Report: evidence-table

## Read first
docs/process/goal-contract-GC-2h-2026-10-18.md (Core, Proof, item 2), docs/process/gc-2h-contract-review-2026-10-18.md
(the two CRITICALs), ADR-109, ADR-110, ADR-111, issue #352, backend/ofo_app/execution_return.py (`classify` never closes
from the book alone :23-24, :117-118; `drifted` :132), backend/ofo_app/reconcile_attribution.py (PENDING_ABSENT,
`attribute_and_compare`), backend/ofo_app/execution_plan_store.py (close_plan, close reasons incl. the new
`unresolved_from_positions` from #380-1), the #380-1 reconciliation store, backend/ofo/timeutil.py (IST, session start:
never `datetime.now()` in the domain; the caller passes the date).

## What to build
A resolver (app layer) that, for each earlier-day open plan of the account, reads Zerodha's net (positions reply) and the
strategy's other stored plans, applies the Proof's table (an allow-list of the auto-close cases; everything else is the
mismatch branch), closes the plan through `close_plan` with the stated reason, records the mismatch through the #380-1
store when it is not auto-closed, and makes `attribute_and_compare` treat an earlier-day plan as resolved-or-mismatch,
never `pending` (ADR-110 stays for same-day plans). Expose it as a function the routes call (no route wiring here; GC-3F
wires it with #380-2). Adopting the next-day net as a fill is NOT built (owner question OQ-GC2h-1).

## Attack cases
1. net = base + 65 must never become `filled` (ADR-109 (2)); 2. EXIT net 0 must never become `exited` (ADR-111);
3. two earlier-day plans on one contract; 4. a standalone recorded on the contract; 5. expired contract; 6. the session
boundary (15:30 / 09:15 IST, a plan at 23:59); 7. mutation of every branch, killing test named.

## B4 standing items
(a) no time-budgeted job; (b) no new CI import; (c) the auto-close cases are an allow-list; (d) every stored-data and
Zerodha answer state listed in the Proof and the attack cases has a test and a stated result.

Rules: no new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only (run
tests_app/test_reconcile_attribution.py, tests_app/test_execution_return*.py and the store's test via db_run.py if they
need the DB - targeted files only, the VPS PostgreSQL also serves IPODhan production); register any new ApiModel in
tests_app/test_response_door.py; no regenerated files; `coverage.py . --check`. Windows: `-p no:metadata`. No Kite call.
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
