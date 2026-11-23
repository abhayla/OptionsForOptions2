# Final consolidated defects: iron condor live test 2026-11-23

Source: issues.md, 169 rows (ids unique). Consolidated into 71 defects (D-01..D-58 keep their ids from issues-consolidated.md; D-59..D-71 are new). Proof: a script checked that every row id in issues.md maps to exactly one defect (169 mapped, 0 missing, 0 duplicated; table at bottom).

Lead corrections applied: D-21 (no wrong-side claim, class 3 "raises max loss, preview does not say why"); D-22 (alert record exists; narrowed to History page, closed-trade page, index level at firing); L-1 typed MISSING FEATURE class 5 (D-61); N-11 added as class 1 (D-59); duplicate/fifth leg K-2 split out of D-47 as class 1 (D-60); N-7 UNCONFIRMED class 3 (D-69).

## Counts per class
- Class 1: can lose money or a position: 7
- Class 2: a money number wrong or on a different basis: 16
- Class 3: suggestion/alert wrong, missing or late: 19
- Class 4: speed and failures to load: 4
- Class 5: labels, wording, layout: 25

## Counts per type
- DEFECT: 35
- BASIS-LABEL: 18
- MISSING FEATURE: 12
- TEST-DATA NOISE: 1
- UNCONFIRMED: 5

## Top fifteen to fix, in order
1. D-01 A stop level on the wrong side of the market is accepted without warning and instantly closes the whole condor
2. D-02 Adjustment orders go out in an unsafe order: a naked short is left between fills
3. D-59 At expiry settlement of a two-expiry trade the armed index stops are silently removed
4. D-03 After an adjustment the armed stops are not refitted and the app does not warn
5. D-60 A duplicate leg or a fifth leg is accepted silently
6. D-04 The 2-adjustment limit is exceeded or disappears
7. D-05 Saving a stop gives no feedback, double-save makes duplicate exits, and a save can be silently lost
8. D-06 Live Strategies card shows different max profit/loss/breakevens than the builder after an adjustment
9. D-07 The same strategy shows different P&L on the card, the detail page and the positions page at the same minute
10. D-08 On expiry day the Estimated-now numbers and what-if assume about a day left
11. D-36 Adjustment check and Review adjustment drawer are very slow or fail with a server error
12. D-21 The Reduce suggestion raises max loss and the preview does not say why
13. D-22 A fired stop is missing from Alerts History, and the closed trade's own page gives no reason or index level
14. D-71 Expiry settlement leaves no record: no index value, no time, no word "settled"
15. D-12 Theta per day is implausibly large on expiry-day condors

## Questions for the owner (every MISSING FEATURE plus defects whose fix changes what a trader is told or allowed to do)
- D-01 [DEFECT] A stop level on the wrong side of the market is accepted without warning and instantly closes the whole condor: Reject a stop on the wrong side of the market, or ask for confirmation first?
- D-60 [DEFECT] A duplicate leg or a fifth leg is accepted silently: Refuse, merge or warn on a duplicate or fifth leg?
- D-59 [DEFECT] At expiry settlement of a two-expiry trade the armed index stops are silently removed: Keep index stops after part of a two-expiry trade settles, or remove them with a visible note?
- D-02 [DEFECT] Adjustment orders go out in an unsafe order: a naked short is left between fills: Block or reorder adjustment orders so a naked short is never left, or only warn?
- D-04 [DEFECT] The 2-adjustment limit is exceeded or disappears: Should the 2-adjustment limit hold after every adjustment, and can a third be offered?
- D-21 [DEFECT] The Reduce suggestion raises max loss and the preview does not say why: Hide or flag "Reduce" when it raises max loss?
- D-25 [DEFECT] Take profit, whole strategy is offered at a loss with the same numbers as Exit: Offer "Take profit" only when in profit?
- D-33 [MISSING FEATURE] Add to Paper is allowed despite Not enough funds on a 0-day condor: Should paper trades be blocked when funds are short (a 0-day condor needed more margin than the paper funds available)?
- D-61 [MISSING FEATURE] Buying back one short leaves a lone long option with no note on screen: Add a one-line "this is now directional" note after buying back one short?
- D-62 [MISSING FEATURE] Few repair or profit-taking routes on a small condor: Add a "close one leg" and partial profit route for 1-lot condors?
- D-34 [MISSING FEATURE] No profit-target amount or take-profit stop exists: Add a profit-target amount or take-profit stop?
- D-35 [MISSING FEATURE] No notification channel can be added: Add a way to set up notification channels?
- D-41 [MISSING FEATURE] Live and My Strategies cards show no P&L or health, and a card can stay Loading: Show P&L and health on Live / My Strategies cards?
- D-48 [MISSING FEATURE] No control to change the expiry of existing legs: Allow changing the expiry of existing legs?
- D-51 [MISSING FEATURE] Strategy Chart tab says it is not available on paper strategies: Provide the Strategy Chart for paper trades?
- D-54 [MISSING FEATURE] Playbook editor Test does nothing and Delete needs no confirmation: Make playbook Test work, and confirm before deleting a playbook?
- D-55 [MISSING FEATURE] Option chain filters apply late and Change / OI Change columns are always blank: Show Change / OI Change in the chain and apply filters as typed?
- D-56 [MISSING FEATURE] Home overview shows only index values: Show strategy count, P&L and alert count on Home?
- D-68 [MISSING FEATURE] No screen gives the day total for the test trades: Add a day total P&L that excludes old scenario trades?

## What passed (matched hand arithmetic or behaved correctly)
- Entry credit, max profit/loss and breakevens: C7 max profit/loss 1,727.36 / 4,773.64 shown as 1,727 / 4,773 (within Rs 1); C5 156 after an adjustment 1,057.12 / 2,942.88 matched exactly; draft X with 6 legs net 8,320 and max loss -18,004 right.
- Leg and booked P&L on entries and adjustments: C7 buy-back booked +2,606.50 = (46.90 - 6.80) x 65; C9 roll booked -39.00 and -643.50 (with earlier +26, -182) re-derived; C6 159 builder matched hand arithmetic (open credit 68.30, booked -237.25, charges 435.55).
- Stop-outs: C3, C4, C8 and C11 fired at the set level and closed all four legs; C11 final -461.50 matched arithmetic; the alert lists the four exit prices and ends "A paper exit only: no order was sent to Zerodha".
- Time exit: clock-time opportunities appeared at 14:31:01 for C10 and C11 (Open 29 -> 32); C10 exit filled at 14:31:24.
- Manual exits: C7 buy-back and the C5/C9 adjustments booked the amounts shown on the fills.
- Expiry settlement of C2 157: +484.25 gross / +387.01 net (charges 97.24, no exit charges at expiry) matched hand arithmetic.
- Totals: positions header Booked P&L +11,631.57 equals the sum of 24 cards; bell count 29 = 29 rows on Alerts > Active; a strategy with nothing booked (C2 157) matched on card and builder (+290 / -6,210).

