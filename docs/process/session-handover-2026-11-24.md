# Handover: critical group of the 23 Nov live iron condor test (written 2026-11-24 00:25 IST)

Supersedes the PENDING list in HANDOVER.md for the seven class-1 items. Standing direction step 4, item 10.
Tracker (status source): a private tracker artifact (collection `issues`); the issue text is in docs/process/ic-live-test-2026-11-23-issues.md.
Owner rule (23 Nov 17:05): fixed + checked on screen = "Closed"; fixed but the screen check needs live market = "Fixed, not tested".

## DONE (all local, NOT pushed, no PR, no deploy)
Branch `fix/ic-live-test-1123`, worktree `OptionsForOptions2-ic-live-fixes` (sibling of the main checkout), head e1b210d8, 46 commits over
main d387d4cd, tree clean. `fix/ic-live-test-1123-order` is merged into it (fcc7a7fe).
Whole-branch check 00:17: DB files touched 189 of 189 ([local log]); D-60 paper duplicate 2 of 2 ([local log]);
`python tools/ci_local.py` 16 passed, 0 failed, 5 skipped ([local log]); front end 2360 of 2361: one failure,
tests/option-chain.test.js "row 33: a strike range change ..." (expected strikes_each_side 5, got 15), passes when run alone
(27 of 27). NOT diagnosed: timing under load or a real order dependence. Check it first on main.

| Id | Status | Screen check still owed (earliest 25 Nov, live market) |
|---|---|---|
| D-05 | Fixed, not tested | Save lines ARE screen-proven (Saved / Already set / mixed / Not saved / server back). Owed: after a failed refresh, figures go to a dash and Exit is blocked (market closed looked the same) |
| D-59 | Fixed, not tested | Not a defect (stops were never stored). Owed: stops survive a part settlement at 15:45 on a two-expiry paper trade |
| D-01 | Fixed, not tested | Type "Above" a level below the index: red line "Not saved: the live price is already at or beyond this level, ..." and no row; then a safe level saves |
| D-03 | Fixed, not tested | Set an index exit, adjust the trade: the row is marked "set before the last adjustment" with the new short strike; Keep this level -> "Kept:"; the confirm list names the armed exit |
| D-02 | Fixed, not tested | Roll one side of a paper condor: Orderbook lists the buy-back of the short before the sale of its hedge |
| D-04 | Fixed, not tested | A trade at 2 of 2: rolls withheld "plan maximum of 2 reached"; Reduce / Close read "3 of 2; this would be adjustment 3 ..." and CAN be placed; Exit all no count; trade 164 reads "1 of 2" |
| D-60 | Fixed, not tested | Round 1 screen-tested 9 of 9 (question, Cancel, Increase, Keep separate + warning, opposite action, edit form). Round 2 NOT screen-tested: new question box (Escape), Increase over the lots limit, Add to Paper refusing a kept duplicate |

## Owner decisions taken on 23 Nov (all written into the spec on the branch)
ADR-317: (1,2) crossed stop refused, wording approved; (3) duplicate stop not stored, "Already set"; (5,6) "Not saved" line,
"Saving..."; (7) index exits stay armed through an adjustment, marked, never moved.
ADR-318: (1-3) at the plan maximum only risk-cutting routes with the true count; (4) the whole rule set comes from the shape at entry.
Lead's calls awaiting the owner's read: ADR-318 (5) the server accepts reducing baskets at the limit; ADR-319 (3) a kept
duplicate blocks Add to Paper; D-02: a paper ENTRY is recorded as sent (not hedge first).
Sentences marked "pending owner read" in tests/errors/template_pins.json: leg-stop crossed sentence; put-side / no-short /
confirm-list / "could not be checked" lines (D-03); "These orders open or add to a leg, and there is no room left: plan
maximum of N reached."; "Not an adjustment: closes every open leg".

## PARKED / follow-ups (not built; file as issues when the branch is pushed)
1. D-60: strike stepper onto a held contract shows the warning but does not ask (next step: call `admitLegs` in `sendEdit`,
   StrategyBuilderPage.vue ~750). Option Chain "Add Selected" replaces the builder's legs, so REQ-030 AC-12 does not exist
   there: product decision.
2. Spec conflict: the real-order gate treats BUY + SELL of one contract as a duplicate (safety.py:191,399) while REQ-030
   AC-11 keeps them as two legs. Real orders are frozen.
3. D-02: hedge-first recording of a paper ENTRY needs leg order to stop depending on order sequence (`contract_legs`).
4. D-03 minor: the confirm list shows nothing when it cannot read the armed exits (should say "could not check").
5. D-02 minor: stop-out alert lists legs by contract, not in recorded order.
6. D-05 small: the red "Not saved" line stays after the server returns; "Enter at least one level" beside "Saved".
7. D-04: Exit all / Take profit now share "fewest adjustments" with No change below the limit (visible change);
   iron condor "trending day" rule may fire more on a reduced one-sided trade (not measured).
8. Builder banner on the TEST copy from first load: "An unexpected server error stopped this request (reference
   ERR-E213B9CA)". Cause unknown; check whether the live app shows it.
9. The 12:27 stop save on trade 164 cannot be proven: the live API prints to a window, no log file for the day. Worth a
   follow-up: write the API log to a file.
10. Not independently reviewed (tested only): D-05 last fix ef733f08; D-04 server change 2915daf6 and fallback 6972d3d7;
    D-60 round 2 (1a81d59e, e1b210d8).

## BLOCKED on the owner
- The push of `fix/ic-live-test-1123` (one push + one PR at the end, on the owner's word). PR body needs the
  "## Spec-deviation / Class: none" block.
- The reads listed above.
- Priority order of the other 64 tracker rows (group 2 = class 2, money numbers on a different basis).

## NEXT (fresh session, 25 Nov, market hours)
1. Start a test copy of the branch WITH live prices only after deciding how to avoid two stop-watchers on one database
   (the 23 Nov test copy ran with LIVE_MARKET unset: no prices). Option: run the live stack itself from the fix worktree
   for the test window, with the owner told first.
2. Walk the "screen check still owed" column, one issue at a time; set "Closed" per row that passes.
3. Then ask the owner for the push.

## State left on this PC
- Live app (main checkout, API 8765, vite 5173): untouched all session.
- Test copy: vite on 5174 still running from the fix worktree; its API (8766) is STOPPED. Start/stop commands are in the local records folder (not in the repo). Database role ofo_app allows 10 connections: stop the test API before any db_run_fresh.
- Paper book: trade 164 open (1 Dec put spread), 0 armed stops (all test stops cancelled; ids 32-41 cancelled).
- Worktrees: OptionsForOptions2-ic-live-order is merged into the fix branch; remove with wt-rm.ps1 (branch is unpushed, so
  it may need the owner's OK).
- Reviews: docs/process/ic-live-test-2026-11-23-reviews.md; logs stay on the local machine.
