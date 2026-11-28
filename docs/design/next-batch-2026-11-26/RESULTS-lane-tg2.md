STATUS 19:40 | items 1 and most of 2 and 3 walked on 4d975129f; push 1 gate TOTAL PASS (bab5cad5e) | next push: after items 3 to 6 | blocker: none (send_message to the coordinator refused: owner trust of the session)

# Lane TG2 results: weekend test plan, cloud checks on the round 3 build (28 Nov 2026)

Paper only. No broker order endpoint, no real broker session, synthetic data. Market closed.
Build walked: `origin/integration/weekend-r3-1129` head **4d975129f** (Lane Z3: round 3 batch 1). The fix lanes' branches `fix/r3-leftovers-2-1128` and `fix/r3-frontend-2-1128` are not on origin yet at 18:07 IST (item 5 waits for them). `test/r2-plan-walk-1128` has not moved since `72845ce53`.
Scripts: `tests_browser/r3_plan_walk_2_1128/`; screenshots: `screens-tg2/`.

## Set-up (this container)
PostgreSQL 16 (roles as in `app-tests.yml`: `ofo_app` as the app role, `postgres` as owner), Redis, databases `ofo_tg` (plan-walk seed: 1090-contract catalogue +56 days, 17 stored closes, 5 paper trades as Lane TG, plans on #1 and #2, leg stop above 150 on NIFTY 24300 CE of #1) and `ofo_dev` (scenario mode). Both migrate to the one head `0061_order_request_keys`. API `APP_ENV=test`, `FEED_MODE=bus`, own Redis database per stack; worker its own process; vite preview 4173 (tg, API 8000) and 4174 (scenario, API 8001). Helpers `env.sh`, `api_start.sh`, `worker_start.sh`.

## Table of every check walked
| Check | Commit | Result | Proof | One line |
|---|---|---|---|---|
| W-09 plan rupee stop, scenario PATH-10 | 4d975129f | PASS | `w09-alerts-active.jpg`, `w09b.log` | Stop (Rs) 500 on "Scenario PATH-10": P&L +2,983.50 at frame 0, -45.50 at frame 8 (plan watch `watching`), -806.00 at frame 9 (`fired`). One `adjustment_suggestions` row `plan.rupee_loss` shown 11:49 and one Alerts > Active row `Plan rupee stop: 806.0000 (rule 500.0000) Fired at 11:49`, within 35 s of the frame |
| W-10 Compare approaches, Cancel then Confirm | 4d975129f | PARTIAL | `w10-*.jpg`, `w10b.js` | Needs the scenario catalogue day (API `TEST_CATALOGUE_DATE` = scenario day; without it every approach says `This approach could not be turned into a basket.`). Prepare "Close the tested spread" (A-28) goes to the builder staged (`?acted=...&basket=2`, "2 pending changes", `Review and add`). After the confirm list Cancel: counters `Open: 5` (PASS, still Open). After Confirm (paper order placed): the four conditions read `Completed at 28 Nov 2026, 18:18:34 IST`, not `Acted on - Paper - not sent to Zerodha` (the worker was running and closed them within 8 s; re-run with the worker stopped is not done) |
| W-11 Full-exit approach stages held legs | 4d975129f | NOT DONE | | the scenario trade was changed by the W-10 confirm; the scenario database cannot be wiped (insert-only guard on alert styles); a fresh database `ofo_tpl` is being migrated for a clean re-seed |
| W-15 same side / opposite sides (server words) | 4d975129f | PARTIAL | API replies | `Legs 1 and 2 are the same contract and side (NIFTY 8 Dec 24250 CE, Sell).` then next action `Join them into one leg with more lots, or change one of them.` (plan expects `... or change one to a different contract.`). Opposite: `Legs 1 and 2 are the same contract (NIFTY 8 Dec 24250 CE), one Sell and one Buy.` / `A strategy holds one leg per contract: remove one of them, or change one to a different contract.` matches. The builder's own Save draft box was not walked |
| W-23 route-delay tool | 4d975129f | PASS (plan fault: start command) | curl timings | with `holdback:create_app` (the plan writes `holdback.create_app`, which uvicorn refuses): plan-watch 5.22 s through the wrapper, 0.06 s direct; another route 0.09 s |
| W-30 stop percent, weekly trade #1 (monthly half) | 4d975129f | PARTIAL | `w30-1-sheet.jpg`, `w30.js` | stop % 45 typed (Stop Rs cleared) and saved: sheet reads 45 and Rs 731.25 after reopening; Positions and the builder Plan watch print `Stop: not being checked: No adjustment opportunity checked: prices stale or missing.` with no number (market closed, nothing priced). Monthly trade: BLOCKED, none seeded |
| T3-17 #745 / T-Q7 | 4d975129f | PASS | `t317-1-create-guided.jpg`, `t317-2-chain.jpg` | Create Strategy > Guided > I already know my strategy > NIFTY: expiry list loaded, no `took too long` box. Option Chain `10 days left` for 8 Dec = server `expiry_days` 10 |
| T3-17 #749 closed-leg stop sentence | 4d975129f | NOT DONE | | no trade with a leg closed by a stop exists here |
| T2-19 Reset to playbook markers | 4d975129f | PARTIAL / FAIL (words) | `t219-3`, `t219-4` | T-01 switched off for the trade, Rs 400 stop and 15:15 typed and saved; the confirmation names the kept levels; after Confirm: Stop (Rs) 400.00 and 15:15 stay, T-01 box is on again. The marker line reads **`Switched on again: triggers.T-01`** (a raw key, not the trigger's name) (D-TG2-1). No "changed" marker was seen in the sheet. The time field shows `03:15 PM` (browser control) |
| TC-3 Notification settings | 4d975129f | PASS (plan fault) | `tc3-notification-settings.jpg` | reached from the Alerts menu entry `Notification settings` (`/alerts/notification-settings`): `No notification channels are set up yet.` "Side closed" alert: none exists |
| W-29 (54) Plan button | 4d975129f | PASS | `w29-1`, `w29-2` | Positions > Paper: 4 Plan buttons (the 4 running trades), sheet opens in 861 ms; unplanned #3 shows `Set plan` in the builder; no Plan button for the closed #4 |
| W-29 (57) closed trade | 4d975129f | PARTIAL | `w29-3-closed.jpg` | `This trade is closed. Its legs and result are shown below; it cannot be changed.`, `No plan was set for this trade. Closed by your exit on 27 Nov at 10:45.`, no Add/Edit, no "Add a leg to start one"; but a `Plan watch` heading with `This trade is closed; nothing is watched.` is shown (plan: no Plan watch box) |
| W-05 step 1, step 2 | 4d975129f | PASS (step 1) | `w05-1-settings.jpg` | Settings `Most lots in one leg` 100, Default. Step 2 (Add to Paper 5000 lots): market-closed refusal is the existing one (as in the plan) |
| W-21 Lane M read-only SQL | 4d975129f | PARTIAL | psql | strategies 194 and 201 do not exist here (0 paper orders); `paper_alerts` columns: id, strategy_id, trigger_id, created_at, title, body, read_at |
| W-03 stopped-backend half | 4d975129f | PASS | `w03-step4-api-down.jpg`, `w03d.out` | API stopped 12:58:25 UTC, builder open: after ~70 s the last rows stay, each marked `Paper P&L paused - prices not live`, and the text `Could not refresh the rule check` is on the page; after restart the box reads again (`Wait for fresh prices.`) |
| W-25 D Exit with the API down | 4d975129f | PARTIAL | `w25d-exit-api-down.jpg` | the leg Exit button was not clickable (disabled with paused prices), so `The market status could not be read.` was not seen |
| T3-10 every list with the API down | 4d975129f | PASS | `t310-*.jpg` | My Strategies `Could not load your strategies. Nothing was changed.` + Retry; Live Strategies, Alerts Active, History (both blocks) `Could not load this list. Nothing was changed.` + Retry; Positions: `The page could not get an answer from the server.` (twice) plus the list line and Retry |
| D-TG-5 re-look (before the fix lanes' merge) | 4d975129f | still FAIL | `w29-1-positions.jpg` | `Paper P&L paused - prices not live` 8 times on Positions > Paper |

## W-09 in detail (the Core)
- Why PATH-01 gave no stop alert in either lane's run (finding for the plan): PATH-01 is a profitable drift (P&L stays positive, plan watch `now` = 4706.00 at frame 9 against `fires_at` -500.00), so a rupee LOSS stop can never be crossed on it; only T-01 (spot within 0.5 % of the short) fired, at frame 9 (11:45 shown). The `not_ticked` worker line is NOT a block: it is logged once per frame minute for the ~34 cycles where nothing changed; `checks=1` per frame minute, `reads {'FRESH': 1, 'NOT_TICKED': 34}`.
- Path used: PATH-10 (up sweep, 21 frames); Stop (Rs) 500 and Target (Rs) 20000 saved (reply `a loss of Rs 500.00 (2.43 % of max loss) or 2x the credit received, whichever comes first`). Frames 0 to 11 posted by `POST /api/scenario/frame`, 35 s each; plan-watch `now` per frame: 2983.50, 2879.50, 2723.50, 2463.50, 2132.00, 1709.50, 1202.50, 624.00, -45.50, -806.00, -1638.00, -2522.00.
- Database, counted after frame 11: `adjustment_suggestions` for strategy 2: `plan.rupee_loss` 1 (shown 2026-11-06 11:49), `T-01` 1, `T-03` 1, `T-09` 1, `sit.S-02` 1 (all 11:50). The rupee row was written once (frames 10 and 11 did not repeat it). `paper_alerts` stays 0 (that table is the paper exit triggers, not these alerts).
- Worker log words: `background: opportunity strategy=2 rule=plan.rupee_loss record=2 written 2026-11-06 11:49:00+05:30`, then `rule=T-01 record=3`, `T-03 record=4`, `T-09 record=5`, `sit.S-02 record=6` (11:50); 12 lines `strategy 2 check skipped: not_ticked` over 12 frames, no `prices_*` or `no_gate_read` line.
- Alerts > Active (5 rows, `w09-alerts-active.jpg`): `Plan rupee stop: 806.0000 (rule 500.0000) Fired at 11:49` with `Exit the position` / `Continue with the position`.
- Not run (queue says the rupee stop only): % stop, target, time exit, already-crossed.
- Observations (words only, pending owner read, not judged): the rupee-stop line shows `806.0000 (rule 500.0000)` with four decimals and no rupee sign, while the T-09 line shows `₹2.45 (rule ₹3.00)`; the T-09 title reads `A short leg's premium falls to Rs or below (close for pennies)` (the amount is missing from the title).

## Defects found
- **D-TG2-1** (T2-19, 4d975129f): after Reset to playbook the sheet line reads `Switched on again: triggers.T-01` (a raw key). Expected: the trigger's name (`Spot within this % of a short strike`), W-30 step 4 / ADR-330 (9), (32). Screenshot `t219-4-after-reset.jpg`.
- **D-TG2-2** (observation, 4d975129f): the T-09 title `A short leg's premium falls to Rs or below (close for pennies)` has no amount (Alerts, Settings step 2 and 'When to look').

## Plan faults
1. W-09: PATH-01 cannot reach a rupee LOSS stop (it is a profit path). Old: "a scenario path ... frame past the stop" with PATH-01 implied; new: use PATH-10 (strategy name `Scenario PATH-10`), Stop (Rs) 500, frames 0 to 9 (alert at frame 9, 35 s each). The Alerts address is reached from the top bar `Alerts`, which opens `/alerts/active`.

2. W-23: start command `holdback:create_app` (colon), not `holdback.create_app`.
3. TC-3: Notification settings is the Alerts menu entry (`/alerts/notification-settings`), not a button on Alerts.
4. W-10/W-11: the scenario API needs the scenario day as the catalogue day (`TEST_CATALOGUE_DATE`), or every approach fails with `This approach could not be turned into a basket.`; Compare approaches is a link on Positions > Adjustment opportunities; the confirm list is the builder's `Review and add`; with the worker running, Confirm shows `Completed`, not `Acted on`.
5. W-15: next-action sentence differs (see table).

## Decided for the owner
- The pre-push gate steps (ruff ratchet, repo_scan, prepush) run before each push, not before each walked check (a walked check changes no tree).

## Not done
W-11, W-07, W-27/W-25 parts, W-35, AF-05, AF-06, items 3 (rest), 4, 5 and 6 of the queue; item 5 waits for the fix lanes' branches (not on origin).