## Defects

### Class 1: can lose money or a position

#### D-01 [DEFECT] A stop level on the wrong side of the market is accepted without warning and instantly closes the whole condor
- Trader sees: Conditional exit 'Above 25000' saved while NIFTY was ~25,560; it fired at once and closed all 4 legs of C3 (exit charges ~112.71). Alert reads 'NIFTY crossed above 25,000' with no index price at firing. Not rejected, not confirmed.
- Where: Positions > Stops > Conditional exit; alert text
- Source rows: C-1, E-6, D-9
- Seen: 3 row(s), condors C3 (158)
- Unverified: none marked
- Class: 1

#### D-02 [DEFECT] Adjustment orders go out in an unsafe order: a naked short is left between fills
- Trader sees: Roll on C1 155: order 1 sells the 25300 PE hedge, order 2 buys back the short 25400 PE, so the short put is naked after fill 1. Second adjustment sold new short 25650 CE before buying its hedge 25750 CE; fills were recorded in that same order. (J-4 also showed three different max-loss numbers for one adjustment: -685 / -2,756 in the modal, 3,004.08 in the drawer, 2,942.88 after.) C9 164 diagonal roll: hedge 25300 PE sold first, then short 25400 PE bought back; app only warns generically that it could not check for a sold option without protection.
- Where: Review adjustment drawer / Review paper orders dialog; Orderbook tab
- Source rows: F-a2, G-1, H-1, J-4, L-7
- Seen: 5 row(s), condors C1 155, C6 159, C5 156, C9
- Unverified: none marked
- Class: 1

#### D-03 [DEFECT] After an adjustment the armed stops are not refitted and the app does not warn
- Trader sees: C1 155: 'Below 25,355' stayed armed after the roll though the new put spread is 25400/25500 (it can never protect); a leg stop 'Above 124.50' stayed on a contract already closed; 'Above 25,645' sits 5 below the new short 25650. C3b 162: after a reduce, the Above stop is 32 beyond the new breakeven. C1: cancelled rows stay in the stops list, Below 25,355 appears twice; Above 25,645 stays armed below breakeven 25,693.
- Where: Positions > Stops panel
- Source rows: F-a4, G-2, G-7, L-10
- Seen: 4 row(s), condors C1 155, C3b 162
- Unverified: none marked
- Class: 1

#### D-04 [DEFECT] The 2-adjustment limit is exceeded or disappears
- Trader sees: C1: header 'Adjustment limit reached (2 of 2)' yet the offered Close/Exit rows say 'Adjustments used 3 of 2'. C9 164: 'Used 0 of 2' before a Reduce, after it '1 used; no plan maximum set' (the limit vanished).
- Where: Adjustment drawer / adjustment table
- Source rows: G-3, K-8
- Seen: 2 row(s), condors C1 155, C9 164
- Unverified: none marked
- Class: 1

#### D-05 [DEFECT] Saving a stop gives no feedback, double-save makes duplicate exits, and a save can be silently lost
- Trader sees: After Save the input clears with no message; pressing Save twice made TWO identical armed exits on C7. A save made during a 'could not get an answer from the server' error was lost with no warning (C5). A toast shifted the layout and the Save click missed (values stayed, 'No stops set').
- Where: Positions > Stops (paper)
- Source rows: B-4, B-6, C-7
- Seen: 3 row(s), condors C7, C5, all
- Unverified: B-6 and C-7 seen once each
- Class: 1

#### D-59 [DEFECT] At expiry settlement of a two-expiry trade the armed index stops are silently removed
- Trader sees: C9 164 after the 23 Nov legs settled at 15:45: the index stops Below 25,359 / Above 25,728 are gone (Stops panel says "No stops set") on the remaining 1 Dec put spread. No alert, no note. The spread is unprotected overnight.
- Where: Positions > Stops after expiry settlement
- Source rows: N-11
- Seen: 1 row(s), condors C9 164
- Unverified: none marked
- Class: 1

#### D-60 [DEFECT] A duplicate leg or a fifth leg is accepted silently
- Trader sees: Draft X: a fifth long 25300 PE and a duplicate short 25500 PE were accepted as separate rows (6 legs, label turned "Custom Strategy"), never merged or warned. Net 8,320 and max loss -18,004 were arithmetically right.
- Where: Strategy builder picker
- Source rows: K-2
- Seen: 1 row(s), condors draft X
- Unverified: none marked
- Class: 1


### Class 2: a money number wrong or on a different basis

#### D-06 [DEFECT] Live Strategies card shows different max profit/loss/breakevens than the builder after an adjustment
- Trader sees: C1 155: card +1,985 / -4,515, BE 25,466/25,684 vs builder +2,380.32 / -4,119.68, BE 25,457/25,693. C6 159: card +4,150 / -2,350 vs builder +3,766.70 / -2,733.30. A strategy with nothing booked (C2 157) matches. Builder matches hand arithmetic; the card matches neither.
- Where: Live Strategies card vs strategy builder
- Source rows: H-3, I-8
- Seen: 2 row(s), condors C1 155, C6 159
- Unverified: none marked
- Class: 2

#### D-07 [DEFECT] The same strategy shows different P&L on the card, the detail page and the positions page at the same minute
- Trader sees: C4: Live/Paper card -245.07, builder Total P&L -118.34 (11:18), positions page later -401.07. C6: -275.73 vs -269.02; C7: -9.67 vs -3.17 in list vs panel.
- Where: Live/Paper card, builder detail, Positions
- Source rows: A-2, B-12
- Seen: 2 row(s), condors C4, C6, C7
- Unverified: none marked
- Class: 2

