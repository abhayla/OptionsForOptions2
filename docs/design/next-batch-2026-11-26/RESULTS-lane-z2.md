STATUS 10:25 IST | head: the commit this file is pushed in (batch 1 product tree = 5d874d41c5cf3e6470fc1a69ec527fb1e11343a, pushed, gate TOTAL PASS --jobs 2 1624 s) | MERGED (batch 1): fix/r2-backend-2-1128 87ca3b39 (FD2), test/r2-named-green-1128 a0f6e7d6 (TE), test/r2-gaps-1128 9facc09f (TF), fix/r2-worker-issues-1128 6b409ab9 (FE2), fix/r2-plan-screens-1128 45a93645 (FC3), on top of group 1 (Lane Z's 9b12d65b9) | BATCH 2 (14:30 IST) takes: FE2's newer head c1749629, fix/r3-frontend-joins (group A), r3-backend-3, r3-backend-4, r3-readers, r3-chart-teardown, r3-worker-3 and fix/ic-live-test-1123 if clean; what is not SAFE TO CLOSE by then is named under left out | LEFT OUT: fix/r2-exit-stops-2-1128 (FA2) and fix/r2-pages-1128 (FC2) by the coordinator's order (Lane FJ merges them; both would add/add-conflict in one frontend test file each); fix/r3-frontend-joins, r3-backend-3, r3-backend-4, r3-readers, r3-chart-teardown: not on origin at 10:07; fix/ic-live-test-1123: NOT merged, conflicts in docs/process/runbook.md, knowledge/findings/INDEX.md, scripts/orchestrator/prepush.py (merge-tree dry run, nothing touched), also edits spec/decisions/ADR-330.md and tests/orchestrator/test_select_app_tests.py | PROOFS on PostgreSQL 16 (5d874d41c): 200 passed (worker chain + J3 + FE + FE2 + FD2 request-key/cancelled-stops/fields/closed-reads, 8 min 12 s); frontend unit 336 files, 3880 tests passed (in the gate); TE's 27 failing: 19 still fail in 9 files, 8 now pass; migration 0059 to 0060 to 0059 to 0057 to 0060 proven, one head 0060 | OPUS REVIEW (batch 1 head): REVISE; F1 STILL OPEN (Lane FJ: Positions and Alerts page unlock after unknown with no key and no window; builder lock in memory only), F2 closed for round 1's case with one gap (Lane FE3: failed kind read reads watched), F3 server half closed, page half STILL OPEN (Lane FJ: no page reads cancelled_stops); R5 (Lane FD3) a paper exit can still be stored on a real position through POST /strategies/{id}/tracking/exit; R6 (Lanes FE3/FD3) old armed stops on real positions are skipped silently | ROUND 2 READY FOR THE PC: NO | blocker: none (fix lanes FJ, FD3, FE3 needed for R1 to R9)

# Lane Z2 (round 2 group 2 merge, proofs, independent review), 28 Nov 2026

Paper only; no broker call made. Base: origin/integration/weekend-r2-1128 at 9b12d65b9 (group 1 merged by Lane Z). Round 1 (integration/weekend-1127 at faef0723) untouched.

## Decided for the owner
- The coordinator (08:15 and 09:25 IST) changed my order: merge in ONE batch, one check with `--jobs 2`, FJ's branch instead of FA2/FC2/FC3 later, FD3 on top of FD2 later. I followed it; FC3 (plan-screens) was added to batch 1 by the coordinator's order.
- Three environment fixes were needed before the gate could run in this container (none touches the repo): ruff pinned 0.15.12 (the ratchet fails closed on another version), `npm ci` in frontend/, `pip install -r requirements-app.txt`, and `git fetch --unshallow` (ci_checks and app_tests need a merge base with origin/main). Any fresh builder container needs the same four steps.
- The one merge conflict: `tests/orchestrator/test_select_app_tests.py` (PR241_SELECTION, TE added two entries, TF one). Kept all three entries; that file's 50 tests pass.
- fix/ic-live-test-1123 was not merged: it conflicts (see STATUS). Its ADR-330 points (39) to (72), the faster check and the lane rules are therefore not in this build.

## What each proof ran (PostgreSQL 16, fresh database, one clone per test file)
| Proof | Files | Result |
|---|---|---|
| Core (before any other merge): FD2 request key + cancelled stops | tests_app/test_order_request_key_r2_fd2.py, test_paper_orders_r2_fd2.py | 16 passed (15 s) on 514bb9562 |
| Worker proofs, FE/FE2, FD2, on the batch head | test_plan_stop_worker_chain.py, test_worker_j3.py, FE (index_exit_watch, leg_exit_watch, review_fixes), FE2 (10 files `*_fe2_1128`), FD2 (order_request_key, paper_orders, closed_reads, fields, plan_watch_budget, playbook_test_tracked, positions_route, real_door_lots_limit) | 200 passed, 8:12 |
| Frontend unit suite | in the gate | 336 files, 3880 tests passed |
| Gate, serial, group 1 + FD2 (514bb9562) | prepush.py --jobs 1 | TOTAL PASS 2367 s, pushed |
| Gate, batch 1 (5d874d41c) | prepush.py --jobs 2 | TOTAL PASS 1624 s, pushed |
| Migration | 0059 up, 0060 up, 0060 down, 0057 down, up to head | one head `0060_plan_stamp_only_on_switch` |

Pushes: 514bb9562 (group 1 + FD2) and 5d874d41c (batch 1). The STATUS line was not on those two pushes (RESULTS did not exist yet); this file's push carries it.

## TE's 27 failing database tests, re-run on the batch head (file by file, own clone)
8 of 27 now pass: test_migration_0059_last_close.py (4, FD2 fixed the tests), test_egress_gate_doors.py (3), test_kite_broker_reader.py (1; these need no proxy here). Still failing: 19 in 9 files, none caused by this round's stop/exit work as far as the first line shows [Likely]; none fixed by me.

| File (failed) | First error line |
|---|---|
| test_adjustment_history_why.py (1) | reply is STRATEGY_VALIDATION_505 ("No order was stored; a partial exit counts as an adjustment") where the test expects acceptance |
| test_alert_routes.py (2) | AssertionError: answer key set differs from the expected set |
| test_d38_page_counts.py (1) | AssertionError: plan: the reply changed |
| test_execution_return.py (2) | `INTERNAL_SYSTEM_002` unhandled error on POST /strategies/1/execution/return (first-fill entry facts; real door) |
| test_pinned_clock.py (1) | fixture offered on the real clock (the pinned fixture dict differs; today is Saturday, market closed) |
| test_pool_not_held_across_market_wait.py (2) | "the REST reader was not reached: the measurement proves nothing" |
| test_risk_exit_not_gated.py (1) | `[] == [(1, 'open')]` (no record opened; market closed) |
| test_route_latency_budget.py (4) | adjustment-check 20 statements, ceiling 19; adjustment-plan 19, ceiling 18; plan-watch 24, ceiling 23; batch of one row 24 |
| test_slow_price_source_live_day.py (5) | XPASS(strict) on three xfail markers ("a paper read holds its pooled connection...", "plan-watch waits out the whole stalled quote"): the markers are stale; two cases also time out |
I was allowed to turn an xfail into a plain test only where a fix in the build makes it pass; the three XPASS(strict) rows are exactly that, but they sit in a file another lane owns and the marked reasons name hotfix branches that are not in this tree, so I left them for the owner lane (list below).

## Independent Opus review of the joined stop, exit and order paths (batch 1 head 5d874d41c)
Reviewer: reviewer helper, Opus, own checkout, read-only, attacked first (scratch vitest in a copy of frontend/, python -I against the request key with a fake Redis and the paper monitor), no database test, no edit. ~48 tool calls, 8 min. Verdict: **REVISE**.

| Round 1 | State | Evidence |
|---|---|---|
| F1 unknown outcome unlocks Exit/Add | STILL OPEN | Positions and Alerts (PaperStrategies.vue:440-456,507): after a 503 the page posted again 6 s later, `posts=2 elapsed_ms=6000 keys=[null,null]` (the existing test paper-strategies.test.js:463 asserts this). The builder's 120 s window holds in one mounted page (StrategyBuilderPage.vue:816,847) but its lock is an in-memory ref (545) and the add lock is cleared by leaveDrafts (516) |
| F2 index exit with silent tick | CLOSED for the 23 Nov case (paper_monitor.py:408-425,475-484; no report reads paused, monitoring_state.py:271-273); one gap of the same class (R7) | |
| F3 moved leg's cancelled stop | server half CLOSED (routes/paper.py:1557,1571; same key repeat answers the first list, 1488); page half STILL OPEN: no file in frontend/src reads `cancelled_stops` | |

| id | severity | file:line | what | failure | owner lane |
|---|---|---|---|---|---|
| R1 | blocks | frontend/src/components/strategy/PaperStrategies.vue:440-456,507 | after an unknown outcome the first good 5 s list read with units unchanged says "not stored" and turns Confirm on; no window, no key | Positions or Alerts: Exit 2 of 4 lots, 503, 6 s later Confirm again, both commit = 4 lots (a full-leg exit is still caught by EXIT_EXCEEDS_OPEN) | FJ (frontend) |
| R2 | major | StrategyBuilderPage.vue:545,516,546 | the unknown-exit lock lives in memory only; the add lock is cleared on leaving the book | reload or reopen within about 2 min, book unchanged: Exit or Review and add offered again with a new key, placed twice | FJ |
| R3 | major | StrategyBuilderPage.vue:705, SaveDraftBar.vue:453, lib/tracking.js:74-95, ExecuteStrategyPage.vue:121 | a new key on every press, nothing ever resends one key; the key de-duplicates nothing on any page path today; the execute page sends none | any second Confirm carries a fresh UUID, the server places it | FJ (pages) + FD3 (key store) |
| R4 | major | StrategyBuilderPage.vue:669-679,744 | page half of F3: the user learns of the cancelled stop only from two failable reads | move a leg, 201 arrives, the stops re-read fails: new leg has no stop, no offer, no line | FJ |
| R5 | major | backend/ofo_app/routes/tracking.py:529-577, paper_limit.py:176 | POST /strategies/{id}/tracking/exit has no real or unknown kind refusal; neither does the shared write path `place_checked` (FD2's own review F1 still unfixed); no page calls the route in this tree | a direct or stale call on a held-at-broker strategy: 200, a paper exit STORED on a real position (against ADR-330 (64)) | FD3 (paper_limit.py, routes/tracking.py) |
| R6 | major | paper_monitor.py:242-245 with routes/paper.py:2037-2045 | armed stop rows set on real positions before #877 stay armed; the monitor skips them with a log line only; the screen shows "armed at X" | price crosses X, nothing fires, nothing is said: a crossed stop dropped silently | FE3 (worker: paper_monitor.py) + FD3 (routes/paper.py:2037 read) |
| R7 | minor | paper_monitor.py:236-248, monitoring_state.py:278-283 | a failed position-kind read drops every paper exit without adding the strategy to `not_run` | trade reads watched ("active") for up to 60 s while no exit is checked | FE3 (paper_monitor.py, monitoring_state.py) |
| R8 | minor | request_key.py:30,137-143 | Redis 600 s; the "pending" record is written BEFORE the commit, so FD2's note is wrong: a crash after the commit refuses a resend for 600 s (not at once); then the same key places again | Redis restart or eviction between commit and resend lets it through at once | FD3 (durable table) |
| R9 | minor | routes/paper.py:1513-1573, sharedStateText.js:153 | the page's 120 s + 10 s is not backed by a server deadline (3 pool checkouts of 30 s each, row lock up to 30 s, live reads) | stacked worst cases could commit after the page said "not stored"; fix: refuse just before commit when the request is older than about 90 s | FD3 |

Request key (b): Redis down at claim = refused 503 `request_key_store_unavailable` (closed); Redis write fails after commit or process crash after commit = key stays pending, a resend refused `request_key_in_progress` for 600 s, then the same key places again (run: 2 orders with one key); Redis restart = places at once; same key other strategy = refused; other orders = refused; no key = store never touched. Paper door: acceptable only while no page resends a key; do not build an automatic resend on it before the durable table exists. Real door: the key is inert (the server only prepares a sealed form and the page sends no key).

Under (a): the paper order route refuses exits, stops and keep for a real or unknown position (routes/paper.py:1452-1462,1481,2130,2190); new trigger rows only behind that refusal; the monitor never evaluates a real or unknown-kind trigger (`_paper_only`); the alerts answer route places no order; no path fires a plan stop at a wrong price was found.
Not covered by the reviewer: paper_settlement.py writing settle orders on real positions at expiry (ADR-292); an `open` order on a real position through the paper door; `load_contracts([])` after a failed kind read (decides whether R7 lasts 60 s); FC3's wording; ADR-330 (45)-(72) in full; a builder remount test for R2 (read only).
Second round (item 4): the coordinator-named second short pass on batch 2's diff has not been run: batch 2 is not on origin yet.

## Defects found (for a fix lane; not fixed by me)
1. R1 to R9 above, with file and line.
2. The 19 failing database tests above. First fix candidates: test_execution_return `INTERNAL_SYSTEM_002` (real first fill; read the traceback), the four statement ceilings in test_route_latency_budget (one query added per route), the stale xfail markers in test_slow_price_source_live_day.
3. Container note: a fresh container needs the four environment steps under "Decided for the owner"; `pg_ctlcluster 16 main start` before any database run (the cluster stops when the session idles).

## For the owner lane (files I may not edit)
- spec/ or runbook: say that a manual `tests_app` run on a shared database needs `OFO_TEST_DB_PER_FILE=1` (or `GITHUB_ACTIONS=true`) and a fresh template database, one run at a time.
- tests_app/test_slow_price_source_live_day.py: remove the three stale xfail(strict) markers (they pass now).
- FD3 (durable key store): table `order_request_keys(user_ref, key, strategy_id, body_sha256, result jsonb, created_at)` closes R8; a server deadline before commit closes R9.
- FD3 (R5): kind refusal in the one `place_checked` path so every route inherits it (class fix), not per route.
- FJ (R3, R4): the page must send ONE key per Confirm and the same key on every resend, and must read `cancelled_stops` from the 201 reply.

## To file as deferred issues
R2, R3, R4, R5, R6, R7, R8, R9; the 19 failing database tests (9 files); stale xfail markers.

## New on-screen sentences pending owner read
None written by this lane.

## PC pull order for round 2 (paper only, market closed; the head is the commit on the final STATUS line of this file on origin, NOT YET FINAL: round 2 is REVISE)
0. Keep round 1: the local branch `test/weekend-r1` (or the PC's `test/screen-2026-11-27`, head bdb0d126) stays exactly as it is; never reset it.
1. Check the database link first (it reconnects by itself in about 10 s; look anyway).
2. Backup: a verified database backup of the production database before anything else.
3. `git fetch origin integration/weekend-r2-1128`, then `git checkout -b test/weekend-r2 <the head on the STATUS line>`; confirm `git rev-parse HEAD` prints it. No tag exists.
4. Migration 0060 (replaces the plan guard function only; no table or column change; no row is changed): `python scripts/orchestrator/db_run.py . python -m alembic -c backend/ofo_app/alembic.ini upgrade head`; `alembic heads` prints one head `0060_plan_stamp_only_on_switch`. Proof run in this container: 0059 up, 0060 up, 0060 down, 0057 down, up to head (one head). Does OLD code run against the migrated database? **Not safely.** Round 1 code (never sets the signal) on a 0060 database: an accept (POST or Reset) does not stamp `accepted_at`, and a plan whose playbook pointer is NULL loses its own stops on an edit. NEW code against a 0059 database works (0041's guard stamps on every body change and the extra setting is ignored). So: migrate, then restart on the new code in the same session; ROLLBACK RULE: a code rollback must also run `alembic downgrade 0059_last_close`.
5. Seed: none new for round 2 (round 1's last-close seed of 17 rows stays; the stored-close reads with no Zerodha session read it) [Likely: nothing in the batch writes a new seed].
6. Restart order: API, then worker, then feed (Redis must be up: the order request key is refused with 503 when the store is down; Redis already serves the market-data bus). After the API restart open Positions with no Zerodha session: it answers 200 with "not connected" and the stored close.
7. Re-test list (market closed): builder add and exit with the request key (a reload must not duplicate); a moved leg's order reply names the cancelled stop; Positions exit of 2 of 4 lots after an unknown outcome (R1 is open: do NOT test a double Confirm on a real account; paper only); a real position must show no armed paper stop.
8. The PC's own results branch is pushed only after it has this head merged or its findings index regenerated (`python scripts/orchestrator/regen.py .`), and only with the repo's pre-push gate.

## Tasks
| task | model | minutes |
|---|---|---|
| merges, conflict resolution, environment fixes, three gate runs, proofs, RESULTS | Sonnet | about 170 |
| independent review of the stop, exit and order paths (Tier A) | Opus (reviewer helper) | 8 |
