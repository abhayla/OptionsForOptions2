# Test day of 27 Nov 2026: sorting of the notes, observations and issues

Spec basis: none: sorting test-day notes for the owner; no product decision. Where a note is called "covered by a decision", the point is from ADR-330 (read in full today).

## D. Summary (read this first)

1. Usability notes: 36 written down. After merging notes that ask for the same fix: 26 rows (10 merges, 10 ids absorbed).
2. By size: Quick 11, Medium 13, Design 2.
3. By state: already fixed on a branch 8, fixed only in part 4, covered by an existing decision 1, open 13.
4. Observations: 26. On today's issue list 12, missing from the list 4, test set-up weakness 2, nothing to do 8.
5. Today's issue list (26 rows): 15 are fixed on a branch, 3 partly, 2 have a note passed to another lane, 3 have no fix in the five result files (rows 1, 6, 9), 1 waits for your wording (row 17), 2 need no code (rows 7, 18).
6. Duplicates in the list: row 26 is the same as row 13; row 6 is suspected to be row 1; row 22 is the second half of row 8.
7. Issues not on the list: 20 proposed new rows (section C). 5 are High or Critical.
8. Every fix is marked "fixed, not tested". Nothing is re-tested on your PC yet, and nothing is merged.
9. Read first, one: items that make a trader trust a stop that is not there (plan block shows the old stop; percent stop saved with no market; plan stop alerts not raised, three causes).
10. Read first, two and three: the open owner questions (section A end and section C end), and the two Critical rows with no fix in the files I read (row 1 morning empty builder, row 9 slow app with two users).

---

## A. Usability notes

Reading the table: a row with two ids means the notes were merged because one change fixes both. "Fixed, not tested" means the change sits on a branch and has not been re-run on your PC in market hours.

### Positions (Stops panel, tiles)

| Screen | What is awkward | Suggested change | Size | State |
|---|---|---|---|---|
| Positions, Stops panel (UX-02) | Each leg row has a direction word and a bare Stop price box with no label | Label the box and the direction | Quick | Open |
| Positions, leg-stop warning (UX-03 + UX-08 merged) | One long sentence carries the max-loss figures. Rs 16,62,316.50 is a theoretical worst case (NIFTY at zero) but the line does not say so | Short lines, figures on their own line; say "worst case with the sold option unprotected" | Quick | Open. Lane M fixed the leg names and the figures, not this wording |
| Positions, leg-stop warning (UX-07) | Date shown as 2028-12-01 style | Use the "1 Dec" style | Quick | Already fixed today on a branch: Lane M (maxloss-line); date fix passed on your PC in check T1-03 |
| Positions, trade changed elsewhere (UX-32) | Summary cards keep the old numbers with no "old" tag | Mark them stale | Medium | Open |

### Builder

| Screen | What is awkward | Suggested change | Size | State |
|---|---|---|---|---|
| Builder, legs (UX-15 + UX-19 merged) | For about 10 s each leg shows a typed price while the page says "Working out the outcome"; after adding legs the old three stay about 20 s with no "adding" message | One loading state per leg, shown at once | Medium | Open |
| Builder, Change expiry (UX-16 + UX-24 merged) | After picking an expiry, a message says your price for leg 1 was replaced with no reason; another message prints the strike where the price should be | State the reason; print the captured price; keep a typed price | Quick | Open |
| Builder opened from an alert (UX-21) | Staged exits leave the page saying "No legs yet" | Show the staged legs | Medium | Already fixed today on a branch: Lane W (item 11); fixed, not tested |
| Builder, Net Positions (UX-29) | Contract column is so narrow the name wraps onto 4 lines | Widen it | Quick | Already fixed today on a branch: Lane W (item 13); checked by class only, look at it by eye |
| Builder, Add to Paper (UX-30) | Needs two presses; Confirm can grey out while the dialog is open | One press; keep Confirm usable | Medium | Open |
| Builder of a closed trade (UX-11 + UX-23 merged) | Says "Add a leg to start a draft" and Plan watch looks like an error | Show the trade as closed; hide both | Quick | Fixed in part: Lane W (item 8) gives the "This trade is closed" sentence. Hiding Plan watch on a closed trade is not done. Covered by decision ADR-330 (14) for "Add orders" only |
| Builder, Add or Edit leg panel (UX-27) | "Pick from Option Chain" link did not navigate | Make it open the chain | Medium | Open. Re-check first: it may be a click problem of the test tool |