#### D-08 [DEFECT] On expiry day the Estimated-now numbers and what-if assume about a day left
- Trader sees: C2 157 (0DTE, ~3 h left): at 25300 Estimated-now -1,675 / table -1,684 while hand arithmetic at expiry is +484.25; at 25900 -1,898 vs -2,765.75. C2 157: Estimated-now curve says "Estimate not available" at 14:50, 15:00, 15:15, 15:25 (no now-curve at 0 days at all).
- Where: Builder what-if + payoff table
- Source rows: I-3, N-5
- Seen: 2 row(s), condors C2 157, C2
- Unverified: none marked
- Class: 2

#### D-09 [DEFECT] Paper fills in adjustments land far from the quote shown on the dialog
- Trader sees: C4: buy back 25500 PE quoted ~42.55, filled 47.30 (Rs 309 worse). C9: quoted debit 1,625, filled 1,820. Other cases land in the trader's favour (C1, C6, C5); adds fill exactly. Quote can be ~40 s old at confirm. Later: C7 buy-back quote 7.00 filled 6.80; C9 roll fills 6.25 (quote 6.45), 22.75 (quote 23.85); C10 time exit short call bought 1.15 above quote (Rs 149.50); C11 stop bought 51.55 vs 43.15 quoted. Booked P&L re-derived correctly each time.
- Where: Review paper orders dialog vs Orderbook
- Source rows: F-a3, G-5, H-5, J-5, K-9, L-3, L-9, M-13, N-8
- Seen: 9 row(s), condors C4, C3b, C1, C6, C5, C9, C7, C9, C10, C11
- Unverified: none marked
- Class: 2

#### D-10 [DEFECT] Closed legs lose their own booked P&L or exit price; it shows on the wrong leg or nowhere
- Trader sees: C1 155: closed short 25400 PE (+643.50) has no row; the amount shows on the NEW long 25400 PE row. Closed legs show Lots 0 and no exit price. C3 closed card shows no exit prices. Exited C3 paper detail has max profit = max loss = +94.27.
- Where: Builder P&L list, Positions cards, completed list, paper API
- Source rows: C-4, I-12, G-4, F-a8, E-5
- Seen: 5 row(s), condors C1 155, C3 158
- Unverified: none marked
- Class: 2

#### D-11 [DEFECT] Add Booked switch changes the chart but not the max profit/loss/breakeven tiles
- Trader sees: C1 155: tiles 2,380.32 / -4,119.68 / BE 25,457-25,693 identical with switch ON and OFF; chart OFF shows ~+2,200 / -4,300. Full table breakeven 25,466/25,684 differs from the tile. C7 161 payoff chart with Booked ticked: left floor about -7,700 vs max loss -5,303 (looks like booked +2,606 subtracted instead of added).
- Where: Builder tiles/chart
- Source rows: I-7, M-7
- Seen: 2 row(s), condors C1 155, C7
- Unverified: M-7 not rechecked
- Class: 2

#### D-12 [DEFECT] Theta per day is implausibly large on expiry-day condors
- Trader sees: C1 ATM 25600 theta -215/unit/day vs premium 63; C2 157 position theta +4,008/day vs position value ~448; C9 (4 lots) 27,896 vs credit 5,187; net theta/day 6x the remaining profit on 157 (3,753 vs 607). Annual theta /365 with 4 h left; units unlabelled; Decay column differs. C10 0DTE: theta 31,727 vs credit 2,294. C2: theta/unit 149.8 (14:50) -> 1,467.68 (15:25), shown as plain numbers.
- Where: Builder Greeks, option chain, adjustment drawer, API
- Source rows: E-2, A-7, D-14, I-5, J-9, M-9, N-4
- Seen: 7 row(s), condors C1, C2, C4, C9, all 0DTE, C10, C2
- Unverified: I-5 itself calls part of it 'known theta on expiry day'
- Class: 2

#### D-13 [BASIS-LABEL] Max profit/loss are after charges but the P&L table, payoff dialog and API profit_left say before/gross
- Trader sees: C1: dialog says curves are BEFORE charges, yet Max Profit 2,165 / Max Loss -4,335 already include Rs 203.76. C2: table +494/-6,006 vs tiles +301/-6,199. API profit_left 2,986.75 (gross) vs max_profit 2,094 (net); net basis 2,783.
- Where: Charges dialog, P&L Table tab, API
- Source rows: 3, A-1, E-1
- Seen: 3 row(s), condors C1, C2, C4, all live
- Unverified: none marked
- Class: 2

#### D-14 [BASIS-LABEL] The Charges line shows entry charges only while the P&L deducts a round trip, and there are three charge estimates
- Trader sees: C1: P&L -288.59 deducts ~204 but 'Charges Rs 103.56 (before charges)'. C4: Charges 114.16 vs ~216 deducted. API: 103.56 vs 206.84 vs 203.75. Every open card: unbooked-after-charges differs from the leg sum by 64-138 (hidden exit estimate). Drawer 'Not yet booked' -663 vs P&L -869.52. C7: Total after charges 249.24 before and after a buy-back while charges rose 102.38 -> 126.17; card unbooked -2,175.75 vs -2,102.75 from legs (73 unexplained); C8 -725.16 vs -617.50. C2: tile estimate +290.49 (round-trip charges 193.76) vs final net +387.01 (charges 97.24), understated 96.52 for a hold-to-expiry.
- Where: Builder summary, positions cards, drawer, API
- Source rows: 6, A-3, E-7, J-11, F-a6, L-4, N-13
- Seen: 7 row(s), condors C1, C2, C4, all cards, C7, C8, C2
- Unverified: none marked
- Class: 2

#### D-15 [BASIS-LABEL] Paper entry prices are re-quoted at Add to Paper and differ from the plan, with no warning
- Trader sees: C1: planned credit 36.45, paper 35.35. C3 credit 55.95 -> 58.15. C3b planned 65.60 vs paper 65.55, card breakevens still from the plan. Chain prices drift 0.5-2.6 in a minute. Builder summary keeps planned entry / max profit 301 vs paper 290.49. C8 plan 18.90 vs fill 17.60. C11: header still shows planned 23.85 / Get 1,550; fills 23.70 (credit 1,540.50).
- Where: Add to Paper dialog, builder summary
- Source rows: 5, A-4, A-8, C-8, J-13, H-6, M-5
- Seen: 7 row(s), condors C1,C2,C3,C3b,C6,C8, C11
- Unverified: none marked
- Class: 2

