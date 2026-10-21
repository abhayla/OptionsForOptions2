# Screens research: how similar apps lay out our screens (2026-10-19)

Owner brief (2026-10-19): look and content come from studying other brokers and tools; the business requirements stay fixed.
Method: public web pages only (vendor blogs, help centres, a few reviews). No app was logged into, no screenshot seen.
Honest limit: most vendor pages describe features, not pixel layouts. Where a layout, column set, default, empty state or
390 px behaviour was not stated, this note says "not found". The wireframes below are OUR proposals, not copies of any app.
Look and feel (font, colours, card style): follow `D:\Abhay\GLOBAL.md` section 3 "Design & UX preferences" (by path only).

## Decisions summary (one line per screen)
1. Live Strategies: a list of strategy cards grouped by underlying, worst health first; each card = server status label + spot with its time + per-leg LTP with health + paused badge when monitoring is paused.
2. Underlying/index view: two stacked index panels (NIFTY 50, SENSEX), each = value, change, time, health state; no order buttons; no chart-heavy terminal.
3. Home: adaptive stack of 3 states (new / has strategies / has active); live strip small; one primary action first.
4. Option Chain: Calls | Strike | Puts with the 5 default columns, ATM highlighted, expiry on top, Selected Legs bar with live preview; Advanced adds IV, Greeks, bid/ask.
5. Strategy "Live Position" tab: third tab of one strategy (Planning | Live Position | History); summary strip first, then legs table, then triggers and orders.
6. Market context / Learn / Alerts / Settings: plain list screens; Market context content is a designer proposal because no AC defines it; Settings follows REQ-009 AC-8 verbatim.

Cross-cutting rule: every number on every screen comes from the server (ADR-008); the browser only formats.

---

## Live Strategies (REQ-009 AC-2 "Live Strategies"; REQ-044 AC-2; REQ-049; ADR-010)

