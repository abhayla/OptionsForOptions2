# Status ledger: 23 Nov live iron condor test (GC-ICLIVE)

Purpose: one row per issue of the 23 Nov live iron condor test (D-01 to D-71). Update the row at every stage change.
Sources: `session-handover-2026-11-24.md`, `ic-live-test-2026-11-23-issues.md`, the five GC-ICLIVE contracts.

Allowed status values: `Open`, `Root cause found`, `Fix in progress`, `Fix built, in review`, `Fixed, not tested`,
`Needs owner decision`, `Parked`, `Could not reproduce`, `Not a defect`, `Feature request (parked)`.
"Closed" is used only after a screen check on the owner's PC.

| Id | Status | Part | Commits | What changed (one plain line) | Proof (test + result line) | Screen check owed |
|---|---|---|---|---|---|---|
| D-01 | Fixed, not tested | A | 48040b5, 1783674, 383d57e | Crossed stop level is refused with the approved sentence; a leg stop is judged on its own live price; every no-price state still saves | frontend/tests/paper-stops.test.js, tests_app/test_paper_triggers_routes.py: result line pending A7 rerun | Type "Above" a level below the index: red line "Not saved: the live price is already at or beyond this level, ..." and no row; then a safe level saves |
| D-02 | Fixed, not tested | A | 5f3b84a | Paper batches against an open position are recorded buys first; Exit button lists buys first | tests_app/test_paper_batch_buys_first.py, frontend/tests/paper-exit-rows-buys-first.test.js: result line pending A7 rerun | Roll one side of a paper condor: Orderbook lists the buy-back of the short before the sale of its hedge |
| D-03 | Fixed, not tested | A | 0a26b48, 3696188, 11754f6 | Index exits set before an adjustment stay armed and are marked with the new short strike; Keep this level; confirm list names armed exits | tests_app/test_paper_armed_exits.py, frontend/tests/paper-armed-exits.test.js: result line pending A7 rerun | Set an index exit, adjust the trade: row marked "set before the last adjustment" with the new short strike; Keep this level gives "Kept:"; the confirm list names the armed exit |
| D-04 | Fixed, not tested | A | 0713b6e, 340155a, 2915daf, 6972d3d | Plan maximum and rules come from the entry shape; at the maximum only risk-cutting routes are accepted, with the true count | tests_app/test_d04_entry_shape.py, tests_app/test_paper_adjustment_limit.py, tests/adjustment/test_approach_compare.py: result line pending A7 rerun | A trade at 2 of 2: rolls withheld "plan maximum of 2 reached"; Reduce / Close read "3 of 2; this would be adjustment 3 ..." and CAN be placed; Exit all shows no count; trade 164 reads "1 of 2" |
| D-05 | Fixed, not tested | A | d8e9375, e3ea2b3, c65bc5e, ef733f0 | Stop save is never silent (Saved / Already set / Not saved / Saving); failed refresh pauses figures and blocks Exit | frontend/tests/paper-stops.test.js, frontend/tests/paper-strategies.test.js, tests_app/test_paper_triggers_routes.py: result line pending A7 rerun | Save lines are screen-proven. Owed: after a failed refresh, figures go to a dash and Exit is blocked (market closed looked the same) |
| D-06 | Open | B | - | - | - | Issue: Live Strategies card shows different max profit/loss/breakevens than the builder after an adjustment |
| D-07 | Open | B | - | - | - | Issue: The same strategy shows different P&L on the card, the detail page and the positions page at the same minute |
| D-08 | Open | B | - | - | - | Issue: On expiry day the Estimated-now numbers and what-if assume about a day left |
| D-09 | Open | B | - | - | - | Issue: Paper fills in adjustments land far from the quote shown on the dialog |
| D-10 | Open | B | - | - | - | Issue: Closed legs lose their own booked P&L or exit price; it shows on the wrong leg or nowhere |
| D-11 | Open | B | - | - | - | Issue: Add Booked switch changes the chart but not the max profit/loss/breakeven tiles |
| D-12 | Open | B | - | - | - | Issue: Theta per day is implausibly large on expiry-day condors |
| D-13 | Open | B | - | - | - | Issue: Max profit/loss are after charges but the P&L table, payoff dialog and API profit_left say before/gross |
| D-14 | Open | B | - | - | - | Issue: The Charges line shows entry charges only while the P&L deducts a round trip, and there are three charge estimates |
| D-15 | Open | B | - | - | - | Issue: Paper entry prices are re-quoted at Add to Paper and differ from the plan, with no warning |
| D-16 | Open | B | - | - | - | Issue: Breakevens are on different bases on different screens, none labelled |
| D-17 | Open | B | - | - | - | Issue: Time value is negative and uses different prices from the credit, with no label |
| D-18 | Open | B | - | - | - | Issue: The same leg shows 2-4 different prices in the same second |
| D-19 | Open | B | - | - | - | Issue: Option chain LTP often sits outside its own bid/ask |
| D-20 | Open | B | - | - | - | Issue: Put-call parity implies a forward below spot (SENSEX about 72 pts, NIFTY about 4 pts) |
| D-21 | Open | C | - | - | - | Issue: The Reduce suggestion raises max loss and the preview does not say why |
| D-22 | Open | C | - | - | - | Issue: A fired stop is missing from Alerts History, and the closed trade's own page gives no reason or index level |
| D-23 | Open | C | - | - | - | Issue: Stop-out exit rows in the orderbook are labelled Add |
| D-24 | Open | C | - | - | - | Issue: An armed conditional exit is not shown on the builder or tracking panel |
| D-25 | Open | C | - | - | - | Issue: Take profit, whole strategy is offered at a loss with the same numbers as Exit |
| D-26 | Open | C | - | - | - | Issue: The Review adjustment button vanishes when the idea lapses, so a live idea cannot be acted on |
| D-27 | Open | C | - | - | - | Issue: Adjustment history is empty after adjustments |
| D-28 | Open | C | - | - | - | Issue: Running strategies show state draft in the strategy endpoints but LIVE in the paper endpoints |
| D-29 | Open | C | - | - | - | Issue: Alert list has no times, the bell count does not map to what is unread, and old scenario alerts bury the real ones |
| D-30 | Open | C | - | - | - | Issue: Adjustment-opportunity counters and the row count use different units |
| D-31 | Open | C | - | - | - | Issue: The same trigger value differs between drawer, panel and opportunity list |
| D-32 | Open | C | - | - | - | Issue: Watch an index level (drawer) looks like a Conditional exit but does not exit |
| D-33 | Open | C | - | - | - | Issue: Add to Paper is allowed despite Not enough funds on a 0-day condor |
| D-34 | Feature request (parked) | C | - | Not built (owner 24 Nov, ADR-320): No profit-target amount or take-profit stop exists on the Stops panel | - | Issue: No profit-target amount or take-profit stop exists |
| D-35 | Feature request (parked) | C | - | Not built (owner 24 Nov, ADR-320): Notification settings say no channels are set up, with no way to add one | - | Issue: No notification channel can be added |
| D-36 | Open | D | - | - | - | Issue: Adjustment check and Review adjustment drawer are very slow or fail with a server error |
| D-37 | Open | D | - | - | - | Issue: What-if shows nothing for a target level or date |
| D-38 | Open | D | - | - | - | Issue: Other pages load slowly or time out |
| D-39 | Open | E | - | - | - | Issue: Live-data status messages contradict the prices on the same page, then recover |
| D-40 | Open | D | - | - | - | Issue: Header totals blank and cards fail because of expired scenario strategies |
| D-41 | Open | E | - | - | - | Issue: Live and My Strategies cards show no P&L or health, and a card can stay Loading |
| D-42 | Open | E | - | - | - | Issue: My Strategies shows the original legs and closed strategies are missing |
| D-43 | Open | E | - | - | - | Issue: Strategy names are cut off to about 8 characters |
| D-44 | Open | E | - | - | - | Issue: Stop list uses raw contract names, different from the form |
| D-45 | Open | E | - | - | - | Issue: Adjustment comparison table is hard to read |
| D-46 | Open | E | - | - | - | Issue: Greeks and max profit/loss display rounding hides the real number |
| D-47 | Open | E | - | - | - | Issue: Builder strike picker is confusing |
| D-48 | Feature request (parked) | E | - | Not built (owner 24 Nov, ADR-320): Edit-leg form has no expiry control; legs must be removed and re-added | - | Issue: No control to change the expiry of existing legs |
| D-49 | Open | E | - | - | - | Issue: Lots/Quantity switch does not relabel the column header |
| D-50 | Open | E | - | - | - | Issue: Payoff chart shows no tooltip on hover or arrow keys |
| D-51 | Feature request (parked) | E | - | Not built (owner 24 Nov, ADR-320): Strategy Chart tab says it is not available on paper strategies | - | Issue: Strategy Chart tab says it is not available on paper strategies |
| D-52 | Open | E | - | - | - | Issue: Ready-made shapes text points to a panel that is not there |
| D-53 | Open | E | - | - | - | Issue: Builder title New Strategy is not editable and the name box silently limits to 20 characters |
| D-54 | Open | E | - | - | - | Issue: Playbook editor Test does nothing and Delete needs no confirmation |
| D-55 | Open | E | - | - | - | Issue: Option chain filters apply late and Change / OI Change columns are always blank |
| D-56 | Open | E | - | - | - | Issue: Home overview shows only index values |
| D-57 | Open | E | - | - | - | Issue: Dates on the adjustments page use US month/day |
| D-58 | Open | E | - | - | - | Issue: Small wording problems: zero-price message, quote characters in names, tested-side wording |
| D-59 | Fixed, not tested | A | none | No code defect: stops were never stored by settlement; no change made | none: result line pending A7 rerun | Stops survive a part settlement at 15:45 on a two-expiry paper trade |
| D-60 | Fix in progress | A | 813fec2, 1a81d59, e1b210d | Adding a held contract asks Increase / Keep separate / Cancel on builder paths (one door); Add to Paper refuses a kept duplicate. Strike stepper onto a held contract warns but does not ask (open) | frontend/tests/leg-duplicate-d60.test.js, tests_app/test_paper_duplicate_leg_d60.py: result line pending A7 rerun | Round 2 not screen-tested: question box (Escape), Increase over the lots limit, Add to Paper refusing a kept duplicate; stepper after A5 |
| D-61 | Open | E | - | - | - | Issue: Buying back one short leaves a lone long option with no note on screen |
| D-62 | Feature request (parked) | C | - | Not built (owner 24 Nov, ADR-320): Few repair routes on a small condor (partial profit refused at 1 lot; both rolls refused on 2 lots) | - | Issue: Few repair or profit-taking routes on a small condor |
| D-63 | Open | B | - | - | - | Issue: Two-expiry trade: P&L table omits booked legs and Greeks sum across expiries unmarked |
| D-64 | Open | E | - | - | - | Issue: After the 15:30 close the page shows raw errors and never says settlement comes at 15:45 |
| D-65 | Open | E | - | - | - | Issue: Renaming a paper trade from the builder fails, and its status differs between lists |
| D-66 | Open | E | - | - | - | Issue: Completed page "last saved" shows the last builder save, not the close time |
| D-67 | Open | E | - | - | - | Issue: Adjustment toasts pop up within minutes of opening a trade and cover page buttons |
| D-68 | Open | E | - | - | - | Issue: No screen gives the day total for the test trades |
| D-69 | Open | C | - | - | - | Issue: Index value frozen at 25,366.40 on reads from 15:15 to 15:27 |
| D-70 | Open | C | - | - | - | Issue: 1 Dec put prices kept moving after the market-closed banner |
| D-71 | Open | C | - | - | - | Issue: Expiry settlement leaves no record: no index value, no time, no word "settled" |