#### D-16 [BASIS-LABEL] Breakevens are on different bases on different screens, none labelled
- Trader sees: C6 159: builder BE excludes charges but includes booked loss; compare page BE includes charges. C5 156: max profit/loss after charges, single BE 83,467 before (83,452.9 after). C9: builder 25,374/25,713 vs adjust page 25375.84/25712.08.
- Where: Builder, compare page, adjustment page
- Source rows: H-4, J-6, K-6
- Seen: 3 row(s), condors C6, C5, C9
- Unverified: none marked
- Class: 2

#### D-17 [BASIS-LABEL] Time value is negative and uses different prices from the credit, with no label
- Trader sees: C1 0DTE: Time value -2,295..-2,412 with intrinsic 0. Draft X: 'Get 3,393' uses plan prices, Time value -3,439 uses live prices, so it moves every second while the credit is frozen.
- Where: Builder summary
- Source rows: 4, K-5
- Seen: 2 row(s), condors C1, draft X
- Unverified: none marked
- Class: 2

#### D-18 [DEFECT] The same leg shows 2-4 different prices in the same second
- Trader sees: C2: 25300 PE 7.00 / 7.45 / 7.25 / 7.10 across four panels. C5: 83000 PE 661.55 / 657.95 / 656.05 in 3 s. C7 25400 PE 21.05 / 21.35 / 21.65. C1 table 75.50 vs panel 75.00.
- Where: Builder tables and panels
- Source rows: C-5, I-6, J-7, J-14
- Seen: 4 row(s), condors C1, C2, C5, C7
- Unverified: none marked
- Class: 2

#### D-19 [DEFECT] Option chain LTP often sits outside its own bid/ask
- Trader sees: NIFTY 0DTE: 25600 CE LTP 63.10 vs bid 63.90 / ask 64.10; 25800 PE 224.45 vs 225.10/225.75. Later 6 of 12 samples outside (PE25800 bid 307.10 vs LTP 306.15).
- Where: Option chain
- Source rows: D-13, K-11, E-8
- Seen: 3 row(s), condors C1
- Unverified: E-8 tester says a 7-8 s offset may explain it
- Class: 2

#### D-20 [UNCONFIRMED] Put-call parity implies a forward below spot (SENSEX about 72 pts, NIFTY about 4 pts)
- Trader sees: SENSEX 26 Nov: C-P vs spot-K off by about -72 on every strike (83200: -44.85 vs +29.3). NIFTY 25508.60: constant -3.9 to -4.3. Could be a carry effect; not explained.
- Where: Option chain
- Source rows: D-15, K-12
- Seen: 2 row(s), condors C5, chain
- Unverified: none marked
- Class: 2

#### D-63 [BASIS-LABEL] Two-expiry trade: P&L table omits booked legs and Greeks sum across expiries unmarked
- Trader sees: C9 164 after the diagonal roll: tiles Max profit/loss/Breakeven show "-" with a reason (honest), but the P&L Table lists only open legs while total +199.02 includes booked closed legs; Greeks add both expiries (theta +146/unit on a 7-rupee expiring short); margin still 3,63,673; payoff chart shows "Estimated now" only.
- Where: Builder tabs
- Source rows: L-8
- Seen: 1 row(s), condors C9 164
- Unverified: none marked
- Class: 2


### Class 3: suggestion/alert wrong, missing or late

#### D-21 [DEFECT] The Reduce suggestion raises max loss and the preview does not say why
- Trader sees: C9 164: Reduce preview max loss 21,037.90 -> 22,736.09, actual after fill 22,859.73 (reducing the tested put spread removes put credit so the 4-lot call spread becomes the biggest loss; max profit 4,962.10 -> 3,140.27). The table never says why. The tested side (put) was right (on C7 the index was 70 points from the short put and 230 from the short call), so no wrong-side claim stands.
- Where: Review adjustment drawer / Compare
- Source rows: K-7, J-10
- Seen: 2 row(s), condors C9 164
- Unverified: none marked
- Class: 3

#### D-22 [DEFECT] A fired stop is missing from Alerts History, and the closed trade's own page gives no reason or index level
- Trader sees: The alert record EXISTS (Alerts > Active > Earlier: time, level, exit prices; C3 stop fired 11:21:58). Still: /alerts/history says 'No alerts yet'; the closed trade's page says 'No legs yet' (C4 160) or just 'Exited' (C3) with no reason; the index level at the moment of firing is not shown, only the stop level.
- Where: Alerts > History, builder of a closed strategy
- Source rows: C-3, D-8, J-2
- Seen: 3 row(s), condors C3, C4
- Unverified: none marked
- Class: 3

#### D-23 [DEFECT] Stop-out exit rows in the orderbook are labelled Add
- Trader sees: C4 160: the 4 stop-out exits carry Kind 'Add' and 25500 PE reads B Add 130 @64.30, so they look like new buys.
- Where: Builder Orderbook
- Source rows: J-1
- Seen: 1 row(s), condors C4 160
- Unverified: none marked
- Class: 3

#### D-24 [DEFECT] An armed conditional exit is not shown on the builder or tracking panel
- Trader sees: C7 161: armed 'Above 25,720' is only under Positions > Stops; the plan block lists only Target/Stop lines and shows the watch level as 'Above None'. C8: the rule-based stop ("loss of 40% of max loss") IS shown on the panel, so only the index-level conditional exit is missing.
- Where: Builder tracking panel
- Source rows: D-2, H-9, L-6
- Seen: 3 row(s), condors C7 161, C8
- Unverified: none marked
- Class: 3

#### D-25 [DEFECT] Take profit, whole strategy is offered at a loss with the same numbers as Exit
- Trader sees: C3b 162 at P&L -223 offers Take profit, identical to Exit (debit 8,468), while C4 160 correctly refuses. C5 156: Take profit has the same numbers as Exit in every row (debit 988.60, charges 75.55).
- Where: Compare approaches
- Source rows: F-a5, M-6
- Seen: 2 row(s), condors C3b 162, C5
- Unverified: M-6: whether C5 was at a loss is not stated
- Class: 3

#### D-26 [DEFECT] The Review adjustment button vanishes when the idea lapses, so a live idea cannot be acted on
- Trader sees: C7: delta 0.3675 -> 0.3311 and the row went Lapsed within 3 minutes; approaches could not be opened afterwards.
- Where: Adjustment opportunities / tracking panel
- Source rows: D-3
- Seen: 1 row(s), condors C7
- Unverified: none marked
- Class: 3

