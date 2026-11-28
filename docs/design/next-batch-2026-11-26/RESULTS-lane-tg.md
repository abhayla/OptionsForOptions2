STATUS 15:20 | item 1 (a to g) walked, results below; items 2 to 4 not started | next push: after item 3 | blocker: none

# Lane TG results: the round 2 test plan walked in the cloud (28 Nov 2026)

Paper only. No broker connection, no broker order endpoint. Market closed.
Build head walked: see "Build" below. Screenshots: `screens-tg/` (JPEG, 1366x768, each under 300 KB). Scripts: `tests_browser/r2_plan_walk_1128/`.

## Build
- Base `origin/integration/weekend-r2-1128`; the three test merges ran clean, none needed an abort: `fix/r3-frontend-joins-1128`, `fix/r3-worker-3-1128`, `fix/r3-backend-5-1128` are all ancestors of the walked head `e7eced25` (merge of backend-5).
- Migrations: ONE head, `0061_order_request_keys`; `alembic current` after the upgrade also prints it.
- Seed: 1090-contract catalogue (expiries +56 days), 17 close rows (`written 17`), 5 paper trades (#1 TC Condor Running 1 with a plan, #2 TC Strangle Open with a plan, #3 TC Unpriced Trade no plan, #4 TC Completed Trade, #5 Wide Iron Condor 20x no plan), then one leg stop on #1 NIFTY 24300 CE (above 150). The fills went in by SQL because the route refuses paper entries with the market closed (as Lane TC found).
- API: the real `create_app`, `APP_ENV=test`, `TEST_CATALOGUE_DATE=2026-11-28`, `LIVE_MARKET=1` with a dead `KITE_WS_URL` (the app refuses LIVE_MARKET under test with the real address), the real `LiveMarket` (`TC_PLAIN=1`: NO stored session, so this is the D-1 case). Worker: `python -m ofo_app.background` as its own process. `vite preview` on 4173 proxying to the API.

## Table of every check walked

| Check | Result | Screenshot / evidence |
|---|---|---|
| W-34 worker running, market closed (the Core) | PASS for planned trades (#1, #2); see note on unplanned trades | `w34-a-live.jpg`, `w34-a-positions.jpg`, `w34-a-builder.jpg` |
| W-34 worker stopped, then started | PASS | `w34-b-live.jpg`, `w34-b-positions.jpg`, `w34-b-builder.jpg` |
| W-13 / W-17 / SW-8 Alerts History and Active slow (12 s) | PARTIAL: no error block, "Still loading" seen only at 22 s | `slow-alhist-t7.jpg`, `slow-alhist-t22.jpg`, `slow-alact-t7.jpg`, `slow-alact-t22.jpg` |
| W-02 / W-03 plan watch slow (9 s and 12 s), Positions and builder | PARTIAL: no error block, but "Still loading. The server is taking longer than usual to answer." never shown for plan watch | `slow-pw-t7.jpg`, `slow-pw12-t22.jpg`, `slow-bld-t7.jpg`, `slow-bld-t22.jpg` |
| W-33 step 1, AF-03, AF-04, SW-1 to SW-9 with the stored close, no session | PARTIAL: the banner and closes show on all (D-1 fixed); every running row's paper P&L is still "paused" (D-TG-1) | `c-sw*.jpg` |
| W-26 case A | PASS, one plan fault (no per-leg lots control) | `w26-a1-raised.jpg`, `w26-a2-dialog.jpg`, `w26-a3-cancelled.jpg` |
| W-26 case B | OWNER DECISION PENDING (recorded, not judged) | `w26-b1-dialog.jpg`, `w26-b2-after-cancel.jpg` |
| W-32 the leg's own expiry control | FAIL (D-TG-2) | `w32-1-after-chip.jpg`, `w32-2-review.jpg` |
| W-01 Reset keeps typed levels | PASS | `w01-1-save.jpg`, `w01-2-reset.jpg` |
| SW-6 Add to Paper with the market closed | PASS (Confirm is greyed) | `sw6-2-add-dialog.jpg` |

## Item 1 in detail

### 1a W-34 (Core, proof read back)
Worker started 14:52 IST as its own process, market closed. Copied from the page (Live Strategies card, trade #1 TC Condor Running 1 and #2):
`⏸ Monitoring paused` / `Health unknown` / `The market is closed.` / `Since 14:56`.
The same three lines on Positions (Plan watch box under it) and on the builder of #1 (`w34-a-builder.jpg`). `GET /api/monitoring-state?ids=1,2` answers `reason: market_closed`, `reason_text: "The market is closed."`.
Never "the worker does not list this trade" for a planned trade.
Observation (set-up note): trades #3 and #5 have no plan; the worker lists only planned trades ("0 strategies monitored" until two plans were saved), so they read `Not being watched: the worker does not list this trade.` and Positions says `No plan: nothing is watched for this strategy` beside it. This is the reader's design (monitoring_state.py: "no plan, or not traded yet"), but it is the exact sentence round 1 called a defect. If the PC's 9 trades were unplanned, round 1's reading was this, not a worker fault. The coordinator should decide whether that sentence belongs on an unplanned running trade.
Worker stopped at 14:57:53 IST; at 15:00:04 and on a reload of all three pages (`w34-b-*`): `Monitoring paused` / `Health unknown` / `Not being watched: no worker has reported in the last 2 minutes.` Worker started 15:01:12; the first poll 3 s later (15:01:15) answered `market_closed`: the badge went well inside 30 s.
Set-up fault found on the way (for the PC, see "Set-up notes"): with `FEED_MODE` unset the API treats "no bus" as "no worker" and every trade reads "no worker has reported" even with the worker running (`routes/monitoring_status.py read_found`).

### 1b Slow answers (delays done with Playwright route handlers; the server's own time beside the page)
| Route and delay | Server's own answer time | What the page showed |
|---|---|---|
| plan-watch 9 s, Positions | 218 ms | box `Loading the rule check...` at 3 s and 7 s, rows at 10 s; no error block |
| plan-watch 12 s, Positions | 183 ms | `Loading the rule check...` until 10 s, rows at 14 s; no error block; no "Still loading" line |
| plan-watch 12 s, builder of #1 | 80 ms | `Loading the rule check...` to 10 s, then `Updating the numbers` at 22 s; no error block |
| alerts active 12 s | 15 ms | nothing for 3 to 14 s, then `Still loading. The server is taking longer than usual to answer.` at 22 s; no error block |
| alerts history 12 s | 15 ms | same as active |
Never seen: "The page could not get an answer from the server." or "The plan watch is not available right now.". Seen but not expected: on plan watch the "Still loading." sentence does not appear at all within 12 s (the plan expects it). On Alerts the sentence appears only after the second poll (at 22 s) and nothing is shown for the first 14 s. The rows themselves arrive after the delay.

### 1c The stored close, no session (D-1), nine screens
Banner `Market closed. Prices are from 27 Nov 2026, 15:29:58 IST.` is on Home, Positions, Live Strategies, My Strategies, builder and Option Chain; indexes `NIFTY 50 24187.35`, `SENSEX 79234.50`, each `27 Nov 2026, 15:29:58 IST`; builder spot 24187.35; chain `NIFTY24187.35as of 15:29:58`; Stops panel `NIFTY last 24187.35 as of 15:29:58` (not "Index values unavailable."). Never "Not available" for an index. D-1 of round 1 is fixed for the banner and the index values. Console errors during the sweep: 0.
But (new, D-TG-1): every running row still reads `P&L —` with `Paper P&L paused - prices not live` (Live Strategies, My Strategies), Home reads `Total P&L (after charges) +457.93`, `Includes 1 closed strategy.`, `4 strategies left out: their prices are not live.`, while the LTP column on the Live card shows the closes (`147.50`). The plan's SW-3 "must not show" list names this.
Other seen texts: Option Chain every strike `-` / `not available` (only 15 closes seeded; the plan expects held contracts priced, others "not available": the held 24000/24100/24300/24400 strikes were not in the strip around 23450 to 23600 that was read, not walked further); Alerts Active `No alerts yet. Alerts start when strategy monitoring rules are added.`; Positions Real part shows the sentence `Connect your Zerodha account...` AND the whole raw JSON object (`{ "error_class": "BROKER_AUTHENTICATION", ... }`) twice on the page (known D-2 of round 1 for the 409; the raw JSON on screen is on the plan's "must not show" list).
AF-03: no mixed-time case (all legs priced by one close); AF-04: Home figure +457.93 = the closed trade #4 only, the four running trades excluded with the count line; the My Strategies rows are `P&L —`, so the sum check is trivial (= the closed trade). AF-05: same.

### 1d W-26
Case A (raised before pressing Exit all): the builder has no per-leg lots control on a running trade (the leg's "1 lot" is a plain span); the only lots control is the Multiplier, which raised all four legs 1 to 2 ("4 pending changes"). Exit all dialog, word for word: `Exit Paper positions ... Exit all closes every open leg. The change waiting on NIFTY 8 Dec 24000 PE, NIFTY 8 Dec 24400 CE, NIFTY 8 Dec 24100 PE, NIFTY 8 Dec 24300 CE is not sent and will be discarded. This is not a real trade. Paper orders use no real money. The market is closed. Exits can be placed from 09:15 on Monday 30 Nov. Cancel Confirm`. After Cancel: lots `2 lot` on all four, `4 pending changes`, multiplier still 2, no staged exit. PASS. The sentence names all four legs in one list.
Case B (nothing staged, "owner decision pending"): Exit all dialog: no discard sentence, Confirm greyed. After Cancel the builder reads `4 pending changes` and `Exiting these legs (staged, not placed yet)` with a Discard button.

### 1e W-32
Stop set on #1 NIFTY 24300 CE (above 150; `contract_id 836`). Leg 3's own expiry control (`Change expiry of leg 3`, options 8 Dec / 14 Dec) moved only that leg ("2 pending changes", expiries 8,8,14,8 Dec). Review dialog, 12 s after opening: `Review Paper orders B Exit NIFTY 8 Dec 24300 CE ... S Add NIFTY 14 Dec 24300 CE ... Checking whether this exit leaves a sold option without protection... The market is closed. Exits can be placed from 09:15 on Monday 30 Nov. Cancel Confirm`. The sentence `The stop on NIFTY 8 Dec 24300 CE will be removed; set a new one after the move.` is NOT in the dialog. The server does produce it: the same `GET /paper/strategies/1/armed-exits?orders=...` answered by hand returns `{"lines":["The stop on NIFTY 8 Dec 24300 CE will be removed; set a new one after the move."]}`. The server log shows no `armed-exits` and no `exit-risk` request from the page during the review. FAIL, new (D-TG-2). Not confirmed.

### 1f W-01
Stop (Rs) typed 100 and saved: the sheet closed and reopened with Stop (Rs) 100.00, stop percent 6.15, target 3000.00. Reset to playbook asks `Reset the conditions? Reset to playbook / Cancel` after stating `Reset to playbook puts back this playbook's conditions only. The levels you typed on the sheet (profit target, rupee target, rupee stop, time exit, the adjustment limit) and the plan's settings stay as you set them.`; after confirming it reads **`Nothing differed from the playbook, so nothing was put back.`** The values that stayed: Stop (Rs) 100.00, Target (Rs) 3000.00, target 61.54 %, max adjustments 2.

### 1g SW-6
A draft from Ready-made "Bull Put Spread": Add to Paper first asks `Name this paper trade ... A name can be up to 20 characters.`, then the dialog reads `Add to Paper S Add NIFTY 8 Dec 24200 PE ... B Add NIFTY 8 Dec 24000 PE ... Held at my broker  This is not a real trade. Paper orders use no real money. Orders can be placed from 09:15 on Monday 30 Nov. Cancel Confirm`. Confirm is greyed (disabled). No tick box. PASS (the dialog says so and Confirm is greyed; the server refusal was not needed).

## Plan faults for Lane X2
1. W-26 step 2: "Raise one leg's lots": old line `**Raise one leg's lots (do not press Review).**` new line `**Raise the lots with the Multiplier (the leg rows' lots are plain text on a running trade; there is no per-leg lots control), do not press Review. All legs rise.**` Expected text in case A then names every leg: `The change waiting on <leg>, <leg>, ... is not sent and will be discarded.`
2. SW-8: "Records" is not a page: `/alerts/records` is "Page not found". Records is the History page's block `Stops and expiry settlements`. Old `Open Alerts; read Active, History and the Records view` new `Open Alerts > Active and Alerts > History; the Records list is the block "Stops and expiry settlements" on History`.
3. W-26 case B: the dialog has no discard sentence and Confirm is greyed; after Cancel `4 pending changes` and the staged-exit line remain (as the plan already notes).
4. W-34: the plan's round-1 text says the sentence appears on "all running trades"; with the worker running it appears only for planned trades; add `A running trade with no plan reads "Not being watched: the worker does not list this trade." with "No plan: nothing is watched for this strategy" beside it; give the trade a plan first.`
5. Set-up R2-0: add `FEED_MODE=bus` to the API's environment (else every trade reads "no worker has reported").
6. W-02/W-03: the plan expects "Still loading. The server is taking longer than usual to answer." for plan watch; the build never prints it for plan watch inside 12 s (only the box line `Loading the rule check...`); only Alerts prints it. Write the box line as the expected text or file as a defect.
7. SW-9: the Stops panel is inside Positions > Paper (`?tab=paper&strategy=<id>`), not a separate page; the Live Strategies "Stops" link opens that.

## Defects found
- **D-TG-1** (new, with no stored session): the closes reach every screen but every running paper row's P&L, the Home total and the Live Strategies cards stay `P&L — · Paper P&L paused - prices not live`; Home `4 strategies left out`. The leg LTP column shows the close figure while the P&L beside it is paused. Cause read in `routes/paper.py _figures` (lines 745 to 775): `connected` is false with no session, so the book state is NOT_CONNECTED and the figures stay null; Lane TC's harness (a connected, silent socket) priced the same rows. Needs the owner lane of `routes/paper.py` / `live_market.attach_closed_view`. Plan's SW-3 "must not show": "Paper P&L paused - prices not live instead of close figures for legs that have a close".
- **D-TG-2** (new): the leg's own expiry control does not show `The stop on <leg> will be removed; set a new one after the move.` in the Review dialog; the dialog also stays on `Checking whether this exit leaves a sold option without protection...`; the page makes no `armed-exits` or `exit-risk` request (the server's answer is correct when asked by hand). File: the Review path in `frontend/src/components/strategy/PaperConfirmDialog.vue` (calls at line 219) for a leg-expiry move.
- **D-TG-3** (known D-2, plus new): Positions on `/positions/current-positions` with no session prints the raw JSON of the 409 (`{ "error_class": "BROKER_AUTHENTICATION", ...}`) twice. Screenshot `c-sw2-positions-real.jpg`.
- Observation: Exit all and Review dialogs say `No price for 4 of 4 legs; the server prices the exit when you confirm.` while the legs show a stored close; not judged.

## Set-up notes for the PC
- API needs `FEED_MODE=bus` and `REDIS_URL` (the monitoring badge reads "no worker" without it) and the worker as its own process. A running trade needs a plan to be listed by the worker.
- The API under `APP_ENV=test` with `LIVE_MARKET=1` refuses to start unless `KITE_WS_URL` is not the real Kite address.
- Seed with `last_close_store seed <file>` must not be piped to `head` (the pipe killed it before it wrote; I re-ran it: `written 17`).
- Restart vite only after API route changes (not needed here).

## Decided for the owner
- Used my own database `ofo_tg` (not `ofo_dev`) for items 1, 3 and 4 so the scenario seed (which insists on `ofo_dev`) could be used later for W-09 without mixing rows.
- Wrote the 17 closes from Lane TC's `closes17.json` (synthetic; source `tc_synthetic_2026-11-28`).
- Gave #1 and #2 a plan (Stop Rs 2000, Target Rs 3000) so the worker lists them; the owner's PC trades are the real test of the unplanned case.

## Not done (so far)
Items 2, 3 and 4 of the queue (W-09, R2-F1/F3/FJ and the real-kind position, then section 4 onward).

## Task / model / minutes
| task | model | minutes |
|---|---|---|
| set-up and item 1 | Sonnet (this session) | 33 |

SAFE TO CLOSE: not yet (item 1 only).
