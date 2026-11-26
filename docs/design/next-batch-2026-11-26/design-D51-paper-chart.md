# D-51 design note: Strategy Chart for a paper trade (Lane U, read-only study)

Spec basis: REQ-091 AC-1..AC-7 (spec/requirements/REQ-091.md), ADR-203, ADR-320 (7) ("D-51 the Strategy Chart for paper trades (REQ-091, data source open)"), ADR-008, ADR-002. `spec_similar` found no row on paper charts (nearest ADR-203 s1). So: SPEC CHANGE needed for the paper case (REQ-091 is silent on paper).

## Core / Proof
Core: the sentence "The strategy chart is not available." is NOT a paper rule. It is the server's refusal text when the held flag `strategy_price_history` is off. No code in frontend/src or backend branches on "paper" for this chart.
Proof (read this turn): sentence defined twice only: backend/ofo/errors/templates.py:1226-1227 (`price_history_held`) and frontend/src/lib/priceChart.js:8 (fallback `NOT_AVAILABLE`). Test tests_app/test_strategy_price_history_route.py:163-174 asserts the same sentence on a 409 with the flag off. `grep -n paper` in StrategyPriceChart.vue, priceChart.js, strategy_price_history.py, ofo/outcome/price_history.py: no hits.
Not proven: the owner's server flag state on 23 Nov (not readable from the repo). The owner saw it on C3/C4 (paper, docs/process/ic-live-test-2026-11-23-issues.md:540-546) because those were the trades opened; the builder never hides the tab (ChartCard.vue:85 lists it always).

## Root cause (file:line)
1. Route `GET /strategies/{id}/price-history` has `dependencies=[Depends(require_price_history)]` (backend/ofo_app/routes/strategies.py:738-739); `require_price_history` raises `StrategyRefused("price_history_held", CONFLICT)` when `held_switches.held_on("strategy_price_history")` is false (strategies.py:693-698).
2. The flag is ON only if APP_ENV is development/test, else only with `OFO_HELD_STRATEGY_PRICE_HISTORY` on AND a non-blank `OFO_HELD_STRATEGY_PRICE_HISTORY_REF` (backend/ofo_app/held_switches.py:57-60). Grep finds no deploy config setting it (only tests/spec).
3. Frontend: a 409 sets `held = e.parts.what_happened` (StrategyPriceChart.vue:129-130), printed at line 17, i.e. the server sentence.
4. Spec drift: REQ-091 AC-1 says with the flag off "the tab is absent in production, not a placeholder". The builder shows the tab regardless (ChartCard.vue:85, 343-345); no read of `/features` (features.py:27 lists the flag) gates it. That is a defect against AC-1 on its own.

