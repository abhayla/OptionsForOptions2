# Handover: GC-ICFIX phase 1, 13 Nov 2026

Contract: `docs/process/goal-contract-GC-ICFIX-2026-11-13.md`. Branch `fix/gc-icfix` in `D:\Abhay\Ventures\OptionsForOptions2-gc-icfix`.
NOTHING IS PUSHED. Tracker: https://claude.ai/artifact/LcMTSr5xx8LvAYVniotkxK (rows u001..u611).
Status in one line: the repairs are built and checked on the branch; the full local check is green; the SCREEN PROOFS are not done, so phase 1 is PARTIAL.

## LATEST STATE (14 Nov 2026, 08:49 IST) - read this first
- DONE since 05:41: screen proofs u104, u006, u116, u130, u165 done on the test-data copy; a saved Target equal to the default applies on the last day (390c5034); a refused rule check shows its sentence, never the raw error object (bc583b5f); owner question Q9 recorded (4c787395).
- PENDING: sixth full local check started 08:5x on 27fc677e (log `D:\Abhay\scratch\gc-icfix-backup\prepush-run6-27fc677e.log`), result not known when this was written; a new backup bundle after it; the live app copy (API 8765, vite 5173) still serves an older head and needs a restart from the branch.
- BLOCKED on a market day and the owner's Kite login: u145 (a stop firing on screen) and u154 (the 8-order Confirm box): Monday 16 Nov if the exchange is open (check the calendar first).
- PARKED: "Max profit / Max loss after the charges really paid" = issue #707, branch `build/gc-icfix-paisa` head 15245e87. It was merged as d9c62ee2 and REVERTED as 27fc677e (08:47), so this branch no longer has it. Four rounds; a database test failed (`'962' == '962.00'`). Left: format money text once at the reply boundary, a database-path test with a stored futures row, re-run the four database files one at a time. Finding: `guard-removal-drops-the-value-shape-it-also-gave`.
- Consequence meanwhile: Max profit / Max loss after charges still estimate a full round trip; a closed practice trade's Max figures do not equal its Total; the review can differ from the page by a paisa; the Completed row lacks the word "Charges".
- OWNER: questions Q4, Q7, Q8, Q9 open in `docs/process/owner-questions-2026-11-13.md`; builder folders now 17 (the 12 named below plus `-left`, `-alert`, `-paisa`, `-eq`, `-raw`); nothing pushed; the push happens only on the owner's words "push GC-ICFIX".
- CORRECTION: an earlier note called "a futures leg priced as an option in the review" unconfirmed; it IS real at `adjustment_readers.py` ~171 (past fills), repaired only on the parked branch.
- Test-data copy: STOPPED (07:2x). A user-level usage monitor was built this session outside the repo (plan: the owner's Claude plans folder, `usage-monitor-plan-2026-11-14.md`); not part of this contract.

## LATEST STATE (14 Nov 2026, 05:41 IST) - read this first; it supersedes the 02:50 block below where they differ
- Full local pre-merge check, fifth run: `TOTAL PASS 3302.1s` on head `b28de7f92d0bc59791cd14c038710006eb25928d`
  (the PC was low on memory, 1.7 GB free, so it took 55 minutes; a normal run is about 34).
- Built and merged AFTER the 02:50 block: the four screen leftovers of issues 3 and 4 (`aa7bb84c`: Profit left
  breakdown by ADR-306, the charge-rates sentence under Max profit / Max loss, after-charges labels, "P&L (before
  charges)" table header, a dash in the TOTAL row's percent cell); the target alert sentence of ADR-294 (2)
  (`935ac140`, 2 rounds, Opus check: "Profit before charges +Rs 61.75 reached your target of 1%; after charges
  -Rs 218.85"; a real (broker) trade gets a true reason because charges paid on broker orders are not read: Q8; the
  optional figure cannot stop the rule check). So NOTHING buildable is left in phase 1.
- Still OPEN in phase 1, both waiting on the owner: (1) the six screen proofs u104, u116, u130, u145, u154, u165 and
  the screenshot half of u006; (2) removal of the builder worktrees (Q7): now 14 folders: the 12 named below plus
  `OptionsForOptions2-gc-icfix-left` and `OptionsForOptions2-gc-icfix-alert`.
- Screen proofs, exact diagnosis (measured 03:10): the PC was NOT locked (`OpenInputDesktop` succeeds; a LogonUI process
  exists anyway); the Chrome window was MINIMISED; after restoring it (`ShowWindow`, 9) the first screenshot works
  (1536x695) and every screenshot after a scroll or click times out. Not tested: window not in the foreground or
  covered, display asleep. The real page area is 1536x695, NOT the 1536x639 the contract assumes: record the measured
  size in u154. Do the proofs with the owner at the laptop, screen on, Chrome in front.
- Known small gaps, none blocking: the rule-set test screens' use of the new alert sentence is pinned by a source-text
  test only; the guard's warning log names the instrument, not the trade; "1%" in the alert against "1 %" elsewhere
  (u501); the list-total function reads each trade's figures by name with no fallback; a slow rule check is re-asked
  0-5 s after each answer with no back-off (issue 26); `tests_app/test_background_worker.py` took 20 minutes under
  load; a builder raised the whole-suite run limit for one command (`FULL_SUITE_BUDGET=9`) because the brief told it
  to run the whole suite.

## STATE AT 02:50 IST (earlier block; still right except where the block above says otherwise)
- Full local pre-merge check: `TOTAL PASS 1980.6s` on head `be8f438427ba5c02f75ed03cd413d8dea69d8c29` (89 commits ahead of main). It took four runs:
  run 1 stopped at the interface gate (2 call mismatches), run 2 at the scans gate (4 structure guards), run 3 at the
  app tests (3 stale tests), run 4 passed. A full run is about 34 minutes on this PC. It skips the 898 tests that need the
  database: those run in CI at the single push, and builders ran only the database files near their changes.
- Backup: `D:\Abhay\scratch\gc-icfix-backup\gc-icfix-p0-be8f4384.bundle` (270,535 bytes, `git bundle verify`: okay).
- Not pushed: the branch has no upstream; `gh pr list --head fix/gc-icfix` is empty; no branch of that name on origin.
- Merged AFTER the sections below were written: the Opus re-check passed (issues 3 and 4: issue 4 rated REPAIRED; the
  adjustment-route crash fix: PASS) and `build/gc-icfix-avg` is merged; Profit left / Loss left follow ADR-306.
- The live dev copy runs from the branch folder but from head cb7e2500: it predates the last merges (one read for the
  three totals, the adjustment crash fix). RESTART it from the branch before any screen proof. The test-data copy is
  stopped.
- Phase 1 rows still OPEN: u104, u116, u130, u145, u154, u165 (screen proofs: blocked, see BLOCKED), u129 (Opus money
  check: its last four screen leftovers are not built), u006 (core proof: mechanism proven by a background alert record,
  screenshot missing).
- Next session, in this order: (1) owner wakes the laptop screen and brings Chrome to the front; (2) restart the live
  copy and start the test-data copy from the branch; (3) the six screen proofs; (4) the four screen leftovers of
  issues 3 and 4 plus the Rs amount and after-charges figure in the target alert (ADR-294 (2)); (5) a full local check
  and a new backup; then phase 2 (P1).
- The 12 builder worktrees are NOT removed (`OptionsForOptions2-gc-icfix-u102`, `-u111`, `-u122`, `-u123f`, `-u124`,
  `-u126`, `-u127`, `-u129r`, `-u130f`, `-u151`, `-u161`, `-avg`). All 12 are clean and every one's head is contained in
  `fix/gc-icfix` (checked), but the removal tool `wt-rm.ps1` refuses work that is not on origin: exit 3 "not in main,
  unpushed", and `-Discard` needs a sha on origin/main (exit 7). With one push at the very end, the tool cannot remove
  them before that push. They were not removed by any other means. Owner question Q7. After the push:
  `wt-rm.ps1 -Discard -MergedSha <merge sha>` per folder (launcher kept: `wtclean_run.ps1` in the session scratch folder).
  Main checkout unchanged by this session: 4282 tracked files, 206 entries in `frontend\node_modules`.
- Before launching the full check: run its gates directly (interface gate, both `repo_scan` suites, the whole
  `app_tests` step, the whole frontend suite). `tools/ci_local.py` runs none of them.

## DONE (built, independently checked, merged on the branch)
- Setup u001-u005.
- Issue 1: the plan Target is acted on; any saved Target acts; an empty Target per ADR-305.
- Issue 2: plan card and plan box show could-not-load with Retry; limits are read from the rule check; re-read on refresh with an as-of time.
- Issue 5: the stop warning follows the live check (rupees, percent, time); an already-true condition shows a grey line with the adjustment number.
- Issue 6: the dialog frame (buttons pinned, body scrolls).
- Issue 7: Customise edits the trade's own rules.
- Issues 3 and 4: the after-charges figure comes from one engine function on every total; booked / unbooked split; profit left by ADR-306; breakdown one tap away; one read feeds the three totals.
- Decision rows ADR-294 to ADR-306:
  - 294 profit target is before charges, said out loud; 295 no plan is allowed, and it is stated; 296 the stop is quiet after an adjustment; 297 adjustment limit reached; 298 practice equals real; 299 Draft, Running, Completed; 300 a condor outside the entry guide is shown with a warning;
  - 301 profit left and loss left are after all charges; 302 profit left has no cap; 303 where charges go between booked and unbooked; 304 the plan Target acts, limits on screen are the rule check's own; 305 the plan box is what the app does; 306 profit left and loss left add up.
- Findings written today: 14 new files plus 3 extended, in `knowledge/findings/` (index regenerated).

## PENDING in phase 1
- The Opus re-check of issues 3 and 4 and of the adjustment-route crash fix (branch `build/gc-icfix-avg`, not merged).
- Small screen leftovers of issues 3 and 4: P&L table rows unlabelled; the charge-rates sentence under Max profit / Max loss not shown; the totals strip's paid row; the Profit left breakdown not reworked to ADR-306.
- The after-charges figure and the rupee amount in the target alert sentence (ADR-294 (2)).
- EVERY screen proof (u104, u116, u130, u145, u154, u165): none done.
- The P0 close: full local check u172, backup u173, findings u175 (done by this task, uncommitted), handover u176 (this note).

## BLOCKED
- Screen proofs: Chrome screenshots time out after the first frame although the PC is not locked. The owner must wake the screen and bring the Chrome window to the front.

## PARKED / owner questions
- `docs/process/owner-questions-2026-11-13.md`: Q4 open (the recover line shows on every fresh trade); Q1-Q3, Q5, Q6 answered.

## Running state at hand-over
- The LIVE dev copy runs from the branch folder (API 8765, vite 5173, Redis 6380, tunnel 5432).
- The test-data copy is STOPPED. Start it for screen proofs with the launcher `scn_stack_icfix.py` in the session's scratch folder; PIDs are in `D:\Abhay\scratch\gc-icfix-backup\started-pids.txt`.
- Backup bundle so far: `gc-icfix-setup-f2c69d8e.bundle` only; a new one is due at the close.

## Worktrees to remove at the close
Remove with `wt-rm.ps1` (never a plain delete), counting the main checkout's tracked files before and after: `OptionsForOptions2-gc-icfix-u102`, `-u111`, `-u122`, `-u123f`, `-u124`, `-u126`, `-u127`, `-u129r`, `-u130f`, `-u151`, `-u161`, `-avg`, plus the agent runtime's own folders under the main checkout's agent-worktrees directory created on 13 Nov. The integration folder `OptionsForOptions2-gc-icfix` is KEPT.

## NEXT
Later runs use `/goal D:\Abhay\Ventures\OptionsForOptions2-gc-icfix\docs\process\goal-contract-GC-ICFIX-2026-11-13.md`. First finish the phase 1 PENDING list, then phase 2 (P1). The single push happens only when the owner writes "push GC-ICFIX".

## LESSONS (proposed, not applied)
Each is a registry finding in `knowledge/findings/` (the product ones are listed there too).
- A "green" fast-check total skipped the changed code's own test (16 passed, the Target test did not run, a changed JSON file was not a test target). Proposed: the fast check lists the tests it selected and fails if a changed file selects none.
- Parallel helpers plus two app copies exhausted the shared database role's connections: three verdicts unusable (random 8-13 failures). Proposed: one database-test slot enforced by a lock file. (Extended finding `db-role-connection-limit-below-pool-size`.)
- Builders wrote tests after the code when the brief only said "failing test first". Fixed in practice by demanding two commits in order; nothing checks it yet.
- A step budget in a brief is not a stop: builders used 139, 113, 98 and 89 calls against limits of 65-80. Proposed: a hard turn limit on the helper type. (Extended `builder-budget-is-prose`.)
- "No screenshot" needs a known-good comparison: Chrome screenshots time out after the first frame while page text still reads.
- The answer guard counts only decision rows written by the main session, so it fires when a helper wrote them. Proposed: accept a decision row written by a helper.
- Two helpers given one scratch folder with no file names overwrote each other's setup script. Proposed: one file name (or folder) per helper in the brief.
- Money lesson: a money question to the owner carries a worked example that sums the figures (ADR-301 subtracted charges twice; ADR-306 repaired it).
