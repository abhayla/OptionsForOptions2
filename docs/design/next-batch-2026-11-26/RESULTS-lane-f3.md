STATUS 00:40 IST 29 Nov | CI-2 spec fixes + W-25 D tests + Positions not-connected fix: built, merged with wave 1 (8425feea), full check running, ONE push by 01:30 | still failing browser specs: 0 (8 screen specs 1652 passed / 0 failed / 20 flaky-on-retry / 2 skipped; real-API files 14 passed / 2 skipped) | blocker: none

# RESULTS Lane F3 (frontend tail), branch fix/r3-frontend-f3-1128, base origin/integration/weekend-r3-1129 + FJ2 68a46dd62 + RA2 (fix/r3-leftovers-2-1128)

| Item | State | Red line (first, on the base) | Green |
|---|---|---|---|
| 1 I-113 Real total after disconnect | Fixed, not tested in a browser | real-total-disconnect-f3-1128: a 200 read with `broker_connected:false` that still carried the stated +650.00 kept printing it 70 s later (1 of 2 red; the hung-read case was already green) | 2/2 |
| 2 I-199 stored close as-of | Fixed, not tested in a browser | stored-close-asof-f3-1128: a LIVE book with `as_of` printed no time (1 of 3 red) | 3/3; paper-pause-as-of's old assertion "an as_of is never printed on a non-paused book" replaced (RA2 rule) |
| 3 I-207 raw 409 JSON | Fixed, not tested in a browser | positions-not-connected-409-f3-1128: the JSON text and the sentence printed twice (3 of 4 red) | 4/4 |
| 4 I-91 closed rows | Partly: the page reads and prints the server's fields; the server sends none yet | closed-row-cells-f3-1128 (3 of 4 red) | 4/4; ClosedRows users 7 files / 83 tests |
| 5 I-203 Completed rows in My Strategies | Fixed, not tested in a browser (by design: ADR-259) | my-strategies-completed-pointer-f3-1128: no sentence said where Completed rows are (2 of 4 red) | 4/4; My Strategies files 6 / 72 tests |
| 6 I-209 paused sentence, mixed states | Not reproduced on the base: FJ2's one scope rule already prints it once (3 PAUSED + 3 NOT_CONNECTED + 2 stored closes, 2 as_of cases); regression test kept | paper-paused-mixed-f3-1128 green on first run | 2/2 |
| 7 I-200 Adjustments page Retry | Already fixed on the base (Lane FC2, I-86: ListLoadFailed with Retry on this page); not rebuilt | list-load-failed-r2-fc2 (includes "Adjustment opportunities") | 14/14 |
| 8 I-201 dismissed row reason | Fixed, not tested in a browser | opp-dismissed-reason-f3-1128: with a reason sent the page already printed it; with none the row said only "You dismissed this" (2 of 3 red) | 3/3; adjustment tests 5 files / 50 |
| 9 W-15 | Not built (product decision), see Question for the owner | | |

Guards on the final head: paper-paused-once-fj2-1128 4, home-paused-asof-fj2-1128 2, exit-market-closed-adr330-60 7, exit-rule-all-doors-r3-fj (all) green; Positions tests 71/71 after item 3.

Item 1 cause: `realTotals` read `real_pnl.state === 'stated'` and printed its `pnl_text` even when the reply said `broker_connected:false`. Class fix: a read that says no broker is connected never yields a figure; the reason is the server's, else the not-connected line.
Item 2: the one as-of formatter is `istTime` (the layout notice's). Row text "As of <time>" is printed in the row's state line (PaperStrategies already prints `stateText`). The Home "left out" count drop is server side (`totals.left_out_count`, RA2): the page prints the server's `left_out_text` as sent, so nothing to change.
Item 3 cause: with a refused read and the connection read saying disconnected, the page printed the refusal's four parts in the block AND its first part in the Real totals card; a refusal whose parts were the raw JSON printed it both times. Class fix: not connected + refusal = ONE sentence in the block (the server's sentence when it reads as a sentence, never `{`, `error_class` or a class code; else the not-connected line) + Retry; the totals card says only the dash.