### Plan sheet and Plan watch

| Screen | What is awkward | Suggested change | Size | State |
|---|---|---|---|---|
| Plan sheet (UX-10) | For an existing trade it sits only on the builder page, far down | A Plan button on the Positions card | Design | Open. ADR-330 (9) and (13) say what a plan is and where Plan watch shows, not where the plan is opened from. Owner question 1 |
| Plan sheet (UX-17) | Past-date refusal names "time_exit", a code word | Name the visible box label | Quick | Already fixed today on a branch: Lane W (item 3) |
| Builder, Plan block (UX-34) | Keeps the old stop after a saved change until reload | Show the saved value at once | Medium | Open. Not on the issue list (section C) |

### Alerts

| Screen | What is awkward | Suggested change | Size | State |
|---|---|---|---|---|
| Alerts, Active (UX-12 + UX-33 merged) | "No alerts yet" shows for several seconds while 2 to 4 alert rows are still loading | Show "Loading..." until rows arrive | Quick | Already fixed today on a branch: Lane W (item 9) |
| Alerts (UX-28 + UX-36 merged) | Some rows show only the trade name as the reason | Show the rule in words | Medium | Open. ADR-330 (19) adds trade number and expiry to the title, not the rule sentence |
| Adjustment opportunity (UX-22) | "Acted on" is stamped when legs are staged, not when orders are placed | Stamp only when an order is placed | Medium | Already fixed today on a branch: Lane W (item 10). Needs your confirmation: it changes the wording of REQ-112 AC-2 |

### Option Chain

No usability notes today. (UX-27, the chain link in the leg panel, is listed under Builder.)

### My Strategies

| Screen | What is awkward | Suggested change | Size | State |
|---|---|---|---|---|
| My Strategies (UX-05 + UX-06 merged) | For about 5 s after Undo the list says "No saved strategy matches" though the row is coming back; "Show strategies" looks clickable but an early click does nothing | Show a loading line; grey the button until ready | Quick | Open. Lane R made the Undo last longer, not this |
| My Strategies, bulk delete (UX-14) | A running strategy could be ticked with a draft and the button read "Delete selected (2)" | Block running strategies from bulk delete | Design | Covered by an existing decision: ADR-330 (8) says a running paper strategy is deleted in bulk, with a line "N of them are running". The note disagrees with it. Owner question 2 |

### Home

| Screen | What is awkward | Suggested change | Size | State |
|---|---|---|---|---|
| Strategy tiles (UX-18) | Every open strategy says "Paper P&L paused, prices not live" | Show the notice once per screen | Medium | Open. ADR-330 (35) already adds a count line to the header total ("1 strategy left out"); the tile text is not decided. Owner question 3 |

### Exit dialog

