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

