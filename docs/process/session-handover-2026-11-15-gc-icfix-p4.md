2026-11-15 17:22 IST (from the system clock). GC-ICFIX handover after the screen proofs, the fixes they led to, and two reviews. Branch fix/gc-icfix, head 874aacd5 plus this one records commit. Nothing is pushed.

## Status of the check (read first)
- Fast gates on 874aacd5: `python tools/ci_local.py` TOTAL 16 passed, 0 failed, 5 skipped (log `D:\Abhay\scratch\gc-icfix-run\fix-ci_local.log`); `python -m pytest tests -m repo_scan` 1469 passed (log `fix-repo_scan.log`). Both were run after the last code commit. This records commit adds only docs, so a gate run on it is in part E of the task, not claimed here.
- The FULL local check (the one that ends in a pass marker) has NOT been run on the final head. The last full pass was on 870a3170 (run 14). The marker no longer matches. The next session (or the manager right after this commit) runs it before any push.
- The single push happens only on the owner's words "push GC-ICFIX".

## DONE (merged on the branch since 870a3170; sha = the fix, test-first commit before it)
- A held profit-target sentence uses the record's own figures and the user's stored target, not the live loss and not the gate's rung (5eac813a, 13649f51).
- Adjustments used leaves out the closing Exit all; the history row carries `is_exit`; the screen labels it "Exit" (93df7dfa, 180aac00). Before: "3 of 2" on a finished trade.
- Yes/no rule alerts and clock-time (T-10b) alerts name their rule (ed0b836d, db5f4445, 6004d45f).
- "[object Object]" on not-checked rules is gone (2b1788a6).
- The positions page opens on Paper when the user is not connected and has an open paper strategy (38abea1e).
- The breakeven rule (T-02) line names its figure (7e45461e). Wording is PENDING the owner's read (see below).
- A stored alert keeps the value, threshold and limit of the sample that confirmed it; it no longer falls back to the latest check (871d0baa). A held ladder row keeps its rung (15967796). A held target flag says the user's stored limit (13649f51). The worker limit test builds its event with the sample's limit (fdd2c508).
- Migration 0053 closes drafts whose paper book is flat (93d35106), deleted finished rows included (b33b3a52). It would close 39 rows on the dev database (27 not deleted, 12 deleted). It is NOT applied to any database.
- A detection test: the real settle job leaves a fully settled strategy "closed" (a30dfc96).
- A stale A-26 name test now reads the name from the catalogue (322961ef).
- Three gate failures fixed: a test in the wrong folder (ce584493), a test fake without the limit property (f8bd1957), a stale docs/api/openapi.json (874aacd5).
- Decision rows: ADR-314, ADR-315, ADR-316. Findings: eight new files in `knowledge/findings/`. Issues: #710 to #717, plus a comment on #709.

## Screen proofs (test-data copy PATH-61, owner's visible Chrome, read-only)
Walk-through run 1 and 2 (`screen-proofs-1.md`):
| Item | Verdict then |
|---|---|
| u511 "/" opens My Strategies | PASS |
| i20 held strategy refuses delete | PASS (delete + Undo itself not reachable: no deleting of trades) |
| i25 status words | Completed list PASS (11 rows "Completed"); My Strategies and Live lists say only "Running"; paper cards show no status word; expired trades still sit as live cards (AMBIGUOUS) |
| i8 alerts name trade and rule | PARTIAL: strategy shown; about 12 alerts said only "Your rule was triggered" (fixed since, not yet seen) |
| i19 reminder sentences | PASS |
| i24 paused totals, leg named, Booked always shown, expired wording | PASS |
| i18 Paper tab first | FAIL then (Positions selected); fixed in 38abea1e; re-proof PASS |
| i21 adjustment history on Completed | PASS (two re-checks); first bounce not reproduced |
| i12 fired rules on the trade page | PASS; "[object Object]" x3 FAIL then, fixed in 2b1788a6 |
| i22 "Time exit (on expiry day)" | PASS on the plan block |
| i14 Compare "Showing 5 of 5" | PASS (N below M not reachable) |
| i15 rule set refill note | PASS |
| u507 Greeks at target with basis | PASS |
| u510 expiry text | PASS |
| pages of 25 (opportunities) | PASS ("Showing 1-25 of 176 rows") |
| u502/u505/u513 Save state | PARTIAL: disabled with no legs, enabled with unsaved legs, captured line keeps its space; "Save off when unchanged" not reached |
| u504/u506 menus | PASS (Live, Adjustments, Create not opened) |
| i10 exit warning | PARTIAL: dialog opens; the cover-lost warning needs a partial exit of a protected short, not reached |
| i11 Take profit | wording PASS; "offered" not reachable (needs a trade in profit) |
| guided condor warning | PARTIAL: "Could not check against the entry guide." (needs live Greeks) |
| i17, i18 Retry, D4, i23, toasts, i9 | NOT REACHABLE |

