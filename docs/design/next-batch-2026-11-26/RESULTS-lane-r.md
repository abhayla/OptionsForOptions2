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
| N-04, staged exit stays after the page closes the Exit dialog | Fixed, not tested | The page closed the dialog but left the exit staged in the legs. | Page-side closes that left staged exits: 2; 0 after (one `cancelPaperDialog`, restoring the legs as they were before the Exit click). The user's own Cancel keeps the chosen exits as edits, as u513 (owner test note #85) decided; the gate caught round 1 dropping them (`exit-preview-not-pending.test.js`). | `exit-dialog-page-close.test.js`: 6 failed, then 13 pass; review round 2: 6 more failed, then pass. |
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
| S-02, a lock wait on delete ends as a raw 500 | Fixed, not tested (wording approved by the owner, ADR-330 (26)) | The error door had no case for a busy database (sqlstate 55P03, 57014, 40P01), so it answered the generic internal error. | Write routes that end as ERR-xxxx on a busy database: 49 in 21 route files; 0 after. Left: `order_book_store.py:152` answers BAD_HOLDING (#746). | `tests_app/test_store_busy.py` (real DB): 6 failed, then 10 passed. |
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

1. Builder on a running paper trade: change the lots of one leg ("1 pending change"), then click the per-leg Exit of another leg; leave the dialog open and stop the API (as in row 4).
2. Expected: the dialog closes by itself, "1 pending change" (your lot change only), the other leg not staged for exit. (Your own Cancel keeps the exit as an edit, by the earlier u513 rule.)
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
3. Wording approved by the owner as written, 26 Nov 2026 (ADR-330 (26)).
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
| N-21 | fixed, not tested | The Stops panel re-read only its own list after Save; the legs come from the parent's 5 s timer (`PaperStops.vue:58-75`, `PaperStrategies.vue:362`). The server refuses an exit of a fired leg, so a display lag only. |
| N-22 | fixed | above. |
| N-23 | not a defect | The "taking longer than usual" notice is designed (`StrategyBuilderPage.vue:277, 1275`); the delay is the outcome call's round trip (a speed item, not measured). |
| N-24 | not a defect (fixed by N-14) | The builder's compact paper list already uses `strategyListLabel` since the N-14 commit, after the tested a9bd41a8. Re-test on this branch. |
| N-25 (a) | not a defect | The after-charges line belongs on every plan summary, saved or not (ADR-330 (17), ADR-263). |
| N-25 (b) | fixed | with C-04. |
| N-26, N-30 | fixed (N-26) / open (N-30) | with C-04; the ~3 s before the result shows is not addressed. |
| N-27 | fixed, not tested (the Exit column may still need a scroll in the narrow panel) | `PaperBookPanel.vue:59` price and time inline; Exit cell cut off. |
| N-28 | cell split fixed, not tested; product question LR-Q8 | The exit average is served (`routes/paper.py:617-624`), not computed in the browser (ADR-008 holds); the cell split ships with N-27; how to label an average of several exits is the owner's. |
| N-29 | placeholders fixed, not tested; hyphen not a defect | Placeholder bars `bg-surface-muted` on white (`MyStrategiesPage.vue:173-174`); the hyphen is a test-tool artefact (plain v-model, saved name right). |
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

## Re-test: N-21, N-27, N-28, N-29 (Part C push)

1. Positions > Paper > Stops on a running trade: set a leg stop just beyond the leg's price so it fires. Expected: the leg row leaves the card within a second or two of "fired" (not ~9 s).
2. Builder of a running paper trade > Net Positions: each LTP shows its time on its own small line under the price.
3. Closed rows: the exit price stands alone on the right, the stop-loss sentence on its own line under it.
4. My Strategies: reload; the grey loading bars are clearly visible for the moment before the list shows.
5. Nothing else on these screens changed wording.

## After LANE R DONE (7bf64eb): review round, N-28, #744

| Finding | Status | Root cause (one sentence) | Class before / after | Tests red, then green |
|---|---|---|---|---|
| Exit path, independent Opus review of N-04/N-05 round 2 and the u513 correction | Fixed, not tested (MAJOR 1 and MINOR 2) | MAJOR 1: the u513 correction left the Exit snapshot alive after the user's Cancel, so a later page-side close restored the old legs and silently wiped edits made after the Cancel; MINOR 2: a block that arrived during a POST left the dialog open with Confirm enabled (nothing posted). | Page closes that can wipe later user edits: 1 path (two Exit clicks with a Cancel between); 0 after (the user's Cancel ends the snapshot). Confirm while blocked: enabled in 2 states; disabled after (a `blocked` prop on the paper confirm dialog). | `exit-dialog-page-close.test.js` A1, A2, A3, A8: 4 failed on the pushed code (lead's run), then 18 pass; full suite 2,981 pass. |
| N-28 = ADR-330 (27), closed exit averaged over several exits | Fixed, not tested | The closed row printed the average with no count. | The server builds the text once (catalogue template `closed_exit_average`, "{value} (avg of {count})"; reply field `exit_fills`); every screen that prints it gets it. | `tests_app/test_paper_closed_rows.py`: red KeyError 'exit_fills', then 7 passed (real DB). |
| #744, the remaining N-07 readers | Fixed, not tested | The Full table printed the reply row, the leg list's "now" price came from the reply, and the Paper P&L rows ignored a failed book read. | Builder views of a paper leg's price / P&L on the book: 2 of 5 before, 5 of 6 after (left: Advanced Details bid/ask, not a price or P&L). One join (`chartCard.paperBookLeg`: contract, side, lots); guard mutation-tested on 7 breaks. | `full-table-one-source-744.test.js`: 6 failed, then 7 pass. `one-source-d41.test.js` test 8 now expects the dash on a failed read. |
| S-02 wording | Approved (ADR-330 (26)) | - | The ADR-NB-1 placeholder is now ADR-330 (26) everywhere; the pin is marked owner-read. | `tests/errors`: 710 passed. |

## Re-test: exit path round 3

1. Builder on a running paper trade: per-leg Exit on one leg; Cancel (the exit stays as "1 pending change", as before).
2. Change the lots of another leg ("2 pending changes"); then per-leg Exit on a third leg; leave the dialog open and stop the API.
3. Expected: the dialog closes by itself and "2 pending changes" remain (your kept exit and your lot change); only the third leg's exit is gone.
4. Start the API; press Exit all, Confirm, and stop the API while "Placing..." shows (or open a second tab and exit a leg there at the same moment).
5. Expected: once the answer arrives the dialog closes or its Confirm is greyed; nothing is sent twice.

## Re-test: N-28 and #744

1. Builder of paper trade 172 > Net Positions > closed rows: 25850 CE reads "174.73 (avg of 2)"; a leg closed by one exit shows the bare price.
2. Open the "P&L Table" tab and switch on "Full table": each leg's LTP and P&L equal the legs table at the same moment; P&L % shows "-".
3. A leg whose price moved shows "Price has moved ... now <the legs table's LTP>".
4. Stop the API for a few seconds: the legs table, the P&L Table, the Full table and the Paper P&L panel rows all show "-"; restore: all come back.
5. Orderbook: each fill of 25850 CE is still its own row (153.00 and 196.45).

## Part D (re-test of 7bf64eb, owner comment 7187957060)

Result on the PC: 15 PASS with this morning's failure gone, 3 PASS with a remainder (D-N07, D-N13, D-S02), 1 FAIL (D-N11).

| Finding | Status | Root cause (one sentence) | Class before / after | Tests red, then green |
|---|---|---|---|---|
| D-N11, "1 unsaved leg" for a staged removal on a running trade | Hardened, NOT reproduced | The old test drove a hand-built harness and snapshot, so the page's own snapshot never ran (detection gap, now closed); on the real path (real routes, real page, real book fixture, real bin click, real Settings route) the wording was already right, so the owner's case is not explained. | "Pending" now reads the page's Drafts Mode state itself, not a field of the book reply (`paper.book.strategy_id`, which a refreshed book could in principle lack). | New `leave-builder-real-path-adr329.test.js`: N11a green before and after; N11c (book without strategy_id) red, then green. If the PC still shows "unsaved leg": note the deployed commit and copy the `GET /api/paper/strategies/<id>` reply. |
| N-37, restored legs read "Your price, typed" | Fixed, not tested | A paper-fill leg is recognised by contract, planned entry and capture time; the restore re-reads the book, its fills carry newer times, so no held leg matched and every leg showed as typed. | Restored legs shown as typed: 3 of 3; 0 after (the hold carries the fill keys and the restore takes the fresh fill's entry and time). | N37: 3 typed lines, then 0. |
| N-35, stale builder still offers the bins | Fixed, not tested | Only the Exit buttons read the blocked rule; the leg list and the controls had no lock. | Leg-edit controls enabled while the trade changed elsewhere: 24 (4-leg fixture); 0 after, through one `locked` prop with the existing reload line as the reason. Choice: the same lock holds while the book read fails (the Exit rule); it lifts when the read recovers. | `leg-lock-n35.test.js`: red, then 3 pass. |
| D-N13 / N-34, empty "New Strategy" frame while opening | Fixed, not tested | The opening flag hid only "No legs yet"; the card title and the action bar still showed. | Shell parts shown while opening: 4; 0 after (one loading card with the existing "Working out the outcome..." text). | `opening-shell-n34.test.js`: red, then 3 pass. |
| D-N07 remainder, API down shows an error block on the P&L Table tab | Question LR-Q10 | Without an outcome reply the page shows its error block for the whole numbers area; the P&L Table's rows come from that reply. The dash rule works when the outcome answers and only the book read fails (tested). | - | - |
| D-S02, the busy wording cannot be clicked | As designed | The wording needs another session holding the strategy's row lock until the statement times out; two tabs deleting at once queue in milliseconds and get a refusal or "not found", never the busy line. The owner can see it only through `tests_app/test_store_busy.py` (one file, `scripts/orchestrator/db_run.py`). | - | - |
| N-36, Back replays a cancelled clash question | Fixed, not tested | A cancelled add was not recorded on the hold, so Back replayed the same draft link. | 1 path; each Add Selected is now its own history entry and the handled mark is the draft text plus that entry: Back asks nothing, a new Add Selected still asks. | N36 in `chain-trip-adr329.test.js`: red, then pass. |
| N-39, "2 deleted" stays ~3 s after Undo | Fixed, not tested | The line was cleared only after the restore calls finished. | 1 line; cleared at once, put back only if a restore fails. | `my-strategies-bulk.test.js`: red, then pass. |
| N-31, N-33, N-41, N-42 | Not a defect | N-31: the index had no tick yet after the API restart (self-clears); N-33: Exit on a Live card opens Positions by design (D-N22); N-41: drafts 182/183 were most likely restored by a late Undo on the result line (a deleted row cannot be listed: every read filters deleted rows); N-42: the plan sheet at Add to Paper is REQ-161 AC-1 (Lane P's area). | - | - |
| N-32 | Not a defect | During a pending partial exit the P&L Table row shows "-" and "Planned entry" because the row's lots differ from the book's (the one join, #744). The ~10 s Confirm lock is the exit's round trip. | - | - |
| N-38, N-40, delete history | Questions LR-Q11, LR-Q12, LR-Q13 | - | - | - |
| N-43 | Deferred #749 | The stop-loss sentence wraps in the narrow Exit column. | - | - |

## Re-test: Part D fixes

1. D-N11: open a running paper trade by My Strategies > Open in Builder; bin one leg; You > Settings. Expected "Leave the builder? The 1 pending change will be lost." Stay. If it still says "unsaved leg", note the commit the PC runs and save the `GET /api/paper/strategies/<id>` reply from the browser's network tab.
2. N-37: same trade, bin one leg, Market > Option Chain, Back. Expected: "1 pending change" and no leg reads "Your price, typed ...".
3. N-35: open the trade in two tabs; in tab 2 exit one leg; in tab 1: the bins, strike +/-, lots, Clear all, Add/Edit and Shift/Width/Hedge are greyed, with "This trade changed elsewhere. Reload to see the current legs."; reload: all enabled.
4. D-N13: open `/strategy/builder?strategy=<a running trade>` fresh. Expected: one loading card, never an empty "New Strategy" with Save / Add to Paper, then the trade.
5. N-36 / N-39: chain clash > Cancel > Back: no question again; My Strategies bulk delete > Undo: the "2 deleted" line goes at once.

## After the close (owner comment 7189204004, run 15:31 to 15:50 IST on 7bf64eb)

Result on the PC: 3 PASS (AC-01 market-closed Save, AC-03 the three P&L places equal at the last close, AC-SETTLE SENSEX
trade 173 settled with the right sum), 1 FAIL (AC-R06), 1 NOT CHECKED (AC-R10).

| Finding | Status | Root cause (one sentence) | Class before / after | Tests red, then green |
|---|---|---|---|---|
| AC-R06 / N-46, Home and Positions totals pause when one trade cannot be priced | Fixed, not tested; owner-approved ADR-330 (35) | The server summed every non-expired strategy and blanked the whole total on any other missing price, exactly as ADR-324 (1) says ("Any other reason a price is missing ... keeps today's behaviour: the figure is blank with its reason"); #173, expiring that day and awaiting settlement, had no live price. | Totals over several paper strategies that blank on one unpriced member: 3 (Positions header, Today total, Home Total P&L); 0 after: the server sums the strategies that can be priced and a count line names how many were left out and why. All unpriced: blank with the reason, as before. | `tests_app/test_paper_totals.py` -k ac_r06: 2 failed, then 22 passed; `test_d68_today_total.py` 10 passed (one test that pinned the whole-pause rule rewritten); frontend `home-figures-d56`, `paper-list-4b`: 45 passed. |
| N-47, settled trade's Positions card has no settlement sentence | Fixed, not tested | The list reply already carried the server's settlement sentence; the card's reader dropped it. | 1 screen; the card prints the same server sentence as the builder. A leg that expired worthless still shows the server's exit text (e.g. 0.00) - that is the settlement price. | `paper-list-4b.test.js`: 1 failed without the fix (lead's run), then 29 pass; app test `test_paper_triggers_routes.py` -k settlement: 2 passed. |
| N-48, settled trade's builder shows "No legs yet" and Add leg | Fixed, not tested | The empty-legs block did not know the trade was finished. | 1 screen; a trade whose book has closed rows and no open position shows no empty-legs block and no Add leg / Add/Edit. | `builder-completed-n48.test.js`: red, then pass. |
| N-44, "No price for:" above a priced table after the close | Fixed, not tested | The Paper P&L panel took the unpriced line from the tracking reply (live prices only) when the book had none. | One reader: the line comes from the book read only. | `one-source-d41.test.js`: 1 failed with the old line, then 18 pass. |
| N-45, prices keep moving after the close under "Prices are from 15:30:00" | Deferred #752, question LR-Q14 | The label time is clamped to the close; the figure is the feed's latest quote. | - | - |
| N-45 / ADR-330 (36), prices keep moving after the close under "Prices are from 15:30:00" (round 2: LR-Q17) | Fixed, not tested: (a) frozen at the close, (b) own time; (c) deferred; #752 stays open | Round 1 froze the figure at the last quote made by the close, but a contract first priced after the close (API restart after 15:30, strike first subscribed after hours) was still clamped by `NormalizedQuote.price_at` to "15:30:00" while showing a later price. | Places that clamp a post-close price time: 1 (`quote.py price_at`); 0 after: a trading-day post-close quote carries its own time (before the open, holiday and weekend stay at the previous close, F-19). | `tests/marketdata/test_close_freeze.py` (path a 99.75, path b 100.10 at 15:33:48, in-hours guard and reopen, fresh pre-open) and `tests_app/test_close_freeze_routes.py` (path b, one leg of each kind). |
| ADR-330 (39), D-69: an index frozen while option frames kept arriving read live (owner 26 Nov ~21:00 IST) | Fixed, not tested (review SHIP); D-69 root cause unconfirmed: the change detects a frozen index, it does not explain it | Feed health was judged on the whole feed, so an index with no tick for minutes read live while option frames arrived (F-32). | Places that judge an index quote's own age: 0 before; 1 after (`FeedState.quote_health`, read by `QuoteBook`; 60 s, `detection.index_quote_max_age_seconds`, market hours; options keep the feed word). | `tests/marketdata/test_index_quote_age.py`, `tests_app/test_paper_trigger_unheld_index.py` (two ADR-330 (39) tests), `tests_app/test_paper_monitor.py` (a stale index tick does not fire an armed exit; a fresh crossing tick does). |
| AC-R10, Compare's "Open in builder and prepare basket" greyed after the close | NOT CHECKED (by design after the close: "Wait for fresh prices") | - | - | Re-test at the open, below. |

## Re-test: after-close items (next market day)

1. AC-R10 (at the open, after 09:15): Alerts > "Compare approaches" on a paper trade's alert > "Open in builder and prepare basket" is enabled once prices are live; click it: the builder opens on that trade with the chosen approach's legs staged.
2. N-47 (after the close on an expiry day, or on SENSEX trade 173 now): Positions > Paper > Show closed positions > the settled card's closed legs read "Paper - settled at expiry: SENSEX closed at 84,328.59", the same as the builder.
3. N-48: open the builder of trade 173: no "No legs yet", no Add leg; the closed legs and "Closed: result" show.
4. N-44 (after the close): builder of a running paper trade > Paper P&L panel: no "No price for: ..." line when every leg shows a price.
5. AC-R06 (after the close, with one settled trade): Home's "Total P&L" shows a figure over the trades that can be priced, with the count line, and equals the sum of those rows on My Strategies.

## Owner answers of 26 Nov ~16:00 IST (ADR-330 (28) to (31))

| Item | Status | What changed | Tests red, then green |
|---|---|---|---|
| ADR-330 (28), Add to Paper while prices are not live (was N-40 / LR-Q12) | Fixed, not tested | When the page's one price rule (priceState) says prices are not live, the confirm list shows a tick box labelled "Prices are not live; the entry is the last captured price, as of HH:MM." and Confirm stays disabled until it is ticked; a typed entry price keeps the line. Choices: the time is the OLDEST capture time of the ticked legs (no leg reads fresher than it is); with no readable capture time the ", as of ..." part is dropped; after the close and while the builder has no priced answer, prices count as not live, so the tick box shows then too. REQ-109 AC-1 carries the sentence. | `paper-add-not-live.test.js`: 3 failed, then pass; full frontend suite 3,004 pass. |
| ADR-330 (29), P&L Table with the API down (was D-N07 remainder / LR-Q10) | Closed as designed | The error block stays: with the outcome unreadable there are no rows to dash. No build. | - |
| ADR-330 (30), the builder's "Settings" button (was N-38 / LR-Q11) | Fixed, not tested | The button reads "View" (label only; its popover's screen-reader name "Builder settings" is unchanged). REQ-138 AC-1 carries the label. | `gcui-legs.test.js`: red "expected 'Settings' to be 'View'", then 28 pass. |
| ADR-330 (31), Deleted / Restored in the history (was LR-Q13) | Handed to Lane J | See below. | - |

### Handed to Lane J: ADR-330 (31)

It needs a migration (Lane R adds none). Evidence: `strategy_history.change_summary` (JSONB) items are checked on every
insert by the plpgsql validator `ofo_strategy_change_items_valid` (`backend/ofo_app/alembic/versions/0008_strategy_store.py`
~327-346: kinds underlying, leg_removed, leg_added, quantity, field, legs_reordered, replaced_unreadable, restored;
`ELSE ok := FALSE`, SQLSTATE 23514); its body is md5-pinned in the allowlist function; migrations 0011 (entries_repriced,
the `_NEW_SIMPLE_KINDS` pattern) and 0025 (renamed) widened it the same way. No existing kind fits: `restored` means
"restored to version N" and requires `seq` (`backend/ofo_app/strategy_store.py` ~488). Needed: kinds `deleted` and
`undeleted` with exactly `{kind}`, the md5 re-pinned, the kinds mirrored in `backend/ofo/strategy/definition.py` ~308 and in
the summary text / catalogue labels of `stored_form.py`; then `delete_draft` / `undelete_draft` (`strategy_store.py`
~359-383, both inside `begin_nested`, so a failing history write rolls the delete back) write one entry each (bulk: one per
strategy). `strategy_history.at` is stamped by the database, so the times need nothing.

## Re-test: ADR-330 (28) and (30)

1. With live prices: Add to Paper on a new shape: no tick box; Confirm works as before.
2. After the close (or with the feed stopped): Add to Paper: a tick box "Prices are not live; the entry is the last captured price, as of HH:MM."; Confirm stays grey until ticked.
3. Type your own entry price for one leg: the tick box still shows; tick, Confirm: the typed price is the entry.
4. Builder: the button beside the search reads "View" and opens the same "Show legs as" choice.
5. Nothing else in the confirm list changed wording.

## To file as deferred issues (ADR-330 (36), round 2; not filed)

1. **ADR-330 (36) (c): start-up read of each contract's 15:30 close.**
   Evidence: `backend/ofo/marketdata/quote.py` `price_at`; steps: start the API after 15:30 with a held contract and open the trade: the figure is the first frame received (e.g. 100.10 as of 15:33:48), not the 15:30 close. The broker adapter's day read exists (`backend/ofo_app/paper_settlement.py:274` `owner_close_of` reads a Kite DAY candle; `price_history_source.day_close_reader`).
   Spec basis: ADR-330 (36) (c), LR-Q17 ("exact close later"), ADR-200 (2), ADR-015.
   Done when: a process started after the close shows the 15:30 close for a held contract, labelled "Prices are from 15:30:00".
2. **The depth popup after the close shows the latest frame, not the frozen close.**
   Evidence: `backend/ofo/marketdata/feed_health.py` `depth_after_close` (~346-349) reads `e.quote`/`e.depth`, and `backend/ofo_app/chain_push.py` `_last_trade_at` (~401) beside it; review run: figure 99.75, popup bid 100.05 / ask 100.15. Steps: after the close, with a frame after 15:30, open the depth popup of a held contract.
   Spec basis: ADR-330 (36), ADR-200 (1) and (2), REQ-080 AC-7.
   Done when: depth after the close (bid, ask, day stats) comes from the served quote, the same frame as the figure.
3. **The REST index spot after hours is the post-close value.**
   Evidence: `backend/ofo_app/live_market.py:477` `_index_reading` / `index_spot` (via `spot_source`) returns Kite's current REST `last_price`, while the chain and index header show the frozen tick. Settlement is unaffected. Steps: after the close compare the REST spot with the index header.
   Spec basis: ADR-330 (36), ADR-200 (2), ADR-119.
   Done when: the after-hours spot goes through the same cut-off (`made_by_the_close`).

### More to file as deferred issues (Opus re-check of ADR-330 (36) round 2, 26 Nov evening; not filed)

- **A frame with no exchange time is labelled with its arrival time after the close.** Evidence: `backend/ofo/marketdata/quote.py:197` returns the quote's own time, which is the arrival time when Kite sends no exchange time (`backend/ofo_app/kite_provider.py:184`); review run: a fresh process, a frame with no exchange time arriving 21:05:12 is labelled 21:05:12. Spec basis: F-19 (a stamp that is not a price time is never shown as one), ADR-200 (2). Done when a post-close frame without an exchange time is labelled as the previous close (or shown unpriced) and a test pins it.
- **The broker-status reply still clamps a path-(b) price to 15:30:00.** Evidence: `backend/ofo_app/broker_status.py:144` uses `price_time`; no frontend file renders `live_market_closed` today (API only). Spec basis: ADR-330 (36) (b). Done when it reads the same own-time rule as `NormalizedQuote.price_at`.
- **Index age is measured from the exchange stamp against the server clock with no lower bound (ADR-330 (39)).** Evidence: `backend/ofo/marketdata/kite_provider.py:181`: a stamp 10 min ahead of the server clock reads available; `paper_monitor.on_quote` and `paper.price_of` accept a future stamp while `spot_source` refuses it as `tick_in_future`. Spec basis: ADR-330 (39), ADR-327 (2). Done when one rule refuses a future stamp everywhere.

## Re-test: ADR-330 (34), (35), (36) (next market day and evening)

1. (34) Builder: add two legs (unsaved): under the bar "Unsaved legs are not kept if you reload or close this page. Save to keep them."; Save: the line goes. A running paper trade with one pending change shows it too.
2. (35) After the close with one settled or unpriced trade: Home's Total P&L is the sum of the priced trades with the count line (as AC-R06), now owner-approved.
3. (36a) After 15:30 with the API running since before the close: a running paper trade's prices stay at their last pre-close values while "Prices are from 15:30:00" shows; they do not change over 10 minutes.
4. (36b) Restart the API after 15:30, open the same trade: each leg shows a price labelled with its own time ("as of 15:4x:xx"), never "Prices are from 15:30:00".
5. Mixed (one leg of each kind, e.g. add a new strike after the close to a builder that held its legs through the close): note the banner time; it follows the open question LR-Q18.

## D-15 re-check (round 1, branch lane-r-dd)

| Finding | Status | What the screen shows today | Verdict |
|---|---|---|---|
| D-15, paper trade summary names no price basis; "Plan: Get Rs X" line withdrawn | Question LR-Q19 (basis label done to spec; plan line not rebuilt) | The server (`routes/outcome.py` `_with_price_basis`) sets `summary.price_basis_text` from the paper book, shown under the Get by `MoneySummary.vue` (`data-testid="money-basis"`). (a) unplaced plan / no paper strategy: "At plan prices". (b) fully filled paper trade: "At paper fill prices". (c) partly filled: "At paper fill prices for 3 of 4 legs; the rest at their entered prices", or "At their entered prices: none of 4 legs is a paper fill". (d) one leg exited: only the legs still held are counted, so 3 held legs that match the book read "At paper fill prices" (the exited leg is not named). Book unreadable: "At their entered prices (the paper book could not be read)". `plan_line` is always null; no "Plan: Get Rs X" line appears. | Done to spec for the basis label (ADR-321 (8), ADR-322 (2)); plan line: spec says "only when every leg is a fill" but is silent on an exited leg and on the wording, so not built: LR-Q19 |

Proof, run this turn: `python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_outcome_price_basis_d15.py` = 13 passed (a: `test_no_paper_strategy_says_plan_prices`; b: `test_every_leg_a_fill_says_paper_fill_prices_and_serves_no_plan_line`; c: `test_an_edited_leg_at_a_live_price_is_not_called_a_paper_fill`, `test_no_leg_matching_the_book_says_so`; d: `test_an_exited_plan_leg_never_prices_the_held_subset_as_the_plan_credit` pins only `plan_line is None`; it does not pin the basis text of the held subset, which I read from the code). `npx vitest run tests/price-basis-d15-d17-d18.test.js` = 7 passed.

## For the PC session: D-27 (no cause proven; read-only, one step)

Core of the step: find out whether the server has the adjustment rows for strategy 155 or the screen loses them.

1. Log in to the app in the browser on the PC. Open the builder on trade 155 (C1 155) and open the "Adjustment history" section (it reads on every opening). Open devtools, Network tab, filter "adjustment-history".
2. The request is `GET /api/strategies/155/adjustment-history` (no body; route `backend/ofo_app/routes/adjustment_history.py`, reads the stored paper orders owned by the logged-in user). Or paste that URL in the address bar of the same logged-in browser. Read only: it places nothing.
3. Copy the full JSON reply and save it as `d27-155-adjustment-history.json` (also copy the status code). Do not edit it.
4. Record: (a) `rows.length`; (b) for each row its `step` (entry / adjustment / settle / stop), `number`, `at`, `is_exit` and `orders[].kind` / `side` / `quantity`; (c) `totals.adjustments_used` and `totals.adjustments_max`; (d) at the same moment, what the builder's Adjustment history section shows: the "no step recorded" line (`steps-none`), the error line, or N rows, and their order.
5. Decide: rows present in the JSON but the section empty or short = a screen defect (`frontend/src/components/strategy/AdjustSteps.vue`, with the page's gate `paper && savedId && !showNumbers && state === 'no-draft' && !opening` at `StrategyBuilderPage.vue:1351`; note whether the section was shown at all). A 404 or `rows: []` = the server has no rows for 155: then also open `GET /api/paper/strategies/155` (the paper book) and save it as `d27-155-paper-book.json`; record `orders[]` (count, kind, time of each) and `status_word`. Orders there but no history rows = a server defect in `ofo.engine.adjust_history` (batch rule: one `placed_at` per batch); no orders there either = the adjustments were never stored (a placement defect). Rows equal and screen equal but the owner expected a second adjustment = the second change was never placed (check the Orderbook for 155).
