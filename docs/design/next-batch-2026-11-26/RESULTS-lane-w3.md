STATUS 23:08 | push 1: queue item 1 walked on build a1d704225 (wave 1 NOT on origin yet: none of FJ2 4201d3af2, F2 28c0e7be6, F3 937e80bbe, RA2 4ec19fdd6, leftovers-2 1f8e0018c is an ancestor) | next: items 2 and 3 on a1d704225, then re-walk when the build moves | blocker: none (send_message to the coordinator is refused: session trust, this line is the report)

# Lane W3 results: the plan walker on the build (28 Nov 2026)

Paper only. No broker order endpoint, no real broker session, synthetic data. Market closed (Saturday), except the scenario stack (PATH-10, a served scenario day with a frozen clock of 6 Nov 11:39:59).
Build under test: `origin/integration/weekend-r3-1129` head **a1d704225** (wave 0: RA, FJ, FJ2 merged earlier; one alembic head `0062_order_request_keys_expiry`). Fetched again at 23:02 IST: still a1d704225. Every row names its commit.
Worktree `../wt-build` = the build (purpose: the build under test; plain `git worktree remove` when the lane ends). Scripts: `tests_browser/r3_plan_walk_3_1128/`; screenshots: `screens-w3/` (JPEG, each under 300 KB).

## Set-up (this container, fresh)
PostgreSQL 16 and Redis started; roles as in `app-tests.yml` (API as the non-superuser `ofo_app`, migrations as `postgres`); `pip install -r requirements-app.txt`; `npm ci` in `wt-build/frontend`, `npm run build`.
- `ofo_tg` (stack A: API 8000, worker, vite preview 4173): TG2's seed: 1090-contract catalogue +56 days, 17 stored closes (`closes17.json`, price_at 15:29:58), five paper trades (`seed_strategies.py` with `TC_API_BASE=http://127.0.0.1:8000`, the base WITHOUT `/api`, then `seed_orders.sql`), plans on #1 and #2, leg stop above 150 on contract 836 (NIFTY 24300 CE) of #1. `LIVE_MARKET=1`, dead `KITE_WS_URL`, `FEED_MODE=bus`, `TEST_CATALOGUE_DATE=2026-11-28`.
- `ofo_dev` (stack B: scenario PATH-10, API 8001, worker, vite 4174): made from the migrated template `ofo_tpl` by `reset_dev.sh` (stops API and worker, `DROP DATABASE ofo_dev WITH (FORCE)`, `CREATE DATABASE ofo_dev TEMPLATE ofo_tpl`, `load_cat.py PATH-01 PATH-10`, `seed_scenario.py PATH-10`, restarts both). `TEST_CATALOGUE_DATE=2026-11-06`. Strategy 1 stores paper orders (the served scenario).
- Plan fault found while setting up (for the plan lane): `seed_strategies.py` needs `TC_API_BASE` WITHOUT the `/api` suffix (the routes are `/strategies`, `/paper/...`); with `/api` every call is a 404.