## Merge with FJ2's hand-over (f23, 4297f7065)
FJ2 built the same defects as my items 3 (D-TG-3), 5 (T2-17) and the Retry of item 7. Merged, both intents kept. Conflict in PositionsPage.vue: FJ2's `plain` filter (a JSON-looking string is dropped) is used by my `looksRaw` and `brokerOffLine`; my one-sentence + Retry block (shared LoadFailed) stays; FJ2's tests positions-409-json-fj2-1128 and failed-load-retry-fj2-1128 and my positions-not-connected-409-f3-1128 are green together (106 tests, 17 files with the FJ2 and Exit guards). One fix in the merge: with `broker_connected:false` my I-113 branch repeated the block's sentence in the Real card (FJ2's test red, 2 instead of 1); the card now keeps only its dash. MyStrategiesPage.vue merged without a conflict (FJ2's empty-state text and my pointer both stay). AdjustPlanSheet.vue and PlanEntry.vue are as the merge gave them.

## Extra item I-66 / D-W2-2 (coordinator message 20:26 IST; after batch 1, so pushed as a third, small push on the coordinator's ask)
Finding: summary cards keep the previous numbers after the data is no longer current, with no "old" tag. Cards read in my pages: Positions Real (hidden after 90 s since the last good read, OLD_FIGURE_TEXT, item 1) and Positions Paper (paused sentence with its time when the refresh fails: already fail closed); Home P&L (paused, as-of); Home Unread (dash plus "Could not be read right now." on a failed read). The gap was Home "Running strategies": read once at mount and never again. Fix, test first (home-reread-f3-1128, 3 of 4 red on the base): re-read every 30 s and on focus; a failed re-read shows a dash and the existing note on that card only. No new wording, no browser clock. Files: HomeOverviewPage.vue only (mine). If W2 saw other cards (a layout price notice, the Live card), tell me the screen: their files are not mine.

## MUST: a stored-close figure must never read as current (commit 45ff71c20)
Case: no broker session, market closed: the server sends a book as state LIVE with `as_of` = the close's real time (RA2). Before: as-of printed on PAUSED / NOT_CONNECTED only; the per-leg time was a bare clock. Built, test first (stored-close-screens-f3-1128, 7 of 9 red on the base; the other two guard that a live book prints nothing), one named test per screen, all green (9/9):
- paper list rows (paperList.js): row line "As of <date, time IST>" (`istTime`, always with the date; a LIVE book with no as_of prints nothing);
- PaperBookPanel.vue: `book-as-of` for LIVE with as_of (`last_price_at` is never sent by the server, so it is not relied on);
- Positions: `totals-paper-as-of` in the Paper P&L card (PositionsTotals.vue, fed by PaperStrategies' summary `storedAsOf`) and the row lines;
- Home: `home-pnl-as-of` under Total P&L;
- the list header totals (PaperStrategies, builder Paper tab): `totals-as-of`;
- totals: the OLDEST stored-close time of the rows (time comparison only, no money), computed in paperList (`withStoredClose`) because the server's `totals_as_of` collects paused books only; the server may add its own later: then the page should prefer it (backend note below);
- per-leg price time (PaperStrategies `paper-ltp-at`): `istStamp` (the clock on today's date, else the whole date).
Touched outside my list, as-of lines only (the coordinator allowed it): PaperBookPanel.vue, PaperStrategies.vue (summary field, one totals line, one stamp call). Tested against a mocked `state: 'LIVE', as_of: <past date>`, not a real RA2 answer (RA2's branch moved to 88500c2a9 after my last merge; I did not merge it into this branch so its backend commits do not ride on this push).
Wording pending owner read: "As of <date, time IST>" (same prefix everywhere).
For RA2 / backend: `totals_as_of` could include stored-close books; the page computes the oldest itself until then.

## W-25 part D (coordinator 22:55 IST, owner's PC round 2, build 829ff65f): a failed or slow read greys every Exit
Reproduced on the Positions paper list (PaperStrategies), test first (exit-slow-failed-read-f3-1128, 5 tests): NOT reproduced. After a good read and a failing refresh, with a leg ticked, Exit is enabled, opens the dialog, the dialog says "Prices are not live..." and, with the market closed, also the server's market-closed sentence (ADR-330 (60)); Confirm is off; nothing is sent. With nothing ticked the button is grey with its plain line (that grey is the tick rule, not the read). A failed FIRST read has no list: the error block with Retry and no Exit control; a slow first read shows the loading line and no Exit control (the API client times out at 10 s; the PC's link at ~134 ms per query makes a long page read time out and show the error block). The tests stay as guards.
What does grey every Exit on a failed read: the builder's book panel (PaperBookPanel: Exit all and each leg's Exit), by the older D-05 / REQ-109 AC-5 rule, with its reason line; exit-gate-d05 pins it. That is the F1b lane's file and a money screen: not changed here.
Possible clash, so not decided: ADR-330 (60) ("Not chosen: grey the Exit button itself") against D-05 (no exit from old prices, the builder greys Exit on a failed read). They agree on Positions (button open, dialog explains, Confirm off) and differ in the builder's panel.

## CI-2: the failing browser specs (coordinator 17:24 UTC, confirmed 23:44 IST)
Classification table and the result: `docs/design/next-batch-2026-11-26/ci2-playwright-classification-f3.md` (98 distinct tests failing on my head, (b) stale spec 97 + (c) 1, (a) none, (d) none; every one fixed to the decided behaviour, none skipped or quarantined). Count still failing after this push: 0 (single-run result above; CI's own run on the build decides). One product change rode in: Positions, not connected, keeps a clean four-part server message with a Retry (my own item 3 had dropped its next action).
Money-path note (Exit): the spec changes for the Exit dialog only re-pin what the product already does (market-state answer asked first, idempotency key in the body, Confirm waits for the re-read after an unknown outcome, a failed read leaves Exit open with the dialog explaining). No Exit code was touched.

## Found, not assigned
- Builder PaperBookPanel.vue (Lane F1b): Exit all / each leg's Exit greyed while a read has failed (D-05) against ADR-330 (60); see "Question for the owner".
- CI frontend job time: Playwright with all specs green is about 9 minutes on 4 workers here; the CI runner uses 2 workers (playwright.config.ts): expect 15 to 18 minutes for that step.

## For the owner lane
- Lane F1/FJ2, `PaperStrategies.vue` row `paper-closed-leg`: the cells `paper-closed-unbooked` and `paper-closed-pnl` are `pnlText(null)` (a dash). Print `c.unbooked` and `c.pnl` (new fields of readPaperList's closed row), else `c.pnlReason`, when present.
- Backend (Lane RA2/B2) `backend/ofo_app/routes/paper.py` `_closed_row` (line ~716): add `unbooked_text` and `pnl_text` (a closed lifecycle has nothing left to book: its P&L is its booked) or `pnl_reason_text`. Until then the Positions closed row keeps its dash cells; ClosedRows.vue (P&L table, builder) shows the two columns only when the server sends a figure or reason.
- `LiveStrategyCard` leg table (Lane F1): same two fields.

## Decided for the owner
- A refused Positions read with the connection read saying "not connected" is the not-connected state (one sentence + Retry), as the 200 path already is.
- A LIVE book with a readable `as_of` is a stored close: "As of <time>" line (RA2 note).

## Question for the owner
- W-25 D / builder Exit on a failed read: ADR-330 (60) says the Exit control opens its dialog and the dialog gives the reason ("Not chosen: grey the Exit button itself"); D-05 / REQ-109 AC-5 (tests exit-gate-d05) grey Exit all and each leg's Exit in the builder's book panel while the read has failed. On Positions the two already agree. Real case: PC round 2, ~134 ms per query, read slow/failed: every Exit greyed, the market-closed sentence never reached. Recommendation: make the builder's panel open the same dialog (as Positions does since 28 Nov, FJ r3), which says "Prices are not live" and keeps Confirm off; the same fail-closed result with a reason the user can read. Lane F1b owns PaperBookPanel.vue.
- W-15 (LegList.vue): the B/S badge of a leg is a plain span; there is no side toggle. Real case: W-15, two identical legs (same expiry, strike and type): the user cannot flip one to the other side in the list, only delete and re-add (TG: "not built"). A toggle changes what the builder lets a user do, so it is a product decision. Recommendation: build it as a click on the B/S badge that flips that leg only, with Undo, in LegList for the builder, after you approve the wording.
- Does the Real total hide at 90 s (the server's own stale rule, as built) or earlier? OLD_FIGURE_TEXT "The real P&L figure is more than 90 seconds old and is hidden until the next read." is marked pending owner read in source. Recommendation: keep 90 s: the page re-reads every 30 s, so a figure older than 90 s means three reads failed.

## New wording for the owner to read
- My Strategies pointer: "Completed strategies are listed under Strategies > Completed Strategies." (data-testid completed-pointer)
- Adjustments, dismissed row with no reason: "No reason given"
- "As of <time>" (stored-close row line, from paperList STORED_CLOSE_PREFIX)
- Positions not connected: reuses "No broker is connected, so no real positions are shown." (already pending read)

## Spec line for item 5
ADR-259 (6 Nov 2026): a strategy whose every leg is closed leaves My Strategies' open list and Live Strategies and is listed on Strategies > Completed Strategies. So My Strategies lists no Completed rows by design; the page now says where they are.

## Not done
- nothing in the queue; items 6 and 7 needed no change (see table)

## Tasks
| task | model | minutes |
|---|---|---|
| items 1-4 | Sonnet (this session) | 55 |

SAFE TO CLOSE after the push of 29 Nov ~01:00 (head = the pushed head of fix/r3-frontend-f3-1128; left: item 4 needs backend `_closed_row` fields and Lane F1's PaperStrategies cells, item 9 W-15 and the 90 s question are owner questions, nothing proved in a browser)
