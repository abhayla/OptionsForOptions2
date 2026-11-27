STATUS 17:52 | A: first full draft in this push (54 rows, section C included) | B: not started | next push ~Sat 14:00 (design B); parent message refused, this line is the report

# Paper vs real: every difference, 27 Nov 2026 (Lane E, read only)

Branch `docs/paper-real-audit-1127` from `origin/integration/nb-1126` (206a9f0). No product code, no migration, no broker call was made.

**The rule being audited** (owner, 27 Nov, ADR-330 (58), his words as given in the lane brief): "Paper orders are similar to real orders. Do not discriminate between them... There will only be a tag on the paper... Other than that, everything will be same." Note: ADR-330 on this branch ends at item (31) of the 25-26 Nov answers; item (58) is not in the repository text I could search (`grep -rn "similar to real orders\|Do not discriminate" spec docs knowledge` found nothing). The rule is taken from the brief; it needs writing into the spec (R4 of spec-first) before a build rests on it.

## 1. What real-order capability exists today (the plain answer)

**The server places no real order of any kind. A real ENTRY and a real EXIT can each be prepared and handed to Zerodha; nothing then watches, stops or exits a real position.** Evidence:

| Question | Answer | Evidence |
|---|---|---|
| Can the server place, change or cancel a Kite order? | No. The only allowed Kite calls are session token, margins, basket margin and GET orders / trades / positions. | `backend/ofo/broker/kite_endpoints.py:4` ("No call may place, modify or cancel an order"), `:23-29`; `kite_http.py:87` `check_call` refuses anything else; ADR-054 |
| Real entry? | Yes, as an offsite basket: `POST /strategies/{id}/execute` builds read-only LIMIT orders; the user's browser posts them to Kite's page; `POST /strategies/{id}/execution/return` reconciles what came back. Shown in the app only when `GET /features` says `order_path` is on. | `routes/execute.py:3-5,293`; `routes/execution_return.py:132`; `scenario_mode.py:81-84`; `execution/basket.py:276` `build_basket`; frontend `StrategyActions.vue:13` -> `routes.js:88` -> `ExecuteStrategyPage.vue:121` -> `BasketForm.vue` -> `ReturnCheck.vue:22`; `orderPath.js:15-16,43-46` |
| Real exit? | Yes, the same door with action EXIT: opposite side, net quantity, depth limit prices; EXIT at net 0 is refused. Not by a stop, an alert or the time. | `routes/execute.py:11-17`; `execute_plan.py:225`; `ExecuteStrategyPage.vue:145-151` |
| Real stop, trigger, time exit, expiry? | None. Triggers exist only as paper triggers; the worker that fires them is `paper_monitor`; real expiry settlement only logs. `broker_held_triggers` is off. | `paper_trigger_store.py:1-13`; `paper_monitor.py:1-25`; `real_settlement.py:1-17`; `kite_flags.json` |
| Real P&L on screen? | No. The Positions screen prints "Real P&L is not shown yet: the server does not price Zerodha positions." The engine has `broker_contract_pnl`, not shown. | `PositionsTotals.vue:19`; `engine/real_pnl.py:62` |
| A send path in domain code? | `submit_confirmed(preparation, *, choice, confirmed_by, submitter, acknowledgement)` exists, but no concrete transport and no caller were found anywhere in `backend/`. Not wired. | `execution/partial.py:920`; `execution/send_guard.py:90-93` (grep of `backend/` for callers: none) |

So today a real trade can be entered and exited only by the user on Kite's page after our basket; every protection a paper trade gets after entry (stop, alert, exit dialog, exit-risk read, expiry settlement, P&L figure) has no real twin. The Exit dialog and its not-live rule exist only in paper code, as Lane U found.

## 2. Method and limits