## Queue item 1: MUST money-path items on the build commit (two columns)
| Item | Walked on a lane branch (per its RESULTS) | Proven on the build a1d704225 | Proof | One line |
|---|---|---|---|---|
| Unknown-outcome block, page | FB2 / FJ: Lane W2 I-188 PASS (e2da71f50, a1d704225) | **PASS** | `u1.js` (MODE=lost), `u1-lost-1-after-first-confirm.jpg`, `u1-lost-2-second-exit-dialog.jpg` | Builder, scenario strategy 1, Exit leg 1, Confirm, the POST cut before the server: page reads `The first exit's outcome is not known yet; no second exit is sent until the server's answer is known.`; every per-leg Exit button disabled; a second Exit dialog shows `We could not confirm the order. Check Orderbook ...` with Confirm greyed; POSTs after the lock: 0; `paper_orders` count 4 before and after |
| Unknown-outcome block, server: second order, same key, different body | FD2 / FD3: Lane W2 I-138 PASS (a1d704225) | **PASS** | `u1_api.py` output below | K1 exit 65 of contract 61: 201, orders 4 to 5. K1 again with exit 130: **409 `STRATEGY_VALIDATION_581` "This request key was already used for a different order set." / "No order was stored; ..."**, orders 5 to 5. K1 again with the same body: 201 (the first reply replayed), orders 5 to 5 |
| Second order with a NEW key (what the brief calls "a different key and body") | not on a lane list | **PARTIAL: the server does not refuse it** | `u1_api.py` step 4 | K2, the same exit 65 sent again: 201, orders 5 to 6 (a second partial exit committed; 2 of 4 lots twice is the 27 Nov case). The guard against this is the page lock (row above), not the server. See "Decided for the owner" 1 |
| Lock across a reload (no clock move) | FJ2 4201d3af2: Lane W2 PASS | **PASS** | `u1-lost-3-after-reload.jpg` | reload: same sentence, 0 POSTs; a second tab (same browser): Confirm greyed, 0 POSTs |
| Lock across a reload with the clock moved | FJ2 4201d3af2: Lane W2 point 1 PASS (+200 s and -200 s, 0 POSTs) | **FAIL (D-W2-1 still open on this build)** | `u1.js` (OFFSET), `u1-off600000-4.jpg`, `u1-off600000-5.jpg`; holds: `u1-off60000-4.jpg`, `u1-off60000-5.jpg` | A fresh page load with the wall clock +600 s (`Date` shifted, `performance.now` not), 25 s of real time after the cut: the lock sentence is gone, Confirm enabled, a POST went out (POSTs 1 to 2). Run twice: both released. With +60 s and with +0 s: held, 0 POSTs. The SAME page instance with its `Date` moved +600 s, then the Orderbook re-read: held. Cause as Lane W2 wrote it (a page's first sight of a lock counts the wall age once). FJ2 4201d3af2 is not in this build |
| Lock released when the first exit was in fact stored (reply lost after the server stored it) | FB2: W2 I-14 PASS | **PASS** | `u1.js` (MODE=committed), `u1-committed-1-after-first-confirm.jpg` | the server stored (orders 4 to 5); within 6 s the page read the book, dropped the lock (no sentence, three Exit buttons left enabled); the next Exits on other legs were new orders (5 to 6 to 7); no leg exited twice |
| Second tab release | FJ2 4201d3af2: W2 point 2 PASS (3 s and 12 s); on a1d704225 W2 saw D-W2-2 (about 2 minutes) | **PASS (same leg) / PARTIAL (another leg)** | `u2.js`, `u2-1-tabA-locked.jpg`, `u2-2-tabA-after.jpg` | Tab A cut and locked, tab B (other browser profile) stores the SAME leg's exit (builder or Positions > Paper, 201): tab A's lock sentence and `Updating the numbers...` are gone within 5 s. Tab B stores a DIFFERENT leg's exit: tab A keeps both for 115 s, then clears (the lock waits for the 130 s rule when an unrelated leg moved: by design, fail closed; the figures stay on `Updating the numbers...` for those two minutes = D-W2-2) |
| Leg-expiry Review sentence | FJ2 4201d3af2: W2 point 5 PASS (stop above 100 on PATH-01 23150 PE) | **FAIL (D-TG-2 still open)** | `w3b.js`, `w3b-review-leg3.jpg` | `ofo_tg` #1, leg 3 `NIFTY 24300 CE 8 Dec` (leg stop above 150, armed), expiry chip to 14 Dec, Review: the dialog lists `Exit NIFTY 8 Dec 24300 CE` and `Add NIFTY 14 Dec 24300 CE`, `Checking whether this exit leaves a sold option without protection...`, `The market is closed. Exits can be placed from 09:15 on Monday 30 Nov.`; **no `The stop on NIFTY 8 Dec 24300 CE will be removed; set a new one after the move.` line**. The three legs without a stop: no such line (right) |
| Plan block shows the stop and target figure, market closed | F2 28c0e7be6: W2 FAIL (D-W2-3) | **FAIL (I-197 / D-W2-3 still open)** | `w3a.js`, `w3a-plan-block.jpg` | builder #1: `Playbook: "Iron condor: system default"`, `Target: not being checked: No adjustment opportunity checked: prices stale or missing.`, `Stop: not being checked: ...` (twice), `As of 23:00:37 IST`, `Max adjustments: 2 / Time exit: 14:30`; no stop or target figure (the plan holds Stop 50 %, Rs 812.50, Target 50 %, Rs 2437.50 per `GET /api/strategies/1/adjustment-plan`) |
| Stored-close P&L WITH ITS DATE: book panel, paper list, Positions, Home | RA2 4ec19fdd6: W2 PARTIAL (P&L shown, no state word or as-of time) | **FAIL (D-TG-1 still open)** | `w3a.js`, `w3a-home.jpg`, `w3a-positions.jpg`, `w3a-live.jpg`, `w3a-mystrat.jpg`, `w3a-builder1.jpg` | Stored close 15:29:58 on 27 Nov is read (banner `Market closed. Prices are from 27 Nov 2026, 15:29:58 IST.` on all five screens). Running trades: Home `P&L - Paper P&L paused - prices not live, as of 28 Nov 2026, 22:59:50 IST` x4; Live Strategies x4; My Strategies x4; builder `Total P&L -`, `Paper P&L paused - prices not live`, four leg rows with `-` and `no price`. Positions: only the closed trade has a figure (`P&L (after charges) +457.93`, `Includes 1 closed strategy.`), `4 strategies left out: their prices are not live.` None shows a stored-close P&L with a date |
| Exit Confirm greyed with the market closed | FJ: TG2 W-25 PASS | **PASS** | `w3a.js`, `w3a-exit-dialog.jpg` | builder `ofo_tg` #1: 4 Exit buttons enabled; dialog `... The market is closed. Exits can be placed from 09:15 on Monday 30 Nov. Cancel Confirm`; Confirm count 1, enabled false; also `No price for 1 of 1 legs; the server prices the exit when you confirm.` |
| One missing strategy row does not blind the book | FD3 / FE3 | **PASS** | curl | `GET /api/plan-watch?strategy_ids=1,99,2`: items `1 ok`, `99 refused`, `2 ok`. `GET /api/monitoring-state?ids=1,2,99,3`: ids 1, 2, 3 answered, 99 answered `not_listed`. `ids=1,abc,2`: 200, ids 1 and 2 answered (`abc` dropped) |
| Monitoring list names each trade, with `market_closed` | FE3 (W-34) | **PASS** (monitored trades) | curl | `GET /api/monitoring-state?ids=1,2,3,5`: #1 and #2 `reason: market_closed`, `The market is closed.`; #3 and #5 (no plan, the worker lists 2 strategies) `reason: not_listed`, `Not being watched: the worker does not list this trade.` |

### Server half, as run (`u1_api.py`, scenario strategy 1, API 8001)
```
1 first order, key K1, exit 65 of contract 61
  POST key=d41a04c9 qty=65 -> 201 orders 4->5
2 SAME key K1, DIFFERENT body (exit 130): must be refused, nothing stored
  POST key=d41a04c9 qty=130 -> 409 orders 5->5 :: {"error_class":"STRATEGY_VALIDATION","code":"STRATEGY_VALIDATION_581","what_happened":"This request key was already used for a different order set.","impact":"No order was stored; a repeat of a request must carry the same orders as the first.","what_is_blocked":"Placing these paper orders.","next_action":"Read the strategy's orders, then press Confirm again if you still want them.","external_text":null}
3 SAME key K1, SAME body (a repeat)
  POST key=d41a04c9 qty=65 -> 201 orders 5->5
4 NEW key K2, same exit 65 again
  POST key=f25f6f9b qty=65 -> 201 orders 5->6
```

## Defects found
No new defect id this push: the four FAILs above are the open ones already named by Lanes TG, TG2 and W2, now confirmed on the build a1d704225 (D-W2-1, D-TG-2, D-W2-3 / I-197, D-TG-1). Each re-check is in the item 3 table when walked. The walk adds one precision to D-W2-1: a fresh load with the clock +600 s releases the lock at 25 s real (+60 s holds).

## Plan faults
1. `seed_strategies.py`: `TC_API_BASE` must be without `/api` (see Set-up).
2. The brief and the plan call the new-key case "refused"; the server stores it (see Decided for the owner 1).

## Decided for the owner
1. A second order with a NEW key and a different or the same body is stored by the server (step 4 above). Only the page lock stops it. Is that the intended contract (ADR-017, ADR-330 (58)), or must the server also refuse a second exit on a strategy whose first exit's key is still pending or unknown? Recommendation: keep it (the server cannot know the first outcome is unknown) and keep the plan sentence as "the page sends nothing; a repeat with the same key and another body is refused".

## Not done (yet)
Queue items 2 (TG2's not-walked rows) and 3 (re-check of every defect) on this build; they follow in the next push. Rows that need the wave 1 build wait for it.

SAFE TO CLOSE: no (queue not finished)