#### D-27 [DEFECT] Adjustment history is empty after adjustments
- Trader sees: C1 155: 'Adjustment history' opens empty after 2 adjustments; the link on the adjust page leads to the same empty block.
- Where: Builder bottom, adjust page
- Source rows: G-6
- Seen: 1 row(s), condors C1 155
- Unverified: none marked
- Class: 3

#### D-28 [DEFECT] Running strategies show state draft in the strategy endpoints but LIVE in the paper endpoints
- Trader sees: 155,156,157,159,160,161 are 'draft' in /api/strategies and /strategies/{id}, LIVE in /api/paper/strategies.
- Where: API
- Source rows: E-3
- Seen: 1 row(s), condors C1-C7
- Unverified: none marked
- Class: 3

#### D-29 [DEFECT] Alert list has no times, the bell count does not map to what is unread, and old scenario alerts bury the real ones
- Trader sees: Active rows have no time; 20 rows (17 old Scenario PATH-xx) vs bell 21-24; the 3 real T1123 items are buried; cannot tell which of 22 unread are stop-outs. Bell 29 = 29 rows on Active (matches), but no read/dismiss control, row click does nothing, and no alert for the C7 buy-back or C9 roll.
- Where: Alerts > Active, bell
- Source rows: D-7, J-3, L-11
- Seen: 3 row(s), condors C1, C4, all, C7, C9
- Unverified: none marked
- Class: 3

#### D-30 [BASIS-LABEL] Adjustment-opportunity counters and the row count use different units
- Trader sees: Open 23 + Dismissed 0 + Acted 0 + Completed 19 + Lapsed 47 = 89 vs 'Showing 1-25 of 52 rows' (later 93 vs 56). Counters count conditions, the list counts rows (one row can hold 4 conditions). 16 Nov PATH opportunities on expired contracts still Open. C10 row still Open after its 14:31:24 exit when read at 14:33; clock-time opportunities did appear on time (Open 29 -> 32).
- Where: Adjustment opportunities
- Source rows: D-6, H-10, M-12
- Seen: 3 row(s), condors all, C10, C11
- Unverified: none marked
- Class: 3

#### D-31 [BASIS-LABEL] The same trigger value differs between drawer, panel and opportunity list
- Trader sees: C6: 0.6851 % drawer, 0.6882 % panel, 0.7293 % list within a minute (fire time vs live, not labelled).
- Where: Adjustment drawer / panel / list
- Source rows: D-5
- Seen: 1 row(s), condors C6
- Unverified: none marked
- Class: 3

#### D-32 [BASIS-LABEL] Watch an index level (drawer) looks like a Conditional exit but does not exit
- Trader sees: C8 163: tester typed an exit level into the drawer Watch box; it only alerts, nothing says so.
- Where: Adjustment drawer vs Stops
- Source rows: J-12
- Seen: 1 row(s), condors C8 163
- Unverified: none marked
- Class: 3

#### D-33 [MISSING FEATURE] Add to Paper is allowed despite Not enough funds on a 0-day condor
- Trader sees: C1: margin needed above the funds available [account figure removed], 'Not enough funds' shown, Add to Paper still allowed; nearest expiry is today. A product question whether paper should block. Margin needed [account figure removed] (2 lots, 100 wide, max loss 10,905) and [account figure removed] (1 lot, 50 wide, max loss 1,910): 25x-70x max loss for a defined-risk condor; Not enough funds shown (available [account figure removed]).
- Where: Create Strategy / Add to Paper
- Source rows: 8, M-4
- Seen: 2 row(s), condors C1, C10, C11
- Unverified: whether the margin figure is the exchange figure is unchecked
- Class: 3

#### D-34 [MISSING FEATURE] No profit-target amount or take-profit stop exists
- Trader sees: Only an index-level Target on the builder; no profit amount field on the Stops panel.
- Where: Builder, Stops panel
- Source rows: C-9
- Seen: 1 row(s), condors C1 155
- Unverified: none marked
- Class: 3

#### D-35 [MISSING FEATURE] No notification channel can be added
- Trader sees: Notification settings only say 'No notification channels are set up yet.' with no way to add one.
- Where: /alerts/notification-settings
- Source rows: D-10
- Seen: 1 row(s), condors -
- Unverified: none marked
- Class: 3

#### D-62 [MISSING FEATURE] Few repair or profit-taking routes on a small condor
- Trader sees: C7 161 (1 lot): partial profit refused ("50% is not a whole number of lots", reason right), so full Take profit is the only option; no "close 1 of 2 legs". C8 163 (2 lots, put side tested): both rolls are refused (no strike at target delta; roll costs 2,087-4,963 over the 634 cap; 25350 beyond the 25400 wing); only Reduce / Close tested spread / Exit remain.
- Where: Review adjustment drawer
- Source rows: L-2, L-5
- Seen: 2 row(s), condors C7 161, C8 163
- Unverified: none marked
- Class: 3

#### D-69 [UNCONFIRMED] Index value frozen at 25,366.40 on reads from 15:15 to 15:27
- Trader sees: NIFTY 25366.40 identical on the builder at 15:15:18 and 15:25:27 and on the index view at 15:25:51 while option prices moved (stamp advanced). Cause unknown (feed, display or a tool read).
- Where: Index feed
- Source rows: N-7
- Seen: 1 row(s), condors all
- Unverified: cause unverified
- Class: 3

#### D-70 [UNCONFIRMED] 1 Dec put prices kept moving after the market-closed banner
- Trader sees: C9 24900 PE 83.70 -> 75.85 and 25000 PE 107.70 -> 99.65 between 15:30:24 and 15:38:09 after "Market closed". Re-marked by the app or live feed not checked.
- Where: Builder / chain after close
- Source rows: N-9
- Seen: 1 row(s), condors C9 164
- Unverified: feed vs re-mark unverified
- Class: 3

#### D-71 [DEFECT] Expiry settlement leaves no record: no index value, no time, no word "settled"
- Trader sees: C2 157 at 15:46: legs show "Closed, booked" exactly like a manual exit; no index value, no time, no "expired/settled"; builder becomes "No legs yet". No alert or record for C2 or C9; only stop-loss records exist. (Settlement arithmetic itself matched: +484.25 gross / +387.01 net.)
- Where: Builder, Alerts / Records after expiry
- Source rows: N-10, N-14
- Seen: 2 row(s), condors C2 157, C9 164
- Unverified: none marked
- Class: 3


