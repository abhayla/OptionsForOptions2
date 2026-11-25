# GC-ICLIVE final report: the 71 issues of the 23 Nov live iron condor test (25 Nov 2026)

Chain: five unattended cloud parts (A to E), contracts `docs/process/goal-contract-GC-ICLIVE-<A..E>-2026-11-24.md` and
the common rules `docs/process/goal-contract-GC-ICLIVE-common-2026-11-24.md`. Branch `fix/ic-live-test-1123`, draft
pull request #722 (still a draft, not merged, nothing deployed, no real order, no broker call).
Part reports: `docs/process/GC-ICLIVE-<A..E>-report-2026-11-24.md`. Ledger: `docs/process/ic-live-test-2026-11-23-status.md`.

A cloud session cannot open the app, so no issue is Closed. "Fixed, not tested" means: a failing-first test, the fix,
a passed independent review; what is left is the screen check on the owner's PC.

## Counts per status (71)

| Status | Count |
|---|---|
| Fixed, not tested | 57 |
| Could not reproduce | 5 (D-07, D-20, D-50, D-69, D-70) |
| Feature request (parked) | 5 (D-34, D-35, D-48, D-51, D-62) |
| Parked | 2 (D-15, D-27) |
| Needs owner decision | 2 (D-25, D-57) |
| Open or Fix in progress | 0 |
| **Total** | **71** |

## All 71 issues

