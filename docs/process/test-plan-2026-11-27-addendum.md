# Test plan 27 Nov 2026: addendum (Lane X, written 27 Nov from the code and specs at `206a9f0`)

Companion to `docs/process/test-plan-2026-11-27.md` (final version `b6fb348`). Paper only. Same recording rule as section 6 of
that plan. Nothing is fixed during a check: each row is PASS, FAIL or NOT CHECKED (reason).
Sources are the code and specs on `origin/integration/nb-1126` at `206a9f0`; page and button names are copied from the
frontend source (file:line given). A line "not visible: test-only" means a user can see nothing for that item; the covering
test is named. Nothing was run in a browser while writing this addendum.

## 1. Task 1: click-by-click steps for the items that had none (AX-01 to AX-14; live-price items first)

### AX-01 An index quote older than 60 s is not live in market hours (ADR-330 (39), D-69)
- **Needs live prices:** yes (market hours, feed connected). It cannot be forced by clicking: the index tick must go silent for more than 60 s while option frames keep arriving (real case F-32 / D-69). If it does not happen, NOT CHECKED (reason: the index tick did not go silent).
- **Steps:**
  1. Between 09:15 and 15:30 IST with prices connected, click "Home", then "Overview". Read the strip with "NIFTY 50" and "SENSEX".
  2. Watch each index's time. If one index stops moving for more than 60 s while the other updates, read the small word beside it.
  3. Click "Positions", then "Current positions". On a paper strategy with open legs click "Stops" and read the line under the level fields. (The "Stops" link on a Live Strategies card opens the same panel.)
  4. If an index "Conditional exit" is armed, look at its state chip.
- **Expected:**
  - Home strip: the index row keeps its value and time and a health word "stale" shows beside it (strip-health).
  - The sentence "Index values unavailable." shows at the front of the strip only when the whole index answer is not live (feed or socket down); one silent index in a live feed does not show it there.
  - Stops panel: the line reads "Index values unavailable." (normally "<UNDERLYING> now <value> as of <time>").
  - Armed index exit: not visible: test-only. The chip stays "armed" and nothing exits until a fresh tick crosses the level. Tests: `tests_app/test_paper_monitor.py` (test_adr_330_39_a_stale_index_tick_does_not_fire_an_armed_exit_and_a_fresh_crossing_tick_fires), `tests/marketdata/test_index_quote_age.py`.
- **Source:** `frontend/src/composables/useIndexLive.js:57`, `frontend/src/components/layout/IndexStrip.vue:23`, `frontend/src/components/strategy/PaperStops.vue:133-138,218`, `frontend/src/lib/dataHealthText.js:21`, `backend/ofo/marketdata/feed_health.py:193`, `backend/ofo_app/index_push.py:100-125`.

### AX-02 The payoff hover reading stays through live refreshes (ADR-330 (38), REQ-083 AC-2)
- **Needs live prices:** yes (the refresh is the live re-computation of the chart reply).
- **Steps:**
  1. In market hours click "Strategies", then "Strategy Builder". Open a strategy with legs (for example a saved one from "My Strategies").
  2. In the chart card click the tab "Payoff Graph", then the sub-tab "Graph".
  3. Rest the mouse on the chart at one index level. Note the tooltip's first line (for example "At 22,300 (-1.0%)") and the figures on "At expiry" and "Estimated now".
  4. Keep the mouse still and wait for one or more live refreshes.
  5. Keyboard variant: click the chart, press the Right Arrow key once, wait for a refresh, press Right Arrow again.
  6. Move the mouse off the chart.
- **Expected:** "The reading stays under the mouse (or at the arrow-key position) through every live refresh and its figures update in place, re-read from the new reply at the same index level; a level no longer in the reply shows the nearest level (ADR-330 (38)); the mouse leaving the chart clears it." So: the tooltip does not vanish at a refresh, keeps its first line, the P&L figures change in place; if that level is gone it moves to the nearest level (for example "At 22,200 (-1.5%)"); the arrow position survives and the next press steps from it; moving the mouse off clears it.
- **Source:** `frontend/src/components/strategy/PayoffChart.vue:407-418,82-84`, `frontend/src/components/strategy/ChartCard.vue:82`, `spec/requirements/REQ-083.md:42-47`, `frontend/tests/payoff-hover.test.js:179-230`.

