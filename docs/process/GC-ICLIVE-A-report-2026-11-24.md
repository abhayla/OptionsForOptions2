# GC-ICLIVE Part A report: the seven critical issues (24 Nov 2026)

Contract: `docs/process/goal-contract-GC-ICLIVE-A-2026-11-24.md`. Branch `fix/ic-live-test-1123`, draft pull request
abhayla/OptionsForOptions2#722 (still a draft, not merged). Run in a cloud session; no screen was opened, so every issue
below ends at **Fixed, not tested**; the screen check owed is in the ledger
(`docs/process/ic-live-test-2026-11-23-status.md`). Reviews: `docs/process/ic-live-test-2026-11-23-reviews.md` and the
`ic-live-test-2026-11-24-A*-review*.md` files.

## Per issue

**D-01 (a crossed stop level saved).** Already fixed on 23 Nov. A4 checked the three gate commits: behaviour unchanged,
and the shown line matches ADR-317 character for character. Proof: `test_paper_triggers_routes.py` 61 passed; Part A DB
pass 287 passed. Not tested: the red line on screen with live prices.

**D-02 (sells recorded before their hedge).** Already fixed on 23 Nov (buys first, REQ-159 AC-6). Added: the stop-out
alert now lists legs in the recorded order (it used the send order); the `buys_first` docstring now says a paper ENTRY
is recorded as sent. The red api test `test_ic_paper_loop_core.py:188` had the OLD expectation (send order); the code
is right by REQ-159 AC-6, so the test was corrected (38debbf). Proof: tests first red 1 failed, then 25 passed; DB pass
287 passed. Not tested: the Orderbook order on screen.

**D-03 (armed exits lost after an adjustment).** Already fixed on 23 Nov. Added: the confirm list says "Could not check
your armed exits." when it cannot read them (was: nothing), pinned `pending owner read`; a DB test that another user's
strategy is refused (404). Proof: vitest 109 passed over the eight files mounting the dialog; DB pass 287 passed.

**D-04 (adjustment count and rules from the wrong shape).** A4 found the screen offered baskets the server refused when
the entry shape could not be classified (the offer had no fallback). Fixed in round 2 (the offer reads the server's
`entry_type`); round 2's review found four more callers classifying with the live index while the server did not;
round 3 removed the spot from `entry_type`, so all eight callers classify one way. The red api test
`test_adjustment_history_why.py:141` had the OLD expectation: its third basket added a leg at the plan maximum, which
ADR-318 point 5 refuses; the code is right, the test now reduces (0802084). Proof: round 3 tests red 5 failed, then
147 passed over the D-04 files; DB pass 287 passed. Not tested: "2 of 2" and "3 of 2" on screen.

**D-05 (a stop save silent or lost).** A4 passed ef733f08 (no CRITICAL or MAJOR). A6: the red "Not saved" line now
clears only on a refresh that started after the failure (round 1 cleared it on any later refresh, a race the review
found); beside "Saved" only "Enter at least one level" hides, never the price reason. The read order uses a per-read
token, not a counter (the money scan flags arithmetic in screen code). Proof: tests first red 2 failed, then 46 passed.

**D-59 (stops after a part settlement).** No code defect (23 Nov). Proof: DB pass 287 passed.

**D-60 (a duplicate leg added silently).** A4 found two MAJOR: Drafts Mode merged a kept duplicate into one order, and
the strike stepper, Shift, Width and Hedge had no question. Built in A5 and three more rounds: every move asks through
one door (`legDoor.js`), one live question per move (a newer move, a net-zero step, any legs replacement or leaving the
page closes it), moved legs are checked against each other, Increase raises base lots with lots (a later multiplier no
longer drops it), Drafts Mode sends a kept duplicate as separate orders so the server refuses it with its sentence.
Proof: vitest whole suite 3x 2396 passed; DB pass 287 passed. Not tested: the question box on screen.

## Rounds beyond the two-round rule (decision)

D-04 and D-60 each kept one MAJOR after two rounds. The two-round park rule clashed with the Definition of Done
("nothing else open" on the seven). By the owner's direction of 24 Nov (take the call on regular things), D-04 got one
more round and D-60 two more, each reviewed by a fresh helper; both classes are now covered.

## Deferred (outside the issues' classes; next steps)

1. Builder: a legs replacement while a leg-edit request is still in flight does not cancel that request, so its reply
   lands on the new legs. Same behaviour before Part A. Next: `guard.cancel('leg-edit')` in `setLegs`, with a test.
2. Tracking: `_playbook_type` (`routes/tracking.py`) decides whether the generic 0.5% detection is hidden from the
   current shape at the live index, not the entry shape. Next: read it through `entry_type`.
3. Plan route: an unused `judge_spot` read is kept only because `tests/test_spot_clock_scan.py` requires it. Owner
   decision: drop the scan's plan-route entry, then the read.
4. REQ-109 AC-5 reading: exiting a priced leg while another leg has no price is accepted (the server checks the named
   legs). Owner to confirm the per-leg reading.
5. "Not saved:" reasons other than the crossed level now start with a capital letter (8b3b21d7); allowed by ADR-317
   point 5, not read by the owner.
6. The flaky option-chain test (A3): the cause is inferred (a reconnect timer left by an unmounted page), not
   reproduced; fixed by unmounting every page after each test; 3 whole-suite runs green before and after.

## Environment findings (also in docs/process/GC-ICLIVE-cloud-setup.md)

The sandbox proxy breaks the egress-gate tests (4 failed with it, 127 passed without); CI installs mypy unpinned (a
deliberate test call needed a type-ignore); `prepush.py` must run without `OFO_REQUIRE_DB_TESTS` set.

## Gates (section 6b)

| Gate | Result line |
|---|---|
| Regenerate generated files | only the coverage-register commit line changed (b0ec7a8) |
| `scripts/reply_inventory.py --check` | rc=0 |
| OpenAPI drift test | 1 passed |
| `coverage.py . --check` | OK (the GitHub issue comparison could not run here: HTTP 401) |
| vitest whole suite, 3 runs | 183 files, 2396 passed, each run |
| DB files this part touched, one run | 287 passed |
| `tools/ci_local.py` | TOTAL: 16 passed, 0 failed, 5 skipped (on c192f19) |
| `scripts/orchestrator/prepush.py` | see the pull request comment for the final head |

## Summary

- DONE: D-01, D-02, D-03, D-04, D-05, D-59, D-60 at Fixed, not tested; ledger of 71 rows; four A4 reviews and nine
  later reviews; the database route; the front-end test isolation.
- PENDING: the screen checks owed (ledger), on the owner's PC in market hours.
- BLOCKED: none.
- PARKED: none (see Deferred).
- NEXT: Part B, `docs/process/goal-contract-GC-ICLIVE-B-2026-11-24.md`, launched by the orchestrating session.
