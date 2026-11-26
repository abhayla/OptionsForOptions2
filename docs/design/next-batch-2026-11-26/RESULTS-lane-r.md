# Lane R results: the owner's screen checks of 26 Nov 2026

Branch `fix/screen-findings-1126`, cut from `origin/feat/nb-screens-w2-1126` at `a9bd41a`. No PR. Paper only. Evidence:
`docs/process/screen-checks-2026-11-26.md` (verbatim copy of PR #722 comment 7184365037). Highest status claimed: **Fixed,
not tested** (the owner tests on his PC). Standing-direction step 4 item 10 (defects in what is built).

Spec basis: ADR-328 (2) to (4), ADR-329 (1) to (3), ADR-330 (8) and (19) to (23), ADR-327 (2), ADR-002, ADR-003, ADR-008.

How it was checked: every fix has a failing test first that follows the owner's steps on the real pages, real router and
recorded paper books (vitest); S-02 has a real PostgreSQL test (a second connection holds the row lock). No browser
walk-through was possible in the cloud: the app needs the broker feed and the owner's database. Exit and money changes
(N-04/N-05, N-07) had an independent Opus review; both came back FIX FIRST, and round 2 fixed every finding listed below.

## Per finding

| Finding | Status | Root cause (one sentence) | Class before / after | Tests red, then green |
|---|---|---|---|---|
| Row 12, Drafts Mode across the chain trip | Fixed, not tested | The builder dropped the chain-trip hold whenever the URL carried `?strategy=`, and Back from the chain returns to the `?strategy=<id>` entry, so the book was read again over the held edit. | Chain-to-builder returns whose URL names the held strategy: 3 of 3 tested paths lost the edit (paper, saved, changed book); 0 after. | `chain-trip-adr329.test.js` R12a-c: 3 failed on the old page; pass after. |
| Row 11, replace question on a draft link | Answered (LR-Q1, option 1) | A pasted link is a full page load and unsaved legs live in page memory only, so no code can ask. | Spec and check text corrected (ADR-329 (3), ADR-328 (2), modular-doors RESULTS.md row 11); no code. | n/a; `draft-link.test.js` stays the in-app test. |
| N-04, staged exit stays after the page closes the Exit dialog | Fixed, not tested | The page closed the dialog but left the exit staged in the legs; the user's own Cancel did the same. | Closes without the user's choice that left staged exits: 2; 0 after (one `cancelPaperDialog`, restoring the legs as they were before the Exit click). | `exit-dialog-page-close.test.js`: 6 failed, then 13 pass; review round 2: 6 more failed, then pass. |
| N-05, "Review and add" looks usable while blocked | Fixed, not tested | Review and add read the blocked rule only for edits that came from an Exit, and an open dialog's Confirm ignored it. | Buttons that commit paper orders reading one blocked rule: 2 of 3; 3 of 3 after; a blocked Confirm posts nothing for any paper dialog. | same files; A3: 1 POST before, 0 after. |
| N-07, third price reader (P&L Table) | Fixed, not tested (part; rest #744) | The P&L Table printed the outcome reply's LTP and P&L and the plan's entry, while the legs table and the Paper P&L panel read the book. | Builder views of a paper leg's price/P&L: 3 of 6 on the book before (legs table, Paper P&L, and none other); after, the P&L Table too (joined by contract, side and lots; a failed read shows "-" in rows and TOTAL). Left: Full table, leg-list "now" price, Paper P&L rows after a failed read (#744). | `pnl-table-one-source-n07.test.js`: 5 failed, then round 2: 7 of 12 failed, then pass; guard `paper-leg-readers-guard.test.js` red on 3 mutations. |
| N-01, refusal line vanishes | Fixed, not tested | A watcher in `PaperStops.vue` cleared every "Not saved" line when the list's next good poll arrived. | Clear paths not driven by a user edit or a new Save: 1; 0 after. "First Save showed nothing" not reproduced. | `paper-stops.test.js`: 2 failed, then pass. |
| N-14, every paper trade has the same name | Fixed, not tested (ADR-330 (19) a and the lists half of b; alert titles are Lane P's) | Add to Paper saved an unsaved strategy under the shape name and never asked; the lists showed the bare name. | Lists showing a bare name: My Strategies, Live cards, Home recent, Positions > Paper (2 spots); 0 after, one label maker `strategyListLabel` in `lib/saveDraft.js`. A list reply carries only the first leg's expiry, so a calendar spread shows that date on My Strategies, Live and Home. | `add-to-paper-name-adr330.test.js`, `strategy-list-label-adr330.test.js`: 10 failed without the fix, then 16 files / 228 tests pass. `e2e/my-strategies.spec.ts` updated, not run (needs the servers). |
| R-06 / N-18, doubled label on Home | Fixed, not tested | `HomeOverviewPage.vue` spread "(after charges)" over the figure's name, then appended it again. | Places that can print the suffix twice: 1; 0 after. | `home-figures-d56.test.js`: red "(after charges) (after charges)", then pass. |
| N-10, wrong refusal parts for the other-index add | Fixed, not tested | `addFromChain` built its refusals from the server-failure parts. | 2 refusal sites; 0 after (both use `INVALID_LINK_PARTS`). | F1 test: red on "Try again in a moment", then pass. |
| N-13, "No draft strategy is open" while a trade opens | Fixed, not tested | `load()` set the empty-builder state before the `?strategy=` book read answered. | Open paths showing the empty builder before their read: 4; 0 after. | 3 of 5 new tests failed, then pass. |
| N-11, leave question for a staged removal | Fixed, not tested (ADR-330 (22)) | The question counted pending changes but called them unsaved legs. | 1 question; it now says "pending changes" for a running trade on the builder and the chain page. | `leave-builder-adr329.test.js`: red, then pass. |
| N-12, Stops link does not reach the trade | Fixed, not tested (ADR-330 (21)) | The Positions page ignored `?strategy=` unless an exit was asked. | 1 link; it now opens that trade's Stops panel and scrolls to it; the list is not filtered. | `paper-exit-link-s14.test.js`: red, then pass. |
| N-08, chain ticks stay after Add Selected | Fixed, not tested (ADR-330 (20)) | Add Selected pushed the draft link and never cleared the selection. | 1 store; the builder clears the ticks only after it has added them (Cancel on a clash, the other-index refusal or an error keeps them). REQ-030 AC-10 amended. | N08a, N08d failed without the fix (lead's run), then 57 pass. |
| N-15, Orderbook quantity in units | Fixed, not tested (ADR-330 (23), #747) | The order rows carried units only, no lots or lot size, and the browser must not divide by a guessed lot size. | 1 table; the server now sends `lots` per order row (catalogue lot size, same source as the closed rows; a quantity that is not whole lots sends null and shows "-"); the column reads "Lots". Caveat: an NSE lot-size revision re-divides old orders with the new lot. | `tests_app/test_paper_order_lots.py` (real DB): 3 failed (KeyError 'lots'), then 3 passed; vitest 28 pass. |
| S-02, a lock wait on delete ends as a raw 500 | Fixed, not tested (wording pending owner read, ADR-NB-1) | The error door had no case for a busy database (sqlstate 55P03, 57014, 40P01), so it answered the generic internal error. | Write routes that end as ERR-xxxx on a busy database: 49 in 21 route files; 0 after. Left: `order_book_store.py:152` answers BAD_HOLDING (#746). | `tests_app/test_store_busy.py` (real DB): 6 failed, then 10 passed. |
| N-02 | Deferred #745 | A timed-out parallel read leaves the box after the other read succeeds. | - | - |
| N-03, N-06, N-09, N-16, N-17, N-19 | Not a defect | N-03 legal hold (REQ-079); N-06 by design (D-C50); N-09 and N-17 test-tool artefacts; N-16 name vs engine shape (REQ-076 AC-8/9); N-19 by design (REQ-080 AC-9). | - | - |

Detection changes: row 12, the R12 tests close the hole C6 left (it never returned to a `?strategy=` entry); N-07, the
guard `paper-leg-readers-guard.test.js` (wiring and registry, REMAINING rows pinned by file:line); N-04/N-05, one cancel
path and one blocked rule (structural); S-02, the one error door; N-01, one clear rule in the component. Findings:
`knowledge/findings/leg-price-read-by-several-panels-on-one-screen.json`, `knowledge/findings/lock-wait-ends-as-raw-500.json`.

Process notes: (1) helper worktrees made with isolation were not cut from this branch every time (each brief opened
with a base check and re-cut); (2) the `verifier_inflight_gate` hook refuses every write in every worktree while ANY
review agent runs, so a review blocked three builders for about 15 minutes: run reviews when no builder needs to write.

## Re-test: row 12 (push 1)

1. Open a running paper trade in the builder (Live Strategies > click its name). Click the bin on one leg: "1 pending change".
2. Top menu Market > Option Chain. Press the browser Back arrow.
3. Expected: still "1 pending change", the removed leg still gone. Click Discard.
4. Again: bin on one leg, Market > Option Chain; in a second tab exit one leg of that trade on Positions; first tab Back.
5. Expected: "The strategy changed while you were away. Your unsaved edits were not restored." and "0 pending changes".

## Re-test: N-01 (push 1)

1. Positions > Paper > Stops on a running trade > Conditional exit.
2. Type an Above level the index is already beyond; Save.
3. Expected: "Not saved: the live price is already at or beyond this level ..." in red.
4. Wait a full minute without touching anything. Expected: the line is still there.
5. Change the level by one point. Expected: the line goes.

## Re-test: R-06 (push 1)

1. Open Home.
2. Expected: the total reads "Total P&L", the figure, and "(after charges)" once.
3. Reload the page and watch the total.
4. Expected: the label never shows "(after charges) (after charges)" or a bare "(after charges)" without its name.
5. (Not part of this fix: the gap against My Strategies is not proven wrong; check it after 15:30 when prices stop.)

## Re-test: N-04 / N-05 (push 2)

1. Builder on a running paper trade: change the lots of one leg ("1 pending change"), then click the per-leg Exit of another leg; Cancel.
2. Expected: still "1 pending change" (your lot change), the other leg not staged for exit, the figures as before the Exit click.
3. Click Exit all (dialog open, do not confirm); in a second tab exit one leg of that trade. Back in the first tab.
4. Expected: the dialog closes by itself, "This trade changed elsewhere. Reload to see the current legs.", no "No legs yet" and no staged exits; "Review and add", "Exit all" and every "Exit" are greyed out.
5. Reload: the current legs, every button enabled.

## Re-test: N-07 (push 2)

1. Open the builder of a running 2-lot paper trade; open the "P&L Table" tab.
2. Expected: each leg's LTP and P&L equal the legs table at the top left at the same moment; the column reads "Entry price".
3. Exit 1 lot of one leg (Confirm). Expected: that row shows the same P&L as the legs table (booked plus open).
4. Stop the API for a few seconds (as in row 4). Expected: the P&L Table rows and its Total show "-", like the legs table.
5. Still different (deferred #744): the "Full table" switch on that tab, and the Paper P&L panel after a failed read.

## Re-test: N-10, N-13 (push 2)

1. Open `/strategy/builder?strategy=<a running trade>` fresh. Expected: a loading line, never "No draft strategy is open" or "No legs yet", then the legs.
2. Same by Live Strategies > the trade's name, and by Back from the Option Chain.
3. Build 3 NIFTY legs; Option Chain > SENSEX; tick one; Add Selected.
4. Expected: "These contracts are on SENSEX; the legs in the builder are on NIFTY. Nothing was added." with "What to do next: Check the values you entered and try again." (no "Try again in a moment").
5. The 3 NIFTY legs are unchanged.

## Re-test: N-11, N-12 (push 2)

1. Builder on a running paper trade: bin on one leg; click Settings (top menu). Expected: "Leave the builder? The 1 pending change will be lost." Stay.
2. A new unsaved strategy with 3 legs: Settings. Expected: "Leave the builder? The 3 unsaved legs will be lost." Stay.
3. Live Strategies > "Stops" on a running trade that is not first in the list.
4. Expected: Positions opens on the Paper tab, the page scrolls to that trade, its Stops panel is open.
5. The other trades are still listed.

## Re-test: S-02 (push 2)

1. Not clickable on purpose: the case needs a second database session holding a lock on the strategy row.
2. What changed for the user: a delete or other write that waits on a busy database now says "This strategy is busy with
   another action, so nothing was changed." and "Wait a moment, then try again." instead of ERR-xxxx.
3. Wording pending the owner's read (ADR-NB-1 in ADR-330 (8)).
4. Normal deletes: My Strategies > Delete on a draft still deletes as before.
5. Nothing to check after 15:30.

## Re-test: N-08 (push 2)

1. Build 3 legs in the builder; Market > Option Chain; tick two contracts with Buy; Add Selected.
2. Expected: the builder shows 5 legs.
3. Market > Option Chain again. Expected: "Selected Legs" is empty.
4. Tick a contract you already hold with the same action; Add Selected; Cancel in the question; go back to the chain.
5. Expected: that tick is still there.

## Re-test: N-14 (push 3)

1. Strategies > Create Strategy > Guided > Short Iron Condor > Open in Strategy Builder > Add to Paper.
2. Expected: a "Name this paper trade" box prefilled "Short Iron Condor". Type "IC wk1" and Save; then Confirm the paper trade.
3. Expected: My Strategies, Live Strategies and Positions > Paper show "IC wk1 (#<its number>, 1 Dec)".
4. Again Add to Paper on another unsaved shape, then Cancel in the name box. Expected: nothing is added.
5. Not changed here: alert titles still read "Paper strategy - <name>" (the alerts lane adds the number and expiry).

## Part C (second batch, owner comment 7185059890)

| Finding | Status | Root cause (one sentence) | Class before / after | Tests red, then green |
|---|---|---|---|---|
| C-04 / N-26 / N-30, bulk delete Undo lasts 2-3 s | Fixed, not tested | The delete flow kept its Undo only in a timed state that cleared after the served wait; the bulk result line never had an Undo and a single delete had no result line. | Undos offered only in a timed pop-up: 6; 4 after (single and bulk delete fixed; Save Undo, Clear all Undo, the chain's one-leg Undo and the generic toast remain, deferred). N-30's ~3 s before the result shows is not addressed. | `my-strategies-bulk.test.js`: 5 failed, then 23 pass. |
| N-25 (b), "1 of them are running" | Fixed, not tested | `bulkConfirmText` used "are" for any count. | 1 sentence; REQ-070 updated. | same file. |
| C-12b, stale index number in the Stops panel | Fixed, not tested | With the feed down the server keeps the answer LIVE but marks each row's health stale; the one index reader looked at the answer state only. | `useIndexAnswer` screens that drop a stale value: 1 of 3; the Stops panel now reads the row health through the shared reader. The Home strip and Index page keep the number with a "stale" word, unchanged (by design today). | `stops-index-stale.test.js`: 4 failed, then 61 pass. |
| N-22, Cancel moves in the Exit dialog | Fixed, not tested (pixels not seen: jsdom has no layout) | The risk-check line and the status lines were shown with v-if and no reserved height, so the centred dialog shrank. | Moving spots in the paper confirm dialog: 2; 0 after (always-rendered slots). Listed, not fixed: AdjustPlanSheet.vue:44, LegList.vue:167/200/283, SaveDraftBar.vue:491, BrokerSettingsPage.vue:160. Finding `controls-move-while-user-acts-v-if-lines.json`. | `paper-confirm-no-shift-n22.test.js`: 2 failed, then 154 pass. |
| C-05 (NOT CHECKED) | How to check | The PC database has no strategy held at the broker. | - | Check after the first real order (ADR-289): My Strategies > tick a strategy held at Zerodha with others > Delete selected: it is kept and named with the server's reason. |
| C-12a (NOT CHECKED) | How to check | The Positions page has no index strip. | - | Open Home in a second tab; compare the Stops panel's "as of" time and value with the strip at the same second (or the Option Chain spot). |

### Part C triage of the observations (N-20 to N-30, C-01b, S-09)

| Id | Class | Reason / action |
|---|---|---|
| C-01b | not a defect | A placed paper book follows ADR-263 (2) ("a paper book's breakevens carry the same charges as its Max Profit / Max Loss and booked P&L, with a line saying so"; server text `routes/paper.py:772`, `errors/explanations.py:1905,1912`); ADR-330 (17) is about the plan summary only. Two bases on two screens: if the owner wants one, that is a new question (LR-Q9). |
| N-20 | not a defect | Home "Total P&L —" right after the API restart is the first-read / paused state (`paperPnl.js:25-30, 62-66`), not a wrong figure. |
| N-21 | defect, fixing now | The Stops panel re-read only its own list after Save; the legs come from the parent's 5 s timer (`PaperStops.vue:58-75`, `PaperStrategies.vue:362`). The server refuses an exit of a fired leg, so a display lag only. |
| N-22 | fixed | above. |
| N-23 | not a defect | The "taking longer than usual" notice is designed (`StrategyBuilderPage.vue:277, 1275`); the delay is the outcome call's round trip (a speed item, not measured). |
| N-24 | not a defect (fixed by N-14) | The builder's compact paper list already uses `strategyListLabel` since the N-14 commit, after the tested a9bd41a8. Re-test on this branch. |
| N-25 (a) | not a defect | The after-charges line belongs on every plan summary, saved or not (ADR-330 (17), ADR-263). |
| N-25 (b) | fixed | with C-04. |
| N-26, N-30 | fixed (N-26) / open (N-30) | with C-04; the ~3 s before the result shows is not addressed. |
| N-27 | defect, fixing now | `PaperBookPanel.vue:59` price and time inline; Exit cell cut off. |
| N-28 | layout fixing now; product question LR-Q8 | The exit average is served (`routes/paper.py:617-624`), not computed in the browser (ADR-008 holds); the cell split ships with N-27; how to label an average of several exits is the owner's. |
| N-29 | placeholders fixing now; hyphen not a defect | Placeholder bars `bg-surface-muted` on white (`MyStrategiesPage.vue:173-174`); the hyphen is a test-tool artefact (plain v-model, saved name right). |
| S-09 | defect, deferred #748 | A newly subscribed contract shows the "unavailable" health word instead of the REQ-133 AC-3 waiting state. |

## Re-test: C-04 (Part C push)

1. My Strategies: save two throw-away drafts (e.g. "UNDOTEST-1", "UNDOTEST-2"); search UNDOTEST; tick both; Delete selected; Delete.
2. Expected: the line "2 deleted." stays with "Undo" and "Dismiss" beside it; wait 30 seconds: still there.
3. Click Undo. Expected: both rows come back and the line goes.
4. Delete one draft by its own Delete: the line "1 deleted." (or the server's summary) with Undo stays too; Dismiss removes it.
5. Tick a running paper trade with one draft and press Delete selected: the question reads "... 1 of them is running."; Cancel.

## Re-test: C-12b and N-22 (Part C push)

1. Positions > Paper > Stops on a running trade: the line "NIFTY now ... as of ..." shows.
2. Stop the price feed (as in Part C). Within a few seconds the line reads "Index values unavailable." with no number.
3. Start the feed again: the number comes back without a reload.
4. Live Strategies > Exit on a running trade: watch the Cancel button while "Checking whether this exit leaves a sold option without protection..." finishes.
5. Expected: Cancel does not move; one click on it closes the dialog.