### (a) What the studied apps do
- Sensibull Positions: positions auto-grouped by stock/index; user can make named strategy groups, each with its own P&L, exit all legs together or one by one; filter by expiry, sort by instrument. https://blog.sensibull.com/2022/09/02/trade-better-with-sensibull-positions-page/ . Column set, first-shown element, spot display, empty state: not found (same URL, and https://zerodha.com/z-connect/?p=305072 states none). A user comment says several trades on one index blend together and are hard to tell apart (https://blog.sensibull.com/2022/09/02/trade-better-with-sensibull-positions-page/ comments, via search result). Lesson for us: one card per strategy, never merged by underlying.
- Sensibull advanced positions: the Analyse widget shows a payoff/target table (Target Day and Expiry Day P&L, "Show %" toggle). https://blog.sensibull.com/2023/07/06/payoff-table-on-strategy-builder-analyse-widgets/
- Sensibull alerts: WhatsApp alerts on net P&L and strike/spot, plus margin warnings (https://blog.sensibull.com/2022/09/02/trade-better-with-sensibull-positions-page/). A forum quote says price and P&L alerts were later replaced by "Conditional Exit" built on Zerodha ATO (https://tradingqna.com/t/sensibull-updates/184261, undated, unverified).
- AlgoTest: lets a user select several running strategies and watch combined MTM and delta, with alerts via Telegram/email/web (LinkedIn promo post surfaced by search: https://linkedin.com/company/algotest). Screen layout: not found (https://algotest.in/blog/option-strategy-builder-algotest-vs-dhan.md says nothing on monitoring screens).
- Streak: a "Deployed" page and an order log show hypothetical P&L for virtual deployments; live deployments notify and the user presses Buy/Sell (https://zerodha.com/z-connect/?p=368853). Field names and status labels: not found.
- Kite: long positions carry a blue P marker, short an orange P; click shows quantity, average price, P&L, quick exit/modify (https://support.zerodha.com/category/trading-and-markets/kite-web-and-mobile/articles/kite-option-chain). Kite has no "strategy" object.
- Dhan, Upstox, Angel One, Opstra: positions sync / positions page exist (https://www.dhan.co/options-trader-web/; https://www.strike.money/reviews/definedge-opstra), layout/columns not found. Angel One added search/filter/sort on its Positions page (https://www.angelone.in/news/product-updates/starting-options-trading-now-made-easy-on-your-angel-one-android-app, from search summary).
- Pattern across apps (what is verified): group by underlying or user-named group; show P&L per group; filter by expiry. Nobody's page was verified to show data age per price. We must (REQ-049 AC-4).

### (b) Recommended content list (card = one saved/live strategy)
| Item | Serves |
|---|---|
| Strategy name, underlying (NIFTY / SENSEX), expiry | REQ-009 AC-2; REQ-049 AC-6 (per-strategy) |
| Server status label, shown as given (ADR-010 words: Healthy / Watch / Adjustment opportunity / Exit condition reached) with the 4-colour dot | ADR-010 Q20; REQ-049 AC-6 |
| Spot: underlying value + its own time ("NIFTY 24,350.10 at 11:42:07") + its health word when not "available" | REQ-049 AC-4; REQ-072 AC-2 |
| Per leg: action, strike, CE/PE, lots, LTP, quote time, health word when not available | REQ-049 AC-1, AC-2, AC-4 |
| Paused badge `⏸ Monitoring paused` + grey "Health unknown" dot, replacing the colour dot, per strategy | REQ-049 AC-6 |
| Paused / dropped-feed sentence: "Live market data disconnected. Last updated: <time>. Live strategy monitoring is paused." | REQ-049 AC-5, ADR-077 |
| Never-had-a-price label: "Draft — Live data not connected" (no time) | REQ-049 clarification 2026-10-15 |
| Execution-blocked uses its own lock badge, never health red | REQ-049 AC-6 |
| Net P&L as a server string, "—" if the server sent none; no browser maths | no AC for the list; supports REQ-044 AC-4, ADR-008, ADR-010 Q150 |
| Tap card -> that strategy's Live Position tab | REQ-044 AC-2 |
| Group header per underlying with count; sort inside group: red, orange, yellow, green, then paused | no AC; supports REQ-049 AC-6 (NIFTY active / SENSEX paused example) |
| Stale or unavailable values: show last value greyed WITH "stale since <time>", or "Unavailable"; never an unlabelled old number | REQ-049 AC-4 |

Defaults (designer decisions, no AC): group by underlying; per-card legs collapsed to 2 lines on mobile, expanded on desktop. (The designer proposed executed-only here; the orchestrator decision below keeps saved drafts in their own group.)
Empty state (no live strategies): "No live strategies yet. Plan one in Create Strategy, then execute it with your Zerodha account." Buttons: Create Strategy, My Strategies. Not found in any app (none of the sources above states an empty state).
Loading state: skeleton cards; after 5 s without any price show "Draft — Live data not connected" only if no quote was ever held (REQ-049 clarification).

### (c) Wireframes
Desktop (>= 1024 px), cards in a 2-column grid:
```
Live Strategies                                   [Create Strategy]
NIFTY (2)  ------------------------------------------------------------
+-----------------------------------+ +--------------------------------+
| Iron Condor Oct-27          (o) Watch| | Short Straddle Oct-27   ⏸ Monitoring paused |
| NIFTY 24,350.10 @ 11:42:07        | | (grey) Health unknown          |
| P&L +1,240.00 (server)            | | Live market data disconnected. |
|-----------------------------------| | Last updated: 11:31:40.        |
| SELL 24500 CE 1L  LTP 62.10 @11:42| | Live strategy monitoring is    |
| BUY  24600 CE 1L  LTP 31.40 @11:42| | paused.                        |
| SELL 24200 PE 1L  LTP 58.00 stale |
| BUY  24100 PE 1L  LTP 29.90 @11:42|
| [Open Live Position]              | | [Open Live Position]           |
+-----------------------------------+ +--------------------------------+
SENSEX (1)  -----------------------------------------------------------
```
390 px, one card per row, legs collapsed:
```
Live Strategies            [+ Create]
NIFTY (2)
+-------------------------------+
| Iron Condor Oct-27   (o)Watch |
| NIFTY 24,350.10  11:42:07     |
| P&L +1,240.00                 |
| 4 legs  1 stale   [v Legs]    |
+-------------------------------+
| Short Straddle    ⏸ paused    |
| (grey) Health unknown         |
| Last updated: 11:31:40        |
+-------------------------------+
[Home][Strategies][Positions][Market][More]
```
Rule for the builder: health colour dot + a word ("Watch"), never colour alone (colour-blind safe; REQ-049 AC-6 says colours are not reused for paused).

### (d) Dropped (breaks a business rule)
- Quick exit / modify / "Exit all legs" buttons on a card: Sensibull and Kite offer them; ours must route to the owning strategy's Modify Strategy flow with Before/After and confirmation, never a one-tap order (ADR-002 Q30; REQ-044 AC-3 "actions route back to the owning strategy").
- Alert-triggered automatic orders (Kite ATO / Sensibull Conditional Exit): see SPEC CHANGE section; not built.
- A browser-computed P&L from LTP x quantity: ADR-008 (one engine, no browser maths).
- Words like "best", "recommended exit", "Suggested action": ADR-003; use "Adjustment opportunity detected", "Your rule was triggered".

---

## Underlying / index view (REQ-009 AC-4 "Underlying/index view"; REQ-072; REQ-049)

### (a) What the studied apps do
- Dhan: Markets menu lists Nifty 50, Sensex and many more indices; page layout not found; prices delayed 15 min when not logged in (https://www.dhan.co/options-trader-web/).
- Kite: indices are added to a watchlist by typing the index name; Kite has no dedicated index screen that was verified (https://kite.trade/docs/kite/kite-mobile/marketwatch/ via search summary; the help article body was not retrieved). Watchlist limits 25 lists x 250 instruments on web (https://zerodha.com/z-connect/?p=445134, search summary).
- Upstox: spot and future price at the top right of the chain widget (https://upstox.com/market-talk/chain-feature-upstox-options-traders/).
- Sensibull, Opstra, Streak, AlgoTest, Angel One: index/underlying page not found.
- Kite chain bottom bar carries PCR, Max Pain, ATM IV, IV Percentile (https://support.zerodha.com/category/trading-and-markets/kite-web-and-mobile/articles/kite-option-chain) - these are the closest "underlying summary" metrics seen.

### (b) Recommended content list
| Item | Serves |
|---|---|
| Two panels: NIFTY 50, SENSEX (no other index; REQ-072 AC-1 limits the index rows to these two) | REQ-072 AC-1 |
| Value, absolute and % change vs previous close (server strings), timestamp of the value | REQ-049 AC-4; REQ-072 AC-2 |
| Health word + dot when not "available" (stale / delayed / unhealthy / unavailable) | REQ-049 AC-2; REQ-072 AC-2 |
| Per panel link "Open Option Chain for NIFTY" (pre-selects underlying) | REQ-029 AC-5 (reachable from Market) |
| Per panel link "Your live strategies on NIFTY (n)" | no AC; supports REQ-049 AC-6 |
| Nearest expiry shown beside the value as a plain date | no AC; supports REQ-029 AC-8 |
| Closed-market state: "Market closed. Last close 24,310.50 at 15:30" | REQ-049 AC-4 |
| Login required, nothing visible logged-out | REQ-010 AC-1 |
Optional, off by default: day high/low and a sparkline are NOT recommended: no AC, and the data source supplies spot only (REQ-072); "not found" in the apps to justify them.
Empty/error state: "Index values unavailable. Last updated <time>." plus Retry (REQ-049 AC-4, AC-5).

### (c) Wireframes
Desktop:
```
Underlying / index view
+-------------------------------+ +-------------------------------+
| NIFTY 50          (o) available| | SENSEX            (o) available|
| 24,350.10   +82.40 (+0.34%)   | | 80,112.55  +210.10 (+0.26%)   |
| as of 11:42:07 IST            | | as of 11:42:07 IST            |
| Next expiry 27 Oct            | | Next expiry 23 Oct            |
| [Option Chain] [Strategies 2] | | [Option Chain] [Strategies 1] |
+-------------------------------+ +-------------------------------+
```
390 px: the same two panels stacked, links as two full-width text buttons per panel.

### (d) Dropped
- Buy/Sell on an index or future ("trade NIFTY"): ADR-002, REQ-009 AC-5.
- Gainers/losers, 10+ indices, global indices (Dhan menu): REQ-072 AC-1 (two index rows only); scope.
- Any real-time value on a logged-out page: REQ-010 AC-1.

---

## Home / dashboard (REQ-008; REQ-009 AC-1)

### (a) What the studied apps do
- Dhan: no dashboard described on its Options Trader page; header links go to gainers/losers lists (https://www.dhan.co/options-trader-web/).
- Upstox: mobile home has "My Lists" at the bottom of the home screen (https://upstox.com/help-center/252634).
- Kite: market watch as the home; redesign adds custom groups and a Discover tab (https://zerodha.com/z-connect/?p=445134, search summary).
- Sensibull, Opstra, Streak, AlgoTest, Angel One home: not found.
- Observed pattern (weak evidence): brokers open on a watchlist; none of the retrievable pages shows an action-first home. Our REQ-008 asks for exactly that, so we follow the spec, not the apps.

### (b) Recommended content list
| Item | Serves |
|---|---|
| Adaptive stack by state (3 states below) | REQ-008 AC-2 |
| New user: "Welcome, [Name]"; "Plan your trade. Follow your strategy. Then execute."; "Pro trial: day n of 7, ends <date>"; button "I already know my strategy"; quiet line "Already trade with Zerodha? Connect when ready" | REQ-008 AC-3 |
| New user prominent: Create Strategy, Explore Option Chain, Learn | REQ-008 AC-2 |
| Has strategies, none active: My Strategies, Create Strategy, recent results | REQ-008 AC-2 |
| Has active: Active Strategies (compact Live Strategies cards, top 3 by severity), Important Alerts, "needs attention" list | REQ-008 AC-2; REQ-009 AC-1 |
| Small market strip: NIFTY 50 and SENSEX value, change, time, health dot | REQ-008 AC-4; REQ-072 AC-2 |
| Account status row: trial/plan, Zerodha connection "Not connected" with a Connect link only in context | REQ-009 AC-1 "Account status"; REQ-008 AC-5 |
| No Zerodha gate, no connect modal at login | REQ-008 AC-1, AC-5 |
| Overview/Important alerts/Active strategies/Account status are Home's four blocks | REQ-009 AC-1 |
Empty state: the "new user" state IS the empty state. Trial ended: show plan status line only; what happens after trial is not specified (see gaps).

### (c) Wireframes
Desktop, active-strategies state:
```
[strip: NIFTY 24,350.10 +0.34% 11:42 (o) | SENSEX 80,112.55 +0.26% 11:42 (o)]
Active Strategies (3)                       Important alerts (1)
[card][card][card]                          Watch: Iron Condor ...
                                            Account status: Pro trial, ends 26 Oct; Zerodha: not connected [Connect]
```
390 px: strip (one line, two values) -> Important alerts (if any) -> Active strategies cards (top 3 + "See all") -> Account status. New-user state: Welcome, tagline, trial line, 3 big buttons (Create Strategy, Explore Option Chain, Learn), "I already know my strategy" link, quiet Zerodha line last.

### (d) Dropped
- Forcing broker connect on first login (typical broker onboarding): REQ-008 AC-1, AC-5.
- Terminal-style home (watchlist, depth, gainers): REQ-008 statement "not a trading terminal".
- "Top picks / best strategy today" tiles: ADR-003 (use "Strategies you could consider" if ever added; no AC requires it).

---

## Option Chain (REQ-029, REQ-030, REQ-031; ADR-002, ADR-056)

### (a) What the studied apps do
- Kite: expiry chosen at the top with days remaining; ATM strike highlighted and clicking ATM price recentres; red/green OI bars; bottom bar PCR, Max Pain, ATM IV, IV Percentile; "Greeks" view for Delta/Gamma/Theta/Vega; tapping an LTP opens Buy/Sell/add to watch; basket mode turns buttons into "Add Buy/Sell to basket" with margin. https://support.zerodha.com/category/trading-and-markets/kite-web-and-mobile/articles/kite-option-chain . Column names not stated there.
- Upstox: columns include OI, change in OI, IV, bid/ask; header switcher swaps columns to Greeks; user can show/hide/reorder columns; spot and future at top right; strategy mode: tap LTP, choose Buy/Sell, quantity, "Add to strategy" (mobile). https://upstox.com/market-talk/chain-feature-upstox-options-traders/ , https://upstox.com/?p=7635 (search summary), https://upstox.com/help-center/252634 (steps; the 4-leg limit comes from the search summary of help-center/t-252634).
- Sensibull: chain with OI build-up, PCR, Max Pain, IV percentile/rank, Greeks (https://blog.sensibull.com/2018/07/09/option-chain-tutorial/, search summary); live Positions column on the chain for Pro users, lots/quantity switch in Settings, Quick Trade mini order window; desktop first, mobile later (https://blog.sensibull.com/2023/04/12/feature-update-sensibull-option-chain/). Default columns and header: not found.
- Dhan: "Advanced Option Chain" with orders from the chain and per-contract Greeks; Multi-Strike OI view; columns not found (https://www.dhan.co/options-trader-web/; https://algotest.in/blog/option-strategy-builder-algotest-vs-dhan.md).
- AlgoTest: its strategy builder starts from the live option chain; payoff graph with max profit, max loss, breakevens (https://algotest.in/blog/option-strategy-builder-algotest-vs-dhan.md).
- Angel One: chain with OI, Greeks and contract info; builder (InstaTrade, Sensibull-powered) has predefined and custom tabs, Max Profit, Max Loss, Margin, payoff graph (https://www.angelone.in/news/product-updates/angel-one-options-strategy-builder).
- Opstra: free tier chain with full Greeks (secondary source, https://algotest.in/blog/opstra-vs-sensibull.md says only "option-chain data"; the Greeks claim came from a search summary of a review); free plan data updates every 15 min (https://www.strike.money/reviews/definedge-opstra). Layout not found.
- Streak: no option chain page found.
- Common to all verified: mirrored Call/Put halves around strike; ATM emphasis; expiry on top; Greeks behind a switch, not by default.

### (b) Recommended content list
| Item | Serves |
|---|---|
| Header: underlying selector (NIFTY / SENSEX), spot with time and health, expiry selector (days left shown) | REQ-029 AC-1, AC-8; REQ-049 AC-4 |
| Layout Calls (left) | Strike (centre) | Puts (right) | REQ-029 AC-1; REQ-030 AC-4 |
| Default columns per side: LTP, Change, OI, Volume; Strike in the middle | REQ-029 AC-2 |
| IV column only at Advanced; Advanced Details adds Bid/Ask, Delta, Gamma, Theta, Vega, OI Change | REQ-029 AC-2, AC-3; ADR-056 |
| ATM strike row highlighted; "Go to ATM" link | REQ-029 AC-8 (Kite pattern) |
| Selected contracts highlighted; checkbox per Call/Put cell, Buy and Sell chips per contract row | REQ-029 AC-8; REQ-030 AC-1, AC-2, AC-4 |
| Per-quote health: stale/unavailable shown on the cell ("stale 12:03"), not hidden | REQ-049 AC-2, AC-4 |
| LTP/bid/ask live; OI and IV refresh slower, and say so ("OI updated 11:40") | REQ-029 AC-4 |
| Filters by level: Guided expiry, strike range, ITM/ATM/OTM; Standard + premium, OI/volume; Advanced all | REQ-029 AC-9 |
| Persistent Selected Legs bar: legs with +/- lot stepper, count button "Add Selected (4)", Undo on remove | REQ-030 AC-7, AC-8, AC-9, AC-15 |
| Live preview in that bar: net premium (credit/debit), max profit, max loss, breakevens, mini payoff graph - all from the server | REQ-031 AC-1, AC-2; ADR-008 |
| Multi-expiry notice "Multiple expiries detected - Continue / Review Selection"; each leg shows its expiry | REQ-030 AC-6; REQ-029 AC-10 |
| Unavailable contract row: "Currently unavailable on Zerodha" + plain reason, cannot be added, Refresh | REQ-030 AC-16 |
| Matching template named but not auto-applied | REQ-030 AC-14 |
| Link "Open in Strategy Builder" | REQ-029 AC-5 |
Defaults (no AC; designer decision): show 15 strikes either side of ATM at first open (Kite recentres on ATM; Upstox lets users hide/reorder columns - we offer only the level-based sets); first expiry = nearest. Column hide/reorder (Upstox): not offered at V1 (no AC; keeps level rule simple).
Empty state: market closed -> "Market closed. Showing last prices from <time>"; no expiry data -> "No contracts available for this expiry" + choose another.

### (c) Wireframes
Desktop:
```
NIFTY v  24,350.10 @11:42:07 (o)    Expiry: [27 Oct v] 8 days     Level: Standard
Filters: Strike range [ATM +/- 15 v]  [ITM][ATM][OTM]  Premium [..]  OI/Vol [..]
 CALLS                              |   STRIKE   |                PUTS
 [ ] LTP   Chg    OI     Vol  B S  |            |  LTP   Chg    OI     Vol  [ ] B S
 [ ] 210.5 +4.2  1.2L   40K  B S  |   24,200   |  48.0  -3.1  2.3L   55K   [ ] B S
 [x] 62.1  +1.5  8.9L  210K  B S  | > 24,350 <ATM | 70.4  -0.9  7.1L  190K [x] B S
 ...
+------------------------------ Selected Legs (2) ----------------------------+
| SELL 24500 CE 1L [-][+]   BUY 24600 CE 1L [-][+]   Net credit 30.70 | Max profit .. | Max loss .. | BE .. | [mini payoff] |  [Add Selected (2)] |
```
390 px (value columns trimmed to LTP + OI per side; Change/Volume behind a "Columns" sheet that keeps the REQ-029 AC-2 set):
```
NIFTY 24,350.10 11:42 (o)  [27 Oct v]
 LTP   OI  | Strike | OI   LTP
 62.1 8.9L | 24,350 | 7.1L 70.4   <- ATM highlighted
 tap a cell -> bottom sheet: contract, LTP/Chg/OI/Vol, [Buy][Sell], lots stepper
Selected Legs (2)  Net credit 30.70   [Add Selected (2)]   (bar fixed at bottom, tap to expand)
```

### (d) Dropped (breaks a business rule)
- Direct order placement from the chain (Kite LTP tap Buy/Sell; Dhan "place orders from the chain"; Sensibull Quick Trade; Upstox bid/ask opens order entry): REQ-029 AC-6, ADR-002. In ours, Buy/Sell chips only set a leg's action for import (REQ-030 AC-2).
- "Place order" in the basket from the chain: ADR-002; orders only via the Strategy Execute screen.
- IV, ATM IV, IV Percentile at Guided/Standard (Kite bottom bar, Upstox default): REQ-029 AC-2/AC-9, ADR-056 (IV from Advanced only).
- Live chain for non-Pro users (Opstra free = 15-min data): REQ-029 AC-7; logged-out data: REQ-010 AC-1.
- "Performance indicator" sentiment signals (Upstox): reads as advice, ADR-003; no AC.
- Auto-netting of a Buy and Sell of the same contract: REQ-030 AC-5, AC-11.

---

## Strategy screen, "Live Position" tab (REQ-044 AC-1, AC-2, AC-4; ADR-010; ADR-110)

### (a) What the studied apps do
- Sensibull: positions can be sent to the Analyse widget for payoff/target-day tables and adjustments (https://zerodha.com/z-connect/?p=305072; https://blog.sensibull.com/2023/07/06/payoff-table-on-strategy-builder-analyse-widgets/). The 2018 tracking post shows P&L and Greeks per strategy; fields and layout not found (https://blog.sensibull.com/2018/05/30/new-feature-track-your-options-strategies-greeks-and-pl-in-sensibull/).
- Streak: Deployed page + order log; virtual vs live; fields not found (https://zerodha.com/z-connect/?p=368853).
- Dhan: payoff graph "updates live as the market moves"; Greeks toggle between decimals and per-lot view (https://algotest.in/blog/option-strategy-builder-algotest-vs-dhan.md).
- Angel One / Upstox / Opstra / AlgoTest live-position tab: not found.
- No studied app was verified to split "plan" from "live"; ours is a spec decision (ADR-010 Q150).

### (b) Recommended content list (order = reading order)
| Block | Serves |
|---|---|
| Tabs: Planning | Live Position | History, same strategy header | REQ-044 AC-2; ADR-010 |
| Header: name, underlying, expiry, status label + health dot (or `⏸ Monitoring paused` + grey dot), spot with time | ADR-010; REQ-049 AC-5, AC-6; REQ-072 AC-2 |
| Paused banner text exactly per REQ-049 AC-5 | REQ-049 AC-5 |
| Summary strip: net P&L, max profit, max loss, breakevens, days to expiry, margin used (all server) | ADR-010 Q150 list; REQ-044 AC-4; ADR-008 |
| Distances: spot to each breakeven and each short strike (points and %), plus the user's trigger value where one exists | ADR-010 Q20 ("Distance 1.2%, your trigger 0.8%") |
| Legs table: action, contract, lots, entry price, LTP + time + health, leg P&L | REQ-044 AC-4; REQ-049 AC-2 |
| Greeks (net): Standard and above; Guided hides them | ADR-056 (Greeks Advanced; if Greeks level differs for this tab: no AC, see gaps) |
| Triggers: what is monitored and its state; a trigger record shows data health at trigger time | REQ-049 AC-3; ADR-010 |
| Adjustment opportunities: "Adjustment opportunity detected" + [Review adjustment] | ADR-003; REQ-044 AC-3 |
| Orders for this strategy, newest first; open plan row "Order placed - waiting for Check with Zerodha" with Zerodha quantity marked "not yet confirmed", link to Execute | ADR-110; REQ-044 |
| Actions: Modify Strategy (Before/After), Exit Strategy -> Execute flow | ADR-002 Q30 |
| Payoff graph (server-supplied points) with spot marker | ADR-008; REQ-031 pattern |
Empty states: strategy not yet executed -> Live Position tab shows "Not executed yet. Live monitoring starts after execution." with link to Planning. No monitoring rules -> "Your strategy is being monitored" (ADR-010 Q154).

### (c) Wireframes
Desktop:
```
< Live Strategies   Iron Condor Oct-27      (o) Watch       NIFTY 24,350.10 @11:42:07
[Planning] [Live Position] [History]
P&L +1,240.00 | Max profit 4,100 | Max loss 5,900 | BE 24,180 / 24,520 | 8 days | Margin 1.1L
Distance to short call 24,500: 150 pts (0.62%), your trigger 0.8%   [Watch]
Legs ------------------------------------------------------------   Payoff graph
 SELL 24500 CE 1L  in 70.2  LTP 62.1 @11:42 (o)  +8.1              (server points,
 ...                                                                  spot marker)
Triggers | Adjustment opportunities | Orders (3)   [Modify Strategy] [Exit Strategy]
```
390 px: header (name, status, spot) sticky; tabs as a segmented control; blocks as stacked cards in the same order; legs as 2-line rows (line 1 action/contract/lots, line 2 LTP+time+leg P&L); Greeks and payoff in collapsed cards; two action buttons in a bottom bar.

### (d) Dropped
- One-tap "Exit all" and quick modify as market orders: ADR-002 Q30 (controlled modification, Before/After, confirmation).
- "Best adjustment", "Suggested action: Move Call Spread": ADR-003.
- Treating Zerodha lots outside the strategy as legs: REQ-044 ADR-109 (outside lots shown apart on Positions, not part of any strategy).
- Probability of profit stated as a promise: ADR-008 Q15 (no false precision; labelled estimate only).

---

## Positions (REQ-009 AC-3; REQ-044 AC-3; ADR-109, ADR-110) - supporting note

Apps: Sensibull groups by underlying with user groups (URL above); Kite marks long/short with P markers and shows qty, average, P&L (Kite URL above); Dhan/Angel One/Upstox: positions exist, columns not found.
Recommended: two lists, "Strategy-linked" (our fills, grouped by strategy) and "Outside lots" (bought outside the app, shown apart, marked "not part of any strategy"), columns: contract, qty (Zerodha's, "not yet confirmed" while a plan is open), average, LTP+time+health, P&L; a row's only action is "Open strategy" (REQ-044 AC-3). Dropped: row-level Exit/Add buttons (ADR-002). Empty: "No open positions."

---

## Market context (REQ-009 AC-4 "Market context")

### (a) Apps
- Kite chain bottom bar: PCR, Max Pain, ATM IV, IV Percentile (Kite URL above). Sensibull: PCR, Max Pain, IV rank/percentile, and its own blog warns these have low predictive power (https://blog.sensibull.com/2018/07/09/option-chain-tutorial/, via search summary). Upstox chain: India VIX, PCR, Max Pain, OI analysis (https://upstox.com/?p=7635, search summary). Opstra: OI and PCR charts, IV charts (secondary review via search summary, https://www.strike.money/?p=10163). A dedicated "market context" page in any app: not found.

### (b) Recommended content list
No AC defines this page's content (REQ-009 only names it; REQ-011 is Learn). So everything here is "no AC; supports REQ-009 AC-4" and a designer proposal, kept to what the data model can supply (REQ-049 AC-1 has OI, IV, volume; VIX/PCR are not in the data model yet - gap).
| Item | Serves |
|---|---|
| NIFTY 50 and SENSEX value, change, time, health | REQ-072 AC-2 |
| Market status line: open / closed, last update time | REQ-049 AC-4 |
| Per underlying, per selected expiry: total OI calls vs puts, PCR (OI-based), shown as plain facts with a "what is this?" Learn link | no AC; supports REQ-009 AC-4, REQ-011 AC-2 |
| Each fact labelled "Information, not a signal" | ADR-003 |
Not included: Max Pain, IV Percentile, VIX, FII data (no data source named in the spec; ATM IV also touches the Advanced-only IV rule).
Empty/stale: "Not available. Last updated <time>."

### (c) Wireframes
Desktop: two columns (NIFTY | SENSEX), each a card with value row, then a 3-row facts table. 390 px: stacked cards, facts as label : value lines.

### (d) Dropped
- Sentiment verdicts ("Bullish bias", "performance indicator"): ADR-003.
- IV Percentile / ATM IV at Guided/Standard: REQ-029 AC-2 / ADR-056.

---

## Learn (REQ-009 AC-7; REQ-011)

### (a) Apps
- Zerodha Varsity separates Options Theory and Options Strategies modules, one chapter per strategy covering entry, break-evens, strike selection, risk and P&L management (https://zerodha.com/z-connect/varsity/varsity-march-2015-update, 2015, may differ now). Sensibull launched with free webinars listed under "Education" (https://zerodha.com/z-connect/sensibull/introducing-sensibull-the-options-trading-platform, 2018). Opstra has a blog section (https://www.strike.money/reviews/definedge-opstra). In-app Learn layouts: not found for all eight apps.

### (b) Recommended content list
| Item | Serves |
|---|---|
| Three tabs: Strategy education, Options concepts, Platform guidance | REQ-009 AC-7; REQ-011 AC-1 |
| Strategy page template: what it is, when people use it, payoff shape (labelled sample), max profit/loss formula, breakevens, risks | REQ-011 AC-1; ADR-003 wording |
| Search box + list; cards with title and one-line summary | no AC; supports REQ-011 AC-1 |
| "Learn more" links from other screens (e.g. chain IV label -> concept page), shown at Guided level | REQ-011 AC-2 |
| Content scope itself is open | REQ-011 "Open" note |
Empty/not-yet-written: "More lessons coming" shows only listed items, no placeholders.
Wireframes: desktop 3 tabs + 2-column card grid; 390 px a segmented control and one-column list.
(d) Dropped: any lesson phrased as "you should take this trade" (ADR-003); sample payoffs unlabelled on public pages (REQ-010 AC-3).

---

## Alerts (REQ-009 AC-6: Active, History, Notification settings)

### (a) Apps
- Kite alerts: page at kite.zerodha.com/orders/alerts with a "New alert" button; data points OHLC, % change, price, quantity, OI, volume; operators >, >=, <, <=, =; limits 500 alerts, 200 ATOs; notification in Kite plus email (https://support.zerodha.com/category/trading-and-markets/alerts-and-nudges/kite-alerts/articles/what-are-kite-alerts-and-how-do-i-use-them , via search summary). List columns: not found.
- Sensibull: P&L and strike/spot WhatsApp alerts (positions blog URL above); later replaced by Conditional Exit (forum, unverified).
- AlgoTest: MTM target, stoploss, delta alerts to Telegram/email/web (LinkedIn post via search).
- Others: not found.

### (b) Recommended content list
| Item | Serves |
|---|---|
| Tabs Active | History | Notification settings | REQ-009 AC-6 |
| Active row: strategy, message in calm wording, status colour+word, time, data health at trigger | ADR-010 Q20; REQ-049 AC-3 |
| Alerts are generated from strategy rules and health states; no free-form price alerts at V1 (no AC for them) | no AC; supports REQ-009 AC-6 |
| Message style: "Watch - NIFTY moved closer to your upper short strike. Distance 1.2%, your trigger 0.8%. You don't need to act yet." | ADR-010 Q20 |
| Each row opens the strategy's Live Position tab | REQ-044 AC-2 |
| History: same row, resolved time, filter by strategy | REQ-009 AC-6 |
| Notification settings: channel toggles (what channels exist is not specified; list only channels REQ/ADR name) | REQ-009 AC-6, AC-8 "Notifications" |
Empty: "No active alerts. We tell you here when a rule is triggered or a strategy needs attention." Mobile: list rows, history as second tab.
### (d) Dropped
- Alert that places an order (Kite ATO, Sensibull Conditional Exit): see SPEC CHANGE section.
- "Act now" / "recommended action": ADR-003.

---

## Settings = Account & Settings (REQ-009 AC-8)

### (a) Apps
- Kite and others keep settings in a profile/avatar menu; the retrievable pages gave no layout for any of the eight apps (not found).

### (b) Recommended content list
Menu from the avatar: Profile, Zerodha connection, Subscription & Billing, Free Eligibility, Referrals, Notifications, Security, Preferences, Strategy Preferences, Broker & Market Data (the ten items of REQ-009 AC-8, same order, same words, as in `frontend/src/router/nav.js` ACCOUNT_ITEMS).
- Zerodha connection page: connection state, last login time, "Connect" in-context only (REQ-008 AC-5), token expiry note.
- Broker & Market Data: which feed, health state per underlying (REQ-049 AC-2, REQ-072 AC-2).
- Preferences: UX level (Guided / Standard / Advanced) because the chain and Greeks depend on it (REQ-029 AC-9).
- Others: content not defined by any AC; keep to a labelled form per page. No AC; supports REQ-009 AC-8.
Wireframe desktop: left menu list + right form; 390 px: list screen, tap opens a detail screen with a back arrow.
(d) Dropped: none found that breaks a rule; the standing rule is that nothing here exposes order entry.

---

## Mobile frame (390 px), all screens
Bottom bar of 5: Home, Strategies, Positions, Market, More (More = Orders, Alerts, Learn, Account & Settings). This keeps the seven sections of REQ-009 reachable; no AC says "bottom tabs", so it is a layout choice (GLOBAL.md section 3 prefers bottom tab nav on mobile). Cards not tables below 480 px, except the chain, which stays a table with fewer columns. Min tap target 44 px. No horizontal page scroll; only the chain/scenario table scrolls inside its card (ADR-008 table is "horizontally scrollable").

## Orchestrator decisions on this note (GC-5S, 2026-10-19, under ADR-114)
- **Live Strategies groups:** the page shows two groups, "Executed" (live monitoring, REQ-044 AC-2) and "Saved drafts
  (live prices)", instead of executed-only. Basis: REQ-044 AC-2 places live monitoring there after execution but does
  not exclude drafts, and the GC-5S core proof follows a saved draft; the list has no execution state yet (GC-3F), so
  until it does every saved strategy is in the drafts group with its server status shown. Not an owner question: no
  two business rules clash.
- **ADR-010 status words and colours** on the card wait for REQ-043 (GC-4); until then the card shows the server's
  `status_label` as given and the REQ-049 AC-6 paused badge.
- **Strategy name, expiry, net P&L** on a card: shown only if the server already returns them; no new figure, no
  browser maths (ADR-008).
- **The five SPEC CHANGE items below are NOT adopted.** Per ADR-114 (4) the requirement wins for the build: the chain
  keeps visible Buy and Sell on every contract row at every width (REQ-030 AC-2; the table scrolls inside its card at
  390 px), IV stays Advanced-only (REQ-029 AC-2), no rule-triggered orders, Market context / index view show only what
  REQ-072 and REQ-049 supply (no PCR/OI totals until a scope decision), Greeks on the Live Position tab at Advanced
  (ADR-056). They are listed for the owner in `docs/process/owner-questions-2026-10-19.md` as optional scope ideas.
- **Builder briefs** cite this note as `Design basis: docs/design/screens-research-2026-10-19.md section <name>`.

## Would need a SPEC CHANGE (owner decision)
1. Mobile Buy/Sell on every chain row. Text: REQ-030 AC-2 "Each contract row has Buy and Sell buttons; the action is chosen explicitly and never inferred (Q53)." At 390 px two buttons per side do not fit; we propose a bottom sheet with Buy and Sell after tapping a cell. Choice: keep sheet (still explicit) or require visible buttons (forces horizontal scroll).
2. ATM IV / PCR / Max Pain on the chain or Market context for all levels (Kite, Upstox, Sensibull do). Texts: REQ-029 AC-2 "IV appears from the Advanced level only (Q232, ADR-056)". Not done unless the owner extends it.
3. Alert-triggered orders (Kite ATO, Sensibull Conditional Exit). ADR-002: "Every trade placed through the platform belongs to a strategy"; the spec has no AC for rule-triggered execution without a user press (REQ-009 AC-6 lists only Active, History, Notification settings). Not built; owner may want a "rule-triggered exit" feature later, and it would need its own REQ.
4. Market context and Underlying/index view have no content AC (REQ-009 AC-4 names them only); proposals above add PCR and OI totals. Needs the owner's OK as a scope item, not a change to existing text.
5. Greeks on the Live Position tab at Standard: ADR-056 keeps Greeks at Advanced for the chain (REQ-029 AC-3, AC-9); ADR-010 Q150 lists Greeks in the live view without a level. Which level applies is not stated; the tab above shows them at Advanced only unless the owner says otherwise.

## Not verified (honest list)
Sensibull (no layout, columns, defaults, mobile, empty states), Opstra (no positions or chain layout, mobile rated only by a review), Streak (Deployed page fields), AlgoTest (live monitoring screen), Dhan (chain columns, positions columns, dashboard), Upstox (default view, bottom metrics, web strategy builder payoff), Angel One (chain columns, positions columns), Kite (chain column names, index screen, Home). All 390 px claims for the apps: not found; the 390 px wireframes are ours. Several facts come from search-result summaries rather than the full page; those are marked "via search summary".

## Sources
- https://blog.sensibull.com/2022/09/02/trade-better-with-sensibull-positions-page/
- https://zerodha.com/z-connect/?p=305072
- https://blog.sensibull.com/2023/07/06/payoff-table-on-strategy-builder-analyse-widgets/
- https://blog.sensibull.com/2023/04/12/feature-update-sensibull-option-chain/
- https://blog.sensibull.com/2018/05/30/new-feature-track-your-options-strategies-greeks-and-pl-in-sensibull/
- https://blog.sensibull.com/2018/07/09/option-chain-tutorial/
- https://tradingqna.com/t/sensibull-updates/184261
- https://support.zerodha.com/category/trading-and-markets/kite-web-and-mobile/articles/kite-option-chain
- https://support.zerodha.com/category/trading-and-markets/alerts-and-nudges/kite-alerts/articles/what-are-kite-alerts-and-how-do-i-use-them
- https://kite.trade/docs/kite/kite-mobile/marketwatch/
- https://zerodha.com/z-connect/?p=445134
- https://zerodha.com/z-connect/?p=368853
- https://zerodha.com/z-connect/varsity/varsity-march-2015-update
- https://zerodha.com/z-connect/sensibull/introducing-sensibull-the-options-trading-platform
- https://www.dhan.co/options-trader-web/
- https://upstox.com/market-talk/chain-feature-upstox-options-traders/
- https://upstox.com/?p=7635
- https://upstox.com/help-center/252634
- https://www.angelone.in/news/product-updates/angel-one-options-strategy-builder
- https://www.angelone.in/news/product-updates/starting-options-trading-now-made-easy-on-your-angel-one-android-app
- https://www.strike.money/reviews/definedge-opstra
- https://www.strike.money/?p=10163
- https://algotest.in/blog/option-strategy-builder-algotest-vs-dhan.md
- https://algotest.in/blog/opstra-vs-sensibull.md
- https://linkedin.com/company/algotest
- Project: spec/requirements/REQ-008, 009, 010, 011, 029, 030, 031, 044, 049, 072; spec/decisions/ADR-002, 003, 008, 010; frontend/src/router/nav.js
