# Fix brief: W-096 round 2 - undecidable contracts and earlier-session plans fail closed (Tier A: reconciliation)

Core: two new DB tests on real reply shapes go red now and green after: (1) strategy A holds 65 by its stored plans,
strategy B has an OPEN plan BUY 65 on the same contract filled at Zerodha but not returned, Zerodha net 65 (the
151006/122104 rows re-tagged per strategy) -> A's return reports reconciliation REQUIRED for that contract, never
"no mismatch"; (2) plan 1 created on 2026-10-16 and returned with an empty book on 2026-10-17 (no tag in today's orders,
positions still 65) -> the plan is NOT closed `nothing_placed`; it stays open, reconciliation required.
Proof: those two tests in this PR's CI (#358, its own PostgreSQL); locally the non-DB unit tests of the same logic.

RCA (review MAJOR 1): `others` counts another strategy's OPEN plan orders as 0 (held_units treats None filled as 0)
and the book is filtered to this strategy's tags, so units filled for B are attributed to A. RCA (MAJOR 2): `classify`
reads "no tag in today's book" as terminal-and-unfilled without checking the plan's session date, and Kite's order book
holds only today's orders.
Class (1): every contract of this strategy that ANY other strategy touches through an open or drifted plan -
before: decided as if the other held 0; after: undecidable -> reconciliation required. Class (2): every open plan whose
`created_at` is not in today's trading session (IST date, ofo/timeutil) - before: closable as nothing_placed from an
empty book; after: never closed from the book; reconciliation required with the reason.
Proof: the two core tests + non-DB unit tests per class (an open other-plan, a drifted other-plan, a closed other-plan
still decides normally; created yesterday / today).

Tier: A. Model: opus.
Why Opus: reconciliation state where a wrong pass hides a live position; class-level fix with cross-strategy cases.
Budget: 40 min wall-clock, 44 tool calls. HARD limit: at call 41 commit, push, report.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under 250 words, each new guard with its
killing test (mutation-run on the non-DB tests).
Copy from: none - fixes inside this item's own code.
Findings checked: resolution-on-stale-broker-copy, held-without-platform-fill-invisible-to-ledger,
state-with-no-working-exit, trust-broker-status-word, repo-wide-scan-outside-targeted-tests
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py

## Spec basis
- REQ-060 AC-7: "A broker position in no strategy and not recorded as standalone is offered the grouping choice (Q24)
    and blocks no strategy. A mismatch blocks only the strategy whose contract quantity disagrees (Q199)."
- REQ-057 AC-2: "A submitted order never changes strategy state or positions until the broker confirms execution (Q195)."

## Fix
1. MAJOR 1: in `backend/ofo_app/execution_return.py` (NOT in `execute_plan.py` - W-095 round 4 edits that file in
   parallel), before deciding a contract, look at other strategies' stored plans: any OPEN plan (or a closed plan this
   run finds drifted) with an order on that contract -> the contract is undecidable for this strategy: reconciliation
   required, reason named; never a pass. Closed, undrifted other plans keep counting by their filled quantities.
2. MAJOR 2: an open plan whose `created_at` IST date is not today's (database clock, the same "today" the eligibility
   code uses) is never closed from the book: it stays open, the reply marks reconciliation required with the reason
   "plan from an earlier session"; same-day behaviour unchanged. (Deferred #352 keeps the close-of-day read.)
3. MINOR 3: other strategies' contract keys use THEIR own underlying, not this strategy's.
4. Leave as documented limits (say so in the module docstring, one line each): an unrelated standalone position on the
   same contract keeps `exited` from being reached (MINOR 4); P&L from today's fills only (MINOR 5); external orders
   marked only by the correlation id (MINOR 6).

## Rules
- `git fetch origin && git checkout -B build/W-096-return-route origin/build/W-096-return-route`; push there (PR #358
  is a draft; CI runs on every push).
- NO local database run (the shared test DB is in use). Before push, each as its own command:
  `python -m pytest -q -p no:cacheprovider tests/errors/ tests/test_*.py tests/engine/test_pricing_scan.py`,
  `python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_execution_return.py`,
  `python scripts/ruff_ratchet.py`. If you change a response model, regenerate `docs/api/openapi.json` with
  `python scripts/generate_openapi.py --out docs/api/openapi.json`.
- Do not edit `execute_plan.py` or `routes/execute.py`. No kit or `spec/` edit, no `views/`, no `evidence/`.
