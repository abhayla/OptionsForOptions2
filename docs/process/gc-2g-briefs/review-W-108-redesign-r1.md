# Review brief: W-108 redesign round 1 (PR #398, head 5747818) - Tier A, fresh, narrow

Common brief: docs/process/builder-brief.md (review task: read-only; hands-on attacks first)
Core: an OPEN plan never makes the app's own lots read as outside and never clears a mismatch; once every one of the
plan's orders is final in Zerodha's order book, the normal comparison applies.
Proof: each finding cites path:line and a command run this turn.
Spec basis: ADR-110; ADR-109 (2); REQ-060 AC-6, AC-7; ADR-105; Q224; #405.

ADR-110: "makes no own/outside split for it"
ADR-110: "so a plan the user never returns to cannot hide a shortfall or outside lots for good."
Copy from: none - a review.
Findings checked: state-with-no-working-exit, caller-supplied-verdict-trusted, guard-without-killing-test, test-asserts-implementation-output, guard-as-forbidden-list
Threat model: in scope - the open-plan read (tag lookup, final-state allow-list, missing/duplicated/mismatched rows), the pending/blocked result, the StoreReader check, the outside cap and standalone_unseen; out of scope - route wiring, the stored sticky block, the reconcile screen (GC-3F), forged Python objects (ADR-098).
Why Opus: Tier A review of the GC-2g core (reconciliation quantities) after an independent redesign.
Budget: 20 min wall-clock, 40 tool calls
Report: evidence-table

Checkout (already at 5747818, read-only for you; put any scratch script in a NEW folder under the same scratchpad):
C:/Users/itsab/AppData/Local/Temp/claude/D--Abhay-Ventures-OptionsForOptions2/6e6d07e9-9c28-471b-b352-b399378b3504/scratchpad/w108
Read: the builder brief docs/process/gc-2g-briefs/brief-W-108-redesign.md (main checkout), #405, then
`git diff 0db9fa9 5747818 -- backend tests_app` in the checkout. You did not build or review W-108 before.

Attacks (hands-on: call `attribute_and_compare` from a python script with the test file's fakes, on the real
tests/fixtures/kite_replies/ rows; work every expected value by hand from the rule, not from the code's output):
1. #405 MAJOR closed? Plan 1 OPEN, BUY 65 COMPLETE in orders-122104, Zerodha 65 -> not blocked, 0 outside; Zerodha
   130 -> 65 outside; Zerodha 0 -> blocked. Plan OPEN, order OPEN -> pending + blocked, even with Zerodha 130.
2. Never pending forever with a hidden shortfall: a plan whose orders are all final but filled less (CANCELLED with
   filled 30 of 65) and Zerodha 65 -> what? A plan placed on an earlier day (rows absent from today's book) -> pending
   and blocked for good: is there any path where that clears a shortfall or hides outside lots? (blocked forever is
   acceptable fail-closed for this item; record whether the result names the plan so a later screen can act.)
3. Can a pending contract leak into `outside`, `compared_net` or compare's report as agreeing? Can `blocked` miss a
   holder? Two strategies on one contract with one pending; a pending strategy's OTHER contract (pending covers the
   strategy, not just the contract).
4. Tag matching: two plans of one strategy both open (store allows one open plan? check execution_plan_store); a book
   row whose tag decodes to the plan but quantity bigger/smaller (partial fill COMPLETE impossible?); a tag of another
   strategy; book rows with tag None.
5. Final-state allow-list reuses `execute_plan.TERMINAL_ORDER_STATUSES` - read its definition: exact words, no
   case-folding, nothing else final.
6. StoreReader refusal: a subclass, a dataclasses.replace with a lambda, APP_ENV unset / `Test` / `test ` (trailing space) -> refused?
7. Outside cap: own +65, standalone -100, Zerodha +65 by hand; own -65, Zerodha -130; standalone only.
8. Unbounded order book (builder skipped a size cap): is it a real risk given the input is Zerodha's parsed reply?
   MINOR at most unless you show harm.
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests (reviewer: only tests_app/test_reconcile_attribution.py, with -c pytest-app.ini -p no:metadata)
Report (under 300 words): verdict PASS / REVISE, findings (severity CRITICAL/MAJOR/MINOR, path:line, one-line fix),
covers the class (open plans of any strategy, any book state): yes/no, evidence table.
