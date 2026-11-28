STATUS 18:10 | item 1 (W-09 rupee stop): PASS on 4d975129f | next push: after item 2 groups | blocker: none

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

## W-09 in detail (the Core)
- Why PATH-01 gave no stop alert in either lane's run (finding for the plan): PATH-01 is a profitable drift (P&L stays positive, plan watch `now` = 4706.00 at frame 9 against `fires_at` -500.00), so a rupee LOSS stop can never be crossed on it; only T-01 (spot within 0.5 % of the short) fired, at frame 9 (11:45 shown). The `not_ticked` worker line is NOT a block: it is logged once per frame minute for the ~34 cycles where nothing changed; `checks=1` per frame minute, `reads {'FRESH': 1, 'NOT_TICKED': 34}`.
- Path used: PATH-10 (up sweep, 21 frames); Stop (Rs) 500 and Target (Rs) 20000 saved (reply `a loss of Rs 500.00 (2.43 % of max loss) or 2x the credit received, whichever comes first`). Frames 0 to 11 posted by `POST /api/scenario/frame`, 35 s each; plan-watch `now` per frame: 2983.50, 2879.50, 2723.50, 2463.50, 2132.00, 1709.50, 1202.50, 624.00, -45.50, -806.00, -1638.00, -2522.00.
- Database, counted after frame 11: `adjustment_suggestions` for strategy 2: `plan.rupee_loss` 1 (shown 2026-11-06 11:49), `T-01` 1, `T-03` 1, `T-09` 1, `sit.S-02` 1 (all 11:50). The rupee row was written once (frames 10 and 11 did not repeat it). `paper_alerts` stays 0 (that table is the paper exit triggers, not these alerts).
- Worker log words: `background: opportunity strategy=2 rule=plan.rupee_loss record=2 written 2026-11-06 11:49:00+05:30`, then `rule=T-01 record=3`, `T-03 record=4`, `T-09 record=5`, `sit.S-02 record=6` (11:50); 12 lines `strategy 2 check skipped: not_ticked` over 12 frames, no `prices_*` or `no_gate_read` line.
- Alerts > Active (5 rows, `w09-alerts-active.jpg`): `Plan rupee stop: 806.0000 (rule 500.0000) Fired at 11:49` with `Exit the position` / `Continue with the position`.
- Not run (queue says the rupee stop only): % stop, target, time exit, already-crossed.
- Observations (words only, pending owner read, not judged): the rupee-stop line shows `806.0000 (rule 500.0000)` with four decimals and no rupee sign, while the T-09 line shows `₹2.45 (rule ₹3.00)`; the T-09 title reads `A short leg's premium falls to Rs or below (close for pennies)` (the amount is missing from the title).

## Defects found
(none yet)

## Plan faults
1. W-09: PATH-01 cannot reach a rupee LOSS stop (it is a profit path). Old: "a scenario path ... frame past the stop" with PATH-01 implied; new: use PATH-10 (strategy name `Scenario PATH-10`), Stop (Rs) 500, frames 0 to 9 (alert at frame 9, 35 s each). The Alerts address is reached from the top bar `Alerts`, which opens `/alerts/active`.

## Decided for the owner
- The pre-push gate steps (ruff ratchet, repo_scan, prepush) run before each push, not before each walked check (a walked check changes no tree).

## Not done
Items 2 to 6 of the queue (in progress).
