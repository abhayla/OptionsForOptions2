STATUS 18:55 | items 1-4: Fixed, not tested in a browser (cloud tests green); batch 1 push in progress | items 5-9 not started | next push batch 2 by 01:30 IST Sun | blocker: none (send_message to the coordinator refused: elevated_session_untrusted_device; this line is the report)

# RESULTS Lane F3 (frontend tail), branch fix/r3-frontend-f3-1128, base origin/integration/weekend-r3-1129 + FJ2 68a46dd62 + RA2 (fix/r3-leftovers-2-1128)

| Item | State | Red line (first, on the base) | Green |
|---|---|---|---|
| 1 I-113 Real total after disconnect | Fixed, not tested in a browser | real-total-disconnect-f3-1128: a 200 read with `broker_connected:false` that still carried the stated +650.00 kept printing it 70 s later (1 of 2 red; the hung-read case was already green) | 2/2 |
| 2 I-199 stored close as-of | Fixed, not tested in a browser | stored-close-asof-f3-1128: a LIVE book with `as_of` printed no time (1 of 3 red) | 3/3; paper-pause-as-of's old assertion "an as_of is never printed on a non-paused book" replaced (RA2 rule) |
| 3 I-207 raw 409 JSON | Fixed, not tested in a browser | positions-not-connected-409-f3-1128: the JSON text and the sentence printed twice (3 of 4 red) | 4/4 |
| 4 I-91 closed rows | Partly: the page reads and prints the server's fields; the server sends none yet | closed-row-cells-f3-1128 (3 of 4 red) | 4/4; ClosedRows users 7 files / 83 tests |

Guards on the final head: paper-paused-once-fj2-1128 4, home-paused-asof-fj2-1128 2, exit-market-closed-adr330-60 7, exit-rule-all-doors-r3-fj (all) green; Positions tests 71/71 after item 3.

Item 1 cause: `realTotals` read `real_pnl.state === 'stated'` and printed its `pnl_text` even when the reply said `broker_connected:false`. Class fix: a read that says no broker is connected never yields a figure; the reason is the server's, else the not-connected line.
Item 2: the one as-of formatter is `istTime` (the layout notice's). Row text "As of <time>" is printed in the row's state line (PaperStrategies already prints `stateText`). The Home "left out" count drop is server side (`totals.left_out_count`, RA2): the page prints the server's `left_out_text` as sent, so nothing to change.
Item 3 cause: with a refused read and the connection read saying disconnected, the page printed the refusal's four parts in the block AND its first part in the Real totals card; a refusal whose parts were the raw JSON printed it both times. Class fix: not connected + refusal = ONE sentence in the block (the server's sentence when it reads as a sentence, never `{`, `error_class` or a class code; else the not-connected line) + Retry; the totals card says only the dash.

## For the owner lane
- Lane F1/FJ2, `PaperStrategies.vue` row `paper-closed-leg`: the cells `paper-closed-unbooked` and `paper-closed-pnl` are `pnlText(null)` (a dash). Print `c.unbooked` and `c.pnl` (new fields of readPaperList's closed row), else `c.pnlReason`, when present.
- Backend (Lane RA2/B2) `backend/ofo_app/routes/paper.py` `_closed_row` (line ~716): add `unbooked_text` and `pnl_text` (a closed lifecycle has nothing left to book: its P&L is its booked) or `pnl_reason_text`. Until then the Positions closed row keeps its dash cells; ClosedRows.vue (P&L table, builder) shows the two columns only when the server sends a figure or reason.
- `LiveStrategyCard` leg table (Lane F1): same two fields.

## Decided for the owner
- A refused Positions read with the connection read saying "not connected" is the not-connected state (one sentence + Retry), as the 200 path already is.
- A LIVE book with a readable `as_of` is a stored close: "As of <time>" line (RA2 note).

## Question for the owner
- none yet (W-15 and the 90 s question go here in batch 2)

## New wording for the owner to read
- "As of <time>" (stored-close row line, from paperList STORED_CLOSE_PREFIX)
- Positions not connected: reuses "No broker is connected, so no real positions are shown." (already pending read)

## Not done
- items 5 to 9 (batch 2)

## Tasks
| task | model | minutes |
|---|---|---|
| items 1-4 | Sonnet (this session) | 55 |