| Screen | What is awkward | Suggested change | Size | State |
|---|---|---|---|---|
| Exit (UX-01 + UX-31 merged) | A greyed Exit (0) or a pale Confirm looks the same whether nothing is ticked or prices are paused | Say why, and say when it is safe to press | Quick | Fixed in part: Lane U added "Tick a leg to exit." and "Prices are not live; try again when they update". Re-test |
| Exit dialog (UX-04) | Confirm can be clicked while "Checking whether this exit leaves a sold option without protection..." still shows | Disable Confirm until the check ends | Quick | Already fixed today on a branch: Lane U (re-test step 5) |
| Exit dialog (UX-09) | The safety check outlasts the live quote window, so prices go stale | Keep prices refreshing and show their age | Medium | Fixed in part: Lane U's afternoon change (one price-reading door) removes the slow reads. Showing the age is not done |
| Exit dialog (UX-13 + UX-25 merged) | Exit (n) is enabled only a few seconds; the dialog closes by itself within 20 s when prices go not live, with no message | Keep it open and say why | Medium | Already fixed today on a branch: Lane U (dialog stays open, Confirm grey; also the builder's dialog) |
| Exit dialog (UX-20 + UX-35 merged) | Confirm freezes 10 to 20 s, then vanishes; or sits greyed about 4 s and the result line is out of view | Show "Placing exit...", then the result where the trader is looking | Medium | Fixed in part: Lane U shows "Exit placed on paper (order n)" and one final sentence per exit. The "Placing exit" state and the position of the line are not covered |

### Other

| Screen | What is awkward | Suggested change | Size | State |
|---|---|---|---|---|
| Top menu (UX-26) | An item did not open its wizard on click | Check the click and hover state | Medium | Open. Re-check first: may be a test-tool click |

### Recommended order: the top 10 to do first

Most "Already fixed" rows are not on this list; they need a re-test on your PC, not new work.

1. UX-34, Plan block shows the old stop after a save. A trader may believe a new stop is live when it is not.
2. UX-32, mark a trade "changed elsewhere" cards as old. He stops reading old figures as today's.
3. UX-30, Add to Paper in one press with Confirm staying usable. The most used action should not need two tries.
4. UX-03 + UX-08, leg-stop warning in short lines with "worst case" said. A scary Rs 16,62,316.50 line no longer makes him doubt the app.
5. UX-28 + UX-36, Alerts show the rule in words. He knows why an alert fired without opening the trade.
6. UX-20 + UX-35, "Placing exit..." then the result in view. He knows whether his exit went through.
7. UX-15 + UX-19, one loading state per leg in the builder. No more typed prices that look final but are not.
8. UX-16 + UX-24 (Quick), Change expiry messages say why and print the price. Cheap wording fix on a feature added today.
9. UX-05 + UX-06 (Quick), loading line after Undo and a greyed "Show strategies". No more "nothing matches" scare.
10. UX-02 (Quick), label the Stop price box and its direction. He cannot set a stop on the wrong side by misreading.

### Questions that need your decision

1. Plan button on the Positions card (UX-10): should a trader open the plan sheet from his Positions row? Recommendation: yes, the same sheet, no second copy. Spec basis: ADR-330 (9), (13).
2. Bulk delete of running strategies (UX-14): keep ADR-330 (8), where a running paper strategy can be deleted after a confirmation that says how many are running? Recommendation: keep it; the confirmation line already warns. Spec basis: ADR-330 (8).
3. "Paper P&L paused" notice (UX-18): once per screen instead of on each tile? Recommendation: yes, once, with the "N strategies left out" line of ADR-330 (35). Spec basis: ADR-330 (35).
4. "Acted on" (UX-22): confirm that it means "an order was placed", not "a basket was prepared", which changes REQ-112 AC-2. Recommendation: yes; a cancelled basket should not count as acted on. Spec basis: REQ-112 AC-2.
5. Worst-case line (UX-08): show the theoretical worst case with the label "worst case with the sold option unprotected"? Recommendation: yes; the figure is the decided one (ADR-330 (6)) and the label removes the doubt. Wording is for you to read (ADR-003).
6. Plan watch on a closed trade (UX-23): hide it? Recommendation: yes, nothing is left to watch (ADR-330 (11), (14)).

---

## B. Observations (26)

Test set-up weakness to fix in how a test day is run:
- Start the app after 08:30, or restart it at 08:35, so the instrument list is loaded (OBS-11).
- Keep the PC to server link alive and say so in the plan; it dropped from 10:07 to 10:13 (OBS-24).
- Two testers at once slow the shared API (OBS-12); stagger them or note who is on.
- Write down which pull (build) each check ran on; seven or more pulls were applied during the day, so one result can mix old and new code.
- Check Alerts in both Active and History; an answered or system-closed row is only in History (OBS-23).
- The phone-width drawer cannot be checked with the current tool (issue 7).

| Id | Observation (short) | Bucket | Detail |
|---|---|---|---|
| OBS-01 | Stop line date 2026-12-01 | Defect, on list | Row 4. Fix not done: Lane W handed it to Lane J |
| OBS-02 | Rename box: Esc does not close | Defect, on list | Row 5. Fixed on a branch: Lane W (item 7) |
| OBS-03 | Two identical legs: cause not named | Defect, on list | Row 2. Fixed on a branch: Lane W (item 4) |
| OBS-04 | Just-saved draft: "strategy was not found" in Plan watch | Defect, on list | Row 3. Not fixed: note to Lane J |
| OBS-05 | Red box once on two Live Strategies cards | Defect, on list | Row 6 (suspected same cause as row 1) |
| OBS-11 | Instrument list empty from 08:30 | Defect, on list | Row 1. Critical. No fix in the five result files |
| OBS-12 | "The server took too long to answer" with two testers | Defect, on list | Row 9. Critical. Test set-up also contributes (see above) |
| OBS-13 | Prices dropped about 30 s, every figure a dash | Defect, on list | Rows 11 and 21 |
| OBS-14 | "Page could not get an answer" in builder in live hours | Defect, on list | Rows 8 and 9 |
| OBS-15 | Fresh load: "Not available: the current level of this index" | Defect, missing from list | At 09:30 the market was open. Same family as rows 11 and 21; see C item 4 |
| OBS-16 | Leg quotes stale every 25 to 50 s, Exit greyed | Defect, on list | Row 11 (and 21). Fixed on a branch: Lane U |
| OBS-17 | 56 Zerodha rate-limit refusals on the index quote | Defect, on list | Row 11. Lane U's result: 0 refusals in 10 minutes at 11:34 |
| OBS-18 | Plan watch takes 7 to 20 s | Defect, on list | Row 8. Improved to 5.7 to 6.4 s (OBS-25), still slow |
| OBS-19 | No red "could not get an answer" box on screens checked | Nothing to do | A good result, no action |
| OBS-20 | Step 3 fresh load: "Not available" for the current level | Defect, missing from list | Same as OBS-15 |
| OBS-21 | Armed stop says "above 135.00" while the price is 113.10 | Defect, missing from list | Stop sentence is unclear. See C item 15. Low |
| OBS-22 | Max loss jumps to Rs 16,62,316.50 after a stop Save | Nothing to do as a defect | The figure is the decided one (ADR-330 (6)); the missing explanation is note UX-03 + UX-08 |
| OBS-23 | Active list showed only some rows (note cut off) | Test set-up weakness | Active holds open rows only; check History too. Ask the tester for the full note |
| OBS-24 | Database lost 10:07 to 10:13: tunnel dropped | Test set-up weakness | Row 18; not an app defect |
| OBS-25 | First fix pulled 11:18, figures better | Nothing to do | Record of a fix; shows rows 8 and 11 improved |
| OBS-26 | A plan saved through a timed-out request was stored, but rules and exits could not be read back | Defect, missing from list | Possibly linked to row 20. See C item 2 |
| OBS-27 | Sixth pull 13:33: plan-stop alert fix | Nothing to do | Record of the fix for row 20 |
| OBS-28 | AX-02 chart hover kept through a refresh | Nothing to do | Pass |
| OBS-29 | AX-03 no-plan trade stored three adjustments, no maximum text | Nothing to do | Pass (ADR-330 (11)) |
| OBS-30 | Option chain: LTP 154.30 below bid 154.50 at 25650 calls | Nothing to do (watch) | Last traded price can sit outside the current bid and ask. If it shows again with times, check the age of each figure |
| OBS-31 | Seventh and eighth pulls 13:52 | Nothing to do | Record of the Plan watch and exit-message fixes |

Counts: Defect on list 12 (OBS-01, 02, 03, 04, 05, 11, 12, 13, 14, 16, 17, 18); Defect missing from list 4 (OBS-15, 20, 21, 26); Test set-up weakness 2 (OBS-23, 24); Nothing to do 8 (OBS-19, 22, 25, 27, 28, 29, 30, 31).

---

## C. Issue list check

### Duplicates and overlaps inside the list of 26

| Rows | Finding |
|---|---|
| 13 and 26 | Same defect ("Acted on" stamped too early; row 26 is the cancelled-basket case). Row 26 says so itself. Merge; one fix covers both (Lane W item 10) |
| 1 and 6 | Row 6 is suspected to be row 1. Keep one row |
| 8 and 22 | Row 22 (34 Plan watch requests a minute) is the load side of row 8 (answers take 7 to 20 s). Same area, two fixes (pacing now; one request for all rows later) |
| 11 and 21 | Same screen symptom ("Prices are not live"), but Lane U found two separate causes. Not duplicates; keep both |
| 10 and 25 | Both are the Exit dialog but different (nothing happened vs "could not confirm" after the order was placed). Keep both |

### Status of today's 26 rows from the five result files

- Fixed on a branch, not tested (15): rows 2, 5, 10, 11, 12, 13, 14, 15, 16, 19, 20, 21, 23, 24, 26.
- Fixed in part (3): rows 8 and 22 (pacing only), row 25 (unknown-result part).
- Note passed to another lane, not fixed (2): rows 3 and 4 (Lane J).
- No fix in the five files: rows 1, 6, 9. Rows 1 and 9 are Critical.
- Waiting for the owner's wording: row 17. No code needed: rows 7, 18.

### Issues found in the notes and observations that are NOT on the list

Criticality is my proposal. "Lane" means who owns it, from the lane's own result file where one names it.

| # | Issue | Source | Proposed criticality | Depends on | Owner lane |
|---|---|---|---|---|---|
| 1 | Add to Paper accepted 5000 lots (no lot limit or freeze check on the one paper order door) | Lane W item 15 | High | none | W. Fixed on a branch; three owner points open (no freeze row stored: not refused; paper exits not checked; check is per order, not per leg total) |
| 2 | Plan stop alerts not raised, three causes. (a) the strategy's daily alert cap held the stop; (b) the rupee loss stop skipped the fast path and waited for the candle close; (c) a plan saved through a timed-out request could not be read back (OBS-26; my reading, not confirmed by the lane). Row 20 is the symptom only | Row 20, OBS-26, Lane J | Critical | none for (a), (b); (c) needs row 8 | J. (a) and (b) fixed on branch loss-stop; (c) open. Owner question open: the style's quiet time after an alert still holds a loss stop (REQ-170 AC-5) |
| 3 | The worker silently pausing a strategy it cannot price | From the brief; no evidence in the files I read | High | row 21 | J |
| 4 | Index "Not available" while the index is ticking (OBS-15, OBS-20) | Observations | High | rows 11, 21 | U |
| 5 | Plan watch page rejecting an answer with a reason object | From the brief; not seen in the files I read | Medium | row 8 | R (page reader) |
| 6 | Plan block showing the old stop after a save (UX-34) | Note | High: he may trust the wrong stop | none | R |
| 7 | Percent stop saved to the weekly row with no market | From the brief; not in the files I read | High: a stop that cannot fire | none | J |
| 8 | Exit dialog not blocked when the feed is down | UX-25, row 10 | High | row 21 | U. Fixed on a branch (dialog stays open, Confirm grey); builder dialog included |
| 9 | Missing "as of" time when paused | From the brief | Medium | row 21 | R |
| 10 | Typed entry price refused when the feed is down. ADR-330 (28) says he can still type his own entry price | From the brief | High | row 21 | W or R |
| 11 | Completed Strategies header says 15, rows show 14 (ADR-330 (15)) | From the brief | Medium | none | R |
| 12 | Alerts staying Active after the last leg exits (ADR-330 (3): closed by system) | From the brief; related to row 15 | High | none | J |
| 13 | Builder exit sentence without the order number | From the brief; Positions already says "(order n)" | Low | row 10 | U (builder dialog is in Lane U's deferred list) |
| 14 | "Reset to playbook" shows no changed markers (ADR-330 (9), (32)) | From the brief | Medium | none | J |
| 15 | Armed stop sentence unclear ("above 135.00" at price 113.10) (OBS-21) | Observation | Low | none | M |
| 16 | Plan sheet takes 17 s to load (12:42) | Lane W deferred 9 | Medium | row 8 | R |
| 17 | Side-closed question not raised for a trade with no plan. Conflict of ADR-330 (3) and (11) against (2)(b) and (33) | Lane M question Q1 | High | owner decision | M, only after the owner answers |
| 18 | A fired stop never executes if the monitor clock runs ahead of the database clock | Lane J deferred | High | none | J |
| 19 | Unexplained contract name with year 2028 seen on 27 Nov | Lane M | Medium | none | M |
| 20 | Leg stop does not follow a moved leg (issue #774, already filed) | Lane U | Medium | none | U |

The five result files also list about 25 smaller deferred items (wording, double History lists, one Alerts exit double-click). The coordinator files them; I did not repeat them.

### Owner questions that wait in the lane files (not decided here)

- Lane M Q1: does the side-closed question come for a trade with no plan? Recommendation of the lane: yes. Two of your own rows disagree (ADR-330 (3) and (11) against (2)(b) and (33)), so only you decide.
- Lane J: should a plan stop be held during the alert style's quiet time? REQ-170 AC-5 says risk exits are not delayed.
- Lane W: the three points of item 15; wording for the take-profit refusal (item 12); REQ-112 AC-2.