### Class 4: speed and failures to load

#### D-36 [DEFECT] Adjustment check and Review adjustment drawer are very slow or fail with a server error
- Trader sees: Check hangs 30-65 s then 503; C7 failed 3 of 3, C5 156 3 of 3, C6 159 3 tries. With no tester active still 15.6 s; with two testers 56.7 s, /api/health 7.5 s. Panel shows 'Could not read which rules have fired' / 'Could not load the rules in force'. Core could not be proven on C7.
- Where: /api/strategies/{id}/adjustment-check, drawer, tracking panel
- Source rows: D-1, F-a1, F-a7, H-2, I-1, I-2
- Seen: 6 row(s), condors C7,C6,C5,C1,C4
- Unverified: D-1: core not proven on C7
- Class: 4

#### D-37 [UNCONFIRMED] What-if shows nothing for a target level or date
- Trader sees: C6: after setting index level 25350 the Target and Date readouts show '-'; same minute 'Paper P&L paused - prices not live'. Dragging the date also '-'; tester unsure if tab focus is the cause.
- Where: Builder what-if
- Source rows: D-17, H-11
- Seen: 2 row(s), condors C6 159
- Unverified: H-11 marked unverified
- Class: 4

#### D-38 [DEFECT] Other pages load slowly or time out
- Trader sees: Plan dialog 'Loading the plan...' 5-12 s on every paper add; Create Strategy step 4 about 10 s; settings page 10 s then 'could not be read' (second try worked).
- Where: Builder, Create Strategy, /settings/app-settings
- Source rows: B-2, B-3, D-19
- Seen: 3 row(s), condors C5,C6,C7
- Unverified: none marked
- Class: 4

#### D-40 [TEST-DATA NOISE] Header totals blank and cards fail because of expired scenario strategies
- Trader sees: Total/Unbooked/Decay show '-' and 'This contract has expired' (old PATH-xx scenario trades); Booked P&L and Charges mix all strategies (+10,947.43 / 6,140.07). Two PATH cards show a server error.
- Where: Positions paper page header, Live cards
- Source rows: B-11, K-10, I-9
- Seen: 3 row(s), condors PATH-60/61, all
- Unverified: none marked
- Class: 4


### Class 5: labels, wording, layout

#### D-39 [DEFECT] Live-data status messages contradict the prices on the same page, then recover
- Trader sees: C1: first read 'Live market data disconnected... monitoring paused' though spot 25523.85 and leg prices were present; seconds later all live. Seen once. C9 compare page: 'Prices are 0 min old (last update 14:12)' next to 'figures below are not live' and 'Adjustment checks are paused: prices are not live'; spot on the page read 25422.1 and a reload 1-2 min later was live.
- Where: Builder summary, compare page
- Source rows: 2, M-10
- Seen: 2 row(s), condors C1, C9
- Unverified: none marked
- Class: 5

#### D-41 [MISSING FEATURE] Live and My Strategies cards show no P&L or health, and a card can stay Loading
- Trader sees: Live card has breakevens and max profit/loss but no P&L; first paint 'unavailable' and glued text '46.2556.75'; C5 stuck 'Loading this strategy...' while 4 others loaded.
- Where: Live Strategies, My Strategies
- Source rows: 7, B-8
- Seen: 2 row(s), condors C1, C5
- Unverified: none marked
- Class: 5

#### D-42 [DEFECT] My Strategies shows the original legs and closed strategies are missing
- Trader sees: C6/C1 rows still read 'NIFTY 25300 PE and 3 more' (a closed leg), saved before the adjustment. 158 was missing from the list at 11:52; later Completed lists C3, C3b, C4, so that part no longer applies.
- Where: My Strategies, Completed
- Source rows: H-7, I-11, H-8, I-10
- Seen: 4 row(s), condors C1, C6, C3
- Unverified: I-10 marks the missing-Completed part as no longer true
- Class: 5

#### D-43 [BASIS-LABEL] Strategy names are cut off to about 8 characters
- Trader sees: T1123-C5..C9 all read 'T1123-C...' at 1036 px, so strategies cannot be told apart.
- Where: My Strategies
- Source rows: B-7, K-13
- Seen: 2 row(s), condors C5-C9
- Unverified: none marked
- Class: 5

#### D-44 [BASIS-LABEL] Stop list uses raw contract names, different from the form
- Trader sees: 'SENSEX 83400 CE 2026-11-26 Above 992.80 armed' vs 'SENSEX 26 Nov'; 'NIFTY 25600 CE 2026-11-23 Above 124.50' vs 'NIFTY 23 Nov 2026 25600 CE'; list sits below the fold after Save.
- Where: Stops list
- Source rows: B-5, C-6
- Seen: 2 row(s), condors C5, C1, C4
- Unverified: none marked
- Class: 5

#### D-45 [BASIS-LABEL] Adjustment comparison table is hard to read
- Trader sees: Drawer first renders every number as '-' while reading; Compare values and 'Largest/Lowest' labels interleave; rows without column labels (C5 156, 35 s load).
- Where: Adjustment drawer / Compare
- Source rows: D-4, I-13
- Seen: 2 row(s), condors C6, C5
- Unverified: none marked
- Class: 5

#### D-46 [BASIS-LABEL] Greeks and max profit/loss display rounding hides the real number
- Trader sees: Gamma 0.0000/-0.0001, Delta 0.00 on C5/C6; C7 max profit/loss rounded down both ways (1,727.36 -> 1,727; 4,773.64 -> 4,773), within Rs 1.
- Where: Builder summary
- Source rows: B-9, B-10
- Seen: 2 row(s), condors C5,C6,C7
- Unverified: none marked
- Class: 5

#### D-47 [DEFECT] Builder strike picker is confusing
- Trader sees: Picker says '0 legs selected' while the draft holds 4; B/S buttons appear only on hover; lots dropdown only after the first click.
- Where: Strategy builder picker
- Source rows: K-1
- Seen: 1 row(s), condors draft X
- Unverified: none marked
- Class: 5