Close-out run 1 (`closeout-proofs-1.md`): u601 PASS (breakeven alert record 329 written at frame 1; max id 328 to 329). u603 PASS (same event). u604 PASS (frame 6, T-09 records 332 and 336; 8 new records). u606: stale half PASS; the premium-vs-cost rule (T-19) never fired. u607: the clock rule fires at the candle close per ADR-237; the fixture jumps 14:31 -> 15:25, so "late" was a fixture artefact; the alert had no rule name, fixed today, not yet seen on screen. u605 NOT REACHABLE (no margin figure without a broker login). u608 NOT REACHABLE (the fixture only moves in the trade's favour). u602 not needed.

Re-proof on head 93d35106 (`reproof-1.md`): PASS for the Paper tab, the Exit row and "2 of 2", and "[object Object]" gone. NOT REACHABLE for four alert fixes (yes/no name, T-10b name, T-02 line, stored limit): the morning run's alert records are stored and each rule writes one alert per trade per day, so a replay needs those test rows cleared. The fixture sits at frame 2.

## Reviews
- Sonnet, Tier B, 19 commits (870a3170..871d0baa): REVISE, three major findings (held flag used the rung not the limit; stored limit still from the latest check; a held ladder row stored no rung = a regression). All fixed in 4fd50388..fdd2c508.
- Opus, Tier A: Part 2 (alert records) PASS. Part 1 (migration 0053) REVISE for tests only: one cancelling-legs case and one stop-ending case. Fixed in 70265156 and b33b3a52. Three mutations each turned the tests red (`mut-all.log`: EXIT 1 for the group-by-strategy, no-adopted and no-plans mutations).
- Unreviewed after Opus: only the removal of the deleted-row filter (b33b3a52 is itself the follow-up to the review) and the three gate fixes.

## Tests
- Run one database file at a time (the host serves other data). Results in the logs: adjustment_history 3 passed; adjustment_check 11 passed; condition_line_units 41 passed; target_alert_sentence 30 passed; test_strategy_closed_status 11 passed; test_paper_settlement 29 passed; the 0053 migration test file 3 passed (`m53-final2.log`); test_background_worker.py 23 passed in 1490 s (`run-file.log`).
- Not run, said plainly: the background database gate file ran 10 passed and 16 SKIPPED (`g-full.log`, no database attached for that run); I could not verify from the logs how many tests test_background_worker.py holds beyond the 23 that passed. Treat both as unverified until the full local check.
- The three browser-level test files stay unrun by the owner's rule (see PARKED 10).

## Data findings (dev database, read-only)
- The settle job ran on time on 29 Oct, 3, 5 and 9 Nov (from the run notes; not re-read by this session: unverified here).
- 26 not-deleted expired-unsettled strategies are all scenario ones (skipped by design); same source.
- Close-on-last-exit landed 9 Nov 17:46 (47ff1776, checked in git), after all four settle dates. No flat draft has a reducing order after that time (run notes; unverified here).
- The stored brokerage-per-order rate has a test leftover row of 25 from 1 Nov ("GC-SET step 2 proof") over the 20 read from the broker's page on 15 Oct. Finding `test-leftover-in-a-rates-table`.

## PENDING
- The full local check on the final head (see top).
- Owner answers (below).

## BLOCKED
- Live-day items u145, u154, u214, u609: need a market day and the owner's broker login. Check the exchange calendar first.
- Seeing the four alert fixes on screen: needs the morning's test alert records cleared (owner word).

## PARKED / DEFERRED (each has an issue)
1. Eight record fields still read the latest check (target figures, T-19 approach and cost, approaches, carry, beyond, label and unit, stage, adjustments) and a held T-19 flag shows the live cheapest approach: comment on #709.
2. The clock alert does not show its time (the time is not stored): comment on #709.
3. T-09 label "falls to Rs or below" has no amount, in 12 system playbooks (needs a migration like 0051); mixed Rs and the rupee sign: #710.
4. A raw instrument id is shown ("NSE_FO:45392 cannot be used"): #711.
5. "Rule not checked: No adjustment opportunity checked: ..." repeats once per rule (16 times) with a doubled label: #712.
6. Negative Max Profit on two cards: expected (closing charges assumed, owner Q9) but unverified on those two; wording idea "charges exceed the possible profit": #713.
7. Scenario fixture gaps (no frame just after a candle close, no double stop, no margin figure, no two-expiry trade, replay needs alert rows cleared): #714.
8. A nightly audit query "draft, flat, has a reducing order"; the list route loops once per closed row (38 after the repair, latency unmeasured); 0053's real-order exclusion is narrower than `_DELETABLE_SQL` (no effect today): #715.
9. Paper tab when broker state is "partial" and a real server error; the adjustments marker goes N, N+1, N around an exit: #716.
10. Not reachable on screen or not done: i17, i18 Retry, D4, i23, toasts, i9, guided condor warning (needs live Greeks); u404 clear-out of about 70 old practice trades NOT done (deleting data needs the owner's word); issue 26 speed measurement not done (depends on u404); three e2e files unrun by the owner's rule; live-day items u145, u154, u214, u609: #717.
Earlier parked and deferred lists are unchanged: #708 (roll logic), #709 (stored-data changes).

## Decisions taken without asking (owner rule of 14 Nov)
- T-10b names the rule now and shows the time later: the time is not stored, and the name needs no new data. ADR-316.
- T-02 wording: "profit or loss at expiry if the index stays at its current level {value} (rule: below {threshold})". The label alone read as a spot price. PENDING the owner's read; the template pin in `backend/ofo/errors/explanations.py` (adjust_condition_line_t02) guards the text.
- Migration 0053 includes deleted finished rows, so an Undo cannot bring back a "Running" trade (ADR-293). ADR-315.
- u605 and u608 are parked, not built: a fixture for them is its own piece of work (#714).
- A late time exit needs no code change: the rule fires at the candle close (ADR-237); the fixture skipped the candle.

## Waiting on the owner
(a) The words "push GC-ICFIX".
(b) Clear the morning's test alert records on scenario strategies 134, 148, 149, so four alert fixes can be seen on screen. Recommended: yes (test rows only, in the dev database).
(c) Put the brokerage-per-order rate back to 20. Recommended: yes. Business call: it is a money figure shown in every charges total.
(d) Apply migration 0053 to the dev database at the next upgrade, with the app stopped.
(e) u404: clear about 70 old practice trades. Deleting data needs your word.
(f) Read the new T-02 sentence (see above).

## Lessons (short)
- Run the repo-wide gates per batch, not at the end: three failures were found 28 commits after their cause.
- A "stop if quiet" limit must be longer than the job, or a long job looks like a hang.
- Removing a fallback needs the list of who relied on it (the held ladder row lost its rung that way).
- The `reviewer` helper type went silent twice.
- A fix for a rule on new rows needs its repair for existing rows (0049 had none; 0053 is the repair).

## NEXT
1. Run the full local check on the final head; repair on the branch if red.
2. Take the owner's answers (a) to (f). Then, on his word only, push.
3. Monday live items u145, u154, u214, u609: check the exchange calendar first; they need his broker login.
4. After the push, remove the builder work folders with the removal tool; start the next group.