- Wide search by three Sonnet helpers (backend routes/stores/workers, backend domain code, frontend), each with a call budget; I checked the claims that decide the answers myself (the take-profit, adjustment-limit and market-hours rows and the real-capability table: `grep` of `routes/execute.py`, `routes/execution_return.py`, `execute_plan.py` for `may_act|take_profit|duplicate_leg|paper_limit|place_checked` gave 0 hits; I read the quoted lines of paper.py:1388-1402, tracking.py:543-551, playbooks.py:492-508, outcome.py:1295-1310, background.py:70-80, PlanEntry.vue:64, PositionsTotals.vue:14-20).
- The lane brief names `outcome.py:1303`, `background.py:74`, `playbooks.py:499-504`. They are `backend/ofo_app/routes/outcome.py:1295-1310`, `backend/ofo_app/background.py:66-82`, `backend/ofo_app/routes/playbooks.py:492-508`. Not under `backend/ofo/`.
- **Not read** (so a hit there could be missing): most of `routes/paper.py` (130-1360, 1485-2040 beyond decorators), most of `routes/execute.py` and `execution_return.py`, `paper_store.py`, `paper_book.py`, `paper_reasons.py` (20 paper hits), `tracking.py`, `adjustment_history.py` (50 paper hits), `outcome.py` (41 hits), `alerts.py`, tests, `BasketForm.vue`, `ReturnCheck.vue`, `SaveDraftBar.vue` beyond :301, ADR text of 212, 271, 276, 281 beyond quoted lines. A second pass on those is the next job if the owner wants the table closed rather than a strong first cut.
- Zero-hit searches (they prove only that the pattern failed): `is_paper`, `isPaper`, `mode ==` in `backend/ofo/` (0); `place_order|post_order` in `backend/` (0); `guard_paper_order|scenario_id|refuse_orders` in `execute.py` (0); `stop|trigger|alert` in `execution_return.py` (0); `kind === 'real'`, `realExit` in `frontend/src` outside `paperDrafts.js` (0); `"Exit the position"` in non-test `frontend/src` (0; the text is the backend's `explanations.py:453`); `offsite` in `frontend/src` (0). **There is no paper/real tag field in `backend/ofo/`:** paper is told apart by the `PaperOrder` type and by membership of the paper store, not by a tag; the only tag in the code is the Kite client tag `make_tag` (`execution/basket.py:123`). This matters for design B: "where the tag is read" has no existing answer.
- Kinds: *paper-only door with no real twin* includes a paper-only gate or check, not only a door. A row marked *stated by an earlier decision* is allowed for the **paper** half only; where the real half is missing that gap is a defect and says so in the row.

## 3. The table (54 rows)

| # | file:line | what differs | kind | area | risk if a real trade went through it today | size |
|---|---|---|---|---|---|---|
| 1 | backend/ofo_app/routes/paper.py:1370-1429; frontend/src/lib/tracking.js:82 | Paper entry posts typed prices to /paper/strategies/{id}/orders and fills at once in the database. Real entry posts to /strategies/{id}/execute (ExecuteStrategyPage.vue:121) and builds a LIMIT basket from depth with margin check, freeze limits and the pre-execution gate (execute.py:4-21). Two endpoints, not one with a tag. | paper-only door with no real twin | entry | money | large |
| 2 | backend/ofo/tracking/paper.py:84-133 | Paper fills at the leg's last traded price, only when the quote is live. Real uses the user-reviewed limit price (send_guard.py:71-80). | paper-only door with no real twin | entry | money | medium |
| 3 | backend/ofo/engine/orderbook.py:48-56 (real: ofo/execution/price_check.py:24) | Typed paper price must be above 0, fit NUMERIC(14,2) and be a tick multiple. The real send path checks only circuit limits. | paper-only door with no real twin | entry | money | small |
| 4 | backend/ofo_app/routes/paper.py:1391 (ADR-326) | Take-profit-at-loss refusal runs on the paper order route. No take-profit call in routes/execute.py or routes/execution_return.py (grep: 0 hits). | paper-only door with no real twin | entry | money | medium |
| 5 | backend/ofo_app/routes/paper.py:1390 vs ofo/execution/safety.py:390 | Duplicate-leg refusal (ADR-319) exists on both paths, with the same sentence function (gate_duplicate_leg). Listed because the twin exists; no difference found. | branch inside shared code | entry | display | small |
| 6 | backend/ofo_app/paper_limit.py:1-14; routes/paper.py:1401 | Adjustment-count limit enforced when a paper order is placed. No twin on the execute route (grep: 0 hits for paper_limit, place_checked). | paper-only door with no real twin | plan | money | medium |
| 7 | backend/ofo_app/routes/paper.py:1394; routes/tracking.py:549 (may_act.py:4 cites ADR-212) vs ofo/execution/safety.py:358 and routes/execute.py:66,678 | Two market-hours rules. Paper entry and exit call may_act.refuse_unless_allowed ('place' / 'exit'), which also needs a live price. The real route passes market_open into the gate, and safety.py:358 refuses with gate_market_closed / gate_market_unconfirmed. (My first draft said real had no market gate; the Opus review found safety.py:358, and my grep had looked only for may_act.) The rule is shared in intent; the code, the codes and the sentences differ, and paper's also checks price freshness. | branch inside shared code | entry | money | medium |
| 8 | backend/ofo/execution/* (basket, send_guard, partial, sequence, safety, margin_gate, price_check, freeze); only paper hit is safety.py:390 (a comment) | The whole real gate stack (margin, freeze, circuit, lot alignment, reconciliation block, protect-first sequence) has no paper branch: a paper order never enters it. Paper has its own checks instead. | paper-only door with no real twin | entry | money | large |
| 9 | backend/ofo_app/routes/paper.py:15 | Paper POST accepts kinds open/add/exit only; settle and stop are server-only. | branch inside shared code | entry | display | small |
| 10 | frontend/src/components/strategy/SaveDraftBar.vue:301 | Saving with mode === 'paper' runs a different path from save-as (one line read; rest unread). | branch inside shared code | entry | money | small |
| 11 | frontend/src/pages/ExecuteStrategyPage.vue:154-160 | A real order shows 'Plan N: orders for Kite's page', a basket table (side, quantity, symbol). The paper confirm shows price, lots and warning rows. | branch inside shared code | entry | display | medium |
| 12 | backend/ofo/errors/templates.py:1018-1127 (paper_price_invalid, paper_exit_exceeds_open, paper_contract_not_tradable, paper_adjustment_limit, paper_strategy_closed, paper_trigger_*) | Paper refuses with paper_* sentences; real refuses with gate_* sentences. Same situation, different words and different codes. | paper-only door with no real twin | entry | display | medium |
| 13 | backend/ofo_app/scenario_mode.py:81-94 | In test-data (scenario) mode paper orders are allowed on their own scenario and the two real routes are always refused. | branch inside shared code | entry | display | small |
| 14 | frontend/src/lib/usePaperExit.js:10-15 | One gate for every paper Exit button: blocked when the price read failed or is stale, when contracts changed elsewhere, while a post is busy or a dialog is pending. The real exit page has no such gate. | paper-only door with no real twin | exit | exit | medium |
| 15 | frontend/src/pages/ExecuteStrategyPage.vue:116,145-151 | Real exit is gated only by 'the live socket holds every leg'. Both ENTRY and EXIT are offered (the API gives no held flag) and the route refuses the wrong one. No failed-read reason line, no changed-elsewhere check. | branch inside shared code | exit | exit | small |
| 16 | frontend/src/pages/StrategyBuilderPage.vue:498-511; components/PaperBookPanel.vue:18 | exitAllPaper / exitPaper: per-leg and all-leg Exit, edit the legs, then open the confirm list. Real exit has one 'Prepare exit orders' action, no per-leg or per-lot choice. | paper-only door with no real twin | exit | exit | large |
| 17 | frontend/src/components/PaperConfirmDialog.vue:55-56,146,167 | Paper confirm has editable lots, the exit-risk read (/paper/strategies/{id}/exit-risk), the armed-exits read, the not-live acknowledgement and an unknown-outcome state. The real basket has none of these. | paper-only door with no real twin | exit | exit | large |
| 18 | backend/ofo_app/paper_exit.py:1-27; routes/tracking.py:543-564 | Paper exit door reads the server's last traded price and records the order. Real exit legs are built in execute_plan.py:225 from depth limit prices. | paper-only door with no real twin | exit | exit | medium |
| 19 | frontend/src/pages/AlertsPage.vue:34,81,142; backend/ofo/errors/explanations.py:453 | The alert answer 'Exit the position' opens PaperStrategies with exit-only-for. A real position's alert would open the paper door (end-to-end not run). The file's own comment: 'ONE shared paper exit confirmation'. | paper-only door with no real twin | exit | exit | medium |
| 20 | frontend/src/components/live/LiveStrategyCard.vue:197-198 | Exit and Stops links render for a running strategy and always go to the paper exit and stops pages. | paper-only door with no real twin | exit | exit | small |
| 21 | backend/ofo/tracking/closing.py:1-12 | Shared close step; the paper store puts BUY exits first, the real path keeps the plan's own order. | branch inside shared code | exit | exit | medium |
| 22 | backend/ofo_app/paper_settlement.py:1-30 vs real_settlement.py:1-17; ofo/settings/calc.py:182-193; ADR-207 (6) | Paper expiry settles at intrinsic value from the official close and writes orders. Real settlement only logs and writes nothing (its price is always absent). The paper half is stated for paper by name; the real gap is not. | stated by an earlier decision | exit | money | large |
| 23 | frontend/src/components/PaperConfirmDialog.vue:104; lib/paperDrafts.js:265-272; ADR-330 (10) | The dialog accepts kind 'real' and titles it 'Exit Real (Zerodha order) positions'. ADR-330 (10): every exit confirmation names 'Paper' or 'Real (Zerodha order)' in its title. paperDrafts.js says none is rendered today (ADR-281). | stated by an earlier decision | exit | display | small |
| 24 | frontend/src/components/PaperStrategies.vue:8; ADR-281 | Comment: 'an exit is a paper order and sends nothing to Zerodha'. ADR-281 title: order placement on Kite is on hold for the iron condor guidance round, paper only: a hold for one round, not a standing rule. | stated by an earlier decision | exit | exit | small |
| 25 | backend/ofo_app/paper_trigger_store.py:1-13; routes/paper.py:1866-1896 | Conditional-exit and leg-stop triggers live only in the paper_triggers table behind paper routes. No store for a real strategy. | paper-only door with no real twin | stops-and-alerts | stop | large |
| 26 | backend/ofo_app/paper_monitor.py:1-25 (main.py:100); ofo/tracking/stops.py:56-60; ADR-207 (5) | A worker records the stop exit at the live price when the level is crossed, labels it paper and raises an alert. No real-trade worker exists (kite_flags.json broker_held_triggers off). ADR-207 (5): 'No order reaches Zerodha (ADR-165)' states the paper side by name; nothing covers a real stop. | stated by an earlier decision | stops-and-alerts | stop | large |
| 27 | frontend/src/components/PaperStops.vue:2-3,34,128-203; lib/paperTriggers.js:5 | Index-level and leg-stop screens exist only under /paper/strategies/{id}/triggers. 'Paper only: nothing is sent to Zerodha.' No path creates a stop on a real position. | paper-only door with no real twin | stops-and-alerts | stop | large |
| 28 | backend/ofo_app/routes/paper.py:1485-1615 (decorators read) | exit-risk, leg-stop-risk and armed-exits routes sit under /paper/. No real twin found. | paper-only door with no real twin | stops-and-alerts | stop | medium |
| 29 | backend/ofo_app/routes/paper.py:1979-2036; frontend/src/lib/paperAlerts.js:106; ofo/tracking/paper_alert.py:4; ofo/errors/explanations.py:2096-2109 | Fired-stop and settlement alerts: own routes (/paper/alerts, /paper/alerts/records), own templates ('A paper exit only: no order was sent to Zerodha', title 'Paper strategy - {name}'). Real alerts use routes/alerts.py:186 (not compared). | paper-only door with no real twin | stops-and-alerts | stop | medium |
| 30 | backend/ofo/adjustment/alert_gate.py:10; adjustment/monitor_pause.py:3-5; ofo_app/background.py:66-82 | Risk exits (paper triggers, stop-loss) skip the alert gate and the user's pause. By path, not by a mode flag; real has no risk-exit path at all. | branch inside shared code | stops-and-alerts | stop | small |
| 31 | frontend/src/components/layout/AppHeader.vue:325 vs :57 | Bell badge comment says 'unread paper-alert count (GET /paper/alerts)'; line 57 says it reads /alerts/active. Which source it reads is unverified (lines 57-80 not read). | wording only | stops-and-alerts | display | small |
| 32 | frontend/src/components/strategy/PlanEntry.vue:64-65; components/TrackingPanel.vue:198-207 | Armed/fired exits come only from GET /paper/strategies/{id}/triggers (prop at :64; read at TrackingPanel.vue:200). A real strategy has no such read. Confirmed. | paper-only door with no real twin | plan | stop | medium |
| 33 | backend/ofo_app/routes/playbooks.py:492-508 | The playbook test reads only strategies in paper_store.tracked_ids. A real strategy is never tested. (Not in backend/ofo/outcome.py; the lane brief's 'playbooks.py:499-504' is here.) | paper-only door with no real twin | plan | display | small |
| 34 | backend/ofo_app/background.py:1911-1912 (ADR-276 cited; ADR text not read) | Tracked set: open paper legs, or real trades/adopted holdings only when the strategy has no paper order. ADR-276 title says triggers track real strategies as well as paper ones. | branch inside shared code | plan | display | small |
| 35 | backend/ofo_app/routes/outcome.py:1295-1310; ofo/engine/target.py:24; ADR-209 | What-if ask adds the paper strategy's booked P&L. ADR-209 states it for paper by name. A real strategy's booked P&L is not added. | stated by an earlier decision | plan | money | small |
| 36 | backend/ofo/outcome/money.py:23-24,84-88; outcome/service.py:197,442 | The Get price basis uses paper fill prices when a paper strategy exists. | branch inside shared code | plan | money | medium |
| 37 | backend/ofo/errors/templates.py:1183 | Sentence: 'a scenario strategy is checked only under its own scenario, a real one only live'. | branch inside shared code | plan | display | small |
| 38 | backend/ofo/engine/orderbook.py:1-14,70,174; ofo/orders/model.py | Two order models: engine PaperOrder rows for paper, Order/OrderBook for real. Position = engine-derived for paper, Zerodha-reported row for real. | paper-only door with no real twin | P&L | money | large |
| 39 | backend/ofo/engine/real_pnl.py:62 vs ofo/tracking/paper.py:151-214 | Real P&L is the broker's pnl field, shown only if re-derived value agrees. Paper P&L is the engine's own figure from stored fills. Two paths for one number (ADR-008: one engine owns every P&L number). | paper-only door with no real twin | P&L | money | large |
| 40 | frontend/src/components/positions/PositionsTotals.vue:19,39-50 | Paper P&L has figure, basis, reason and closed-note lines. Real P&L side always prints 'Real P&L is not shown yet: the server does not price Zerodha positions.' ADR-330 (10): two totals shown side by side, never added; (24) Real P&L is the sum of the rows shown. | stated by an earlier decision | P&L | display | medium |
| 41 | frontend/src/lib/paperPnl.js:38; pages/HomeOverviewPage.vue:16; LiveStrategiesPage.vue:13; MyStrategiesPage.vue:34; components/live/PnlLine.vue:1 | Home, Live and My Strategies P&L read only readPaperList('/paper/strategies'). No real P&L feed. | paper-only door with no real twin | P&L | display | medium |
| 42 | backend/ofo/engine/extremes_charges.py:1-4,112,183; engine/extremes.py:1,144; engine/book_totals.py:1 | Max profit/loss net of charges, Profit left / Loss left and book totals exist only for a paper book. | paper-only door with no real twin | P&L | display | medium |
| 43 | backend/ofo/charges/paper_charges.py:1-92; ADR-207 (7) | Charges per recorded paper order, shown beside P&L, not subtracted. Stated by name for paper (ADR-207 (7)); no real twin compared. | stated by an earlier decision | P&L | display | small |
| 44 | frontend/src/components/strategy/ChartCard.vue:70-78,288; lib/tracking.js:109; ChargesBreakdown.vue:52-65 | Row P&L is before charges, total after; total labelled 'Paper P&L (not real): '; separate paper charges block. | branch inside shared code | P&L | display | medium |
| 45 | backend/ofo/tracking/paper.py:120-133; ofo_app/strategy_money.py:9-11; ADR-212 | After market close paper display uses the last-held close (ADR-212: paper positions show LTP and P&L from the last close). Paper book page prices with display_price, tracking page with live-only leg_price. | stated by an earlier decision | P&L | display | small |
| 46 | backend/ofo/engine/adjust_history.py:4,61-62,84,163 | A fill state 'paper' reads 'Paper - not sent to Zerodha'. A step that mixes paper and real fills raises ValueError. | branch inside shared code | screens | display | small |
| 47 | backend/ofo_app/routes/positions.py:79,228,288; ADR-201 line 9 | Positions has a Paper tab and 'Paper P&L'; ADR-201: paper shown 'labelled as not a real trade'; paper and real totals separate. | stated by an earlier decision | screens | display | medium |
| 48 | frontend/src/pages/PositionsPage.vue:28-29,159; ADR-330 (10) | Real / Paper / All filter; Paper rows from PaperStrategies, Real rows from GET /positions. ADR-330 (10): 'Filter buttons All / Real / Paper, default All'. | stated by an earlier decision | screens | display | small |
| 49 | frontend/src/components/live/LiveStrategyCard.vue:59,119,129,180-190 | A running strategy's max profit/loss/breakevens come from GET /paper/strategies/{id}; a non-running one uses the plan summary. A real fill would take the plan branch. | branch inside shared code | screens | display | medium |
| 50 | frontend/src/components/strategy/LegList.vue:141-144,284,307 | Leg price label: 'Paper average' (from the book), 'Your price' (typed), 'Planned entry'. | branch inside shared code | screens | display | small |
| 51 | backend/ofo_app/strategy_store.py:122,133-136,174; routes/strategies.py:216,504 | has_paper_order vs has_order picks the refusal wording (ADR-271/299). | wording only | screens | display | small |
| 52 | frontend/src/pages/StrategyBuilderPage.vue:1259-1260; lib/paperDrafts.js:9 | Paper trade gets a dashed frame and the label 'Paper mode - not real trades'. This is the tag itself: expected, keep. | wording only | screens | display | small |
| 53 | frontend/src/lib/tracking.js:20,109; PaperStrategies.vue:11,209,317; lib/adjustDrawer.js:28; lib/sharedStateText.js:94; PaperConfirmDialog.vue:156 | Sentences naming paper: 'This is not a real trade. Paper orders use no real money.', 'Paper trades - not real money', 'This strategy has no open paper legs to exit.', 'Paper P&L (not real)', 'Watch an index level: it only alerts and does not exit'; 'Could not check your armed exits.' (comment says pending owner read). Tag-level ones are expected; the rest follow their rows above. | wording only | screens | display | small |
| 54 | frontend/src/lib/orderPath.js:12-16,43-46 | Real entry/exit is offered only when GET /features order_path is 'on'; the switched-off sentence is 'Placing orders from this app is switched off for now.' Paper has no such switch. | branch inside shared code | screens | display | small |

Rows read only partly say so in their text (SaveDraftBar, the AppHeader badge, ADR-276 tracked set). The PlanEntry row and the playbooks row are Lane U's open facts, now confirmed by reading the lines.

## 4. Counts

By kind:

| kind | rows |
|---|---|
| paper-only door with no real twin | 23 |
| branch inside shared code | 17 |
| stated by an earlier decision | 10 |
| wording only | 4 |
| **total** | **54** |

By area:

| area | rows |
|---|---|
| entry | 12 |
| exit | 11 |
| screens | 9 |
| P&L | 8 |
| plan | 7 |
| stops-and-alerts | 7 |

Kind by area:

| area | paper-only door with no real twin | branch inside shared code | wording only | stated by an earlier decision |
|---|---|---|---|---|
| entry | 6 | 6 | 0 | 0 |
| exit | 6 | 2 | 0 | 3 |
| stops-and-alerts | 4 | 1 | 1 | 1 |
| plan | 3 | 3 | 0 | 1 |
| P&L | 4 | 1 | 0 | 3 |
| screens | 0 | 4 | 3 | 2 |

By risk if a real trade went through it:

| risk | rows |
|---|---|
| display | 25 |
| money | 13 |
| exit | 9 |
| stop | 7 |

By size of the change:

| size | rows |
|---|---|
| small | 24 |
| medium | 20 |
| large | 10 |

**The uncomfortable reading:** of 54 rows only 4 are wording. 23 are doors or gates that exist for paper and not for real, and the 7 rows tagged "stop" and 9 tagged "exit" are the ones where a real trade would sit unprotected. No row in the stops area is stated by a decision for real trades.

## 5. Already shared, no difference found (not counted)

`read_door`, `index_spot_of`, the REST spot and the spot age rule (per Lane U); `tracking/tracked_book.py:8-9` maps real trades into paper `NewOrder` rows so one netter serves both; `engine/duplicate_leg.py:1,26` and `execution/safety.py:390-396` share the duplicate-leg sentence; `engine/legs.py:107` At Expiry mark; `marketdata/feed_health.py:194-199` stale rule (no paper-specific age constant found); `routes/execution_return.py:296` records first-fill facts through the paper route's own helper.

## 6. Section C: parity test names for Lane Q2

Shape for every test: build one strategy twice from identical input, one tagged paper, one tagged real; run the one door; assert the refusal code, the sentence, the confirm list text, the record's fields (everything except the tag) and the audit/timeline entry are equal. Test names (suggested file `tests/test_parity_paper_real.py`; real side runs against a stub broker, never a real endpoint):

Entry
- `test_parity_entry_refused_outside_market_hours_same_code_and_sentence`
- `test_parity_entry_refused_when_prices_not_live_same_sentence` (ADR-330 (28): allowed with the confirm line "Prices are not live; the entry is the last captured price, as of HH:MM")
- `test_parity_entry_price_must_be_tick_multiple_and_positive`
- `test_parity_entry_refused_duplicate_leg_same_sentence`
- `test_parity_entry_refused_take_profit_at_loss_same_sentence`
- `test_parity_entry_refused_adjustment_limit_reached_same_sentence`
- `test_parity_entry_refused_contract_not_tradable_same_sentence`
- `test_parity_entry_over_freeze_limit_blocks_never_splits` (ADR-092)
- `test_parity_entry_margin_short_pauses_with_same_text` (ADR-016)
- `test_parity_entry_confirm_list_has_same_lines_and_only_title_differs`
- `test_parity_entry_record_fields_equal_except_tag`
- `test_parity_entry_audit_entry_equal_except_tag`
- `test_parity_entry_refused_in_scenario_mode_both_or_neither`

Exit (dialog, alert, stop, time, expiry all through one door)
- `test_parity_exit_dialog_blocked_when_price_read_failed_same_reason_line`
- `test_parity_exit_dialog_blocked_when_price_stale_same_reason_line`
- `test_parity_exit_dialog_blocked_when_contracts_changed_elsewhere`
- `test_parity_exit_refused_outside_market_hours_same_sentence`
- `test_parity_exit_exceeds_open_quantity_same_refusal`
- `test_parity_exit_on_closed_strategy_same_refusal`
- `test_parity_exit_per_leg_lots_choice_available_on_both`
- `test_parity_exit_risk_read_shown_on_both`
- `test_parity_exit_not_live_acknowledgement_required_on_both`
- `test_parity_exit_unknown_outcome_state_same_on_both`
- `test_parity_exit_buy_legs_first_order_same_on_both`
- `test_parity_exit_confirm_title_names_paper_or_real_only`
- `test_parity_alert_exit_the_position_opens_same_dialog_for_both`
- `test_parity_exit_record_and_done_sentence_equal_except_tag`
- `test_parity_exit_one_fire_on_two_racing_exits_both`

Stops and alerts
- `test_parity_index_trigger_arms_on_both`
- `test_parity_leg_stop_arms_on_both`
- `test_parity_stop_fires_once_on_crossed_level_both`
- `test_parity_stop_fire_goes_through_the_one_exit_door_both`
- `test_parity_stop_alert_text_equal_except_tag`
- `test_parity_stop_bypasses_alert_gate_and_pause_on_both`
- `test_parity_armed_and_fired_exits_read_for_plan_screen_both`
- `test_parity_stop_not_fired_when_price_not_live_same_alert`
- `test_parity_time_exit_fires_both`
- `test_parity_expiry_settles_at_intrinsic_and_writes_record_both`

Plan, P&L, screens
- `test_parity_pnl_one_engine_same_figure_for_same_fills`
- `test_parity_charges_beside_pnl_both`
- `test_parity_booked_pnl_added_to_target_both` (ADR-209)
- `test_parity_max_profit_loss_and_profit_left_both`
- `test_parity_after_hours_display_uses_last_close_both` (ADR-212)
- `test_parity_playbook_test_reads_both`
- `test_parity_tracked_set_includes_both`
- `test_parity_home_live_mystrategies_pnl_lines_both`
- `test_parity_positions_totals_side_by_side_not_added` (ADR-330 (10), (24))
- `test_parity_leg_price_labels_same_except_tag_word`
- `test_parity_every_user_sentence_equal_after_removing_tag_words` (scan of both templates sets: `paper_*` vs `gate_*` codes map one to one)
- `test_parity_no_branch_on_tag_outside_the_one_reader` (repo scan: the tag is read in one place only; design B)

Known to fail today (expected red until built): every exit, stop, expiry, P&L and "same refusal" test above, because the real side has no door. They are the acceptance list, not a regression list.