#### D-48 [MISSING FEATURE] No control to change the expiry of existing legs
- Trader sees: Edit-leg form has no expiry; user must remove and re-add every leg to move to 1 Dec.
- Where: Strategy builder
- Source rows: K-3
- Seen: 1 row(s), condors draft X
- Unverified: none marked
- Class: 5

#### D-49 [BASIS-LABEL] Lots/Quantity switch does not relabel the column header
- Trader sees: Cells change to 130/65 but the header still says 'Lots'.
- Where: Builder settings
- Source rows: K-4
- Seen: 1 row(s), condors draft X
- Unverified: none marked
- Class: 5

#### D-50 [UNCONFIRMED] Payoff chart shows no tooltip on hover or arrow keys
- Trader sees: Hover at 3 levels and ArrowRight x3 show nothing though the aria text promises a reading; tester says the tool may not trigger hover.
- Where: Payoff chart
- Source rows: A-5, I-4
- Seen: 2 row(s), condors C2 157
- Unverified: A-5 marked unverified
- Class: 5

#### D-51 [MISSING FEATURE] Strategy Chart tab says it is not available on paper strategies
- Trader sees: 'The strategy chart is not available.' on C3/C4.
- Where: Strategy Chart tab
- Source rows: A-6
- Seen: 1 row(s), condors C3, C4
- Unverified: none marked
- Class: 5

#### D-52 [BASIS-LABEL] Ready-made shapes text points to a panel that is not there
- Trader sees: 'Pick strikes, or start from a ready-made shape below.' but no shapes; only via Create Strategy.
- Where: Strategy builder
- Source rows: 1
- Seen: 1 row(s), condors C1
- Unverified: none marked
- Class: 5

#### D-53 [BASIS-LABEL] Builder title New Strategy is not editable and the name box silently limits to 20 characters
- Trader sees: Typing into the title scrolled the page; name is only asked in the Save dialog; Create-Strategy name box stops at 20 characters without saying so.
- Where: Strategy builder
- Source rows: B-1
- Seen: 1 row(s), condors C5
- Unverified: none marked
- Class: 5

#### D-54 [MISSING FEATURE] Playbook editor Test does nothing and Delete needs no confirmation
- Trader sees: Tab says testing past expiries is not in this version; 'Test this playbook' greys out and returns nothing; deleting own playbook asked nothing.
- Where: Playbook editor
- Source rows: D-12
- Seen: 1 row(s), condors -
- Unverified: none marked
- Class: 5

#### D-55 [MISSING FEATURE] Option chain filters apply late and Change / OI Change columns are always blank
- Trader sees: Min OI/volume/premium apply only after leaving the box; Change and OI Change always '-'; Min OI keeps a row if call or put passes.
- Where: Option chain
- Source rows: D-16
- Seen: 1 row(s), condors -
- Unverified: none marked
- Class: 5

#### D-56 [MISSING FEATURE] Home overview shows only index values
- Trader sees: No running-strategy count, P&L or alert count.
- Where: /home/overview
- Source rows: D-18
- Seen: 1 row(s), condors -
- Unverified: none marked
- Class: 5

#### D-57 [BASIS-LABEL] Dates on the adjustments page use US month/day
- Trader sees: '11/11/2026, 12:33:17 AM' vs '23 Nov 2026' elsewhere; 11/1 ambiguous.
- Where: /strategies/adjustments
- Source rows: D-11
- Seen: 1 row(s), condors -
- Unverified: none marked
- Class: 5

#### D-58 [BASIS-LABEL] Small wording problems: zero-price message, quote characters in names, tested-side wording
- Trader sees: Above=0 says 'Enter a price in steps of 0.05'; stored names carry literal double quotes (also held.broker); after adjustment 1 the rule line does not say whether put or call is tested. C9 drawer: 'Time exit: Your playbook sets no time exit'; C6 (expires 1 Dec) is told 'offered on expiry day from 14:30' which reads as if it applied. C2 opportunity shows raw key 'day.beforeHoliday.1500.0'.
- Where: Stops form, API, adjustment drawer
- Source rows: C-2, E-4, J-8, M-11, N-3
- Seen: 5 row(s), condors C3, all, C5, C9, C6, C2
- Unverified: none marked
- Class: 5

#### D-61 [MISSING FEATURE] Buying back one short leaves a lone long option with no note on screen
- Trader sees: C7 161: "Buy back the untested short" buys the 25700 CE and leaves the long 25800 CE; the trade becomes a put spread plus a long call, max profit "No fixed maximum". This is the trader's choice, not a defect; only a one-line note that the shape is now directional is missing.
- Where: Review adjustment drawer / builder tiles
- Source rows: L-1
- Seen: 1 row(s), condors C7 161
- Unverified: none marked
- Class: 5

#### D-64 [DEFECT] After the 15:30 close the page shows raw errors and never says settlement comes at 15:45
- Trader sees: C2 157 at 15:30: "Paper P&L paused - prices not live, as of Time not available", Total P&L "-", payoff "Outcome cannot be shown - Instrument NSE_FO:64457 cannot be used: expired ..." with raw ids; the 15:45 settlement is mentioned only in Settings. Positions cards say "No price for: ..." and totals "-" even for C9 whose 1 Dec legs are priced. After settlement C9 shows "No price for: NIFTY 1 Dec 24900 PE, 25000 PE" while printing LTP 74.55 / 97.15 and P&L.
- Where: Builder, Positions, after 15:30
- Source rows: N-1, N-2, N-12
- Seen: 3 row(s), condors C2 157, C9 164
- Unverified: none marked
- Class: 5

#### D-65 [DEFECT] Renaming a paper trade from the builder fails, and its status differs between lists
- Trader sees: C11 167: Builder > Saved Strategies > Rename gave "Some of the values sent with this request are missing or not in the expected form" twice; the same rename works from My Strategies and on a Draft (C10 166). Builder list says "Draft", My Strategies says "Running" for the same trade.
- Where: Builder saved list, My Strategies
- Source rows: M-1, M-2
- Seen: 2 row(s), condors C11 167, C10 166
- Unverified: none marked
- Class: 5

#### D-66 [DEFECT] Completed page "last saved" shows the last builder save, not the close time
- Trader sees: C1 shows 11:06:39 and C8 12:13:30 vs real stop-outs 13:24:07 and 13:44:08. C10 shows 14:00:44 (before it opened at 14:02), C7 11:18:09, C6 11:15:21, C5 11:11:44 while closed 14:31-14:44. C2 shows 11:12:34 after settlement at 15:45.
- Where: Completed page
- Source rows: M-3, M-14
- Seen: 2 row(s), condors C1, C8, C10, C7, C6, C5
- Unverified: none marked
- Class: 5

