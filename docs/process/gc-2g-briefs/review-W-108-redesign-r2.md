# Review brief: W-108 redesign round 2 (PR #398, head 05ae2c5) - Tier A, fresh, narrow, LAST round

Common brief: docs/process/builder-brief.md (review task: read-only; hands-on attacks first)
Core: no stored plan, open or closed, makes the app's own lots read as outside or clears a mismatch; a plan Zerodha's
book contradicts is pending and its strategy blocked; otherwise the normal comparison applies.
Proof: each finding cites path:line and a command run this turn.
Spec basis: ADR-110; ADR-109 (2); REQ-060 AC-6, AC-7; ADR-105; ADR-016; Q224; #405.

ADR-110: "makes no own/outside split for it"
ADR-110: "so a plan the user never returns to cannot hide a shortfall or outside lots for good."
Copy from: none - a review.
Findings checked: state-with-no-working-exit, caller-supplied-verdict-trusted, guard-without-killing-test, test-asserts-implementation-output, guard-as-forbidden-list
Threat model: in scope - the open-plan and closed-plan reads against today's order book (final-state allow-list, drift, missing/duplicated/differing rows), pending/blocked, the StoreReader check, the outside cap and standalone_unseen; out of scope - route wiring, the stored sticky block, the reconcile screen (GC-3F), forged Python objects (ADR-098).
Why Opus: Tier A last review round of the GC-2g core (reconciliation quantities).
Budget: 20 min wall-clock, 40 tool calls
Report: evidence-table

Checkout at 05ae2c5 (read-only; scratch scripts in a NEW folder under the same scratchpad):
C:/Users/itsab/AppData/Local/Temp/claude/D--Abhay-Ventures-OptionsForOptions2/6e6d07e9-9c28-471b-b352-b399378b3504/scratchpad/w108
Round-1 review findings (reviewer's words, on 5747818): MAJOR closed plans never checked against today's book
(`nothing_placed` close with fill 0, then COMPLETE 65 on Kite -> 65 read as outside, nothing blocked); MINOR duplicate
tag in one plan counted twice; MINOR the cap skipped when expected is exactly 0; MINOR a differing book row failed the
whole account. Round-1 attack scripts (re-usable): the `w108-attack` folder under the same scratchpad.
Read `git diff 5747818 05ae2c5 -- backend tests_app` and backend/ofo_app/execution_return.py:132 (`drifted`).

Attacks (work every expected value by hand from the rule):
1. Each round-1 finding: FIXED / NOT FIXED with path:line and a run.
2. Drift edges: a closed `filled` plan whose row today shows a SMALLER fill (impossible at Kite? say so) or a working
   status; a closed `exited` plan; a closed plan from an earlier day (no rows) -> stored fill, normal; a closed plan
   with SOME tags present and some absent.
3. Does the new drift path reach every holder of the contract (two strategies) and stay off unrelated contracts?
4. Does `book_row_differs` as pending (not an error) open any path where a differing row's fill is COUNTED?
5. Re-run the round-1 open-plan attacks (COMPLETE 65 at Zerodha 0/65/130, OPEN, absent, duplicate rows, CANCELLED 30
   of 65, reader refusals, cap cases) - still the same results?
6. Expected 0 path: own +65, standalone -65, Zerodha +65 by hand from compare's rule.
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests (reviewer: only tests_app/test_reconcile_attribution.py, with -c pytest-app.ini -p no:metadata)
Report (under 300 words): verdict PASS / REVISE, findings (CRITICAL/MAJOR/MINOR, path:line, one-line fix), covers the
class (every stored plan of any strategy against any book state): yes/no, evidence table.
