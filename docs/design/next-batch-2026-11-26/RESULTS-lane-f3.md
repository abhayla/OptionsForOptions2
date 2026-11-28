STATUS 20:50 | batch 1 pushed 5b3f8ad11 (TOTAL PASS); batch 2 = items 5-8 + FJ2 f23 merged (4297f7065), full check running | next push batch 2 by 01:30 IST Sun | blocker: none (send_message to the coordinator refused: elevated_session_untrusted_device; this line is the report)

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

## For the owner lane
- Lane F1/FJ2, `PaperStrategies.vue` row `paper-closed-leg`: the cells `paper-closed-unbooked` and `paper-closed-pnl` are `pnlText(null)` (a dash). Print `c.unbooked` and `c.pnl` (new fields of readPaperList's closed row), else `c.pnlReason`, when present.
- Backend (Lane RA2/B2) `backend/ofo_app/routes/paper.py` `_closed_row` (line ~716): add `unbooked_text` and `pnl_text` (a closed lifecycle has nothing left to book: its P&L is its booked) or `pnl_reason_text`. Until then the Positions closed row keeps its dash cells; ClosedRows.vue (P&L table, builder) shows the two columns only when the server sends a figure or reason.
- `LiveStrategyCard` leg table (Lane F1): same two fields.

## Decided for the owner
- A refused Positions read with the connection read saying "not connected" is the not-connected state (one sentence + Retry), as the 200 path already is.
- A LIVE book with a readable `as_of` is a stored close: "As of <time>" line (RA2 note).

## Question for the owner
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