| Id | Issue | Status | Part | What changed (one line) | Screen check owed |
|---|---|---|---|---|---|
| D-01 | A stop level on the wrong side of the market is accepted without warning and instantly... | Fixed, not tested | A | Crossed stop level is refused with the approved ADR-317 sentence (re-checked character for character in A4); a leg stop is judged on its own live price; every... | Type "Above" a level below the index: red line "Not saved: the live price is already at or beyond this level, ..." and no row; then a... |
| D-02 | Adjustment orders go out in an unsafe order: a naked short is left between fills | Fixed, not tested | A | Paper batches against an open position are recorded buys first; the stop-out alert lists legs in the recorded order; a paper entry is recorded as sent (docstring) | Roll one side of a paper condor: Orderbook lists the buy-back of the short before the sale of its hedge; a stop-out alert lists its legs... |
| D-03 | After an adjustment the armed stops are not refitted and the app does not warn | Fixed, not tested | A | Index exits set before an adjustment stay armed and are marked; the confirm list names armed exits, or says "Could not check your armed exits." when it cannot read... | Set an index exit, adjust the trade: row marked "set before the last adjustment" with the new short strike; Keep this level gives... |
| D-04 | The 2-adjustment limit is exceeded or disappears | Fixed, not tested | A | Plan maximum and rules come from the entry shape through one spot-free entry-type door used by the server limit, the offer, the check route, the worker, the plan and... | A trade at 2 of 2: rolls withheld "plan maximum of 2 reached"; Reduce / Close read "3 of 2; this would be adjustment 3 ..." and CAN be... |
| D-05 | Saving a stop gives no feedback, double-save makes duplicate exits, and a save can be... | Fixed, not tested | A | Stop save is never silent; a failed refresh pauses figures and blocks Exit; the red Not saved line clears only on a refresh started after the failure; only the... | After a failed refresh, figures go to a dash and Exit is blocked; a Not saved line clears on the next good refresh |
| D-06 | Live Strategies card shows different max profit/loss/breakevens than the builder after... | Fixed, not tested | B | The Live card of a paper trade reads the one paper reply (max profit/loss, breakevens with their basis lines) instead of re-computing the open legs | C1 155 card reads +2,380.32 / -4,119.68 and the builder figures |
| D-07 | The same strategy shows different P&L on the card, the detail page and the positions... | Could not reproduce | B | Every paper total already reads book_after_charges; the C4 gap (-245.07 / -118.34 / -401.07) was not found in code. The card now says "Total P&L ... (after charges)"... | Card, builder and Positions totals at the same minute, each labelled after charges with a time |
| D-08 | On expiry day the Estimated-now numbers and what-if assume about a day left | Fixed, not tested | B | Engine already values to 15:30 in exact seconds (the 25300 gap was real time value). On a leg own expiry day a no-IV leg within one tick of intrinsic is valued at... | 0DTE condor after 14:50: Estimated-now curve drawn with the line "a leg with no time value left at the live price is valued at its... |
| D-09 | Paper fills in adjustments land far from the quote shown on the dialog | Fixed, not tested | B | Exit rows of the Review paper orders dialog say "about X, as of HH:MM:SS, the server sets the exit price when you confirm"; fill rule unchanged | Open the dialog, wait, confirm: the row shows its quote time |
| D-10 | Closed legs lose their own booked P&L or exit price; it shows on the wrong leg or nowhere | Fixed, not tested | B | Engine splits each contract into lifecycles: a closed leg is its own row with entry, exit and booked; a reopening starts at 0; a closed book says "Closed: result Rs X... | C1 155: closed short 25400 PE row +643.50 apart from the new long |
| D-11 | Add Booked switch changes the chart but not the max profit/loss/breakeven tiles | Fixed, not tested | B | Add Booked ON: tiles, curves, table TOTAL, 0-P&L columns and BE cells include booked; OFF: open legs with a basis line naming charges and breakevens (ADR-321 (3)) | Toggle the switch on trade 155: tiles, chart floor and table move together; OFF shows the open-legs line |
| D-12 | Theta per day is implausibly large on expiry-day condors | Fixed, not tested | B | On expiry day theta is replaced by "Decay left today: Rs X" (engine leg_decay_left_today) in the builder Greeks, what-if, paper API, chain (per unit) and adjustment... | 0DTE condor: Decay left today about the time value left (157: not 4,008) |
| D-13 | Max profit/loss are after charges but the P&L table, payoff dialog and API profit_left... | Fixed, not tested | B | Served profit_left/loss_left are the ADR-306 after-charges figures (after_split); tiles say after charges, table/curves before; REQ-109 AC-9 wording cites ADR-306 | C4: Total + Profit left = Max profit on one basis |
| D-14 | The Charges line shows entry charges only while the P&L deducts a round trip, and... | Fixed, not tested | B | One cost to close at the live price everywhere; "Charges paid" + "Estimated cost to close"; expiry day pair "If held to expiry" / "If exited now"; the Charges dialog... | 157-type 0DTE trade: two labelled max/profit-left figures; Charges dialog matches the tile |
| D-15 | Paper entry prices are re-quoted at Add to Paper and differ from the plan, with no warning | Parked | B | Done: the server derives the summary price basis from the paper book ("At plan prices" / "At paper fill prices" / N of M), a client cannot claim it; Add to Paper... | Paper trade summary says "At paper fill prices"; Add to Paper shows "plan 36.45" beside a re-quoted price |
| D-16 | Breakevens are on different bases on different screens, none labelled | Fixed, not tested | B | Paper breakevens carry the same charges and booked P&L as Max Profit/Loss, with a basis line; chart marks on the curve basis (ADR-321 (2)) | C6 159: builder, compare and adjust page breakevens agree and say what is inside |
| D-17 | Time value is negative and uses different prices from the credit, with no label | Fixed, not tested | B/C | Owner decided 25 Nov (ADR-322 (2)): time value at live prices, labelled "at live prices, as of HH:MM:SS" (oldest of the spot and leg times); "at the last close... | Builder summary on a live 0DTE condor: label beside the credit basis |
| D-18 | The same leg shows 2-4 different prices in the same second | Fixed, not tested | B | Each builder leg price carries its own quote time; the leg list leads with the server oldest_quote_at; the chain picker uses its quote time; no shared store | Four panels of one leg each show their quote time |
| D-19 | Option chain LTP often sits outside its own bid/ask | Fixed, not tested | B | Chain cell carries last_trade_at; page shows "Last trade 09:19:53 IST" (date if an earlier day). LTP/bid/ask come from one packet (pinned); the rest is a feed-timing... | An LTP outside bid/ask shows an older last-trade time |
| D-20 | Put-call parity implies a forward below spot (SENSEX about 72 pts, NIFTY about 4 pts) | Could not reproduce | B | Carry at 6.5% over 3 days gives F-S +44, not -72 (needs a 17%/yr implied yield); the engine forward uses bid-ask mids, the tester used LTPs; no strike-level snapshot... | Record bid and ask of the same strikes at one moment |
| D-21 | The Reduce suggestion raises max loss and the preview does not say why | Fixed, not tested | C | Every built adjustment approach (all 15 ids) has a "What changes" block: eight measures before against after (profit range, distance to each breakeven, POP, max... | Strategy 164 Reduce reads the put-side reason line; block layout at phone width |
| D-22 | A fired stop is missing from Alerts History, and the closed trade's own page gives no... | Fixed, not tested | C | A fired stop stores the live index value at that moment in its reason; Alerts > History lists fired stops and settlements (GET /paper/alerts/records); the closed... | History tab lists the C3 stop with index value; closed C4 160 page shows the stop reason on its rows (LegList still says "No legs yet") |
| D-23 | Stop-out exit rows in the orderbook are labelled Add | Fixed, not tested | C | Orderbook Kind column keeps the server kind: a stop-out reads Stop, a settlement reads Settled, not Add | Orderbook of C4 160 shows Stop on the stop-out row |
| D-24 | An armed conditional exit is not shown on the builder or tracking panel | Fixed, not tested | C | The tracking panel Plan block lists armed and fired index conditional exits with level and state from the server; the line turns Fired on the tick the strategy exits | C7 161 panel shows "Conditional exit: all legs exit if the index goes above 25,720. Armed." |
| D-25 | Take profit, whole strategy is offered at a loss with the same numbers as Exit | Needs owner decision | C | Built and kept: the Take profit offer names the whole-trade result before charges (the profit test) and after charges beside it. Stopped: ADR-238 (6) "never shown... | After the owner answer: 162-style trade at an after-charges loss |
| D-26 | The Review adjustment button vanishes when the idea lapses, so a live idea cannot be... | Fixed, not tested | C | A lapsed idea says when it lapsed (the close entry of its timeline, not a later append); a live idea keeps its Review button while the trade has an open record | Trade page line "Lapsed at HH:MM:SS IST"; Review stays while the idea is open |
| D-27 | Adjustment history is empty after adjustments | Parked | C | No cause proven (engine and route give rows for two-adjustment shapes; two reviews agree). Built: the section says it is reading, re-reads on every opening, says when... | Open C1 155 adjustment history; record the route reply |
| D-28 | Running strategies show state draft in the strategy endpoints but LIVE in the paper... | Fixed, not tested | C | One server function decides Draft / Running / Completed (status_word on strategy and paper replies; Running = an open leg, ADR-299 (1)); every screen shows the server... | Running condor reads Running on My Strategies, Live and Paper lists |
| D-29 | Alert list has no times, the bell count does not map to what is unread, and old... | Fixed, not tested | C | Alert list, unread count, mark-read and the adjustment inbox read this process's own strategies only, so old scenario PATH alerts no longer bury or inflate the real... | Bell count equals Active rows with no PATH-xx rows |
| D-30 | Adjustment-opportunity counters and the row count use different units | Fixed, not tested | C | Counters state they count conditions, beside conditions and rows; open records on expired contracts lapse as contract_expired with the time (expiry day stays live).... | Opportunities page: conditions/rows line; no 16 Nov PATH rows Open |
| D-31 | The same trigger value differs between drawer, panel and opportunity list | Fixed, not tested | C | A rule with an open record is shown with that record's value on the panel and the drawer; the poll value is labelled Now with its time; drawer lines name their rule | C6 drawer, panel and list show 0.7293 fired, Now beside it |
| D-32 | Watch an index level (drawer) looks like a Conditional exit but does not exit | Fixed, not tested | C | The Watch an index level heading says it only alerts and does not exit (the box is on the Compare page; the only copy) | Heading fits at phone width |
| D-33 | Add to Paper is allowed despite Not enough funds on a 0-day condor | Fixed, not tested | C | The short-funds line reads the ADR-320 (5) sentence; the paper order stays allowed (no server funds check on paper) | 0-day condor with short funds shows the sentence |
| D-34 | No profit-target amount or take-profit stop exists | Feature request (parked) | C | Not built (owner 24 Nov, ADR-320): No profit-target amount or take-profit stop exists on the Stops panel | Issue: No profit-target amount or take-profit stop exists |
| D-35 | No notification channel can be added | Feature request (parked) | C | Not built (owner 24 Nov, ADR-320): Notification settings say no channels are set up, with no way to add one | Issue: No notification channel can be added |
| D-36 | Adjustment check and Review adjustment drawer are very slow or fail with a server error | Fixed, not tested | D | The drawer reads the broker funds once per request and the margins together (at most 4), and no request keeps its database connection while waiting on the broker; a... | Open the Review adjustment drawer on a live condor in market hours with two testers; time it; check /api/health stays fast. |
| D-37 | What-if shows nothing for a target level or date | Fixed, not tested | D | When prices are not live the what-if Target and Date readouts say "not shown while prices are not live" beside the dash; a failed request or refused target never... | Builder what-if with prices not live: pick a level and a date. |
| D-38 | Other pages load slowly or time out | Fixed, not tested | D | Plan read holds no connection in the market wait and asks a failed market read once; settings reads the clock once; Create Strategy step 4 asks planned entries once... | Time the plan dialog, step 4 and settings on the PC in market hours. |
| D-39 | Live-data status messages contradict the prices on the same page, then recover | Fixed, not tested | E | The "prices disconnected" message is decided in one place from the same per-quote health as the prices: shown only when the spot or a held leg (a missing quote... | Builder at a moment the feed blips: the message shows only while a shown price is not live |
| D-40 | Header totals blank and cards fail because of expired scenario strategies | Fixed, not tested | D | Strategies with an open leg on an expired contract are left out of every header figure with a line saying how many; Live cards show the expiry reason (ADR-324 pending... | Positions paper page header with the PATH-60/61 strategies present; Live cards. |
| D-41 | Live and My Strategies cards show no P&L or health, and a card can stay Loading | Fixed, not tested | E | Live card and My Strategies row of a running trade show the Positions paper-list P&L (Positions paused rule; dash + "prices not live"); a failed read says so; no... | Live and My Strategies with prices live, then paused: figure equals the Positions Paper tab |
| D-42 | My Strategies shows the original legs and closed strategies are missing | Fixed, not tested | E | My Strategies lists current legs from the paper book (the Positions source) and closed strategies as Completed; an unreadable book degrades only its row with a line | My Strategies: a rolled condor shows its current legs; closed C4 listed as Completed |
| D-43 | Strategy names are cut off to about 8 characters | Fixed, not tested | E | Name column has a 9.5rem floor (one shared class) on My Strategies, the compact paper list and the builder card, with a title fallback | My Strategies at desktop width: C5 to C9 names in full |
| D-44 | Stop list uses raw contract names, different from the form | Fixed, not tested | E | The Stops list names a leg with the form label ("NIFTY 3 Nov 22300 PE") through one legNamesOf map; after Save the saved row is scrolled into view | Stops form and list side by side; Save brings the new row into view |
| D-45 | Adjustment comparison table is hard to read | Fixed, not tested | E | Compare table: leader label is its own chip apart from the value, column names repeat under every group, numbers right-aligned tabular; the drawer already shows... | Compare with 5+ approaches: chips and column names under each group |
| D-46 | Greeks and max profit/loss display rounding hides the real number | Fixed, not tested | E | One display formatter keeps two significant digits for a Greek that would show as zero or one step ("0.004"); max profit/loss stay whole rupees half-up (REQ-152), now... | C5/C6 Greeks show non-zero digits; C7 max loss reads 4,774 |
| D-47 | Builder strike picker is confusing | Fixed, not tested | E | Picker: Buy and Sell always drawn; the footer adds "N already in the draft"; the lots box still opens after the first click (ADR-325 (4), Q8) | Picker with a 4-leg draft: footer reads "0 legs selected" and "4 already in the draft" |
| D-48 | No control to change the expiry of existing legs | Feature request (parked) | E | Not built (owner 24 Nov, ADR-320): Edit-leg form has no expiry control; legs must be removed and re-added | Issue: No control to change the expiry of existing legs |
| D-49 | Lots/Quantity switch does not relabel the column header | Fixed, not tested | E | The leg list header follows the Lots/Quantity switch | Flip the switch in Settings: header reads Lots or Quantity |
| D-50 | Payoff chart shows no tooltip on hover or arrow keys | Could not reproduce | E | Hover and arrow-key readings pass on the real fixture; only a refresh handing an equal copy of the reply drops the reading, by the decided rule... | C2-type chart: hover and arrows during a live refresh; owner: keep the reading when the levels are unchanged? |
| D-51 | Strategy Chart tab says it is not available on paper strategies | Feature request (parked) | E | Not built (owner 24 Nov, ADR-320): Strategy Chart tab says it is not available on paper strategies | Issue: Strategy Chart tab says it is not available on paper strategies |
| D-52 | Ready-made shapes text points to a panel that is not there | Fixed, not tested | E | The empty-builder hint names the Ready-made tab only when the server lists it, else the Create Strategy page, and shows nothing until the features read answers | Empty builder hint with the feature off and on |
| D-53 | Builder title New Strategy is not editable and the name box silently limits to 20... | Fixed, not tested | E | Each name box says the 20-character limit in one line (room left, at, over), pinned equal to the server limit (ADR-183); the title stays a heading, the name is asked... | Type 20+ characters in the Save box and in the rename box |
| D-54 | Playbook editor Test does nothing and Delete needs no confirmation | Fixed, not tested | E | Delete asks "Delete this playbook?" (Cancel keeps it); the dead Test button is removed and the out-of-V1 line stands where it was, in a fixed sentence when the labels... | Adjustments > Playbooks > own playbook: Delete, Cancel, Delete; no Test button |
| D-55 | Option chain filters apply late and Change / OI Change columns are always blank | Fixed, not tested | E | Chain filters apply as typed (sent 300 ms after the last key, rows stay on screen); Min OI needs every shown side to pass; Change = live minus previous close (exact... | Chain in market hours: Change filled; typing Min OI drops rows as you type |
| D-56 | Home overview shows only index values | Fixed, not tested | E | Home shows running strategies (server status word), the bell number and total P&L (Positions totals, same paused rule); a failed read says so in that figure only | Home with prices live and paused; alert figure equals the bell |
| D-57 | Dates on the adjustments page use US month/day | Needs owner decision | E | Built: one date formatter ("23 Nov 2026", 24-hour IST) used by every screen, frontend and backend scans guard it. Stopped: the ADR-015 Q182 / REQ-049 AC-5 "Last... | After Q5: adjustments page dates; the disconnect sentence |
| D-58 | Small wording problems: zero-price message, quote characters in names, tested-side wording | Fixed, not tested | E | Zero price: "A price of 0 cannot be used. Enter 0.05 or more"; quote pair stripped at the one display function; live T-01 line ends "(put side tested)" / "(call side... | C2 opportunity line, C9/C6 drawer reasons, Stops form Above=0, ADJ-02-type rule line with the side |
| D-59 | At expiry settlement of a two-expiry trade the armed index stops are silently removed | Fixed, not tested | A | No code defect: stops were never stored by settlement; no change made | Stops survive a part settlement at 15:45 on a two-expiry paper trade |
| D-60 | A duplicate leg or a fifth leg is accepted silently | Fixed, not tested | A | Every way a leg is added or moved (picker, edit form, strike step, Shift, Width, Hedge) asks Increase / Keep separate / Cancel through one door; one live question per... | Step a strike onto a held contract: the question box (Escape = Cancel); Increase over the lots limit; Add to Paper refusing a kept duplicate |
| D-61 | Buying back one short leaves a lone long option with no note on screen | Fixed, not tested | E | The What changes block says "This trade now has a long <call or put> with no short against it; its result now depends on direction." for every approach whose... | C7 161-type Compare: Buy back the untested short shows the line |
| D-62 | Few repair or profit-taking routes on a small condor | Feature request (parked) | C | Not built (owner 24 Nov, ADR-320): Few repair routes on a small condor (partial profit refused at 1 lot; both rolls refused on 2 lots) | Issue: Few repair or profit-taking routes on a small condor |
| D-63 | Two-expiry trade: P&L table omits booked legs and Greeks sum across expiries unmarked | Fixed, not tested | B | P&L Table lists closed legs and the charges lines so rows add up to the Total; Greeks Total says "summed across N expiries"; margin unchanged | C9 164: P&L Table shows closed rows; Greeks total labelled |
| D-64 | After the 15:30 close the page shows raw errors and never says settlement comes at 15:45 | Fixed, not tested | E | Between 15:30 and settlement on expiry day, builder, Positions and tracking say "Market closed. Open legs that expire today settle at 15:45." from one clock function;... | Builder and Positions between 15:30 and 15:45 on an expiry day |
| D-65 | Renaming a paper trade from the builder fails, and its status differs between lists | Fixed, not tested | E | Rename from the builder read no revision (422); the shared rename call reads it first and the route still refuses a missing or stale one; the Saved tab re-reads after... | Rename a paper trade from the builder; status matches My Strategies |
| D-66 | Completed page "last saved" shows the last builder save, not the close time | Fixed, not tested | E | The Completed page column reads "Closed" with the last exit, stop or settlement time ("closed 23 Nov 2026, 13:24:07 IST"), or "closed: time not available" | Completed page times match the stop-out times |
| D-67 | Adjustment toasts pop up within minutes of opening a trade and cover page buttons | Fixed, not tested | E | Pop-ups render inside the sticky header block (stay on screen, never float over page buttons; aria-live always present); the rule keeps firing from entry because the... | My Strategies or Positions with 2-3 pop-ups: no button covered; scroll down and raise one |
| D-68 | No screen gives the day total for the test trades | Fixed, not tested | E | The Paper tab header shows "Today (after charges)": real trades opened or closed on the current trading day (newest snapshot India date), scenario left out, paused... | Paper tab header Today on a test day, and on a Saturday |
| D-69 | Index value frozen at 25,366.40 on reads from 15:15 to 15:27 | Could not reproduce | C | A real QuoteBook read of an index tick at 15:15:18 with option frames to 15:27 gives 25366.40 with its own 15:15:18 time; feed health is judged on the whole feed... | Owner: per-quote age limit for the index? |
| D-70 | 1 Dec put prices kept moving after the market-closed banner | Could not reproduce | C | Post-close vendor frames are applied (no after-close freeze); the label keeps the 15:30 close time. Matches the feed, not an app re-mark; no feed log to confirm.... | Owner: freeze option prices at the close? |
| D-71 | Expiry settlement leaves no record: no index value, no time, no word "settled" | Fixed, not tested | C | An expiry settlement stores "Paper - settled at expiry: <index> closed at <level>"; Alerts > History lists it with time and prices; the closed rows show it | C2 157 after expiry: History record and closed-row reason |

## Decisions pending the owner's read

- **ADR-323** (Part C, proposed): suggestions and alerts: records, times, one word, one value (D-22 to D-31).
- **ADR-324** (Part D, proposed): header totals leave out strategies on expired contracts (D-40); timeout wording (D-38).
- **ADR-325** (Part E, proposed): points (1) to (17), the labels, small features and post-close messages (D-39 to D-68).
- ADR-317 to ADR-322 are accepted (owner decisions of 23 to 25 Nov).

## Owner questions (`docs/process/owner-questions-2026-11-24.md`)

| Q | Issue | Question | State |
|---|---|---|---|
| Q1 | D-17 | Which prices "Time value" uses | Answered 25 Nov (ADR-322 (2)), built |
| Q2 | D-25 | May Take profit be offered at an after-charges loss (ADR-238 (6) against ADR-294 (4)) | Open: CLASH |
| Q3 | D-40 | Which figures the header adds up beside expired strategies | Open (ADR-324) |
| Q4 | D-38 | Timeout words; keep typed fields | Open (ADR-324 (4)) |
| Q5 | D-57 | "Last updated" 12-hour (ADR-015 Q182) against 24-hour everywhere (ADR-320) | Open: CLASH |
| Q6 | D-67 | Quiet minutes after entry for a rule already true | Open (recommend 5) |
| Q7 | D-68 | What "Today" adds up | Open (ADR-325 (2)) |
| Q8 | D-47 | Lots box on every strike row | Open (ADR-325 (4)) |

## Parked items and next steps

- **D-15 (Parked):** the "Plan: Get Rs X" line was withdrawn because it priced only held legs after a planned leg was
  exited. Next: check every plan leg is still held, then re-enable with a test.
- **D-27 (Parked):** no cause proven for the empty adjustment history. Next: on the PC, read
  `GET /api/strategies/155/adjustment-history` and record the reply.
- **Feature requests (parked by the owner 24 Nov, ADR-320):** D-34 profit-target stop, D-35 notification channels,
  D-48 change the expiry of a leg, D-51 Strategy Chart on paper strategies, D-62 more repair routes on a small
  condor. Next: the owner schedules them as features.
- **Deferred:** #723 (worker margin refresh answered from the plan cache, Part D).

## Every new user-facing sentence of the chain, with its pin status

Backend sentences are pinned in `tests/errors/template_pins.json`; frontend sentences carry a "pending owner read"
note in their wording module. Base of the list: the branch point from `main` (d387d4c).


## Backend (89 keys; 85 added, 4 changed)

| Key (D-id) | Where | Sentence | Pin status |
|---|---|---|---|
| paper_adjustment_limit (-) | errors/templates.py:990 | These orders open or add to a leg, and there is no room left: plan maximum of {limit} reached. | CHANGED, pending owner read |
| explanation:paper_exit_set_before_call (D-03) | errors/explanations.py:1937 | Exit above {level} was set before this change; your new short call is {strike}. Check this level. | ADDED, pending owner read |
| explanation:paper_exit_set_before_no_call (D-03) | errors/explanations.py:1940 | Exit above {level} was set before this change; you no longer hold a short call. Check this level. | ADDED, pending owner read |
| explanation:paper_exit_set_before_put (D-03) | errors/explanations.py:1943 | Exit below {level} was set before this change; your new short put is {strike}. Check this level. | ADDED, pending owner read |
| explanation:paper_exit_set_before_no_put (D-03) | errors/explanations.py:1946 | Exit below {level} was set before this change; you no longer hold a short put. Check this level. | ADDED, pending owner read |
| explanation:paper_exit_set_before_unchecked (D-03) | errors/explanations.py:1961 | This exit could not be checked against your current legs. Check this level. | ADDED, pending owner read |
| explanation:paper_exit_confirm_call (D-03) | errors/explanations.py:1949 | Exit above {level} stays armed at its level; after this change your short call will be {strike}. Check this level. | ADDED, pending owner read |
| explanation:paper_exit_confirm_no_call (D-03) | errors/explanations.py:1952 | Exit above {level} stays armed at its level; after this change you will hold no short call. Check this level. | ADDED, pending owner read |
| explanation:paper_exit_confirm_put (D-03) | errors/explanations.py:1955 | Exit below {level} stays armed at its level; after this change your short put will be {strike}. Check this level. | ADDED, pending owner read |
| explanation:paper_exit_confirm_no_put (D-03) | errors/explanations.py:1958 | Exit below {level} stays armed at its level; after this change you will hold no short put. Check this level. | ADDED, pending owner read |
| explanation:target_not_live (D-37) | errors/explanations.py:1480 | not shown while prices are not live | ADDED, pending owner read |
| explanation:outcome_problem_leg_named (D-64) | errors/explanations.py:1771 | {leg} cannot be used: {why} | ADDED, pending owner read |
| explanation:outcome_problem_leg_unknown (D-64) | errors/explanations.py:1773 | A leg cannot be used: {why} | ADDED, pending owner read |
| explanation:current_legs_unreadable (D-42, D-39, D-64) | errors/explanations.py:2051 | The current legs could not be read. The legs shown are as saved. | ADDED, pending owner read |
| explanation:market_closed_settles (D-64) | errors/explanations.py:2052 | Market closed. Open legs that expire today settle at {time}. | ADDED, pending owner read |
| explanation:adjust_cmp_adjustments_exit (D-04) | errors/explanations.py:2105 | Not an adjustment: closes every open leg | ADDED, pending owner read |
| explanation:adjust_cmp_adjustments_over (D-04) | errors/explanations.py:2102 | {used} of {max}; this would be adjustment {used}, over your plan maximum of {max} | ADDED, owner read: 2026-11-23 (ADR-318 (2), the owner's own sentence) |
| explanation:adjust_limit_reason (-) | errors/explanations.py:2186 | plan maximum of {max} reached | CHANGED, owner read: 2026-11-23 (ADR-318 (1), the owner's own sentence) |
| adjust_time_exit_not_set (-) | errors/templates.py:1490 | This approach is not built because your playbook sets no exit time. | CHANGED, pending owner read |
| adjust_time_exit_not_yet (-) | errors/templates.py:1493 | This approach opens on the expiry day, from {time}; it is not offered before then. | CHANGED, pending owner read |
| explanation:adjust_condition_side_put (D-58) | errors/explanations.py:1650 | {line} (put side tested) | ADDED, pending owner read |
| explanation:adjust_condition_side_call (D-58) | errors/explanations.py:1651 | {line} (call side tested) | ADDED, pending owner read |
| explanation:paper_totals_left_out_one (D-40) | errors/explanations.py:2076 | 1 strategy left out: its contract has expired. | ADDED, pending owner read |
| explanation:paper_totals_left_out_many (D-40) | errors/explanations.py:2077 | {count} strategies left out: their contracts have expired. | ADDED, pending owner read |
| paper_trigger_already_crossed (-) | errors/templates.py:1042 | the live price is already at or beyond this level, so this exit would close the trade straight away. To close now, use Exit. | ADDED, owner read: 2026-11-23 (approved in session) |
| paper_trigger_leg_already_crossed (D-01) | errors/templates.py:1048 | the live price is already at or beyond this level, so this stop would close the leg straight away. To close now, use Exit. | ADDED, pending owner read |
| explanation:paper_breakevens_with_charges (D-16) | errors/explanations.py:1912 | Breakevens include the booked P&L and about {charges} of charges and taxes. | ADDED, owner read: 2026-11-25 (ADR-322 point 4, answered by the owner in the qu |
| explanation:paper_breakevens_before_charges (D-16) | errors/explanations.py:1915 | Breakevens include the booked P&L and are before charges and taxes: the charges could not be priced. | ADDED, owner read: 2026-11-25 (ADR-322 point 4, answered by the owner in the qu |
| explanation:paper_closed_result (D-10, D-63) | errors/explanations.py:1920 | Closed: result {result} after charges. | ADDED, owner read: 2026-11-25 (ADR-322 point 4, answered by the owner in the qu |
| explanation:paper_greeks_across_expiries (D-10, D-63) | errors/explanations.py:1925 | Greeks are summed across {count} expiries. | ADDED, owner read: 2026-11-25 (ADR-322 point 4, answered by the owner in the qu |
| explanation:paper_closed_result_before (D-63) | errors/explanations.py:1922 | Closed: result {result} before charges. | ADDED, owner read: 2026-11-25 (ADR-322 point 4, answered by the owner in the qu |
| explanation:table_column_decay_left_today (D-08, D-12) | errors/explanations.py:1871 | Decay left today (Rs) | ADDED, owner read: 2026-11-25 (ADR-322 point 4, answered by the owner in the qu |
| explanation:decay_left_today_text (D-08, D-12) | errors/explanations.py:1872 | Decay left today: {amount} | ADDED, owner read: 2026-11-25 (ADR-322 point 4, answered by the owner in the qu |
| explanation:estimate_intrinsic_basis (D-08) | errors/explanations.py:1874 | a leg with no time value left at the live price is valued at its intrinsic value | ADDED, owner read: 2026-11-25 (ADR-322 point 4, answered by the owner in the qu |
| explanation:money_basis_plan (D-15, D-17, D-16) | errors/explanations.py:1820 | At plan prices | ADDED, owner read: 2026-11-25 (ADR-322 point 4, answered by the owner in the qu |
| explanation:money_basis_paper (D-15, D-17, D-16) | errors/explanations.py:1821 | At paper fill prices | ADDED, owner read: 2026-11-25 (ADR-322 point 4, answered by the owner in the qu |
| explanation:money_plan_get (D-15, D-17, D-16) | errors/explanations.py:1830 | Plan: Get {amount} at plan prices | ADDED, owner read: 2026-11-25 (ADR-322 point 4, answered by the owner in the qu |
| explanation:money_plan_pay (D-15, D-17, D-16) | errors/explanations.py:1831 | Plan: Pay {amount} at plan prices | ADDED, owner read: 2026-11-25 (ADR-322 point 4, answered by the owner in the qu |
| explanation:money_basis_mixed (D-15, D-18) | errors/explanations.py:1822 | At paper fill prices for {fills} of {total} legs; the rest at their entered prices | ADDED, owner read: 2026-11-25 (ADR-322 point 4, answered by the owner in the qu |
| explanation:money_basis_none (D-15, D-18) | errors/explanations.py:1825 | At their entered prices: none of {total} legs is a paper fill | ADDED, owner read: 2026-11-25 (ADR-322 point 4, answered by the owner in the qu |
| explanation:money_basis_unread (D-15, D-18) | errors/explanations.py:1827 | At their entered prices (the paper book could not be read) | ADDED, owner read: 2026-11-25 (ADR-322 point 4, answered by the owner in the qu |
| explanation:money_plan_changed (D-15, D-18) | errors/explanations.py:1828 | Plan credit not shown: the plan's lots differ from the paper position | ADDED, pending owner read |
| explanation:paper_stop_reason_index_at (D-22, D-71) | errors/explanations.py:1894 | {what}; {underlying} was at {level} at that moment | ADDED, pending owner read |
| explanation:paper_stop_reason_index_unknown (D-22, D-71) | errors/explanations.py:1896 | {what}; the index value at that moment was not available | ADDED, pending owner read |
| explanation:paper_settle_reason (D-22, D-71) | errors/explanations.py:1898 | Paper - settled at expiry: {underlying} closed at {level} | ADDED, pending owner read |
| explanation:paper_settle_reason_plain (D-22, D-71) | errors/explanations.py:1900 | Paper - settled at expiry | ADDED, pending owner read |
| explanation:paper_settle_history_body (D-22, D-71) | errors/explanations.py:1901 | {what}; settled {prices}. A paper settlement only: no order was sent to Zerodha. | ADDED, pending owner read |
| explanation:adjust_take_profit_basis (D-25) | errors/explanations.py:2196 | Whole trade closed at the planned prices: {before} before charges (the figure the profit test used), {after} after charges. | ADDED, pending owner read |
| explanation:adjust_take_profit_basis_no_charges (D-25) | errors/explanations.py:2199 | Whole trade closed at the planned prices: {before} before charges (the figure the profit test used); the charges could not be priced, so the result after charges is not shown. | ADDED, pending owner read |
| explanation:suggestion_counts_units (D-30) | errors/explanations.py:1603 | Counters count conditions, not rows. Conditions: {conditions}. Rows: {rows}. One row can hold several conditions. | ADDED, pending owner read |
| explanation:suggestion_lapsed_contract_expired (D-30) | errors/explanations.py:1593 | The contracts have expired | ADDED, owner read: 2026-11-25 (ADR-322 point 4, answered by the owner in the qu |
| explanation:money_time_value_live (D-17) | errors/explanations.py:1833 | at live prices, as of {time} | ADDED, owner read: 2026-11-25 (ADR-322 point 2, the sentence as the owner decid |
| explanation:money_time_value_live_untimed (D-17) | errors/explanations.py:1834 | at live prices, time not given | ADDED, pending owner read |
| explanation:money_time_value_closed (D-17) | errors/explanations.py:1835 | at the last close prices, as of {time} | ADDED, pending owner read |
| explanation:money_time_value_closed_untimed (D-17) | errors/explanations.py:1837 | at the last close prices | ADDED, pending owner read |
| explanation:adjust_wc_title (D-21) | errors/explanations.py:2132 | What changes | ADDED, pending owner read |
| explanation:adjust_wc_row_profit_range (D-21) | errors/explanations.py:2133 | Profit range | ADDED, pending owner read |
| explanation:adjust_wc_row_breakeven_distance (D-21) | errors/explanations.py:2134 | Distance from the index to each breakeven | ADDED, pending owner read |
| explanation:adjust_wc_row_pop (D-21) | errors/explanations.py:2135 | Probability of profit | ADDED, pending owner read |
| explanation:adjust_wc_row_max_profit (D-21) | errors/explanations.py:2136 | Max profit | ADDED, pending owner read |
| explanation:adjust_wc_row_max_loss (D-21) | errors/explanations.py:2137 | Max loss | ADDED, pending owner read |
| explanation:adjust_wc_row_credit (D-21) | errors/explanations.py:2138 | Credit or debit of this adjustment | ADDED, pending owner read |
| explanation:adjust_wc_row_margin (D-21) | errors/explanations.py:2139 | Margin | ADDED, pending owner read |
| explanation:adjust_wc_row_net_delta (D-21) | errors/explanations.py:2140 | Net delta | ADDED, pending owner read |
| explanation:adjust_wc_dir_up (D-21) | errors/explanations.py:2141 | up | ADDED, pending owner read |
| explanation:adjust_wc_dir_down (D-21) | errors/explanations.py:2142 | down | ADDED, pending owner read |
| explanation:adjust_wc_dir_same (D-21) | errors/explanations.py:2143 | unchanged | ADDED, pending owner read |
| explanation:adjust_wc_dir_na (D-21) | errors/explanations.py:2144 | not available | ADDED, pending owner read |
| explanation:adjust_wc_not_available (D-21) | errors/explanations.py:2145 | Not available | ADDED, pending owner read |
| explanation:adjust_wc_credit (D-21) | errors/explanations.py:2146 | Credit {amount} | ADDED, pending owner read |
| explanation:adjust_wc_debit (D-21) | errors/explanations.py:2147 | Debit {amount} | ADDED, pending owner read |
| explanation:adjust_wc_no_trade (D-21) | errors/explanations.py:2148 | No trade | ADDED, pending owner read |
| explanation:adjust_wc_below (D-21) | errors/explanations.py:2149 | {level} is {distance} points below the index | ADDED, pending owner read |
| explanation:adjust_wc_above (D-21) | errors/explanations.py:2151 | {level} is {distance} points above the index | ADDED, pending owner read |
| explanation:adjust_wc_at (D-21) | errors/explanations.py:2153 | {level} is at the index | ADDED, pending owner read |
| explanation:adjust_wc_join (D-21) | errors/explanations.py:2154 | {first}; {second} | ADDED, pending owner read |
| explanation:adjust_wc_no_breakeven (D-21) | errors/explanations.py:2155 | Not available: there is no breakeven, so there is no distance to measure. | ADDED, pending owner read |
| explanation:adjust_wc_unknown (D-21) | errors/explanations.py:2157 | Not available: no figure was worked out for this approach. | ADDED, pending owner read |
| explanation:adjust_wc_reason_before (D-21) | errors/explanations.py:2158 | Before: {reason} | ADDED, pending owner read |
| explanation:adjust_wc_reason_after (D-21) | errors/explanations.py:2159 | After: {reason} | ADDED, pending owner read |
| explanation:adjust_wc_reason_both (D-21) | errors/explanations.py:2160 | Before and after: {reason} | ADDED, pending owner read |
| explanation:adjust_wc_reason_side (D-21) | errors/explanations.py:2162 | This removes credit from the {closed} side, so the {remaining} spread becomes the largest loss. | ADDED, pending owner read |
| explanation:adjust_wc_reason_credit (D-21) | errors/explanations.py:2170 | This removes credit that was held against the loss, so the maximum loss is higher than before. | ADDED, pending owner read |
| explanation:adjust_wc_reason_exit (D-21) | errors/explanations.py:2172 | Closing now books today's prices as final, so the loss it locks in is higher than the maximum loss of the position held to expiry. | ADDED, pending owner read |
| explanation:adjust_cmp_breakeven_below (D-21 round 2) | errors/explanations.py:2091 | Profit below {level}, no lower end | ADDED, pending owner read |
| explanation:adjust_cmp_breakeven_above (D-21 round 2) | errors/explanations.py:2093 | Profit above {level}, no upper end | ADDED, pending owner read |
| explanation:adjust_lone_long (D-61) | errors/explanations.py:2166 | This trade now has a long {kind} with no short against it; its result now depends on direction. | ADDED, pending owner read |
| explanation:adjust_wc_lines (D-61) | errors/explanations.py:2169 | {first} {second} | ADDED, pending owner read |
| explanation:paper_today_none (D-68) | errors/explanations.py:2075 | No trades opened or closed today. | ADDED, pending owner read |

Backend count: 89 keys, 69 pending owner read, 20 owner-read.

## Frontend (added lines in frontend/src, non-test, with a "pending owner read" note)

| Constant | Where | Sentence | Pin status |
|---|---|---|---|
| CHAIN_NOT_AVAILABLE (D-55) | lib/chainDisplay.js:39 | not available | pending owner read; pinned by chain-filters-d55.test.js |
| DRAFT_HOLDS_TEXT(n) (D-47) | lib/legDoor.js:8 | {n} already in the draft | pending owner read |
| NO_LEGS_HINT_TAB (D-52) | lib/legEdit.js:26 | Pick strikes, or start from a ready-made shape in the Ready-made tab. | pending owner read |
| NO_LEGS_HINT_PAGE (D-52) | lib/legEdit.js:27 | Pick strikes, or start from a ready-made shape on the Create Strategy page. | pending owner read |
| HOME_RUNNING_LABEL (D-56) | lib/paperPnl.js:15 | Running strategies | pending owner read |
| HOME_UNREAD_LABEL (D-56) | lib/paperPnl.js:16 | Unread alerts | pending owner read |
| HOME_PNL_LABEL (D-56) | lib/paperPnl.js:17 | Total P&L | pending owner read |
| FIGURE_READ_FAILED_TEXT (D-56) | lib/paperPnl.js:18 | Could not be read right now. | pending owner read |
| nameLimitText, over (D-53) | lib/saveDraft.js:40 | This name is longer than {MAX} characters: shorten it to save. | pending owner read |
| nameLimitText, at limit (D-53) | lib/saveDraft.js:41 | That is the {MAX}-character limit: nothing more can be typed. | pending owner read |
| nameLimitText, room left (D-53) | lib/saveDraft.js:42 | A name can be up to {MAX} characters. | pending owner read |
| CLOSED_HEADER (D-66) | lib/sharedStateText.js:37 | Closed | pending owner read |
| CLOSED_PREFIX (D-66) | lib/sharedStateText.js:38 | closed  (prefix before the time) | pending owner read |
| CLOSED_UNAVAILABLE_TEXT (D-66) | lib/sharedStateText.js:39 | closed: time not available | pending owner read |
| PLAN_TIMED_OUT_TEXT (D-38) | lib/sharedStateText.js:57 | The plan took too long to load. Nothing was changed. | pending owner read |
| PLAN_PICK_TIMED_OUT_TEXT (D-38) | lib/sharedStateText.js:58 | The playbook took too long to load, so the fields are as you left them. Nothing was changed. | pending owner read |
| SETTINGS_TIMED_OUT_TEXT (D-38) | lib/sharedStateText.js:59 | The settings took too long to load, so no value is shown. | pending owner read |
| TIMED_OUT_PARTS.what_happened (D-38) | lib/sharedStateText.js:61 | The server took too long to answer. | pending owner read |
| TIMED_OUT_PARTS.impact (D-38) | lib/sharedStateText.js:62 | The prices and figures it was asked for are not shown, so none of them can be mistaken for current values. | pending owner read |
| TIMED_OUT_PARTS.what_is_blocked (D-38) | lib/sharedStateText.js:63 | Nothing was changed and no order was placed. Your choices on this page are kept. | pending owner read |
| TIMED_OUT_PARTS.next_action (D-38) | lib/sharedStateText.js:64 | Try again in a moment. | pending owner read |
| PLAYBOOK_DELETE_CONFIRM_TEXT (D-54) | lib/sharedStateText.js:113 | Delete this playbook? | pending owner read |
| PLAYBOOK_TEST_OUT_OF_V1_TEXT (D-54 round 2) | lib/sharedStateText.js:112 | Testing against past expiries is not in this version: it needs licensed historical option data. | pending owner read |
| PAPER_PRICE_ZERO_REASON (D-58) | lib/tracking.js:23 | A price of 0 cannot be used. Enter 0.05 or more | pending owner read |
| ARMED_UNCHECKED | components/strategy/PaperConfirmDialog.vue:141 | Could not check your armed exits. | pending owner read; pinned by paper-armed-exits.test.js |
| EXITS_LOAD_FAILED_TEXT (D-24) | lib/sharedStateText.js:90 | Could not read the conditional exits. Nothing was changed. | pending owner read |
| exitLineText (D-24) | lib/sharedStateText.js:96 | Conditional exit: all legs exit if the index goes below/above {level}. Fired./Armed. | pending owner read (under the D-24 note) |
| WATCH_LEVEL_LABEL (D-32) | lib/sharedStateText.js:92 | Watch an index level: it only alerts and does not exit | pending owner read |
| SHORT_FUNDS_LINE (D-33) | lib/sharedStateText.js:94 | Not enough funds. Paper trade: this practice order is still allowed; a real order of this size would be refused. | pending owner read |

Frontend count: 29 sentences, all pending owner read.

## ADRs 317-325
Not checked (skipped).


## Screen checks for the owner's PC

Ordered by what each needs. Parked features are left out. Each line is the ledger's "Screen check owed".

### A. Needs live prices (market hours)

- **D-01** (Fixed, not tested): Type "Above" a level below the index: red line "Not saved: the live price is already at or beyond this level, ..." and no row; then a safe level saves
- **D-05** (Fixed, not tested): After a failed refresh, figures go to a dash and Exit is blocked; a Not saved line clears on the next good refresh
- **D-06** (Fixed, not tested): C1 155 card reads +2,380.32 / -4,119.68 and the builder figures
- **D-07** (Could not reproduce): Card, builder and Positions totals at the same minute, each labelled after charges with a time
- **D-08** (Fixed, not tested): 0DTE condor after 14:50: Estimated-now curve drawn with the line "a leg with no time value left at the live price is valued at its intrinsic value"
- **D-09** (Fixed, not tested): Open the dialog, wait, confirm: the row shows its quote time
- **D-11** (Fixed, not tested): Toggle the switch on trade 155: tiles, chart floor and table move together; OFF shows the open-legs line
- **D-12** (Fixed, not tested): 0DTE condor: Decay left today about the time value left (157: not 4,008)
- **D-13** (Fixed, not tested): C4: Total + Profit left = Max profit on one basis
- **D-14** (Fixed, not tested): 157-type 0DTE trade: two labelled max/profit-left figures; Charges dialog matches the tile
- **D-16** (Fixed, not tested): C6 159: builder, compare and adjust page breakevens agree and say what is inside
- **D-17** (Fixed, not tested): Builder summary on a live 0DTE condor: label beside the credit basis
- **D-18** (Fixed, not tested): Four panels of one leg each show their quote time
- **D-19** (Fixed, not tested): An LTP outside bid/ask shows an older last-trade time
- **D-20** (Could not reproduce): Record bid and ask of the same strikes at one moment
- **D-31** (Fixed, not tested): C6 drawer, panel and list show 0.7293 fired, Now beside it
- **D-36** (Fixed, not tested): Open the Review adjustment drawer on a live condor in market hours with two testers; time it; check /api/health stays fast.
- **D-38** (Fixed, not tested): Time the plan dialog, step 4 and settings on the PC in market hours.
- **D-39** (Fixed, not tested): Builder at a moment the feed blips: the message shows only while a shown price is not live
- **D-41** (Fixed, not tested): Live and My Strategies with prices live, then paused: figure equals the Positions Paper tab
- **D-46** (Fixed, not tested): C5/C6 Greeks show non-zero digits; C7 max loss reads 4,774
- **D-55** (Fixed, not tested): Chain in market hours: Change filled; typing Min OI drops rows as you type
- **D-56** (Fixed, not tested): Home with prices live and paused; alert figure equals the bell
- **D-64** (Fixed, not tested): Builder and Positions between 15:30 and 15:45 on an expiry day
- **D-68** (Fixed, not tested): Paper tab header Today on a test day, and on a Saturday
- **D-69** (Could not reproduce): Owner: per-quote age limit for the index?
- **D-70** (Could not reproduce): Owner: freeze option prices at the close?

### B. Needs a paper adjustment (a paper trade adjusted, stopped or settled)

- **D-02** (Fixed, not tested): Roll one side of a paper condor: Orderbook lists the buy-back of the short before the sale of its hedge; a stop-out alert lists its legs in the same order
- **D-03** (Fixed, not tested): Set an index exit, adjust the trade: row marked "set before the last adjustment" with the new short strike; Keep this level gives "Kept:"; the confirm list names the armed exit
- **D-04** (Fixed, not tested): A trade at 2 of 2: rolls withheld "plan maximum of 2 reached"; Reduce / Close read "3 of 2; this would be adjustment 3 ..." and CAN be placed; Exit all shows no count; trade 164 reads "1 of 2"
- **D-10** (Fixed, not tested): C1 155: closed short 25400 PE row +643.50 apart from the new long
- **D-15** (Parked): Paper trade summary says "At paper fill prices"; Add to Paper shows "plan 36.45" beside a re-quoted price
- **D-21** (Fixed, not tested): Strategy 164 Reduce reads the put-side reason line; block layout at phone width
- **D-22** (Fixed, not tested): History tab lists the C3 stop with index value; closed C4 160 page shows the stop reason on its rows (LegList still says "No legs yet")
- **D-23** (Fixed, not tested): Orderbook of C4 160 shows Stop on the stop-out row
- **D-24** (Fixed, not tested): C7 161 panel shows "Conditional exit: all legs exit if the index goes above 25,720. Armed."
- **D-25** (Needs owner decision): After the owner answer: 162-style trade at an after-charges loss
- **D-26** (Fixed, not tested): Trade page line "Lapsed at HH:MM:SS IST"; Review stays while the idea is open
- **D-27** (Parked): Open C1 155 adjustment history; record the route reply
- **D-30** (Fixed, not tested): Opportunities page: conditions/rows line; no 16 Nov PATH rows Open
- **D-40** (Fixed, not tested): Positions paper page header with the PATH-60/61 strategies present; Live cards.
- **D-45** (Fixed, not tested): Compare with 5+ approaches: chips and column names under each group
- **D-47** (Fixed, not tested): Picker with a 4-leg draft: footer reads "0 legs selected" and "4 already in the draft"
- **D-58** (Fixed, not tested): C2 opportunity line, C9/C6 drawer reasons, Stops form Above=0, ADJ-02-type rule line with the side
- **D-59** (Fixed, not tested): Stops survive a part settlement at 15:45 on a two-expiry paper trade
- **D-60** (Fixed, not tested): Step a strike onto a held contract: the question box (Escape = Cancel); Increase over the lots limit; Add to Paper refusing a kept duplicate
- **D-61** (Fixed, not tested): C7 161-type Compare: Buy back the untested short shows the line
- **D-63** (Fixed, not tested): C9 164: P&L Table shows closed rows; Greeks total labelled
- **D-67** (Fixed, not tested): My Strategies or Positions with 2-3 pop-ups: no button covered; scroll down and raise one
- **D-71** (Fixed, not tested): C2 157 after expiry: History record and closed-row reason

### C. Needs neither

- **D-28** (Fixed, not tested): Running condor reads Running on My Strategies, Live and Paper lists
- **D-29** (Fixed, not tested): Bell count equals Active rows with no PATH-xx rows
- **D-32** (Fixed, not tested): Heading fits at phone width
- **D-33** (Fixed, not tested): 0-day condor with short funds shows the sentence
- **D-37** (Fixed, not tested): Builder what-if with prices not live: pick a level and a date.
- **D-42** (Fixed, not tested): My Strategies: a rolled condor shows its current legs; closed C4 listed as Completed
- **D-43** (Fixed, not tested): My Strategies at desktop width: C5 to C9 names in full
- **D-44** (Fixed, not tested): Stops form and list side by side; Save brings the new row into view
- **D-49** (Fixed, not tested): Flip the switch in Settings: header reads Lots or Quantity
- **D-50** (Could not reproduce): C2-type chart: hover and arrows during a live refresh; owner: keep the reading when the levels are unchanged?
- **D-52** (Fixed, not tested): Empty builder hint with the feature off and on
- **D-53** (Fixed, not tested): Type 20+ characters in the Save box and in the rename box
- **D-54** (Fixed, not tested): Adjustments > Playbooks > own playbook: Delete, Cancel, Delete; no Test button
- **D-57** (Needs owner decision): After Q5: adjustments page dates; the disconnect sentence
- **D-65** (Fixed, not tested): Rename a paper trade from the builder; status matches My Strategies
- **D-66** (Fixed, not tested): Completed page times match the stop-out times

## Gates of the final head

| Gate | Command | Result |
|---|---|---|
| Generated files | one commit 26bd65e (reply inventory, `openapi.json`, digest, coverage stage S6.7 for ADR-325) and a82fdf7d (coverage register) | committed |
| Stale expectations | 4f5c3ce8: a 24-hour label (D-57), the D-68 reply model registered, 22 reviewer notes for new text owners | committed |
| Reply inventory | `python scripts/reply_inventory.py --check` | exit 0 |
| OpenAPI drift | `pytest -c pytest-app.ini tests_app/test_openapi_drift.py` | 1 passed |
| Coverage map | `python scripts/orchestrator/coverage.py . --check` | OK: every discovered id has a valid stage (open-issues compare skipped: `gh` not signed in here) |
| Front end, whole | `npx vitest run` | Test Files 220 passed (220); Tests 2591 passed (2591) |
| DB files touched, one pass | 11 files under `/root/ofo-db-fresh.sh` | one pass: 66 failed, 199 passed (ADR-058 cross-file interference, as in Parts C and D). Each file alone, on a fresh clone: 11, 34, 15, 104, 10, 9, 31, 214, 28, 29, 9 passed (494, 0 failed) |
| App suite without DB | `pytest -c pytest-app.ini tests_app -m "not full_chain"` | 5430 passed, 3 failed; the 3 were stale expectations fixed in 4f5c3ce8 (those files: 253 passed); the whole suite runs again inside prepush |
| ci_local | `python tools/ci_local.py` | TOTAL: 16 passed, 0 failed, 5 skipped |
| prepush | `python scripts/orchestrator/prepush.py` | run on the report commit; result line in the progress log and the PR #722 comment |

## DONE / PENDING / BLOCKED / PARKED / NEXT

- **DONE:** 71 of 71 issues have a final status for this chain (counts above); 57 are Fixed, not tested.
- **PENDING:** the owner's read of ADR-323, ADR-324, ADR-325 and questions Q2 to Q8; #723.
- **BLOCKED:** D-25 (Q2) and the last part of D-57 (Q5), each on a clash between two owner texts.
- **PARKED:** D-15, D-27; five owner-parked features.
- **NEXT:** the screen checks on the owner's PC, in the order above (A in market hours first), then the owner's
  answers to Q2 to Q8. The pull request stays a draft until the screen checks pass.