### AX-03 No plan means no adjustment limit (ADR-330 (11), second half)
- **Needs live prices:** yes (placing paper orders needs live prices).
- **Steps:**
  1. Find a paper strategy with open legs and no plan (or remove a plan from one).
  2. Click "Strategies", then "Strategy Builder", open it (builder `?strategy=N`). In the tracking panel find the "Plan" card.
  3. Click "Adjustment history" below it and read the tile "Adjustments used".
  4. Add one more leg by hand (or lots to a leg) and place it with the "Add to Paper" confirm list, even if the strategy already used as many adjustments as its type's old default (an iron condor's was 2). [The exact click path of this add follows the builder's "Add to Paper" flow; the source does not spell it out.]
  5. Re-open "Adjustment history" and read the tile again.
  6. Contrast: on a strategy WITH a plan click "Edit plan", set "Max adjustments" to the number already used, and try the same add.
- **Expected:** Plan card: "No plan: nothing is watched for this strategy" with a "Set plan" button. Tile: "Adjustments used" reading "N of –" with the line "No plan maximum is set for this strategy." The no-plan add is stored, with no "plan maximum" refusal. Contrast (plan at its limit): "These orders open or add to a leg, and there is no room left: plan maximum of {limit} reached." Test: `tests_app/test_paper_adjustment_limit.py::test_no_plan_no_limit_applies_to_a_manual_order`.
- **Source:** `frontend/src/components/strategy/PlanEntry.vue:3,23-24`, `frontend/src/components/strategy/AdjustSteps.vue:8,88`, `backend/ofo/errors/explanations.py:1091,2428`, `backend/ofo/errors/templates.py:1055-1056`, `spec/decisions/ADR-330.md` (11).

### AX-04 D-20: record bid and ask of the same strikes at one moment (data capture, no pass rule)
- **Needs live prices:** yes (09:15 to 15:30 IST).
- **Steps:**
  1. Top menu "Market" > "Option Chain".
  2. Pick the "Underlying" box (NIFTY or SENSEX) and the "Expiry" box.
  3. Tick the "Details" box: it adds "Bid", "Ask", "OI Change", "Delta", "Gamma", "Theta", "Vega" next to "LTP", "Change", "OI", "Volume", "IV" on "Calls" and "Puts".
  4. Optionally tick "Has bid and ask". Note the "as of HH:MM:SS" clock beside the Underlying box.
  5. Take one screenshot showing the "Strike" column, "Bid", "Ask", "LTP" for the strikes in question and the clock; write down strikes and clock time. Repeat twice more, one minute apart, for more samples.
- **Expected:** none (data only; ledger line "Record bid and ask of the same strikes at one moment"; the engine forward uses bid-ask mids and the tester used LTPs). A row with no live price shows the cell text the page prints; that is not a failure.
- **Source:** `frontend/src/pages/OptionChainPage.vue:202-217,239-240,264-277`, `frontend/src/lib/chainDisplay.js:8-23`, `frontend/src/router/nav.js:36-40`, `docs/process/ic-live-test-2026-11-23-status.md` (D-20, line 31).

### AX-05 D-70: prices frozen at 15:30 and the label "Prices are from 15:30:00" (ADR-330 (36))
- **Needs live prices:** no (the feed runs, the market is closed; a running paper trade must exist). Same behaviour as plan checks AF-01 and AF-02.
- **Steps:**
  1. Before 15:30 leave the API running (do not restart it) and keep a running paper trade open.
  2. After 15:30:00 open "Strategies" > "Live Strategies" (the trade's card), or "Market" > "Option Chain", or the builder (My Strategies > row > "Open in Builder"). Read the banner and write down the leg prices.
  3. Reload every few minutes for 10 minutes.
  4. Path (b): restart the API after 15:30, open the same trade and read each leg's price label.
- **Expected:** banner "Market closed. Prices are from <date>, 15:30:00 IST." (Live Strategies and Option Chain). "the after-close figure is the last price received up to the calendar close (15:30:00); later prices are ignored for it". Prices do not change over 10 minutes. After a restart: "each leg shows a price labelled with its own time ('as of 15:4x:xx'), never 'Prices are from 15:30:00'". Mixed trade, server sentence: "Market closed. Prices are from {frozen}; 1 leg as of {later}." or "Market closed. Prices are from {frozen}; {count} legs as of {later}." There is no market-closed banner in the Positions page source: do not expect the label there; it shows on the builder, Live Strategies, Option Chain and the leg picker.
- **Source:** `frontend/src/components/states/MarketClosedBanner.vue:1-30`, `frontend/src/lib/sharedStateText.js:5-9`, `backend/ofo/errors/explanations.py:1512-1519`, `spec/decisions/ADR-330.md` (36), `frontend/e2e/screen-live-strategies.spec.ts:286-293`, `frontend/e2e/screen-option-chain.spec.ts:970-972`, `frontend/src/pages/StrategyBuilderPage.vue:1131`.

### AX-06 N-30: Delete on My Strategies has no extra read before it (timing)
- **Needs live prices:** no
- **Steps:**
  1. Click "Strategies", then "My Strategies".
  2. On a row that shows "Delete" click "Delete"; read the confirm line; click "Delete" in it.
  3. Read the result line under the list and the dark pop-up at the bottom centre.
  4. Within the Undo window click "Undo" (or "Dismiss" on the result line).
  5. Optional: tick a row, "Delete selected (1)", then "Delete".
- **Expected:** confirm line for a draft: "Delete this draft? Its history is kept, and you can Undo right after."; with practice orders: "Practice orders were placed for this strategy. Delete it? Its practice record leaves the lists, and you can Undo right after." The row disappears at once. Result line "Strategy deleted." with "Undo" and "Dismiss" (stays until dismissed, replaced or used). Pop-up "Strategy deleted." with "Undo", gone after the Undo window (setting "Undo window, Clear all", default 10 seconds, min 1, max 120). Bulk: "1 strategy deleted." and "Delete 1 strategy?". A stale revision: the server refuses and the list is re-read. The "no GET per row" part is not visible: test-only (`tests_app/test_strategy_list_revision.py`, `frontend/tests/my-strategies-bulk.test.js`).
- **Source:** `frontend/src/pages/MyStrategiesPage.vue:101-106,187,243-254`, `frontend/src/lib/strategyActivity.js:13-18,73-80,133-143`, `frontend/src/components/strategy/DraftDeleteStatus.vue:16-28`, `backend/ofo/settings/registry.json:629-636`.

### AX-07 NEW-T51: "Pick from Option Chain" inside the builder picker (U-Q4 (a), PK-14)
- **Needs live prices:** no (a closed-market chain also works)
- **Steps:** 1. Open "Strategy Builder" (`/strategy/builder`). 2. Press "Add/Edit". 3. Pick an expiry and wait for the strike rows. 4. Press "Greeks" in the LTP / OI / Greeks switch. 5. In the drawer footer press "Pick from Option Chain" (footer also shows "N legs selected", "Clear All", "Done").
- **Expected:** the drawer switches to the "LTP" view with the strikes panel ("Call LTP", "Strike", "Put LTP") and the page stays on `/strategy/builder`. It does NOT go to Market > Option Chain: by design (U-Q4 (a), REQ-029 AC-5); the full chain is "Market" > "Option Chain". The empty builder has the same button "Pick from Option Chain" in its no-legs state, which opens the drawer on the Strikes tab. Covered by browser test `screen-builder-legs.spec.ts`: PK-14.
- **Source:** `frontend/src/components/strategy/LegPicker.vue:740-742,861,986-994,667-672`, `frontend/src/components/strategy/LegList.vue:206`, `frontend/src/pages/StrategyBuilderPage.vue:1083,1283`, `frontend/e2e/screen-builder-legs.spec.ts:707-718`, `RESULTS-lane-u.md:51`.

### AX-08 ADR-330 (1) second half: the line "the trade has been adjusted since entry"
- **Needs live prices:** no
- **Steps / Expected:** not visible: test-only. The sentence exists only in the spec (ADR-330 (1): "Nothing here is built yet"); only the fixed stop amounts are built, in backend code (`tests_app/test_stop_base_fixed.py`: a roll or add does not move the stop amounts). Do not confuse it with the Stops-panel chip "set before the last adjustment" and its "Keep this level" button (`PaperStops.vue:270`), which is for armed index exits and leg stops.
- **Source:** `spec/decisions/ADR-330.md` (1), `tests_app/test_stop_base_fixed.py:5-6`, `backend/ofo_app/adjustment_readers.py:158-173`.

### AX-09 NEW-T01: Home with no strategies, "Welcome, [Name]" and the 7-day Pro trial (NOT BUILT, #433)
- **Needs live prices:** no
- **Steps:** 1. Sign in as a user with an empty My Strategies list. 2. Open "Home" (`/home/overview`). 3. Read the card under the figures.
- **Expected today:** the line "Plan your trade. Follow your strategy. Then execute." and the links "Create Strategy", "Explore Option Chain", "Learn" and "I already know my strategy"; NO "Welcome, ..." line and NO "7-day Pro trial" line. The spec expects them (REQ-008 AC-3); the welcome slot is empty on purpose until sign-in exists (#433, Stage 5). Browser test `screen-home.spec.ts`: STATE-3 is marked expected-fail. Record what you see; a missing welcome line is the known state, not a new FAIL.
- **Source:** `frontend/src/pages/HomeOverviewPage.vue:96-107`, `frontend/e2e/screen-home.spec.ts:353-362`, `RESULTS-lane-t.md:70`, `RESULTS-lane-u.md:31`.

### AX-10 NEW-T60: remove a leg of a saved strategy, reload (NOT BUILT, REQ-154, #751, ADR-330 (34))
- **Needs live prices:** no
- **Steps:** 1. "Strategies" > "My Strategies", open a saved strategy with 2 legs in the builder (`/strategy/builder?strategy=7` form). 2. Remove one leg. 3. Read the line under the action bar. 4. Reload (F5).
- **Expected today:** step 3: "Unsaved legs are not kept if you reload or close this page. Save to keep them." After the reload the edit is NOT restored: "No draft strategy is open. Add a leg to start one." The spec expects the unsaved change to survive (REQ-154 AC-1); built later with sign-in. Leaving by the menu: "Leave the builder? The N unsaved legs will be lost." (plan check T3-01). Browser test `screen-builder-drafts.spec.ts`: LV-14 (expected-fail).
- **Source:** `frontend/src/lib/saveDraft.js:213`, `frontend/src/pages/StrategyBuilderPage.vue:1124,1293-1295,1332`, `frontend/e2e/screen-builder-drafts.spec.ts:525-536`, `owner-questions-lane-u.md` (U-Q6).

### AX-11 NEW-T62: builder settings list (NOT BUILT, REQ-138 AC-1, #750)
- **Needs live prices:** no
- **Steps:** 1. Open the builder with a strategy (`/strategy/builder?strategy=7`). 2. Press the "View" button (gear icon) beside the index name. 3. Read the panel titled "Builder settings".
- **Expected today:** one setting only, "Show legs as" with "Lots" and "Quantity". The spec expects the list to also hold "Expected-move days", "OI on chart", "Include open positions in margin", "Show manual P&L". Needs server storage (a migration); deferred. Esc closes the panel (MN-5). Browser test `screen-builder-drafts.spec.ts`: MN-7 (expected-fail).
- **Source:** `frontend/src/pages/StrategyBuilderPage.vue:1239-1249`, `frontend/e2e/screen-builder-drafts.spec.ts:1405-1448`, `RESULTS-lane-t.md:101`, `RESULTS-lane-u.md:56`.

### AX-12 NEW-T63: the Lots / Quantity choice is kept after reload (NOT BUILT, REQ-138 AC-2, #750)
- **Needs live prices:** no
- **Steps:** 1. As AX-11, change "Show legs as" from "Lots" to "Quantity" (the legs table column changes). 2. Reload. 3. Open "View" again.
- **Expected today:** back on "Lots"; nothing is saved to the server. The spec expects the choice kept (for example Quantity shows 65, 130 on every later visit). Browser test: MN-8 (expected-fail).
- **Source:** as AX-11.

### AX-13 D-34: profit-target amount / take-profit stop on the Stops panel (parked; not built as asked)
- **Needs live prices:** no (the plan sheet answers from the server)
- **Steps (what a user can do today):** 1. On a paper trade's builder find the "Plan" card (button "Edit plan", or "Set plan" if none). 2. In the plan sheet type an amount in "Target (Rs)" and optionally "Stop (Rs)"; the percent boxes fill from the server; press "Save plan". 3. Open "Plan watch" (builder and the compact box on a Positions paper row). 4. Look at the Stops panel ("Stops on this strategy", empty text "No stops set.").
- **Expected:** the Stops panel has no take-profit entry (D-34 parked, ADR-320 (7)). The plan sheet's "Target (Rs)" covers a rupee profit target (ADR-330 (5): typed in rupees or percent, whole trade, before charges); when hit it raises an actionable alert and nothing exits by itself. The stop sentence is as in plan check T1-13: "a loss of Rs 400.00 (<p> % of max loss), 2x the credit received ... whichever comes first".
- **Source:** `spec/decisions/ADR-320*.md:37-38`, `spec/decisions/ADR-330.md:59-66`, `backend/ofo/errors/explanations.py:1095,1103`, `frontend/src/components/strategy/AdjustPlanSheet.vue:29-30`, `frontend/src/components/strategy/PlanEntry.vue:35`, `frontend/src/components/strategy/PaperStops.vue:259-262`.

### AX-14 Step 3 stand-alone checks (index_level, leg_price, pnl_amount, pnl_percent, time_of_day)
- **Needs live prices:** no
- **Steps:** the check functions themselves: not visible: test-only ("A check only answers; it never exits, alerts or reads a store or a clock"; `tests/test_checks_no_side_effects.py`, `test_paper_monitor`). A tester can see their answers only through the "Plan watch" box (builder beside the live P&L, and each open Positions paper row): each trigger row shows a state word from "Watching" (NotMet), "Fired" (Met), "Not applicable", "Not checked" (NotComputable), "Paused".
- **Expected:** for "Not checked" the server's reason sentence, for example "This rule is not checked now; it never counts as passed.", "This trigger is not checked in this version." or "This rule is not checked in this stage."; an absent figure shows a dash and the reason, never 0; empty box "Nothing to watch yet."; no plan "No plan: nothing is watched for this strategy". There is no row text "checked, not met" in the source. "Not checked" cannot be forced by clicking (it needs a missing price or level): if it does not appear, NOT CHECKED (reason: cannot be forced). Covering tests: `plan-watch-*` in `frontend/tests` (23 pass).
- **Source:** `backend/ofo/checks/outcome.py:1-35`, `backend/ofo/adjustment/playbook_eval.py:37-40,1047-1048,1107`, `backend/ofo/errors/templates.py:1352-1367,1414-1415`, `frontend/src/components/strategy/PlanWatch.vue:62-64`.


## 2. Task 2: the after-close run order for 27 Nov, and the pre-open-data sweep

Run after 15:30 IST. Rows go in `docs/process/screen-checks-2026-11-27.md` as in section 6 of the main plan. Check ids AF-nn, T3-nn, T4-nn are the checks of `test-plan-2026-11-27.md`; AX-nn and SW-n are in this file.

### 2.1 Order

1. **Feed still running, API running since before the close** (nothing restarted yet): AF-01 (frozen at 15:30), AF-04 (Home total with the count line), AF-05 (Home against My Strategies rows), AF-06 (no "No price for:" line), AF-03 (mixed banner time), AF-08 (market-closed Save and the Add to Paper tick box), AF-09 (only if a trade expires today; else NOT CHECKED), AX-05 (prices frozen label).
2. **Restart the API** (AF-02, path (b)): AF-02. Do it after step 1 because a restart changes what step 1 sees.
3. **Stop the price feed** (the pre-open-data state), then the sweep SW-1 to SW-9 below.
4. **Every Tier 3 and Tier 4 part still open that needs no live price** (the feed may stay stopped; the API must run unless the check says to stop it): T3-01 to T3-17 in order (T3-10 needs the API stopped: do it last in this step), T4-01 to T4-07, and the no-live-price AX checks AX-06 to AX-14. Drop any that a row of today already marks PASS or FAIL.
5. **LAST: AF-07** (disconnects Zerodha; live prices are gone until the owner logs in again). Then start the feed and the API again if the owner wants the app left running.

### 2.2 Pre-open-data sweep (feed stopped, after 15:30 IST; judged against ADR-212 and REQ-049 AC-4)

**The rule in plain words** (from spec/decisions/ADR-212.md, ADR-177, ADR-197, ADR-200 (2) as amended by ADR-330 (36), REQ-049 AC-3 to AC-5): after the close, with the feed stopped, the app must NOT show a stale number as if it were live (REQ-049 AC-4: "Screens show when data is stale or unavailable instead of presenting old numbers as live."). Outside market hours the paper screens (Positions > Paper, the builder's paper panel, the totals) show each open leg's LTP, unbooked P&L, strategy totals and decay from the last close the feed holds, under the one market-closed banner (ADR-212, ADR-177). The number is the last price received up to 15:30:00 with its own time. A contract first priced after the close is labelled with its own time, never "15:30:00". A contract with no held close stays unpriced with its reason ("no price" or a dash), never a default, 0 or blank (ADR-200 (4)). A paper entry, exit or fill stays refused. "Paper P&L paused - prices not live, as of <time>" is a market-hours pause. When data is missing or the socket drops the screen says so (REQ-049 AC-5): "Live market data disconnected. Last updated: <time>. Live strategy monitoring is paused." or "Reconnecting - prices as of <time>". A stale price must not move a rule or alert silently (REQ-049 AC-3).

**Source-reading warning (from the research of this addendum, nothing was run):** the banner component `MarketClosedBanner` is mounted by IndexStrip, OptionChainPage, LiveStrategiesPage, StrategyBuilderPage, IndexViewPage, LegPicker and DepthPopup only; no import was found in PositionsPage, PaperStrategies, MyStrategiesPage or AlertsPage, although ADR-212 says the paper screens sit "under the one ADR-177 banner". If the tester sees no banner on Positions, record it as a finding (FAIL against ADR-212), not as a pass.

**Pre-step for every SW check:** stop the price feed from the terminal after 15:30 IST on a trading day (as on 26 Nov). Open Chrome DevTools > Console and keep it open; any red error on a screen below is a fail.

**Must not show on any screen:** "undefined", "NaN", "null", "[object Object]", a raw error or stack trace, an empty cell, "0" or "₹0" or "0.00" standing in for a missing price, a time that is the page-load time instead of the price time, the words "live" or "Data: live" or "Index values are live." next to a closing price, and any English that is not in the quoted strings.

#### SW-1 Home (`/home/overview`)
- **Steps:** 1. Open Home and wait about 10 s. 2. Read the index strip (NIFTY 50, SENSEX): the banner line, each value, the small time beside it. 3. Read the three figures "Running strategies", "Unread alerts", "Total P&L". 4. Reload once and read again.
- **Pass rule:** REQ-049 AC-4; ADR-212 "under the one ADR-177 market-closed banner"; ADR-177 "The market-closed state reads 'Market closed. Prices are from <time>.' on every screen." The Total P&L is the same figure as Positions (`frontend/src/lib/paperPnl.js:1-5`, D-56): last close, or a dash with a reason.
- **Exact sentences expected:** banner "Market closed. Prices are from <HH:MM:SS>." (`sharedStateText.js:5,9`; `MarketClosedBanner.vue:14-19`; `IndexStrip.vue:21`), the time about 15:29 to 15:30 IST (the price's own time); with no usable time "Market closed." alone (`sharedStateText.js:8`), never "Prices are from Time not available."; a missing index value "Not available" (`useIndexLive.js:58`); socket dropped "Reconnecting - prices as of <time>" (`sharedStateText.js:19-20`) or "Live prices are reconnecting"; figure labels "Running strategies" / "Unread alerts" / "Total P&L" (`paperPnl.js:16-18`); Total P&L is the server's after-charges text with "(after charges)" (`tracking.js:143`), or a "—" dash (`paperList.js:15`) with "Paper P&L paused - prices not live" (`priceState.js:11`) or "Paper P&L is not available right now." (`tracking.js:110`); a failed read of one figure "Could not be read right now." in that figure only (`paperPnl.js:19`).
- **Must not show:** an index value with no banner and no time, a value labelled live, "Index values are live." after 15:30, Total P&L as "0", "-0" or "undefined", the page-load time in the banner.

#### SW-2 Positions, Real part (filter "Real", then "All")
- **Steps:** 1. Open Positions; click "Real", then "All". 2. Read the "Real P&L" total and each Zerodha position row (Contract, "Your units", P&L). 3. With no Zerodha position open, read the empty state. 4. Reload.
- **Pass rule:** REQ-109 (ADR-330 (10)), `spec/requirements/REQ-109.md:190`; ADR-016 (Zerodha is the authority, no invented number); REQ-049 AC-4, ADR-177. ADR-212 names only paper screens: the spec gives no real-position closing-price sentence.
- **Exact sentences expected:** total "Real P&L is not shown yet: the server does not price Zerodha positions." beside "—" (`PositionsTotals.vue:19,21`) unless the server serves a figure (then as sent; Lane S's Real P&L is in this head, see T1-17); empty state title "Real positions", message "No open Zerodha positions." (`PositionsPage.vue:120`); a row's P&L cell is the server's text, else "—" with a small grey reason (`PositionsPage.vue:143`); a row whose first read is pending shows the "position-waiting" text (`PositionsPage.vue:141`); a banner is expected per ADR-177 but is not mounted in the source.
- **Must not show:** a Real P&L number the server did not send, Real and Paper totals added together, "No open Zerodha positions." while real rows exist, a blank cell, "0".

#### SW-3 Positions, Paper part (filter "Paper")
- **Steps:** 1. Open Positions > "Paper". 2. Read the totals strip ("Paper P&L" and its charges tap). 3. On one open paper strategy read its card: Total P&L, Booked, Unbooked, Total Decay, Greeks, each leg row (LTP, unbooked, or "no price"). 4. Tick "Show closed positions" and read the closed legs. 5. Open the charges tap. 6. Try Exit on an open strategy and read the refusal; do not confirm anything. 7. Reload.
- **Pass rule:** ADR-212: "Outside market hours (ADR-119 calendar), the paper screens (Positions > Paper, the builder's paper panel, the totals) show each open leg's LTP, its unbooked P&L, the strategy totals and decay from the last close the feed holds ... under the one ADR-177 market-closed banner ... A paper exit, entry or any fill stays refused outside market hours ... A contract with no held close stays unpriced with its reason, never a default (ADR-200 (4))." REQ-109 AC-5 (market hours) and ADR-311: an unpriced leg's cell says "no price", never 0 or blank.
- **Exact sentences expected:** banner "Market closed. Prices are from <time>." (not mounted in PaperStrategies by the source read); a leg with no held close: cell "no price" (`explanations.py:2205`) and "No price for: {legs}." (`:2207`) or "Expired contracts have no price: {legs}." (`:2208`), totals "—" with the reason; totals paused only if a leg is unpriced or the list read failed: "Paper P&L paused - prices not live" (`priceState.js:11`) and "No paper total yet: prices are not live" (`PaperStrategies.vue:208`); a leg expiring today still open after 15:30: "Market closed. Open legs that expire today settle at HH:MM." (`explanations.py:2192`); missing Greeks or decay "—" with the reason (`PaperStrategies.vue:97`); Exit refusal "Prices are not live; try again when they update" (`priceState.js:13`; the ADR-119 outside-hours wording was not found in the files read); charges labels "Before charges", "Charges paid", "Estimated charges to close", "After charges" (`tracking.js:140`).
- **Must not show:** a dash for LTP, Unbooked or Total when the legs did have a close (the 30 Oct 2026 defect ADR-212 fixed); "Paper P&L paused - prices not live" instead of the close figures for legs that have a close; a leg price with no banner or time; an unpriced leg as "0" or blank; an Exit that places a fill.

#### SW-4 Live Strategies
- **Steps:** 1. Open Live Strategies. 2. Read the one banner at the top and confirm there is exactly one, not one per card. 3. For each running paper card read the "P&L" line, the "Checked at" time, the badge "⏸ Monitoring paused" and the dot "Health unknown" (if shown), the status label, the spot line, Max Profit / Max Loss, each leg's LTP. 4. Open the "Stops" and "Exit" links on a card; they only open pages. 5. Wait 60 s for a socket drop or reconnect line.
- **Pass rule:** ADR-212; ADR-177; REQ-049 AC-4/AC-5/AC-6; ADR-200 (2) "a closed market is one banner with the price's own time; the fetch time and the stale noise are not shown" (`LiveStrategyCard.vue:186`); REQ-049 AC-6 "Paused shows the ⏸ Monitoring paused badge and a grey 'Health unknown' dot".
- **Exact sentences expected:** page banner "Market closed. Prices are from <time>." (`LiveStrategiesPage.vue:62`); card P&L "P&L <figure> (after charges)" (`PnlLine.vue:10-12`), paused "P&L —" with "Paper P&L paused - prices not live", read failed "P&L —" with "Paper P&L is not available right now." (`tracking.js:110`); "⏸ Monitoring paused" (`LiveStrategyCard.vue:218`), "Health unknown" (`:220`); no live answer "Draft — Live data not connected" (`legPicker.js:7`); a leg that is no longer live "This leg is no longer a live contract (expired, delisted, or its exchange token now belongs to another contract). It is not priced." (`legPicker.js:15`); under a paused card the server status then "No numbers are shown as live for this strategy." (`LiveStrategyCard.vue:238`); status label "Live market data disconnected. Last updated: <time>. Live strategy monitoring is paused." (`explanations.py:1848`); reconnect line "Reconnecting - prices as of <HH:MM:SS>" (`sharedStateText.js:19-20`); nothing running "Nothing is running." (`sharedStateText.js:62`); "Waiting for the first answer..." (`LiveStrategyCard.vue:239`); "Loading next..." (`sharedStateText.js:59`); the spot line has no "at <time>" after the close (`LiveStrategyCard.vue:244`); per-leg health words are not shown while the market is closed (`LiveStrategyCard.vue:203`).
- **Must not show:** several banners, "Prices are from" with the load time, figures shown as live while the badge says paused, LTP "0", "-" with no reason on a leg that has a close, a blank card, "Loading this strategy..." that never ends (D-41), the legs' health words after the close.

#### SW-5 My Strategies (and the Completed tab)
- **Steps:** 1. Open My Strategies and the Completed tab. 2. For each running row read the P&L line and the "last saved <time>" text. 3. On Completed read "Final P&L", "Charges", "Net after charges", "Adjustments made", "Adjustment cost" and "closed <time>". 4. Reload.
- **Pass rule:** REQ-049 AC-4; the row P&L is the same figure as Positions (D-41, `PnlLine.vue:1-3`), so ADR-212 applies: close figure or a dash with a reason, never 0; ADR-263 "absent -> 'not available: <its reason>', never 0" (`MyStrategiesPage.vue:221`). The spec gives no market-closed sentence for this screen.
- **Exact sentences expected:** "P&L <figure> (after charges)", or "P&L —" with "Paper P&L paused - prices not live" or "Paper P&L is not available right now."; Completed "closed <time>" or "closed: time not available" (`sharedStateText.js:49-50`); "Charges not available: <reason>" and "not available: <reason>" for net (`MyStrategiesPage.vue:222-223`); read failed "Could not load your strategies. Nothing was changed." with Retry (`MyStrategiesPage.vue:73,173`); status words only "Draft", "Running", "Completed" or "Status not available" (`sharedStateText.js:36-38,46`).
- **Must not show:** "Final P&L undefined", "Charges 0" for an unreadable charge, a Running row with a number and no label, "last saved Time not available" (`displayFormat.js:7` returns that when the time is bad: report it as a defect).

#### SW-6 Builder of a running paper trade (My Strategies or Live Strategies > the trade)
- **Steps:** 1. Open the builder of a Running paper strategy. 2. Read the banner under the header, the index level card, the paper panel (Total, per-leg figures, Booked/Unbooked), the legs table LTP column, the "As of HH:MM:SS IST" line and the Orderbook. 3. Read At Expiry / Estimated Now, Greeks and IV tiles. 4. Try "Add to Paper", then cancel without confirming. 5. Read the Exit control's reason.
- **Pass rule:** ADR-197 "After market hours the builder works from the last close ... under the ADR-177 banner ... each captured entry is labelled as the close with its time, and no closing price is ever shown or stored as a live price"; ADR-212; where Kite gives no close for a contract the leg stays "Draft - no price" with the reason (ADR-197 consequences); REQ-105 AC-4.
- **Exact sentences expected:** banner "Market closed. Prices are from <time>." (`StrategyBuilderPage.vue:1217`), or for legs priced only after the close "Market closed. Prices are from {frozen}; 1 leg as of {later}." / "...; {count} legs as of {later}." (`explanations.py:1515,1518`); paper panel "As of HH:MM:SS IST" (`tracking.js:177`); leg expiring today "Market closed. Open legs that expire today settle at HH:MM." (`explanations.py:2192`); unpriced leg "Paper P&L paused - prices not live, as of <time>" (`priceState.js:12`) and "no price" (`explanations.py:2205`); money-time labels "at the last close prices, as of {time}" (`explanations.py:1929`) or "at the last close prices" (`:1931`), never the live forms (`:1927-1928`); Add to Paper: "Prices are not live; the entry is the last captured price, as of HH:MM." with a tick box before Confirm (`priceState.js:24`; `PaperConfirmDialog.vue:54`), do not Confirm; targets "not shown while prices are not live" beside "-" (`explanations.py:1494`); level card with no index price "—" (`StrategyBuilderPage.vue:1139`); Exit "Prices are not live; try again when they update" (`priceState.js:13`).
- **Must not show:** the live form of a money-time label after the close, an entry price without a close label and time, a "price has moved" marker driven by a closing price, a live-looking Estimated Now, a made-up number for an unpriced leg, a successful paper fill.

#### SW-7 Option Chain
- **Steps:** 1. Open Option Chain; NIFTY, nearest expiry. 2. Read the spot, "as of <time>", the banner, any health text, a strip of rows around the ATM, the IV and Greeks columns. 3. Hover a blank cell for its title text. 4. Switch to SENSEX and to a far expiry; tick two contracts and read the Add controls. 5. Look for rows marked "Currently unavailable on Zerodha".
- **Pass rule:** ADR-177 (the chain example: on a Saturday the chain reads "Market closed. Prices are from 15:29:58." and the broker status reads market closed, never "reconnecting"); REQ-114 AC-7; REQ-105 AC-4; REQ-049 AC-4; ADR-212 provenance ("Wherever market data is required, you should be able to see last closing price until the market opens"). No health word while the market is closed (`dataHealthText.js:18-24`).
- **Exact sentences expected:** banner "Market closed. Prices are from <time>." (`OptionChainPage.vue:244`); spot with "as of <time>" (`OptionChainPage.vue:216-217`), no spot-health sentence while closed (`:218`); no "live" word on the socket status when closed (`:183`), no "Reconnecting ..." unless the socket really dropped (`:245`); no data yet "Waiting for live data." (`sharedStateText.js:123`); "Option chain unavailable: not connected to live data." (`useChainLive.js:13`); "The underlying price is missing, so no strikes can be chosen yet." (`sharedStateText.js:125`) or "The underlying price is missing right now: option prices are shown, but the ATM strike, moneyness, IV and Greeks are not." (`:130`); "This expiry is not in the catalogue." (`:126`), "The catalogue lists no options for this expiry." (`:127`), "The catalogue could not be read." (`:128`), "The expiries could not be read, so no chain is shown." (`:132`), "No strikes match the filters." (`:131`); missing cell "-" (`useChainLive.js:14`), Change / OI Change missing "not available" (`chainDisplay.js:39`); "Waiting for the first live price" only in market hours (`dataHealthText.js:28,31`); "Currently unavailable on Zerodha" (`chainUnavailable.js:5`) and "Some contracts are currently unavailable on Zerodha and cannot be added." (`OptionChainPage.vue:253`).
- **Must not show:** a "Stale" / "Delayed" / "Unhealthy" word on every closed cell, "live" socket text, an empty chain with no sentence, bid/ask 0 as "₹0", a different time per row in place of the banner time, "undefined" or "NaN" in IV/Greeks.

#### SW-8 Alerts (Active, History, Records)
- **Steps:** 1. Open Alerts; read Active, History and the Records view ("stops or expiry settlements"). 2. For each fired row read the "fired" line and the "no longer true" line and any data-health text. 3. Open notification settings and read the empty line. 4. If a "side closed" alert exists open its "Add the legs again" confirm and read it; do not confirm. 5. Confirm no new alert fired at or after 15:30 because of the closing prices.
- **Pass rule:** REQ-049 AC-3 "Important rules are never triggered silently from stale data; the trigger record shows data health."; AC-5 "no trigger is claimed without the data proving it (Q182)"; ADR-212 (no fill outside market hours). The spec gives no market-closed sentence for this screen.
- **Exact sentences expected:** empty Active/History "No alerts yet. Alerts start when strategy monitoring rules are added." (`paperAlerts.js:5`; `AlertsPage.vue:29`); empty Records "No stops or expiry settlements yet." (`paperAlerts.js:101`); notification settings "No notification channels are set up yet." (`AlertsPage.vue:22`); monitoring paused "Live market data disconnected. Last updated: <time>. Live strategy monitoring is paused." (`explanations.py:1848`; `templates.py:504`); the market-closed variant "Market closed. Prices are from {time}." with "Prices on screen are the last ones before the close; none are arriving, as expected." (`templates.py:510-511`, line numbers from a grep context: verify); expiry settlement record "Paper - settled at expiry" (`REQ-109.md:116`); alert rows show the server's fired and "no longer true" lines and answer buttons as sent (`AlertsPage.vue:105,126`).
- **Must not show:** a stop or target alert that fired from the closing price after 15:30 with no data-health text, a fired alert with no data-health line, "Live data: live" on a closed market, a blank Records list with no empty line, "undefined" in a row title.

#### SW-9 Stops panel (Live Strategies > "Stops", or Positions > Stops)
- **Steps:** 1. Open Stops for a Running paper strategy. 2. Read the label line, the index line below it, the "Conditional exit" Above/Below boxes, the leg stop rows and the triggers list. 3. Type a level in one leg stop and read its warning text; do not click Save (it writes a record) unless a rule under test needs it. 4. Read the reason line next to Save. 5. Look at any trigger row for a data-health word.
- **Pass rule:** REQ-049 AC-3 and AC-5 (no trigger claimed or fired from stale data; the trigger record shows data health); AC-4; ADR-212 (no paper fill after hours); S-19 (`PaperStops.vue:131`): the index level the stops are judged against comes from the one index reader. The spec gives no Stops-specific market-closed sentence.
- **Exact sentences expected:** label "Paper - exits are recorded in the app, not sent to Zerodha" (`PaperStops.vue:30`); index line live "<NIFTY> now <value> as of <HH:MM:SS>" (`:136`), not live "Index values unavailable." (`useIndexLive.js:57`; `PaperStops.vue:137`), and after 15:30 a value must come with its own time, not the page-load time; saves "Saved: stop <direction> <level>" or "Already set: stop ..." (`:189`); warnings are the server's warning_text as sent (`:76`); the reason next to Save is the server's (`:231`); a data-state line in the tracking panel "Data: live" / "Data: stale" / "Data: paused" / "Data: not known" (`tracking.js:196-197`, REQ-046 AC-5): after the close with the feed stopped it must read "Data: paused" or "Data: stale", never "Data: live".
- **Must not show:** an index level with no time or with the load time, a stop that reads as armed on live data with "Data: live" after 15:30, a trigger that fired after 15:30 from a closing price without a data-health word, "undefined" or "null" in the level boxes, a blank index line when the index is not live.

### 2.3 After-close time estimate (screen minutes)

| Step | Checks | Minutes |
|---|---|---|
| 1 (feed running) | AF-01, AF-04, AF-05, AF-06, AF-03, AF-08, AF-09, AX-05 | 59 |
| 2 (restart) | AF-02 | 8 |
| 3 (sweep, feed stopped) | SW-1 to SW-9 | about 5 each = 45 |
| 4 (Tier 3, Tier 4, AX 06 to 14 still open) | T3-01 to T3-17 (101), T4-01 to T4-07 (35), AX-06 to AX-14 (about 45) | about 180 |
| 5 | AF-07 | 5 |

The minutes of steps 1 and 2 add up to the "After 15:30" estimate of the main plan less AF-07; the rest are Lane X's estimates and the market is not moving, so the PC session may stop at any point and write NOT CHECKED (reason: time) for the rest.
