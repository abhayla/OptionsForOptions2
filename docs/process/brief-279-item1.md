# Builder brief: #279 item 1 - an expired leg not yet settled never blocks reconciliation (Tier A)

Core: a calendar strategy whose near leg's contract expired at today's close, reconciled AFTER the close but BEFORE
`settle_expired_legs` runs, gets no blocking mismatch: the near leg is reported as awaiting settlement (the existing
non-blocking awaiting note from W-085), and the far leg is still compared normally.
Proof: the reproduction from the W-085 verifier - today the run gives `[('MISSING_PLATFORM_POSITION', True)]` for
strategy `CAL` - as a failing test first on the real `ofo.reconciliation` compare function, then green.

Model: opus. Why Opus: reconciliation is the execution-blocking safety gate (ADR-018); a wrong change either blocks
every calendar once per expiry or lets a real mismatch through - Tier A.
Budget: 40 min wall-clock, 60 tool calls. At budget STOP and report done / not done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under 300 words.
Copy from: none - domain fix inside this repo's own `backend/ofo/reconciliation/` (W-085 code); algochanakya has no
expiry-settlement reconciliation.

## Class (defect-fix contract)
- RCA: reconciliation decides awaiting from the in-memory awaiting/settled sets that `settle_expired_legs` fills, so
  any run between the expiry close and settlement sees the expired leg as an ordinary missing position.
- Class: every platform leg whose contract's expiry date has passed (the expiry close is over) and that is not yet in the
  settled set, for every strategy kind (calendar, single leg, spread), regardless of whether settlement has run yet.
  Population before the fix: all such legs block; after: none block, all show the awaiting note.
- Proof: the failing test above plus a test per kind (single expired leg, spread with both legs expired, calendar with
  near leg expired); and the existing 4,000-case equivalence/fuzz style check: blocked ids for NON-expired contracts are
  unchanged (`tests/reconciliation/test_compare_equivalence.py` must pass unloosened).
- Detection: the new tests are the detection; say so, or name what they miss.

## Spec basis
- REQ-060: "reconciliation expects it gone and does not raise AC-2's"
- ADR-083: "Treating it as a mismatch would block every calendar strategy once per near expiry."

## Where
- Your own worktree on a new branch `fix/279-settle-order` from `origin/main` (after PR #284, which added
  `retired_standalones` in `compare.py` - read it first and keep its behaviour).
- Read: `backend/ofo/reconciliation/compare.py`, `backend/ofo/reconciliation/` settlement code from W-085,
  `tests/reconciliation/test_expiry_settlement.py`, issue #279 (`gh issue view 279`).
- Expired must come from the same date source the existing W-085 code uses (passed in, never `date.today()` inside
  the domain - `tests/test_no_wall_clock_asserts.py` guards this). If W-085 has no today input on the compare path,
  add it as a parameter, not a clock read.

## Rules (reviewer checklist, run-discipline B4)
- Fail closed: an expired leg where Zerodha STILL shows a quantity that differs keeps today's
  `RECONCILIATION_MISMATCH_222` behaviour (blocks as before). Only expired + absent at Zerodha + not yet settled
  becomes awaiting.
- A leg whose expiry is TODAY but the close has not passed is NOT expired (no awaiting before the close). If the code
  has no notion of the close time, treat expiry date < the reconcile date as expired and same-day as live, and say so
  in the report.
- Mutation tests first: write the tests, show them red on `origin/main`, then fix. After the fix, mutate the expired
  check (e.g. `<` to `<=`) and show a test goes red.
- No new error codes unless needed; if one is, take the next free `_RM` number after 223 and run
  `tests/errors/test_template_codes_unique.py` if it exists on main.
- Targeted tests only: `python -m pytest -q -p no:cacheprovider tests/reconciliation tests/errors
  tests/test_no_wall_clock_asserts.py`; the orchestrator runs the full suite. Logs to a file, tail only.
- Commit and push `fix/279-settle-order`; do not open the PR; never write `evidence/`, `work/` or the spec.