#### D-67 [DEFECT] Adjustment toasts pop up within minutes of opening a trade and cover page buttons
- Trader sees: C10 gamma 2.95% vs rule 2%, C11 tested delta 0.3809 vs 0.35, within 1-3 min of opening; each toast covers buttons. The rules are working as set; the noise and overlap are the problem.
- Where: Toasts
- Source rows: M-8
- Seen: 1 row(s), condors C10 166, C11 167
- Unverified: none marked
- Class: 5

#### D-68 [MISSING FEATURE] No screen gives the day total for the test trades
- Trader sees: Header Booked P&L +7,496.11 (14:47) vs the T1123 completed nets of -7,783.16 (9 rows); the header includes old Scenario trades and open-trade booked parts. Home overview shows no P&L at all.
- Where: Positions header, Home
- Source rows: N-6
- Seen: 1 row(s), condors C9 164, all
- Unverified: none marked
- Class: 5

## Every original row id to consolidated id

| Row | Defect |
|---|---|
| 1 | D-52 |
| 2 | D-39 |
| 3 | D-13 |
| 4 | D-17 |
| 5 | D-15 |
| 6 | D-14 |
| 7 | D-41 |
| 8 | D-33 |
| A-1 | D-13 |
| A-2 | D-07 |
| A-3 | D-14 |
| A-4 | D-15 |
| A-5 | D-50 |
| A-6 | D-51 |
| A-7 | D-12 |
| A-8 | D-15 |
| C-1 | D-01 |
| C-2 | D-58 |
| B-1 | D-53 |
| B-2 | D-38 |
| B-3 | D-38 |
| B-4 | D-05 |
| B-5 | D-44 |
| B-6 | D-05 |
| B-7 | D-43 |
| B-8 | D-41 |
| B-9 | D-46 |
| B-10 | D-46 |
| B-11 | D-40 |
| B-12 | D-07 |
| C-3 | D-22 |
| C-4 | D-10 |
| C-5 | D-18 |
| C-6 | D-44 |
| C-7 | D-05 |
| E-1 | D-13 |
| E-2 | D-12 |
| E-3 | D-28 |
| E-4 | D-58 |
| E-5 | D-10 |
| E-6 | D-01 |
| E-7 | D-14 |
| E-8 | D-19 |
| C-8 | D-15 |
| C-9 | D-34 |
| D-1 | D-36 |
| D-2 | D-24 |
| D-3 | D-26 |
| D-4 | D-45 |
| D-5 | D-31 |
| D-6 | D-30 |
| D-7 | D-29 |
| D-8 | D-22 |
| D-9 | D-01 |
| D-10 | D-35 |
| D-11 | D-57 |
| D-12 | D-54 |
| D-13 | D-19 |
| D-14 | D-12 |
| D-15 | D-20 |
| D-16 | D-55 |
| D-17 | D-37 |
| D-18 | D-56 |
| D-19 | D-38 |
| F-a1 | D-36 |
| F-a2 | D-02 |
| F-a3 | D-09 |
| F-a4 | D-03 |
| F-a5 | D-25 |
| F-a6 | D-14 |
| F-a7 | D-36 |
| F-a8 | D-10 |
| G-1 | D-02 |
| G-2 | D-03 |
| G-3 | D-04 |
| G-4 | D-10 |
| G-5 | D-09 |
| G-6 | D-27 |
| G-7 | D-03 |
| H-1 | D-02 |
| H-2 | D-36 |
| H-3 | D-06 |
| H-4 | D-16 |
| H-5 | D-09 |
| H-6 | D-15 |
| H-7 | D-42 |
| H-8 | D-42 |
| H-9 | D-24 |
| H-10 | D-30 |
| H-11 | D-37 |
| I-1 | D-36 |
| I-2 | D-36 |
| I-3 | D-08 |
| I-4 | D-50 |
| I-5 | D-12 |
| I-6 | D-18 |
| I-7 | D-11 |
| I-8 | D-06 |
| I-9 | D-40 |
| I-10 | D-42 |
| I-11 | D-42 |
| I-12 | D-10 |
| I-13 | D-45 |
| J-1 | D-23 |
| J-2 | D-22 |
| J-3 | D-29 |
| J-4 | D-02 |
| J-5 | D-09 |
| J-6 | D-16 |
| J-7 | D-18 |
| J-8 | D-58 |
| J-9 | D-12 |
| J-10 | D-21 |
| J-11 | D-14 |
| J-12 | D-32 |
| J-13 | D-15 |
| J-14 | D-18 |
| K-1 | D-47 |
| K-2 | D-60 |
| K-3 | D-48 |
| K-4 | D-49 |
| K-5 | D-17 |
| K-6 | D-16 |
| K-7 | D-21 |
| K-8 | D-04 |
| K-9 | D-09 |
| K-10 | D-40 |
| K-11 | D-19 |
| K-12 | D-20 |
| K-13 | D-43 |
| L-1 | D-61 |
| L-2 | D-62 |
| L-3 | D-09 |
| L-4 | D-14 |
| L-5 | D-62 |
| L-6 | D-24 |
| L-7 | D-02 |
| L-8 | D-63 |
| L-9 | D-09 |
| L-10 | D-03 |
| L-11 | D-29 |
| M-1 | D-65 |
| M-2 | D-65 |
| M-3 | D-66 |
| M-4 | D-33 |
| M-5 | D-15 |
| M-6 | D-25 |
| M-7 | D-11 |
| M-8 | D-67 |
| M-9 | D-12 |
| M-10 | D-39 |
| M-11 | D-58 |
| M-12 | D-30 |
| M-13 | D-09 |
| M-14 | D-66 |
| N-1 | D-64 |
| N-2 | D-64 |
| N-3 | D-58 |
| N-4 | D-12 |
| N-5 | D-08 |
| N-6 | D-68 |
| N-7 | D-69 |
| N-8 | D-09 |
| N-9 | D-70 |
| N-10 | D-71 |
| N-11 | D-59 |
| N-12 | D-64 |
| N-13 | D-14 |
| N-14 | D-71 |