## What the chart needs, and what a paper trade has
Input = saved strategy id; server reads `stored.saved.definition.legs` + `contract_ids` (strategies.py:758-772): per leg action and lots (quantity / lot size, divmod at 767-771), the contract (must resolve LIVE, 759-765), underlying; then Kite 1-min candles per leg plus the index future (strategy_price_history.py:219-237), combined by the one engine `combined_price_series` (ofo/engine/money_summary.py:65-70). Output is prices only, no entry price, no P&L (REQ-091 AC-6). So a paper trade lacks no price input: entries, fills and book are not used at all.
Real paper gap (not the cause of D-51, but wrong for paper): the route charts the SAVED definition's legs, while a paper trade's truth is the book (open net positions, `paper.py:592-609`; `current_legs_many` at paper.py:1098-1126 exists exactly because saved legs go stale after adjustments or exits, D-42/ADR-299). Whether `store.load` returns the post-adjustment legs for a paper trade is NOT verified here (strategy_store.py:764-773 returns the active version's definition; paper adjustments writing a new version is unchecked). Verify first.

## Design
Step 0 (likely whole fix for D-51, no code): owner turns the held flag on in the server env (ADR-203 already accepted the risk). Plus fix the AC-1 defect: ChartCard hides the Strategy Chart tab when `/features` lacks `strategy_price_history` (frontend only, absent not greyed).
Step 1 (paper correctness), server, one reader: add `?basis=book` behaviour, chosen by the server (not the browser) when the strategy has a paper book: legs = open net positions from the ONE paper-book reader (`paper_store.load` + `net_positions`, as paper.py:1098-1126 and `_book` 980-1002 use), `contract_id` per position (paper.py:592-596), lots = |net_quantity| / lot_size, action from sign. Feed `sph.prepare/fetch` unchanged; engine unchanged (no new number: ADR-008). Frontend: nothing computed; StrategyPriceChart keeps asking `/strategies/{id}/price-history`; the book's `net` legs already on the page (paperLegsOf, usePaperBookRead.js:34-47) are NOT used to compute, only the server's reply is drawn. Version key: pass the book's `openKey` (usePaperBookRead.js:57) as `version` so a partial exit or adjustment re-asks (ChartCard prop `savedRevision` is null for paper: StrategyBuilderPage.vue:446-450 calls openSaved(..., null)).

## Answer states (all server `state` + reason string; frontend prints `reason`)
| State | Wording |
|---|---|
| Held flag off | existing "The strategy chart is not available." (tab hidden when `/features` lacks it) |
| Book unreadable | refuse 409 with existing book-unreadable text (PAPER_BOOK_UNREADABLE); never fall back to saved legs silently |
| Prices not live | chart uses Kite history, not the live feed: unaffected; as_of line says the newest candle time (ADR-015). No new state |
| Closed leg (booked P&L) | closed legs are not in the chart (AC-2: "current legs"); note: "Closed legs are not charted: <leg>." (new `notes` row) |
| Partly exited lots | legs at remaining lots (engine's gcd rule, AC-2) |
| Completed trade (all flat) | chart the legs it traded (as `current_legs_many` does, paper.py:1105-1106 "names the legs it traded"), note "This trade is completed; the chart shows the legs it traded." |
| Expired / not LIVE contract | existing `leg_not_listed` (strategies.py:763-765); the most common reason a past paper trade shows no chart |
| History missing for a contract | existing `leg_not_listed` / `all_gaps` / AC-5 "listed from" note |
New wording goes to REQ-091 as new AC-8 (paper basis) with texts in backend/ofo/errors explanations (not in the browser).

## Tests to write (failing first)
- tests_app/test_strategy_price_history_route.py: paper strategy with adjusted legs charts the book's legs (real case: 1 lot condor after a buy-back, strategy 157/172 style), completed trade, partly exited lots, closed leg note, book unreadable 409, unchanged saved-strategy cases.
- frontend/tests/gcui-strategy-price-chart.test.js: tab hidden without the feature; paper version key changes on partial exit; no number computed (existing price-display-scan).
- Guard: add StrategyPriceChart/ChartCard to frontend/tests/paper-leg-readers-guard.test.js registry only if it names a leg price (it should not).

## Files touched
backend/ofo_app/routes/strategies.py (leg source), backend/ofo_app/strategy_price_history.py (notes only), explanations catalogue, spec/requirements/REQ-091.md (AC-1 note, new AC-8), frontend/src/components/strategy/ChartCard.vue and StrategyPriceChart.vue.
Lane R flags: StrategyBuilderPage.vue (only if the version key must be passed: ChartCard's `savedRevision` binding at line 1441 for paper), not the Exit dialog, LeaveBuilderDialog or Stops panel. Lane P: none (no alerts/plans/stops/playbooks).
Migration: none (reads the existing book and saved strategy).

## Owner question (a real input IS missing: the flag, not data)
Spec basis: REQ-091 AC-1, ADR-203 (1)-(2), ADR-320 (7).
Q: On the server you tested (23 Nov), was `OFO_HELD_STRATEGY_PRICE_HISTORY` on with its `_REF` set? Real case: condors C3/C4 showed "The strategy chart is not available." on the Strategy Chart tab.
Options: (A) Yes it was on: then the cause is elsewhere; send the browser's /price-history response body for strategy 159. (B) No: turn it on with REF naming ADR-203, and we hide the tab when it is off (recommended: ADR-203 already accepted the display-rights risk, and this is no code for the paper case). (C) Keep it off: tab hidden, D-51 closes as "held by owner choice".
Then, separately, approve building Step 1 (chart the book's current legs for a paper trade). Recommended: yes, since the saved definition can differ from the book.
